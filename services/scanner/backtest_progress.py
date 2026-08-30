"""Plan and persist one resumable, backward historical replay week at a time.

Both the authoritative cursor and its compact mirror live under ``automation/``.
They are Git-backed machine state, not public website data. A cursor advances
only after a completed week has been merged and validated.
"""
import argparse
import json
import pathlib
from datetime import date, datetime, timedelta, timezone

from .factor_registry import REGISTRY_VERSION
from .unified_v2_scan import MODEL_VERSION, RULESET_ID


SCHEMA_VERSION = "nightly-backtest-progress-v1.0.0"
DEFAULT_REPORT = pathlib.Path("public/unified-v2-rankings.json")
DEFAULT_STATE = pathlib.Path("automation/backtest-state.json")
DEFAULT_MIRROR = pathlib.Path("automation/backtest-progress.json")
TARGET_START = "2000-01-01"


def read_json(path, fallback=None):
 path = pathlib.Path(path)
 return json.loads(path.read_text()) if path.exists() else (fallback or {})


def previous_week(earliest, target_start=TARGET_START):
 first = date.fromisoformat(earliest)
 target = date.fromisoformat(target_start)
 end = first - timedelta(days=1)
 if end < target:
  return None
 start = max(target, end - timedelta(days=end.weekday()))
 return {"label": f"{start.isoformat()}_to_{end.isoformat()}", "start": start.isoformat(), "end": end.isoformat()}


def plan(report, state=None):
 coverage = report.get("coverage", {})
 if not coverage.get("start") or not coverage.get("end"):
  raise ValueError("Published historical report has no coverage")
 state = state or {}
 enabled = state.get("enabled", True)
 window = previous_week(coverage["start"], state.get("target_start", TARGET_START))
 return {
  "enabled": enabled,
  "status": "paused" if not enabled else "complete" if not window else "scheduled",
  "next_window": window,
  "coverage": {"start": coverage["start"], "end": coverage["end"], "sessions": coverage.get("sessions", len(report.get("days", [])))},
 }


def build_state(report, previous=None, completed_window=None, completed_at=None):
 previous = previous or {}
 current_plan = plan(report, previous)
 batches = list(previous.get("completed_batches", []))
 if not batches:
  batches.append({
   "batch_id": f"imported-{current_plan['coverage']['start']}-to-{current_plan['coverage']['end']}",
   "start": current_plan["coverage"]["start"],
   "end": current_plan["coverage"]["end"],
   "sessions": current_plan["coverage"]["sessions"],
   "model_versions": report.get("model_versions", [report.get("version")]),
   "factor_registry_versions": report.get("factor_registry_versions", [report.get("model", {}).get("factor_registry_version", "legacy_unrecorded")]),
   "source": "existing_published_history",
   "time_source": "repository_snapshot",
  })
 if completed_window:
  batch_id = completed_window["label"]
  if not any(item.get("batch_id") == batch_id for item in batches):
   days = [day for day in report.get("days", []) if completed_window["start"] <= day["date"] <= completed_window["end"]]
   batches.append({
    "batch_id": batch_id,
    "start": completed_window["start"],
    "end": completed_window["end"],
    "sessions": len(days),
    "completed_at": completed_at or datetime.now(timezone.utc).isoformat(),
    "model_versions": sorted({day.get("model_version", report.get("version")) for day in days}),
    "factor_registry_versions": sorted({day.get("factor_registry_version", "legacy_unrecorded") for day in days}),
    "source": "nightly_resumable_week",
    "time_source": "workflow_completion",
   })
 refreshed = plan(report, previous)
 return {
  "schema_version": SCHEMA_VERSION,
  "enabled": previous.get("enabled", True),
  "status": refreshed["status"],
  "mode": "backward_one_natural_week_per_night",
  "timezone": "Australia/Melbourne",
  "schedule": "21:30 AEST / 22:30 AEDT",
  "direction": "backward",
  "step": "natural_week",
  "target_start": previous.get("target_start", TARGET_START),
  "coverage": refreshed["coverage"],
  "next_window": refreshed["next_window"],
  "last_successful_batch": batches[-1],
  "completed_batches": batches,
  "active_rules": {"model_version": MODEL_VERSION, "factor_registry_version": REGISTRY_VERSION, "ruleset_id": RULESET_ID},
  "policy": {
   "resume_from_published_coverage": True,
   "completed_weeks_never_recomputed_automatically": True,
   "new_rules_apply_to_future_batches_only": True,
   "old_rules_can_be_replayed_only_as_a_separate_explicit_experiment": True,
   "weekly_artifact_saved_before_merge": True,
   "failure_does_not_advance_progress": True,
  },
  "updated_at": completed_at or previous.get("updated_at") or datetime.now(timezone.utc).isoformat(),
 }


def write_state(report_path=DEFAULT_REPORT, state_path=DEFAULT_STATE, mirror_path=DEFAULT_MIRROR, completed_window=None, completed_at=None):
 report = read_json(report_path)
 previous = read_json(state_path)
 payload = build_state(report, previous, completed_window, completed_at)
 text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
 pathlib.Path(state_path).write_text(text)
 pathlib.Path(mirror_path).write_text(text)
 return payload


def github_outputs(payload, path):
 window = payload.get("next_window") or {"label": "complete", "start": "", "end": ""}
 with pathlib.Path(path).open("a") as handle:
  for key, value in {"enabled": str(payload["enabled"]).lower(), "status": payload["status"], **window}.items():
   handle.write(f"{key}={value}\n")


if __name__ == "__main__":
 parser = argparse.ArgumentParser()
 parser.add_argument("command", choices=("plan", "sync", "complete"))
 parser.add_argument("--report", default=str(DEFAULT_REPORT));parser.add_argument("--state", default=str(DEFAULT_STATE));parser.add_argument("--mirror", default=str(DEFAULT_MIRROR));parser.add_argument("--github-output")
 parser.add_argument("--start");parser.add_argument("--end");parser.add_argument("--completed-at")
 args = parser.parse_args()
 report = read_json(args.report);previous = read_json(args.state)
 if args.command == "plan":
  payload = plan(report, previous)
 else:
  window = {"label": f"{args.start}_to_{args.end}", "start": args.start, "end": args.end} if args.command == "complete" else None
  if args.command == "complete" and (not args.start or not args.end):raise SystemExit("complete requires --start and --end")
  payload = write_state(args.report, args.state, args.mirror, window, args.completed_at)
 if args.github_output:github_outputs(payload, args.github_output)
 print(json.dumps(payload, ensure_ascii=False, indent=2))
