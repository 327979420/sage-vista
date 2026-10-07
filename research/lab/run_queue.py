"""Run pre-registered lab experiments from research/lab/queue, one at a time.

Each spec is frozen before it runs (its SHA256 is stored with the result). A
spec whose result already exists for the same SHA256 is never re-run, so the
daily background job only spends time on new questions. Results, a cumulative
scoreboard and the experiment lifecycle event are committed permanently;
negative results are kept exactly like positive ones.

  python3 -m research.lab.run_queue            # local dry run, writes work/lab
  python3 -m research.lab.run_queue --publish  # Actions: commit results to main
"""
from __future__ import annotations

import argparse
import bisect
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import os
import pathlib
import subprocess

from services.scanner.support_risk import signal_support_plan
from research.lab import datasets
from research.lab.exit_rules import simulate
from research.lab.metrics import evaluate, summarise

ROOT = pathlib.Path(__file__).resolve().parents[2]
QUEUE = ROOT / "research/lab/queue"
RESULTS = ROOT / "research/lab/results"
SCOREBOARD = ROOT / "research/lab/scoreboard.json"
SCOREBOARD_MD = ROOT / "research/lab/SCOREBOARD.md"
EVENTS = ROOT / "research/experiment-events.jsonl"
WORK = ROOT / "work/lab"


def spec_sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def pending_specs():
    out = []
    for path in sorted(QUEUE.glob("*.json")):
        spec = json.loads(path.read_text())
        done = RESULTS / spec["id"] / "result.json"
        if done.exists() and json.loads(done.read_text())["spec_sha256"] == spec_sha(path):
            continue
        out.append((spec.get("priority", 100), spec["id"], path, spec))
    return [item[2:] for item in sorted(out, key=lambda x: (x[0], x[1]))]


def in_eod_window(now=None):
    """Never publish while the daily EOD release may be pushing to main."""
    now = now or dt.datetime.now(dt.timezone.utc)
    minutes = now.hour * 60 + now.minute
    return minutes >= 23 * 60 + 30 or minutes < 4 * 60 + 30


def ensure_dataset(spec, publish):
    entry = datasets.manifest(spec["dataset"]["id"])
    if entry:
        return datasets.load(datasets.download(entry, WORK), entry["sha256"]), entry, None
    source = spec["dataset"]["builder"]
    if source == "ledger":
        data = datasets.build_from_ledger(ROOT / "public/opportunity-ledger.json", ROOT / "work/eodhd-cache", spec["dataset"]["id"])
    elif source == "observation":
        from services.scanner.eodhd import prices
        data = datasets.build_from_observation(ROOT / spec["dataset"]["events_csv"], spec["dataset"]["id"], lambda s: prices(s, start="2004-01-01"))
    else:
        raise ValueError(f"unknown dataset builder {source}")
    path, entry = datasets.save(data, WORK)
    if publish:
        datasets.upload(path)
    return data, entry, entry


def run_spec(spec, data, dataset_entry, cost):
    variants = {v["id"]: v for v in spec["variants"]}
    trades = {vid: [] for vid in variants}
    rows_out = []
    # One stock at a time keeps memory flat even for the 20-year dataset.
    cached_symbol, bars, dates = None, [], []
    for event in sorted(data["events"], key=lambda e: (e["symbol"], e["signal_date"])):
        if event["symbol"] != cached_symbol:
            cached_symbol = event["symbol"]
            bars = datasets.expand(data["prices"][cached_symbol])
            dates = data["prices"][cached_symbol]["date"]
        signal = bisect.bisect_left(dates, event["signal_date"])
        if signal >= len(dates) or dates[signal] != event["signal_date"]:
            continue
        plan = event.get("support_plan") or signal_support_plan(bars, end=signal)
        split = next((s["id"] for s in spec["splits"] if s["from"] <= event["signal_date"] <= s["to"]), None)
        for vid, variant in variants.items():
            result = simulate(bars, signal + 1, variant, support_plan=plan, cost_per_side=cost)
            result["split"] = split
            trades[vid].append(result)
            if result["status"] == "resolved":
                rows_out.append([vid, event["event_id"], event["symbol"], event["signal_date"], split, result["exit_reason"],
                                 result["held"], result["risk_pct"], result["net_return"], result["r_multiple"]])
    summary = {}
    for vid, items in trades.items():
        overall = summarise(items)
        splits = {s["id"]: summarise([t for t in items if t["split"] == s["id"]]) for s in spec["splits"]}
        stress = summarise([{**t, "net_return": t["net_return"] - 2 * cost, "r_multiple": (t["net_return"] - 2 * cost) / t["risk_pct"]}
                            if t.get("status") == "resolved" else t for t in items])
        summary[vid] = {"label": variants[vid]["label"], "family": variants[vid].get("family", vid), "rule": variants[vid],
                        "overall": overall, "splits": splits, "double_cost": {k: stress.get(k) for k in ("mean_return", "expectancy_r", "profit_factor")}}
    for vid, item in summary.items():
        neighbours = [summary[n]["overall"] for n in spec.get("neighbours", {}).get(vid, [])]
        item["verdict"] = evaluate(item["overall"], item["splits"], neighbours, spec["criteria"])
        base = summary[spec["baseline"]]["overall"]
        item["vs_baseline"] = {k: round((item["overall"].get(k) or 0) - (base.get(k) or 0), 4) for k in ("expectancy_r", "mean_return", "median_return", "win_rate")}
    passed = [vid for vid, item in summary.items() if item["verdict"]["passed"] and vid != spec["baseline"]]
    champion = max(passed, key=lambda v: summary[v]["overall"]["expectancy_r"]) if passed else None
    csv_buffer = io.StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(["variant", "event_id", "symbol", "signal_date", "split", "exit_reason", "held", "risk_pct", "net_return", "r_multiple"])
    writer.writerows(rows_out)
    result = {"spec_id": spec["id"], "experiment_id": spec["experiment_id"], "group": spec["group"], "question": spec["question"],
              "dataset": {k: dataset_entry[k] for k in ("dataset_id", "asset", "sha256", "events", "symbols")},
              "cost_per_side": cost, "baseline": spec["baseline"], "criteria": spec["criteria"], "variants": summary,
              "champion": champion, "selection_rule": "highest overall expectancy_r among variants passing every pre-registered check"}
    return result, gzip.compress(csv_buffer.getvalue().encode(), 9, mtime=0)


def render_scoreboard(results):
    board = {"schema_version": "1.0.0", "experiments": [], "champions": {}}
    lines = ["# Research lab scoreboard", "", "Generated by `research/lab/run_queue.py` from every saved result; do not edit by hand.",
             "Event-level results: signals overlap and are not a capital-constrained portfolio.", ""]
    for result in sorted(results, key=lambda r: (r["group"], r["completed_at"])):
        board["experiments"].append({k: result[k] for k in ("spec_id", "experiment_id", "group", "completed_at", "champion")} | {"dataset": result["dataset"]["dataset_id"]})
        if result["champion"]:
            v = result["variants"][result["champion"]]
            board["champions"][result["group"]] = {"spec_id": result["spec_id"], "variant": result["champion"], "rule": v["rule"], "overall": v["overall"]}
        lines += [f"## {result['spec_id']} ({result['dataset']['dataset_id']})", "", result["question"], "",
                  "| Variant | Trades | Win | Mean | Median | PF | E[R] | SQN | Splits + | Passed |", "|---|---|---|---|---|---|---|---|---|---|"]
        for vid, v in result["variants"].items():
            o = v["overall"]
            pct = lambda x: "—" if x is None else f"{x * 100:.2f}%"
            lines.append(f"| {vid} {v['label']} | {o.get('resolved', 0)} | {pct(o.get('win_rate'))} | {pct(o.get('mean_return'))} | {pct(o.get('median_return'))} | "
                         f"{o.get('profit_factor', '—')} | {o.get('expectancy_r', '—')} | {o.get('sqn', '—')} | {'yes' if v['verdict']['checks']['every_split_positive'] else 'no'} | {'**yes**' if v['verdict']['passed'] else 'no'} |")
        lines += ["", f"Champion: **{result['champion'] or 'none passed; baseline stays'}**", ""]
    return board, "\n".join(lines) + "\n"


def write_outputs(root, result, trades_csv, event, manifests):
    out = pathlib.Path(root) / "research/lab/results" / result["spec_id"]
    out.mkdir(parents=True, exist_ok=True)
    (out / "result.json").write_text(json.dumps(result, indent=1, ensure_ascii=False) + "\n")
    (out / "trades.csv.gz").write_bytes(trades_csv)
    for entry in manifests:
        record = pathlib.Path(root) / "research/lab/datasets" / f"{entry['dataset_id']}.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(json.dumps(entry, indent=1) + "\n")
    events = pathlib.Path(root) / "research/experiment-events.jsonl"
    if event["details"]["spec_sha256"] not in events.read_text():
        with events.open("a") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
    results = [json.loads(p.read_text()) for p in (pathlib.Path(root) / "research/lab/results").glob("*/result.json")]
    board, markdown = render_scoreboard(results)
    (pathlib.Path(root) / "research/lab/scoreboard.json").write_text(json.dumps(board, indent=1, ensure_ascii=False) + "\n")
    (pathlib.Path(root) / "research/lab/SCOREBOARD.md").write_text(markdown)


def publish(result, trades_csv, event, manifests, attempts=3):
    def git(*args, check=True):
        return subprocess.run(["git", *args], cwd=ROOT, check=check, text=True, capture_output=True)
    for _ in range(attempts):
        git("fetch", "origin", "main")
        git("switch", "--detach", "--force", "origin/main")
        write_outputs(ROOT, result, trades_csv, event, manifests)
        # Keep the published experiment catalog and summary in step with the event log.
        subprocess.run(["python3", "-m", "services.scanner.experiment_catalog"], cwd=ROOT, check=True, capture_output=True)
        subprocess.run(["python3", "-m", "services.scanner.project_status"], cwd=ROOT, check=True, capture_output=True)
        git("add", "--", "research/lab", "research/experiment-events.jsonl", "research/generated/experiment-catalog.json",
            "docs/EXPERIMENT_SUMMARY_ZH.md", "docs/CURRENT_STATUS_ZH.md")
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            return
        git("-c", "user.name=sage-vista-bot", "-c", "user.email=sage-vista-bot@users.noreply.github.com",
            "commit", "-m", f"research: lab result {result['spec_id']} [skip ci]")
        if git("push", "origin", "HEAD:main", check=False).returncode == 0:
            return
    raise RuntimeError("could not publish lab result after retries")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--max-specs", type=int, default=3)
    args = parser.parse_args(argv)
    if args.publish and in_eod_window():
        print("Inside the 23:30-04:30 UTC EOD window; nothing published.")
        return
    ran = 0
    for path, spec in pending_specs()[: args.max_specs]:
        sha = spec_sha(path)
        data, entry, new_manifest = ensure_dataset(spec, args.publish)
        result, trades_csv = run_spec(spec, data, entry, spec.get("cost_per_side", 0.001))
        now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        result |= {"spec_sha256": sha, "completed_at": now, "code_commit": os.environ.get("GITHUB_SHA", "local")}
        run_url = f"{os.environ.get('GITHUB_SERVER_URL', '')}/{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/{os.environ.get('GITHUB_RUN_ID', '')}"
        event = {"experiment_id": spec["experiment_id"], "event": "completed", "event_at": now,
                 "time_source": "github_actions" if os.environ.get("GITHUB_ACTIONS") else "local",
                 "source_ref": run_url if os.environ.get("GITHUB_ACTIONS") else None,
                 "details": {"lab_spec": spec["id"], "spec_sha256": sha, "result": f"research/lab/results/{spec['id']}/result.json",
                             "dataset": entry["dataset_id"], "champion": result["champion"]}}
        manifests = [new_manifest] if new_manifest else []
        if args.publish:
            publish(result, trades_csv, event, manifests)
        else:
            (WORK / "preview").mkdir(parents=True, exist_ok=True)
            (WORK / "preview" / f"{spec['id']}.json").write_text(json.dumps(result, indent=1, ensure_ascii=False))
        print(f"{spec['id']}: champion={result['champion']} ({entry['events']} events)")
        ran += 1
    if not ran:
        print("No pending lab specs.")


if __name__ == "__main__":
    main()
