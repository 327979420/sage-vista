"""Weekly triangle forward record (the user's request, 2026-10-15): every new shape-1.5 signal after the frozen data ends is recorded
once, with the rule-1.7 order, the taste score, the daily and monthly MACD state and an anonymous chart for the user's blind judging;
each run then replays every recorded order on the latest prices and compares it with 30 same-day random stocks given the same order.
Rule 1.8 candidate (2026-10-15): rule 1.7 only when SPY is over its 200-day average and more than half of the stocks are over theirs;
each record keeps that market state and the summary reports 1.7 and 1.8 side by side.

Prices: the five frozen datasets (research/lab/datasets) plus one EODHD bulk end-of-day file per later session (cached in
work/triangle-bulk). A stock whose bar jumps by more than 1.67x or under 0.6x against its last close (a split after the freeze) stops
being extended. Records are append-only (signals.jsonl); outcomes.json is recomputed each run.

  python3 -m research.lab.triangle_forward            # local preview, writes work/triangle-forward
  python3 -m research.lab.triangle_forward --publish  # Actions: commit research/lab/forward/triangle to main
"""
from __future__ import annotations

import argparse
import bisect
import datetime as dt
import gzip
import hashlib
import json
import multiprocessing
import pathlib
import random
import statistics
import subprocess

from research.lab import buysystem as BS, datasets, selection, triangle15 as N

ROOT = pathlib.Path(__file__).resolve().parents[2]
FOLDER = "research/lab/forward/triangle"
CONFIG = ROOT / FOLDER / "config.json"
BULK = ROOT / "work/triangle-bulk"
PX = None
SPY = None
BREADTH = {}


def market(day):
    """Rule 1.8's market state at the signal day: SPY over its 200-day average, and the share of the dataset's stocks over their
    own 200-day average (300 sampled per day)."""
    c = SPY["close"]; i = min(bisect.bisect_left(SPY["date"], day), len(c) - 1)
    if day not in BREADTH:
        up = n = 0
        for sym in random.Random(day).sample(sorted(PX), min(300, len(PX))):
            q = PX[sym]; j = bisect.bisect_left(q["date"], day)
            if j < len(q["date"]) and q["date"][j] == day and j >= 200:
                n += 1; up += q["close"][j] > statistics.fmean(q["close"][j - 199:j + 1])
        BREADTH[day] = up / n if n else None
    b = BREADTH[day]
    spy200 = c[i] > statistics.fmean(c[i - 199:i + 1])
    return {"spy_over_200d": spy200, "breadth": round(b, 3) if b is not None else None, "ok": spy200 and b is not None and b > 0.5}


def bulk_day(day, fetch):
    """One session's EODHD bulk bars {code: row}, cached as gzip JSON."""
    path = BULK / f"{day}.json.gz"
    if path.exists():
        return json.loads(gzip.decompress(path.read_bytes()))
    rows = fetch(day)
    out = {r["code"]: [r["open"], r["high"], r["low"], r["close"], r["volume"]] for r in rows
           if r.get("code") and None not in (r.get("open"), r.get("high"), r.get("low"), r.get("close"), r.get("volume"))}
    if out:
        BULK.mkdir(parents=True, exist_ok=True)
        path.write_bytes(gzip.compress(json.dumps(out).encode()))
    return out


def extend(prices, days, bars_of):
    """Append later sessions to the series that were still trading on the dataset's last day. Returns the symbols stopped by a jump."""
    last = max(s["date"][-1] for s in prices.values())
    stopped = set()
    for day in [d for d in days if d > last]:
        bars = bars_of(day)
        for sym, s in prices.items():
            if sym in stopped or s["date"][-1] < last or s["date"][-1] >= day:
                continue
            row = bars.get(sym)
            if not row:
                continue
            o, h, l, c, v = (float(x) for x in row)
            prev = s["close"][-1]
            if prev <= 0 or not 0.6 <= o / prev <= 1.67 or not 0.6 <= c / prev <= 1.67:
                stopped.add(sym)
                continue
            s["date"].append(day)
            for k, x in (("open", o), ("high", h), ("low", l), ("close", c), ("volume", v)):
                s[k].append(x)
            if "raw_close" in s:
                s["raw_close"].append(c)
        last = max(last, day)
    return stopped


def scan(symbol):
    global PX
    s = PX[symbol]
    out = []
    for sig in N.signals(s, start=SCAN_START):
        W = BS.periods(s, "week")
        t, d0 = sig["t"], sig["day"]
        p = N.plan(s, sig, W["atr"][t])
        sc = 100 / W["close"][t]
        lo = max(0, min(sig["pushes"][0], t - 156) - 8)
        P = sig["pushes"]
        out.append({"symbol": symbol, "week": sig["week"], "signal_day": s["date"][d0], "close": s["close"][d0],
                    "plan": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in p.items()},
                    "taste": round(N.taste(W, sig), 4), "daily": N.daily_state(s, d0), "monthly_veto": N.monthly_veto(s, d0),
                    "market": market(s["date"][d0]),
                    "chart": {"bars": [[round(W[f][j] * sc, 3) for f in ("open", "high", "low", "close")]
                                       + [round(W["dif"][j] * sc, 4), round(W["dea"][j] * sc, 4), int(W["volume"][j]), round(W["ema20"][j] * sc, 3)]
                                       for j in range(lo, t + 1)],
                              "sig": t - lo, "pushes": [x - lo for x in P], "bottoms": [x - lo for x in sig["bottoms"]],
                              "line": [P[0] - lo, round(W["high"][P[0]] * sc, 4), round((W["high"][P[2]] - W["high"][P[0]]) / (P[2] - P[0]) * sc, 5)]}})
    return out


SCAN_START = "2026-10-12"


def outcome(rec, pool, n_twins=30):
    s = PX[rec["symbol"]]
    d0 = s["date"].index(rec["signal_day"])
    p = rec["plan"]
    if not p["go"]:
        return {"id": rec["id"], "status": "skipped", "why": p["why"]}
    got = N.trade(s, d0, p["level"], p["stop"], p["t1"])
    out = {"id": rec["id"], **{k: got[k] for k in ("status", "R", "why") if k in got}}
    if "fill_day" in got:
        out.update(fill=s["date"][got["fill_day"]], exit=s["date"][got["exit_day"]])
    if got.get("R") is None:
        return out
    W = BS.periods(s, "week")
    t = W["date"].index(rec["week"])
    m = (p["level"] - p["stop"]) / W["atr"][t]; r1 = (p["t1"] - p["level"]) / (p["level"] - p["stop"])
    Rs = []
    seed = int(hashlib.sha256(rec["id"].encode()).hexdigest()[:8], 16)
    for sym in random.Random(seed).sample(pool, min(n_twins, len(pool))):
        q = PX[sym]; i0 = bisect.bisect_left(q["date"], rec["signal_day"])
        if i0 >= len(q["date"]) or q["date"][i0] != rec["signal_day"]:
            continue
        Q = BS.periods(q, "week"); j = BS.completed(Q, i0, len(q["close"]))
        if j < 20 or not Q["atr"][j]:
            continue
        L = q["close"][i0] * 0.98; st = L - m * Q["atr"][j]
        if st <= 0 or (L - st) / L > 0.4:
            continue
        g = N.trade(q, i0, L, st, L + r1 * (L - st))
        if g.get("R") is not None and g["status"] in ("win", "loss", "time"):
            Rs.append(g["R"])
    out["random_R"] = round(statistics.fmean(Rs), 4) if Rs else None
    out["R"] = round(out["R"], 4)
    return out


def run(config, fetch_day, calendar):
    """Returns (new records, outcomes) for every dataset."""
    global PX, SCAN_START, SPY
    SCAN_START = config["start"]
    folder = ROOT / FOLDER
    known = {}
    if (folder / "signals.jsonl").exists():
        for line in (folder / "signals.jsonl").read_text().splitlines():
            if line.strip():
                r = json.loads(line); known[r["id"]] = r
    new, outcomes = [], []
    for ds in config["datasets"]:
        e0 = datasets.manifest(ds)
        PX = datasets.load(datasets.download(e0, ROOT / "work/lab"), e0["sha256"])["prices"]
        extend(PX, calendar, lambda d: bulk_day(d, fetch_day))
        if "SPY" in PX:
            SPY = PX["SPY"]
        BREADTH.clear()
        flagged = selection.impossible_jumps(PX)
        syms = sorted(x for x in PX if x not in flagged and x not in N.FUNDS and PX[x]["date"][-1] >= config["start"])
        with multiprocessing.get_context("fork").Pool() as pool:
            found = [r for chunk in pool.map(scan, syms, chunksize=8) for r in chunk]
        for r in found:
            r["id"] = hashlib.sha256(f"{r['symbol']}|{r['week']}".encode()).hexdigest()[:10]
            r["dataset"] = ds
            if r["id"] not in known:
                known[r["id"]] = r; new.append(r)
        rules = {**N.POOL, "exclude": flagged | N.FUNDS}
        pools = {}
        for rec in [r for r in known.values() if r["dataset"] == ds]:
            day = rec["signal_day"]
            if day not in pools:
                pools[day] = [x for x in selection.eligible_pool(PX, day, rules)]
            outcomes.append(outcome(rec, [x for x in pools[day] if x != rec["symbol"]], config["random_twins"]))
    return new, outcomes


def summary(records, outcomes, judgements):
    by = {o["id"]: o for o in outcomes}
    def group(ids):
        done = [by[i] for i in ids if by.get(i, {}).get("status") in ("win", "loss", "time")]
        if not done:
            return {"trades": 0}
        R = [min(5.0, o["R"]) for o in done]; B = [min(5.0, o["random_R"]) for o in done if o.get("random_R") is not None]
        return {"trades": len(done), "wins": sum(x > 0 for x in R), "mean_R": round(statistics.fmean(R), 4), "sum_R": round(sum(R), 3),
                "random_mean_R": round(statistics.fmean(B), 4) if B else None}
    ids = [r["id"] for r in records]
    do = [i for i in ids if judgements.get(i) == "do"]; no = [i for i in ids if judgements.get(i) == "no"]
    ok = {r["id"] for r in records if r.get("market", {}).get("ok")}
    return {"signals": len(ids), "judged": len(do) + len(no), "all": group(ids), "user_do": group(do), "user_no": group(no),
            "rule18_all": group([i for i in ids if i in ok]), "rule18_user_do": group([i for i in do if i in ok]),
            "open": sum(by.get(i, {}).get("status") in ("waiting", "open") for i in ids)}


def write(root, config, new, outcomes, now):
    folder = pathlib.Path(root) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / "signals.jsonl").open("a") as handle:
        for r in sorted(new, key=lambda r: (r["week"], r["id"])):
            handle.write(json.dumps({"recorded_at": now, **r}, ensure_ascii=False) + "\n")
    records = [json.loads(line) for line in (folder / "signals.jsonl").read_text().splitlines() if line.strip()]
    jpath = ROOT / FOLDER / "judgements.jsonl"
    judgements = {}
    if jpath.exists():
        for line in jpath.read_text().splitlines():
            if line.strip():
                j = json.loads(line); judgements[j["id"]] = j["choice"]
    (folder / "outcomes.json").write_text(json.dumps({"id": config["id"], "computed_at": now, "summary": summary(records, outcomes, judgements),
                                                     "outcomes": sorted(outcomes, key=lambda o: o["id"])}, indent=1, ensure_ascii=False) + "\n")


def calendar_since(day):
    from services.scanner.eodhd import prices
    return [r["date"] for r in prices("SPY", start=day) if r.get("close") is not None]


def fetch_bulk(day):
    from services.scanner.eodhd import get
    return get("eod-bulk-last-day/US", date=day, _timeout=300, _attempts=3)


def publish(config, new, outcomes, now, attempts=3):
    def git(*args, check=True):
        return subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, capture_output=True)
    from research.lab.run_queue import in_eod_window
    for _ in range(attempts):
        if in_eod_window():
            raise RuntimeError("inside the 23:30-04:30 UTC EOD window; triangle forward record not published")
        git("fetch", "origin", "main")
        git("switch", "--detach", "--force", "origin/main")
        write(ROOT, config, new, outcomes, now)
        git("add", "--", FOLDER)
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        git("-c", "user.name=sage-vista-bot", "-c", "user.email=sage-vista-bot@users.noreply.github.com",
            "commit", "-m", f"research: triangle forward record {now[:10]} [skip ci]")
        if git("push", "origin", "HEAD:main", check=False).returncode == 0:
            return
    raise RuntimeError("could not publish the triangle forward record after retries")


def main(argv=None):
    from research.lab.run_queue import in_eod_window
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads(CONFIG.read_text())
    if args.publish and in_eod_window():
        print("Inside the 23:30-04:30 UTC EOD window; nothing published.")
        return
    done = ROOT / FOLDER / "outcomes.json"
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    if args.publish and done.exists() and json.loads(done.read_text()).get("computed_at", "")[:10] == today:
        print("The triangle forward record was already updated today.")
        return
    new, outcomes = run(config, fetch_bulk, calendar_since(config["calendar_from"]))
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if args.publish:
        publish(config, new, outcomes, now)
    else:
        write(ROOT / "work/triangle-forward", config, new, outcomes, now)
    print(f"Triangle forward record: {len(new)} new signals, {len(outcomes)} outcomes recomputed")


if __name__ == "__main__":
    main()
