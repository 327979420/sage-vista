"""Core + 3W satellite paper account (task 046): registered before its start, computed daily on Actions.

Core 50%: SPY and nine sector ETFs, each 10% of the core sleeve's previous-close equity at a rebalance. At the last
NYSE session of each month a sleeve holds its ETF when that close is above its own 200-day simple moving average,
else SHY; trades happen at the next session's open. Satellite 50%: every rule-1.9 order of the frozen 3w-1.9 forward
record, booked with the frozen account rules (account.run_account) on the satellite's own equity; fills and exits come
from the same daily-OHLC replay the forward scorecard uses (forward_judge.recompute). Idle satellite cash earns 0%.
The sleeves are never rebalanced against each other. Whole shares, 0.1% per side, missing prices stop the run.

  python3 -m research.lab.paper            # local preview, writes work/paper
  python3 -m research.lab.paper --publish  # Actions: also commits research/lab/paper to main
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import pathlib
import subprocess

from research.lab import account, calendars

ROOT = pathlib.Path(__file__).resolve().parents[2]
FOLDER = "research/lab/paper"
CONFIG = ROOT / FOLDER / "config.json"
SERIES = ROOT / "work/paper/series.json"
SATELLITE_RULES = {"risk_per_trade": 0.02, "position_cap": 0.2, "max_positions": 10, "heat_cap": 0.1}


def is_month_end(day):
    return calendars.next_session("XNYS", day)[:7] != day[:7]


def signal_month_end(start):
    """The last month-end session strictly before `start` (its signal sets the first core positions)."""
    day = calendars.previous_session("XNYS", start)
    while not is_month_end(day):
        day = calendars.previous_session("XNYS", day)
    return day


def bar(prices, symbol, day):
    series = prices.get(symbol)
    if series is None:
        raise ValueError(f"paper_prices_missing: {symbol}")
    index = series.get("_index") or {d: i for i, d in enumerate(series["date"])}
    series["_index"] = index
    if day not in index:
        raise ValueError(f"paper_price_missing: {symbol} {day}")
    return index[day]


def above_sma(prices, symbol, day, window=200):
    """Close strictly above its own simple moving average of the last `window` closes (equal is not above)."""
    i = bar(prices, symbol, day)
    if i + 1 < window:
        raise ValueError(f"paper_history_short: {symbol} {day}")
    closes = prices[symbol]["close"][i + 1 - window:i + 1]
    return prices[symbol]["close"][i] > sum(closes) / window


def core_targets(prices, sleeves, safe, day):
    return {sleeve: (sleeve if above_sma(prices, sleeve, day) else safe) for sleeve in sleeves}


def run_core(prices, dates, sleeves, safe, equity0, cost, first_signal_day):
    """Daily core equity. Rebalances at the open after each month-end signal, the first one on the start session."""
    shares, cash, equity, rebalances = {}, float(equity0), [], []
    pending = (first_signal_day, core_targets(prices, sleeves, safe, first_signal_day))
    for k, day in enumerate(dates):
        if pending:
            signal_day, targets = pending
            base = equity[-1] if equity else float(equity0)
            want = {}
            for sleeve in sleeves:
                symbol = targets[sleeve]
                price = prices[symbol]["open"][bar(prices, symbol, day)]
                want[symbol] = want.get(symbol, 0) + math.floor(0.10 * base / (price * (1 + cost)))
            opens = {s: prices[s]["open"][bar(prices, s, day)] for s in set(want) | set(shares)}
            for symbol in sorted(shares):  # sells first, so their cash pays for the buys
                drop = shares[symbol] - want.get(symbol, 0)
                if drop > 0:
                    cash += drop * opens[symbol] * (1 - cost)
                    shares[symbol] -= drop
            for symbol in sorted(want):
                add = want[symbol] - shares.get(symbol, 0)
                if add > 0:
                    add = min(add, math.floor(cash / (opens[symbol] * (1 + cost))))
                    cash -= add * opens[symbol] * (1 + cost)
                    shares[symbol] = shares.get(symbol, 0) + add
            shares = {s: n for s, n in shares.items() if n}
            rebalances.append({"date": day, "signal": signal_day, "targets": targets, "shares": dict(shares)})
            pending = None
        value = cash + sum(n * prices[s]["close"][bar(prices, s, day)] for s, n in shares.items())
        equity.append(value)
        if is_month_end(day) and k + 1 < len(dates):
            pending = (day, core_targets(prices, sleeves, safe, day))
        elif is_month_end(day):
            pending = None  # decided on the next run, once the next session exists
    return {"equity": equity, "shares": shares, "cash": cash, "rebalances": rebalances}


def satellite_candidates(px, rows, start):
    """Frozen-account candidates from forward_judge.recompute rows: rule-1.9 orders filled on or after `start`."""
    out = []
    for row in rows:
        trade = row.get("trade") or {}
        if not row.get("eligible") or trade.get("fill_day") is None:
            continue
        series = px[row["symbol"]] if "symbol" in row else None
        if series is None:
            raise ValueError(f"paper_satellite_series_missing: {row['id']}")
        f = trade["fill_day"]
        if series["date"][f] < start:
            continue
        done = trade.get("status") in ("win", "loss", "time")
        last = trade["exit_day"] if done else len(series["date"]) - 1
        out.append({"event_id": row["id"], "symbol": row["symbol"], "signal_date": row["signal_day"], "priority": 0,
                    "entry_date": series["date"][f], "entry_price": float(trade["entry"]), "stop": float(trade["stop"]),
                    "fills": [(series["date"][trade["exit_day"]], float(trade["exit"]), 1.0)] if done else [],
                    "data_ended": False, "closes": [(series["date"][i], float(series["close"][i])) for i in range(f, last + 1)]})
    return out


def run_satellite(candidates, dates, equity0, cost):
    aligned, checks = account.align(candidates, dates)
    scenario = {"initial_cash": float(equity0), "allocation_fraction": 0.1, "cost_rate": cost, "max_positions": 10,
                "fractional_shares": False}
    run = account.run_account(aligned, len(dates), scenario, rules=SATELLITE_RULES)
    return {**run, "checks": checks}


def run_spy(prices, dates, equity0, cost):
    first = bar(prices, "SPY", dates[0])
    open0 = prices["SPY"]["open"][first]
    n = math.floor(equity0 / (open0 * (1 + cost)))
    cash = equity0 - n * open0 * (1 + cost)
    return [cash + n * prices["SPY"]["close"][bar(prices, "SPY", d)] for d in dates]


def compute(config, prices, candidates):
    """Daily series from the start to the last session every core symbol has. None before the first session."""
    symbols = config["core"]["sleeves"] + [config["core"]["safe"], "SPY"]
    last = min(prices[s]["date"][-1] for s in symbols if s in prices)
    dates = [d for d in prices["SPY"]["date"] if config["start"] <= d <= last]
    if not dates:
        return None
    half = config["initial_cash"] / 2
    core = run_core(prices, dates, config["core"]["sleeves"], config["core"]["safe"], half, config["cost_per_side"],
                    signal_month_end(config["start"]))
    sat = run_satellite(candidates, dates, half, config["cost_per_side"])
    spy = run_spy(prices, dates, config["initial_cash"], config["cost_per_side"])
    series = [{"date": d, "core": round(c, 2), "satellite": round(s, 2), "total": round(c + s, 2), "spy": round(b, 2)}
              for d, c, s, b in zip(dates, core["equity"], sat["equity"], spy)]
    return {"as_of": dates[-1], "start": config["start"], "sessions": len(dates), "series": series,
            "core": {"shares": core["shares"], "cash": round(core["cash"], 2), "last_rebalance": core["rebalances"][-1]},
            "satellite": {"open_positions": sat["open_at_end"], "trades": sat["trades"], "skipped": sat["skipped"],
                          "checks": sat["checks"]}}


def forward_rows():
    """(px, rows) per dataset, built exactly as forward_judge.main does on the forward job's local caches."""
    from research.lab import forward_judge as J, triangle_forward as F
    config = json.loads(F.CONFIG.read_text())
    frozen = json.loads((F.ROOT / F.FOLDER / "outcomes.json").read_text())
    records = F.load_records()
    for ds in config["datasets"]:
        recs = [r for r in records if r["dataset"] == ds]
        if recs:
            px = J.cached_prices(ds, config, frozen["computed_at"][:10])
            rows = J.recompute(px, recs, frozen["outcomes"], config)
            for row, rec in zip(rows, recs):
                row.setdefault("symbol", rec["symbol"])
            yield px, rows


def fetch_prices(config):
    from research.lab import datasets
    from services.scanner.eodhd import prices
    from services.scanner.macd_factor_backtest import adjusted_rows
    out = {}
    for symbol in sorted(set(config["core"]["sleeves"]) | {config["core"]["safe"], "SPY"}):
        rows = adjusted_rows(prices(symbol, start=config["history_from"]))
        if not rows:
            raise ValueError(f"paper_prices_missing: {symbol}")
        out[symbol] = datasets._compact(rows)
    return out


def write(root, config, snapshot, now):
    folder = pathlib.Path(root) / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    last = snapshot["series"][-1]
    (folder / "latest.json").write_text(json.dumps({"id": config["id"], "computed_at": now, **{k: v for k, v in snapshot.items() if k != "series"},
                                                    "values": last}, indent=1, ensure_ascii=False) + "\n")
    history = folder / "history.jsonl"
    seen = {json.loads(line)["as_of"] for line in history.read_text().splitlines() if line.strip()} if history.exists() else set()
    if snapshot["as_of"] not in seen:
        with history.open("a") as handle:
            handle.write(json.dumps({"as_of": snapshot["as_of"], "recorded_at": now, "values": last}) + "\n")


def publish(config, snapshot, now, attempts=3):
    def git(*args, check=True):
        return subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, capture_output=True)
    from research.lab.run_queue import in_eod_window
    for _ in range(attempts):
        if in_eod_window():
            raise RuntimeError("inside the 23:30-04:30 UTC EOD window; paper account not published")
        git("fetch", "origin", "main")
        git("switch", "--detach", "--force", "origin/main")
        write(ROOT, config, snapshot, now)
        git("add", "--", FOLDER)
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        git("-c", "user.name=sage-vista-bot", "-c", "user.email=sage-vista-bot@users.noreply.github.com",
            "commit", "-m", f"research: core + 3W paper account {snapshot['as_of']} [skip ci]")
        if git("push", "origin", "HEAD:main", check=False).returncode == 0:
            return
    raise RuntimeError("could not publish the paper account after retries")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads(CONFIG.read_text())
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    if today < config["start"]:
        print(f"Paper account starts on {config['start']}; nothing to record yet.")
        return
    candidates = [c for px, rows in forward_rows() for c in satellite_candidates(px, rows, config["start"])]
    snapshot = compute(config, fetch_prices(config), candidates)
    if snapshot is None:
        print("No session since the start yet.")
        return
    SERIES.parent.mkdir(parents=True, exist_ok=True)
    SERIES.write_text(json.dumps(snapshot["series"], ensure_ascii=False) + "\n")
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if args.publish:
        publish(config, snapshot, now)
    else:
        write(ROOT / "work", config, snapshot, now)
    v = snapshot["series"][-1]
    print(f"Paper account as of {snapshot['as_of']}: total {v['total']:,.0f} (core {v['core']:,.0f}, satellite {v['satellite']:,.0f}); "
          f"SPY {v['spy']:,.0f}")


if __name__ == "__main__":
    main()
