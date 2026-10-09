"""Forward paper accounts: proven portfolios tracked from a fixed start on live prices.

The portfolios and the start date are registered before the start, so the
record is out of sample by construction. Each lab run recomputes every account
from the start with the latest adjusted prices (latest.json) and appends that
day's values to an append-only log (history.jsonl); earlier log lines are
never rewritten, so the as-recorded path stays visible even if a provider later
revises old prices.

  python3 -m research.lab.forward            # local preview, writes work/forward
  python3 -m research.lab.forward --publish  # Actions: commit to main
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import subprocess

from research.lab import account, allocation, datasets
from services.scanner.macd_factor_backtest import adjusted_rows

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG = ROOT / "research/lab/forward/config.json"


def symbols_of(config):
    return sorted(set().union(*(allocation.roles(p) for p in config["portfolios"])) | {config["calendar"]})


def compute(config, prices, as_of_limit=None):
    """Account values from the start to the latest common date; None before the start has a session."""
    calendar = prices[config["calendar"]]["date"]
    dates = [d for d in calendar if d >= config["start"] and (as_of_limit is None or d <= as_of_limit)]
    if not dates:
        return None
    signal_day = calendar[calendar.index(dates[0]) - 1]
    book = allocation.Prices(prices)
    initial, out = float(config["initial_cash"]), {}
    for p in config["portfolios"]:
        run = allocation.simulate(p, book, dates, config["cost_per_side"], initial, signal_day)
        equity = run["equity"]
        peak, fall = initial, 0.0
        for v in equity:
            peak = max(peak, v)
            fall = max(fall, 1 - v / peak)
        out[p["id"]] = {"label": p["label"], "value": round(equity[-1], 2), "return": round(equity[-1] / initial - 1, 6),
                        "max_drawdown": round(fall, 6), "sharpe": account.curve_stats(equity, dates, initial)["sharpe"] if len(dates) > 20 else None,
                        "weights": run["rebalances"][-1]["weights"]}
    return {"as_of": dates[-1], "sessions": len(dates), "start": config["start"], "portfolios": out}


def write(root, config, snapshot, now):
    folder = pathlib.Path(root) / "research/lab/forward"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "latest.json").write_text(json.dumps({"id": config["id"], "computed_at": now, **snapshot}, indent=1, ensure_ascii=False) + "\n")
    history = folder / "history.jsonl"
    seen = {json.loads(line)["as_of"] for line in history.read_text().splitlines() if line.strip()} if history.exists() else set()
    if snapshot["as_of"] not in seen:
        line = {"as_of": snapshot["as_of"], "recorded_at": now, "values": {k: v["value"] for k, v in snapshot["portfolios"].items()}}
        with history.open("a") as handle:
            handle.write(json.dumps(line) + "\n")


def fetch_prices(config):
    from services.scanner.eodhd import prices
    out = {}
    for symbol in symbols_of(config):
        rows = adjusted_rows(prices(symbol, start=config["history_from"]))
        if not rows:
            raise ValueError(f"forward_prices_missing: {symbol}")
        out[symbol] = datasets._compact(rows)
    return out


def publish(config, snapshot, now, attempts=3):
    def git(*args, check=True):
        return subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, capture_output=True)
    from research.lab.run_queue import in_eod_window
    for _ in range(attempts):
        if in_eod_window():
            raise RuntimeError("inside the 23:30-04:30 UTC EOD window; forward accounts not published")
        git("fetch", "origin", "main")
        git("switch", "--detach", "--force", "origin/main")
        write(ROOT, config, snapshot, now)
        git("add", "--", "research/lab/forward")
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        git("-c", "user.name=sage-vista-bot", "-c", "user.email=sage-vista-bot@users.noreply.github.com",
            "commit", "-m", f"research: forward paper accounts {snapshot['as_of']} [skip ci]")
        if git("push", "origin", "HEAD:main", check=False).returncode == 0:
            return
    raise RuntimeError("could not publish forward accounts after retries")


def main(argv=None):
    from research.lab.run_queue import in_eod_window
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads(CONFIG.read_text())
    today = dt.datetime.now(dt.timezone.utc).date().isoformat()
    if today < config["start"]:
        print(f"Forward accounts start on {config['start']}; nothing to record yet.")
        return
    if args.publish and in_eod_window():
        print("Inside the 23:30-04:30 UTC EOD window; nothing published.")
        return
    snapshot = compute(config, fetch_prices(config))
    if snapshot is None:
        print("No session since the start yet.")
        return
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    if args.publish:
        publish(config, snapshot, now)
    else:
        write(ROOT / "work", config, snapshot, now)
    print(f"Forward accounts as of {snapshot['as_of']}: " + ", ".join(f"{k} {v['value']:,.0f}" for k, v in snapshot["portfolios"].items()))


if __name__ == "__main__":
    main()
