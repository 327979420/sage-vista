"""Build the public experiment catalog and its human-readable GitHub summary."""
import json
import pathlib
from collections import Counter
from datetime import datetime, timezone

from .factor_registry import FACTORS

ROOT = pathlib.Path(__file__).parents[2]
LEDGER = ROOT / "research/experiments.jsonl"
EVENTS = ROOT / "research/experiment-events.jsonl"
SUMMARIES = ROOT / "research/experiment-summaries.zh.json"
RESEARCH_CATALOG = ROOT / "research/generated/experiment-catalog.json"
SUMMARY_DOC = ROOT / "docs/EXPERIMENT_SUMMARY_ZH.md"
EVENT_TYPES = {"registered", "started", "checkpoint", "completed", "blocked"}


def _jsonl(path):
 return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _lifecycle(row, events):
 ordered = sorted(events, key=lambda event: event["event_at"])
 by_type = {kind: [event for event in ordered if event["event"] == kind] for kind in EVENT_TYPES}
 historical_times = [value for value in [row.get("created_at"), *(event["event_at"] for event in ordered)] if value]
 registered = by_type["registered"][0]["event_at"] if by_type["registered"] else min(historical_times, default=None)
 started = by_type["started"][0]["event_at"] if by_type["started"] else None
 completed = by_type["completed"][-1]["event_at"] if by_type["completed"] else None
 latest = ordered[-1] if ordered else None
 return {
  "registered_at": registered,
  "started_at": started,
  "completed_at": completed,
  "latest_event": latest["event"] if latest else None,
  "latest_event_at": latest["event_at"] if latest else None,
  "time_source": latest.get("time_source") if latest else None,
  "event_count": len(ordered),
  "events": ordered,
 }


def build(ledger=None):
 rows = ledger if ledger is not None else _jsonl(LEDGER)
 ids = [row["experiment_id"] for row in rows]
 if len(ids) != len(set(ids)):
  raise ValueError("Duplicate experiment_id")
 known = set(ids)
 events = _jsonl(EVENTS)
 unknown_event_ids = sorted({event["experiment_id"] for event in events} - known)
 if unknown_event_ids:
  raise ValueError(f"Events reference unknown experiments: {unknown_event_ids}")
 invalid_events = sorted({event["event"] for event in events} - EVENT_TYPES)
 if invalid_events:
  raise ValueError(f"Invalid lifecycle events: {invalid_events}")
 summaries = json.loads(SUMMARIES.read_text())["experiments"]
 missing_summaries = sorted(known - set(summaries))
 extra_summaries = sorted(set(summaries) - known)
 if missing_summaries or extra_summaries:
  raise ValueError(f"Summary coverage mismatch; missing={missing_summaries}, extra={extra_summaries}")
 events_by_id = {experiment_id: [] for experiment_id in known}
 for event in events:
  events_by_id[event["experiment_id"]].append(event)
 missing_events = sorted(experiment_id for experiment_id, values in events_by_id.items() if not values)
 if missing_events:
  raise ValueError(f"Experiments without lifecycle records: {missing_events}")
 merged = []
 for row in rows:
  experiment_id = row["experiment_id"]
  merged.append({**row, "human_summary": summaries[experiment_id], "lifecycle": _lifecycle(row, events_by_id[experiment_id])})
 merged.sort(key=lambda row: row["lifecycle"]["latest_event_at"] or "", reverse=True)
 factor_links = {factor.id: [ref for ref in factor.research_refs if ref in known] for factor in FACTORS}
 missing_refs = sorted({ref for factor in FACTORS for ref in factor.research_refs if ref not in known})
 linked = {ref for refs in factor_links.values() for ref in refs}
 statuses = Counter("completed" if row["lifecycle"]["completed_at"] else row["status"] for row in merged)
 verdicts = Counter(row["human_summary"]["verdict"] for row in merged)
 return {
  "schema_version": "2.0.0",
  "generated_at": max((row["lifecycle"]["latest_event_at"] for row in merged if row["lifecycle"]["latest_event_at"]), default=datetime.now(timezone.utc).isoformat()),
  "sources": ["research/experiments.jsonl", "research/experiment-events.jsonl", "research/experiment-summaries.zh.json"],
  "experiment_count": len(rows),
  "summary": {"completed": statuses["completed"], "in_progress": len(rows) - statuses["completed"], "candidate": verdicts["candidate"], "not_validated_or_unstable": verdicts["not_validated"] + verdicts["unstable"]},
  "policy": {"append_only": True, "failed_results_preserved": True, "lifecycle_events_required": True, "human_summary_required": True, "historical_backtest_separate_from_production_forward": True},
  "experiments": merged,
  "factor_experiments": factor_links,
  "unlinked_experiment_ids": sorted(known - linked),
  "missing_registry_references": missing_refs,
 }


def _display_time(value):
 return value.replace("T", " ") if value else "未单独记录"


def render_summary(catalog):
 lines = [
  "# Sage Vista 实验总结",
  "",
  "> 这是由实验账本自动生成的中文索引。原始结果、失败结果和限制条件均不会被覆盖。",
  "",
  f"- 实验总数：{catalog['experiment_count']}",
  f"- 已完成：{catalog['summary']['completed']}",
  f"- 待运行或进行中：{catalog['summary']['in_progress']}",
  f"- 当前候选：{catalog['summary']['candidate']}",
  f"- 未验证或不稳定：{catalog['summary']['not_validated_or_unstable']}",
  "",
  "## 怎样阅读",
  "",
  "“候选”不等于已经可用于生产；只有通过独立验证并经规则手册批准后才会改正式评分。旧实验没有精确运行日志时，结束时间使用该结果首次进入 GitHub 的时间，并明确标注。",
  "",
  "## 完整实验档案",
  "",
 ]
 for row in catalog["experiments"]:
  summary = row["human_summary"]
  lifecycle = row["lifecycle"]
  state = "已完成" if lifecycle["completed_at"] else "待运行"
  end = _display_time(lifecycle["completed_at"]) if lifecycle["completed_at"] else "进行中／尚未运行"
  source_note = "（GitHub 首次记录时间）" if lifecycle["completed_at"] and lifecycle["time_source"] == "git_commit" else ""
  lines.extend([
   f"### {summary['title_zh']} · {state}",
   "",
   f"- 实验编号：`{row['experiment_id']}`",
   f"- 分类：{summary['family_zh']}",
   f"- 最早记录：{_display_time(lifecycle['registered_at'])}",
   f"- 开始：{_display_time(lifecycle['started_at'])}",
   f"- 结束：{end}{source_note}",
   f"- 要回答：{summary['question_zh']}",
   f"- 得到什么：{summary['result_zh']}",
   f"- 现在怎么用：{summary['use_zh']}",
   f"- 下一步：{summary['next_zh']}",
   "",
  ])
 return "\n".join(lines)


def write(out=RESEARCH_CATALOG, summary_out=SUMMARY_DOC):
 payload = build()
 out_path=pathlib.Path(out);summary_path=pathlib.Path(summary_out)
 out_path.parent.mkdir(parents=True,exist_ok=True);summary_path.parent.mkdir(parents=True,exist_ok=True)
 out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
 summary_path.write_text(render_summary(payload) + "\n")
 return payload


if __name__ == "__main__":
 print(json.dumps(write(), ensure_ascii=False, indent=2))
