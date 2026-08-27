"""Turn completed research into a concise website decision contract."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path("research/backtest/output")
OUT = Path("public/decision-summary.json")


def metric(block):
    return {key: block.get(key) for key in ("samples", "win_rate", "profit_factor", "expectancy_pct", "median_return_pct")}


def run(out=OUT):
    pullback = json.loads((ROOT / "pullback-context-v2.json").read_text())
    attribution = json.loads((ROOT / "factor-attribution-v1.json").read_text())
    market = pullback["stock_by_market_context"]
    industry = pullback["industry_pullback"]["variants"]
    factor = {row["factor"]: row for row in attribution["factor_attribution"]}
    macd_2026 = factor["日线MACD近5日金叉"]["periods"]["forward_2026"]["with"]
    payload = {
        "version": "production-evidence-v1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "production_status": "awaiting_v2_rescan",
        "plain_summary": "可用主线是长期趋势＋MACD改善＋等待回撤；避免在上涨但未回撤时追高。行业与大盘仅调整优先级，不单独触发买入。",
        "usable": [
            {"name": "日线MACD改善", "role": "核心时机", "verdict": "保留", "metrics": metric(macd_2026), "note": "2026样本为正，但需与长期趋势和位置同用。"},
            {"name": "大盘回撤＋MACD修复", "role": "市场优先级", "verdict": "候选使用", "metrics": metric(market["Pullback + MACD Repair"]["periods"]["forward_2026"]), "note": "整体有效，2026胜率较低但PF仍大于1；不作硬门槛。"},
            {"name": "行业ETF回撤到支撑", "role": "行业加分", "verdict": "弱支持", "metrics": metric(industry["Pullback At Support"]["periods"]["forward_2026"]), "note": "可用于排序和解释，不能单独决定买入。"},
        ],
        "avoid": [
            {"name": "长期上涨但未回撤", "verdict": "不追高", "metrics": metric(market["Uptrend No Pullback"]["periods"]["forward_2026"]), "note": "2026利润因子小于1，期望为负。"},
            {"name": "行业回撤后强制要求MACD修复", "verdict": "不作硬门槛", "metrics": metric(industry["Pullback + MACD Repair"]["periods"]["forward_2026"]), "note": "2026样本中PF小于1，会过度筛选。"},
            {"name": "成交量恢复必须命中", "verdict": "样本不足", "metrics": metric(industry["Pullback + MACD + Volume Recovery"]["periods"]["forward_2026"]), "note": "只有18个2026样本，仅展示，不影响生产排名。"},
        ],
    }
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    return payload


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False))
