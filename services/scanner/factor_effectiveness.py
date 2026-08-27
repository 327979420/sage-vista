"""Publish factor-level backtest conclusions for the product UI."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


SOURCE = Path("research/backtest/output/factor-attribution-v1.json")
OUT = Path("public/factor-effectiveness.json")


def run(source=SOURCE, out=OUT):
    report = json.loads(Path(source).read_text())
    rows = []
    for item in report["factor_attribution"]:
        metrics = item["periods"]["forward_2026"]["with"]
        status = item["status"]
        if "基础资格" in status:
            action = "保留为核心时机"
            tone = "keep"
        elif "候选正贡献" in status:
            action = "继续观察，样本不足"
            tone = "watch"
        elif "拖累" in status:
            action = "不进入生产加分"
            tone = "avoid"
        else:
            action = "只展示，不作独立加分"
            tone = "neutral"
        rows.append({
            "factor": item["factor"],
            "research_status": status,
            "action": action,
            "tone": tone,
            "samples_2026": metrics["samples"],
            "win_rate_2026": metrics["win_rate"],
            "profit_factor_2026": metrics["profit_factor"],
            "expectancy_2026": metrics["expectancy_pct"],
        })
    payload = {
        "version": "factor-effectiveness-v1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "coverage": {"period": "forward_2026", "factors": len(rows), "source_signals_end": "2026-06-24"},
        "warning": "这是因子归因而非因果证明；因子存在重叠，不能把胜率直接相加。",
        "factors": rows,
    }
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
