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
    long_path = ROOT / "long-history-v1.json"
    if long_path.exists():
        long = json.loads(long_path.read_text())
        factors = {row["factor_id"]: row for row in long["factors"]}
        exits = long["exit_comparison"]
        def forward_metric(factor_id):
            block = factors[factor_id]["forward_2026"]["hit"]
            return {"samples":block["samples"],"win_rate":block["win_rate_pct"],"profit_factor":block["profit_factor"],"expectancy_pct":block["mean_return_pct"],"median_return_pct":block["median_return_pct"]}
        trail = exits["forward_2026"]["trail_8pct"]
        payload = {
            "version":"production-evidence-v2.0.0",
            "generated_at":datetime.now(timezone.utc).isoformat(),
            "production_status":"long_history_completed_research_only",
            "plain_summary":"2001—2024开发、2025独立验证和2026前向已分开。没有单因子达到A级正式加权；底部放量和底部看涨吞没可优先观察。8%移动止损提高胜率和中位数，但长期平均收益略低于固定止损。",
            "usable":[
                {"name":"+1R后8%移动止损","role":"风险管理候选","verdict":"有条件使用","metrics":{"samples":trail["samples"],"win_rate":trail["win_rate_pct"],"profit_factor":trail["profit_factor"],"expectancy_pct":trail["mean_return_pct"],"median_return_pct":trail["median_return_pct"]},"note":"适合减少盈利回吐；长期开发期和2025的平均收益/PF略低，不能宣称全面优于固定止损。"},
                {"name":"底部放量","role":"B级技术确认","verdict":"优先观察","metrics":forward_metric("volume.bottom_expansion"),"note":"长期多数年份偏正、2025近中性、2026明显偏正；保留但暂不提高正式权重。"},
                {"name":"底部看涨吞没","role":"B级技术确认","verdict":"优先观察","metrics":forward_metric("structure.bottom_bullish_engulfing"),"note":"开发期、2025和2026的稳健方向较一致，但历史可用年份仍少，不单独触发买入。"},
            ],
            "avoid":[
                {"name":"双底","verdict":"停权","metrics":forward_metric("structure.double_bottom"),"note":"长期与2026胜率增量偏弱，不能因视觉形态重复加分。"},
                {"name":"更高低点","verdict":"停权","metrics":forward_metric("structure.higher_low"),"note":"长期多数年份未带来正增量，2025和2026也没有改善。"},
                {"name":"周线双看涨吞没","verdict":"停权","metrics":forward_metric("structure.weekly_double_bullish_engulfing"),"note":"2025与2026均明显偏弱，且样本有限。"},
            ],
        }
        Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
        return payload
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
