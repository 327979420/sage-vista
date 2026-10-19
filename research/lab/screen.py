"""Find the stocks for a wider, unseen universe (engineering check; no returns are computed).

Every common stock the provider lists (US: on a primary exchange; another market with the spec's "exchange", e.g. HK), listed today or delisted, is downloaded once and kept if it met the
research pool's floor (close >= $5, >= $10M traded) on enough sessions inside the window. Tickers that appear in both the listed and
the delisted lists are left out, because a reused ticker can join two companies' prices (the 2026 EODHD audit's warning); stocks
already in the frozen research universe are left out, so the result has never been seen by any rule. The kept stocks are written
as alphabetical shards small enough for one lab dataset each.
"""
from __future__ import annotations

import concurrent.futures
import pathlib
import re
import math
import datetime

from services.scanner.macd_factor_backtest import adjusted_rows

PRIMARY = {"NASDAQ", "NYSE", "AMEX", "NYSE MKT", "NYSE ARCA"}


def candidates(listed, delisted, exclude, primary=PRIMARY):
    """Primary-exchange common stocks, without reused tickers or already-known symbols, in a fixed order. `primary` None keeps every
    exchange in the provider's list (non-US lists are per exchange already, e.g. HK)."""
    common = lambda rows: {x["Code"] for x in rows if x.get("Type") == "Common Stock" and (primary is None or x.get("Exchange") in primary) and x.get("Code")}
    live, gone = common(listed), common(delisted)
    reused = live & gone
    return sorted((live | gone) - reused - set(exclude)), {"listed": len(live), "delisted": len(gone), "reused": len(reused)}


NAME_EXCLUSIONS = ("ETF", "ETN", "REIT", "FUND", "INDEX", "投資法人", "上場投信", "ファンド", "指数")


def company_key(code):
    return re.split(r"[.\-]", str(code), maxsplit=1)[0].lstrip("0") or "0"


def jp_candidates(listed, delisted):
    # Reused codes are checked across the full lists, regardless of provider type.
    live = {str(x["Code"]) for x in listed if x.get("Code") is not None}
    gone = {str(x["Code"]) for x in delisted if x.get("Code") is not None}
    reused = live & gone
    rows = listed + delisted
    bad_type = {str(x["Code"]) for x in rows if x.get("Code") is not None and x.get("Type") != "Common Stock"}
    matches = {term: {str(x["Code"]) for x in rows if x.get("Code") is not None and term in str(x.get("Name") or "").upper()} for term in NAME_EXCLUSIONS}
    bad_name = set().union(*matches.values())
    names = {str(x["Code"]): str(x.get("Name") or "") for x in rows if x.get("Code") is not None}
    return sorted((live | gone) - reused - bad_type - bad_name), {
        "listed": len(live), "delisted": len(gone), "reused": len(reused),
        "non_common_type": len(bad_type), "excluded_name": len(bad_name),
        "name_matches": {term: len(codes) for term, codes in matches.items()},
        "excluded_metadata_union": len(reused | bad_type | bad_name),
    }, names


def valid_jp_rows(raw):
    """One finite, positive OHLC daily bar per date; zero volume is valid.

    Invalid/missing bars do not contribute to the dedupe window or liquidity.
    Duplicate dates use the first valid provider row, counted once.
    """
    out = {}
    for row in raw:
        try:
            day = row["date"]
            if datetime.date.fromisoformat(day).isoformat() != day:
                continue
            if not all(math.isfinite(float(row[k])) and float(row[k]) > 0 for k in ("open", "high", "low", "close", "adjusted_close")):
                continue
            volume = float(row["volume"])
            if not math.isfinite(volume) or volume < 0:
                continue
            out.setdefault(day, row)
        except (KeyError, TypeError, ValueError):
            continue
    return [out[d] for d in sorted(out)]


def jp_dedupe(stats, failed):
    groups = {}
    for code in sorted(set(stats) | set(failed)):
        groups.setdefault(company_key(code), []).append(code)
    winners, removed, unresolved = [], [], []
    for codes in groups.values():
        # A failed alias has unknown coverage: never silently substitute another alias.
        if any(code in failed for code in codes):
            unresolved.extend(code for code in codes if code in stats)
            continue
        winner = min(codes, key=lambda c: (-stats[c]["window_bars"], c))
        winners.append(winner)
        removed.extend(c for c in codes if c != winner)
    return sorted(winners), sorted(removed), sorted(unresolved)


def jp_review_flags(kept, names):
    flags = []
    for code in kept:
        key = company_key(code)
        if key.isdigit() and any(lo <= int(key) <= hi for lo, hi in ((1300, 1699), (2500, 2599), (8950, 8999))):
            flags.append({"code": code, "name": names[code]})
    return flags


KR_NAME_EXCLUSIONS = ("ETF", "ETN", "REIT", "FUND", "INDEX", "SPAC", "ACQUISITION", "KODEX", "TIGER", "스팩", "리츠")
KR_REVIEW_TERMS = ("PREF", "우", "HOLDINGS", "지주")


def kr_company_key(code):
    return str(code).split(".", 1)[0]


def kr_candidates(listed, delisted):
    """Exchange-keyed provider lists; qualified identities keep board moves distinct."""
    names = {}
    bad_type, bad_class, proxy, reused, bad_format = set(), set(), set(), set(), set()
    matches = {term: set() for term in KR_NAME_EXCLUSIONS}
    live, gone = set(), set()
    for board in ("KO", "KQ"):
        for source, target in ((listed[board], live), (delisted[board], gone)):
            for row in source:
                if row.get("Code") is None:
                    continue
                key = kr_company_key(row["Code"])
                code = f"{key}.{board}"
                if len(key) != 6:
                    # Amendment 2026-10-19 (Claude, before any Korea data): exclude and count, never abort the screen.
                    bad_format.add(code)
                    names[code] = str(row.get("Name") or "")
                    target.add(code)
                    continue
                target.add(code)
                names[code] = str(row.get("Name") or "")
                if row.get("Type") != "Common Stock":
                    bad_type.add(code)
                if key[5] != "0":
                    bad_class.add(code)
                if key == "069500":
                    proxy.add(code)
                for term in matches:
                    if term in names[code].upper():
                        matches[term].add(code)
    reused = live & gone
    bad_name = set().union(*matches.values())
    excluded = reused | bad_type | bad_class | bad_name | proxy | bad_format
    return sorted((live | gone) - excluded), {
        "listed": len(live), "delisted": len(gone), "reused": len(reused),
        "non_common_type": len(bad_type), "非普通股代码": len(bad_class), "代码格式异常": len(bad_format),
        "excluded_name": len(bad_name), "market_proxy": len(proxy),
        "name_matches": {term: len(codes) for term, codes in matches.items()},
        "excluded_metadata_union": len(excluded),
    }, names


def kr_dedupe(stats, failed):
    groups = {}
    for code in sorted(set(stats) | set(failed)):
        groups.setdefault(kr_company_key(code), []).append(code)
    winners, removed, unresolved = [], [], []
    for codes in groups.values():
        if any(code in failed for code in codes):
            unresolved.extend(code for code in codes if code in stats)
            continue
        winner = min(codes, key=lambda c: (-stats[c]["window_bars"], c.rsplit(".", 1)[1] != "KO", c))
        winners.append(winner)
        removed.extend(c for c in codes if c != winner)
    return sorted(winners), sorted(removed), sorted(unresolved)


def kr_review_flags(kept, names):
    return [{"code": c, "name": names[c]} for c in kept
            if any(term in names[c].upper() for term in KR_REVIEW_TERMS)]


def qualifies(rows, window, pool, raw=None):
    """Sessions inside the window that meet the pool floor. With `raw` (the provider's rows, version 2) the $5 floor uses the
    unadjusted close, because a split-adjusted close drops the early years of stocks that later split (a look-ahead); the dollar
    volume uses the adjusted close and the provider's split-adjusted volume, as before."""
    start, end = window
    raw_close = {x["date"]: x.get("close") for x in raw} if raw is not None else None
    good = 0
    for r in rows:
        if not start <= r["date"] <= end:
            continue
        price = raw_close.get(r["date"]) if raw_close is not None else r["close"]
        if price is not None and price >= pool["min_close"] and r["close"] * r["volume"] >= pool["min_dollar_volume"]:
            good += 1
    return good


def screen(symbols, fetch, window, pool, min_sessions, workers=6, raw_floor=False, reasons=None, japan=False):
    """Download each symbol once (in parallel), keep the ones with at least `min_sessions` pool sessions; failures are counted.
    `reasons` (a dict) receives why each failure happened: the provider's error text or "empty" for no history."""
    def one(symbol):
        try:
            raw = fetch(symbol)
            if japan:
                raw = valid_jp_rows(raw)
            rows = adjusted_rows(raw)
        except Exception as error:
            return symbol, None, str(error)[:80]
        if not rows:
            return symbol, None, "empty"
        good = qualifies(rows, window, pool, raw if raw_floor else None)
        info = {"good_sessions": good, "first": rows[0]["date"], "last": rows[-1]["date"], "bars": len(rows)}
        if japan:
            info["window_bars"] = sum(window[0] <= r["date"] <= window[1] for r in rows)
        return symbol, info, None
    stats, failed = {}, []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        for symbol, info, why in ex.map(one, symbols):
            if info is None:
                failed.append(symbol)
                if reasons is not None:
                    reasons[symbol] = why
            else:
                stats[symbol] = info
    kept = sorted(stats) if japan else sorted(s for s, info in stats.items() if info["good_sessions"] >= min_sessions)
    return kept, stats, sorted(failed)


def shards(symbols, size):
    return [symbols[i:i + size] for i in range(0, len(symbols), size)]


def run(spec, data, dataset_entry, root, listed=None, delisted=None, fetch=None):
    korea = "exchanges" in spec
    if korea and spec["exchanges"] != ["KO", "KQ"]:
        raise ValueError('Only the registered exchanges ["KO", "KQ"] are supported')
    exchange = spec.get("exchange", "US")
    primary = PRIMARY if exchange == "US" else (set(spec["primary_exchanges"]) if spec.get("primary_exchanges") else None)
    if fetch is None:
        from services.scanner.eodhd import get, symbols, eod_symbol
        if korea:
            listed = {board: symbols(False, board) for board in spec["exchanges"]}
            delisted = {board: symbols(True, board) for board in spec["exchanges"]}
        else:
            listed, delisted = symbols(False, exchange), symbols(True, exchange)
        fetch = lambda s: get(f"eod/{s if korea else eod_symbol(s, exchange)}", **{"from": spec["fetch_start"], "period": "d", "_attempts": spec.get("attempts", 3),
                                                               **({"to": spec["window"][1]} if exchange == "TSE" or korea else {})})
    japan = exchange == "TSE"
    if korea:
        names, counts, provider_names = kr_candidates(listed, delisted)
    elif japan:
        names, counts, provider_names = jp_candidates(listed, delisted)
    else:
        names, counts = candidates(listed, delisted, data["prices"].keys(), primary)
    reasons = {}
    kept, stats, failed = screen(names, fetch, spec["window"], spec["pool"], spec["min_sessions"], spec.get("workers", 4), spec.get("raw_price_floor", False), reasons, japan=japan or korea)
    if spec.get("retry_failed"):
        # a second, slower pass over the failures; what still fails keeps its reason
        retry_reasons = {}
        k2, s2, failed = screen(failed, fetch, spec["window"], spec["pool"], spec["min_sessions"], 1, spec.get("raw_price_floor", False), retry_reasons, japan=japan or korea)
        stats.update(s2)
        kept = sorted(set(kept) | set(k2))
        reasons = retry_reasons
    extra = {}
    if japan or korea:
        # Coverage alone selects the company representative. Liquidity never selects
        # a shorter alias as fallback (good_sessions is only a download-time tally).
        winners, duplicates, unresolved = (kr_dedupe if korea else jp_dedupe)(stats, failed)
        kept = sorted(s for s in winners if stats[s]["good_sessions"] >= spec["min_sessions"])
        counts.update(company_duplicates=len(duplicates), unresolved_company=len(unresolved),
                      below_liquidity=len(winners) - len(kept))
        extra = {"exchange": "TSE", "currency": "JPY", "company_duplicates": duplicates,
                 "unresolved_company": unresolved, "review_flags": [] if korea else jp_review_flags(kept, provider_names)}
        if korea:
            extra = {"exchanges": ["KO", "KQ"], "currency": "KRW", "company_duplicates": duplicates,
                     "unresolved_company": unresolved, "review_flags": kr_review_flags(kept, provider_names)}
    files = []
    for k, part in enumerate(shards(kept, spec["shard_size"])):
        path = pathlib.Path(root) / spec["shard_dir"] / f"{spec['shard_prefix']}-{chr(97 + k)}.txt"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(part) + "\n")
        files.append({"file": str(path.relative_to(root)), "symbols": len(part)})
    by_year = {}
    for s in kept:
        y = stats[s]["first"][:4]
        by_year[y] = by_year.get(y, 0) + 1
    crit = spec["criteria"]
    fail_share = len(failed) / max(len(names), 1)
    empty = sum(1 for s in failed if reasons.get(s) == "empty")
    errors = len(failed) - empty
    error_share = errors / max(len(names), 1)
    passed = (error_share <= crit["max_error_share"] if "max_error_share" in crit else fail_share <= crit["max_failed_share"]) and len(kept) >= crit["min_kept"]
    return {**extra, "kind": "screen", "spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
            "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "symbols")}, "window": spec["window"], "pool": spec["pool"],
            "min_sessions": spec["min_sessions"], "provider_counts": counts, "candidates": len(names), "downloaded": len(stats), "failed": len(failed),
            "failed_share": round(fail_share, 4), "failed_empty": empty, "failed_errors": errors, "error_share": round(error_share, 4),
            "failed_examples": {s: reasons.get(s) for s in failed[:40]}, "raw_price_floor": bool(spec.get("raw_price_floor")),
            "kept": len(kept), "shards": files, "first_bar_year_of_kept": dict(sorted(by_year.items())),
            "criteria": crit, "passed": passed, "champion": None}, stats, failed


def render(result):
    lines = [f"# {result['spec_id']}", "", f"Plain-language report written by the research lab on {(result.get('completed_at') or '—')[:10]}. "
             "Every number comes from `result.json` in this folder.", "", "## The question", "", result["question"], "", "## What the lab found", "",
             f"- Provider lists (primary-exchange common stocks): {result['provider_counts']['listed']} listed, {result['provider_counts']['delisted']} delisted, "
             f"{result['provider_counts']['reused']} tickers in both (left out).",
             f"- Candidates after leaving out the {result['dataset']['symbols']} stocks already in {result['dataset']['dataset_id']}: {result['candidates']}.",
             f"- Downloaded {result['downloaded']}, failed {result['failed']} ({result['failed_share'] * 100:.1f}%)"
             + (f": no history at the provider {result.get('failed_empty')}, errors {result.get('failed_errors')} ({result.get('error_share', 0) * 100:.1f}%)." if "failed_empty" in result else "."),
             f"- Price floor on the {'unadjusted' if result.get('raw_price_floor') else 'split-adjusted'} close.",
             f"- Kept (at least {result['min_sessions']} sessions with close >= ${result['pool']['min_close']:.0f} and >= ${result['pool']['min_dollar_volume'] / 1e6:.0f}M traded, "
             f"{result['window'][0]} to {result['window'][1]}): **{result['kept']}**, in {len(result['shards'])} shards.",
             "", "| Shard | Stocks |", "|---|---|", *[f"| `{x['file']}` | {x['symbols']} |" for x in result["shards"]],
             "", f"**Passed: {'yes' if result['passed'] else 'no'}** ("
             + (f"download errors at most {result['criteria']['max_error_share'] * 100:.0f}% after a retry" if "max_error_share" in result["criteria"] else f"failed downloads at most {result['criteria']['max_failed_share'] * 100:.0f}%")
             + f", at least {result['criteria']['min_kept']} stocks kept)."]
    if result.get("exchange") == "TSE":
        lines = [line.replace("$", "JPY ").replace("Provider lists (primary-exchange common stocks)", "Provider lists (all types; exclusions below)") for line in lines]
        lines[lines.index(next(x for x in lines if x.startswith("- Candidates after")))] = f"- TSE candidates after provider metadata exclusions: {result['candidates']}; US dataset symbols are not a cross-market exclusion list."
        lines += ["", "## TSE exclusion counts", "", "Counts by reason can overlap; name_matches count unique symbols per substring.",
                  *[f"- {k}: {v}" for k, v in result["provider_counts"].items()],
                  "", "## Review flags only — Claude must review before freezing at STOP 2", "",
                  "These ranges do not exclude stocks. Any change needs a dated pre-signal note.", "",
                  "| Code | Provider name |", "|---|---|",
                  *[f"| {x['code']} | {x['name'].replace('|', '/').replace(chr(10), ' ')} |" for x in result["review_flags"]]]
        if not result["review_flags"]:
            lines.append("No kept codes in the review ranges.")
    if result.get("exchanges") == ["KO", "KQ"]:
        lines = [line.replace("$", "KRW ").replace("Provider lists (primary-exchange common stocks)", "Provider lists (all types; exclusions below)") for line in lines]
        lines = [f"- KO + KQ candidates after metadata exclusions: {result['candidates']}; US reference symbols are not excluded." if line.startswith("- Candidates after") else line for line in lines]
        lines += ["", "## Korea exclusion counts", "", "Counts can overlap; name_matches counts unique listings per substring.",
                  *[f"- {k}: {v}" for k, v in result["provider_counts"].items()],
                  "", "## Review flags only — Claude must review before freezing at STOP 2", "",
                  "PREF, 우, HOLDINGS, 지주 are flags, not exclusions.", "",
                  "| Code | Provider name |", "|---|---|",
                  *[f"| {x['code']} | {x['name'].replace('|', '/').replace(chr(10), ' ')} |" for x in result["review_flags"]]]
        if not result["review_flags"]:
            lines.append("No kept names match the review terms.")
    return "\n".join(lines) + "\n"
