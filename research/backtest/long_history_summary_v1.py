"""Combine annual V2 summaries into robust, website-sized conclusions."""
from __future__ import annotations

import json
import pathlib
import statistics
from datetime import datetime, timezone

from services.scanner.factor_registry import FACTORS_BY_ID

ANNUAL = pathlib.Path("research/backtest/output/annual")
LEDGER = pathlib.Path("public/opportunity-ledger.json")
TRAILING = pathlib.Path("research/backtest/output/trailing-stop-v1-2026.json")
OUT = pathlib.Path("research/backtest/output/long-history-v1.json")
PUBLIC = pathlib.Path("public/factor-effectiveness.json")

EXCLUDE = {"macd.daily_bull_cross", "qualification.long_trend"}
AVOID = {"structure.double_bottom", "structure.higher_low", "structure.weekly_bullish_engulfing", "structure.weekly_double_bullish_engulfing", "volume.relative_expansion"}
PRIORITY_CANDIDATES = {"structure.bottom_bullish_engulfing", "volume.bottom_expansion", "risk.overhead_unfilled_gap"}


def _annual_rows():
    rows = {}
    for path in sorted(ANNUAL.glob("*.json")):
        payload = json.loads(path.read_text())
        rows[payload["year"]] = payload
    return rows


def _factor_row(payload, factor_id):
    return next((row for row in payload["factors"] if row["factor_id"] == factor_id), None)


def _annual_deltas(annual, factor_id, years):
    result = []
    for year in years:
        row = _factor_row(annual[year], factor_id)
        if not row:
            continue
        horizon = row["horizons"]["20"]
        hit, miss = horizon["hit"], horizon["non_hit"]
        if hit["samples"] < 30 or miss["samples"] < 30:
            continue
        result.append({"year":year,"samples":hit["samples"],"win_delta_pct":horizon["delta_win_rate_pct"],"median_delta_pct":round(hit["median_return_pct"]-miss["median_return_pct"],3)})
    return result


def _period(annual, factor_id, years):
    values = _annual_deltas(annual, factor_id, years)
    if not values:
        return {"eligible_years":0,"hit_samples":0,"median_annual_win_delta_pct":None,"median_annual_return_delta_pct":None,"positive_both_years":0}
    return {
        "eligible_years":len(values),
        "hit_samples":sum(row["samples"] for row in values),
        "median_annual_win_delta_pct":round(statistics.median(row["win_delta_pct"] for row in values),3),
        "median_annual_return_delta_pct":round(statistics.median(row["median_delta_pct"] for row in values),3),
        "positive_both_years":sum(row["win_delta_pct"]>0 and row["median_delta_pct"]>0 for row in values),
    }


def _single_year(annual, factor_id, year):
    row = _factor_row(annual[year], factor_id)
    if not row:
        return {"samples":0,"win_delta_pct":None,"median_delta_pct":None}
    horizon = row["horizons"]["20"]
    hit, miss = horizon["hit"], horizon["non_hit"]
    return {"samples":hit["samples"],"win_delta_pct":horizon["delta_win_rate_pct"],"median_delta_pct":round(hit["median_return_pct"]-miss["median_return_pct"],3)}


def _metric(values):
    wins = [value for value in values if value > 0]
    losses = [value for value in values if value < 0]
    return {"samples":len(values),"win_rate_pct":round(100*len(wins)/len(values),2) if values else None,"mean_return_pct":round(100*statistics.mean(values),3) if values else None,"median_return_pct":round(100*statistics.median(values),3) if values else None,"profit_factor":round(sum(wins)/abs(sum(losses)),3) if losses else None}


def _forward(ledger, factor_id):
    events = [row for row in ledger["events"] if row["signal_date"].startswith("2026-") and "unified_v2" in row["source_systems"] and row["evaluation"]["returns"].get("20") is not None]
    def hit(row):
        selection = row["selection"]
        return factor_id in selection.get("scored_factor_ids",[])+selection.get("observed_factor_ids",[])+selection.get("risk_factor_ids",[])
    yes = [row["evaluation"]["returns"]["20"] for row in events if hit(row)]
    no = [row["evaluation"]["returns"]["20"] for row in events if not hit(row)]
    ym, nm = _metric(yes), _metric(no)
    return {"hit":ym,"non_hit":nm,"win_delta_pct":round(ym["win_rate_pct"]-nm["win_rate_pct"],3) if yes and no else None,"median_delta_pct":round(ym["median_return_pct"]-nm["median_return_pct"],3) if yes and no else None}


def _tier(factor_id, development, validation, forward):
    if factor_id in AVOID:
        return "D", "长期偏弱或近期恶化", "停止加权；只保留审计记录"
    if factor_id in PRIORITY_CANDIDATES:
        if factor_id == "risk.overhead_unfilled_gap":
            return "B", "稳健胜率偏正，但均值结论冲突", "候选取消风险扣分；先保持展示，不直接加分"
        return "B", "跨阶段候选，尚未达到正式验证", "保留观察；不得单独触发或重复加分"
    recent_positive = validation["samples"]>=100 and forward["hit"]["samples"]>=100 and validation["win_delta_pct"] is not None and forward["win_delta_pct"] is not None and validation["win_delta_pct"]>0 and validation["median_delta_pct"]>0 and forward["win_delta_pct"]>0 and forward["median_delta_pct"]>0
    if recent_positive:
        return "B", "2025和2026同向，长期仍混合", "继续影子观察，不提高生产权重"
    if development["median_annual_win_delta_pct"] is not None and development["median_annual_win_delta_pct"]>0:
        return "C", "长期有方向、独立期不稳定", "按市场阶段展示，不作固定加分"
    return "C", "没有稳定的跨时期增量", "只展示或停权，不作为买入依据"


def _weighted_exit(annual, years, variant):
    rows = [annual[year]["exit_comparison"][variant] for year in years if annual[year]["exit_comparison"][variant]["samples"]]
    samples = sum(row["samples"] for row in rows)
    def weighted(key):
        return round(sum(row["samples"]*row[key] for row in rows)/samples,3) if samples else None
    return {"samples":samples,"win_rate_pct":weighted("win_rate_pct"),"mean_return_pct":weighted("mean_return_pct"),"median_annual_return_pct":weighted("median_return_pct"),"sample_weighted_annual_profit_factor":weighted("profit_factor"),"mean_r":weighted("mean_r")}


def run(out=OUT, public=PUBLIC):
    annual, ledger, trailing = _annual_rows(), json.loads(LEDGER.read_text()), json.loads(TRAILING.read_text())
    if sorted(annual) != list(range(2000,2026)):
        raise RuntimeError("Annual archive must contain every year 2000 through 2025")
    factor_ids = sorted({row["factor_id"] for payload in annual.values() for row in payload["factors"]}-EXCLUDE)
    factors = []
    for factor_id in factor_ids:
        development = _period(annual,factor_id,range(2001,2025))
        validation = _single_year(annual,factor_id,2025)
        forward = _forward(ledger,factor_id)
        tier,status,action = _tier(factor_id,development,validation,forward)
        factors.append({"factor_id":factor_id,"name_zh":FACTORS_BY_ID[factor_id].name_zh,"tier":tier,"research_status":status,"action":action,"development_2001_2024":development,"validation_2025":validation,"forward_2026":forward,"five_year_blocks":{
            "2001_2005":_period(annual,factor_id,range(2001,2006)),"2006_2010":_period(annual,factor_id,range(2006,2011)),"2011_2015":_period(annual,factor_id,range(2011,2016)),"2016_2020":_period(annual,factor_id,range(2016,2021)),"2021_2024":_period(annual,factor_id,range(2021,2025))}})
    factors.sort(key=lambda row:(row["tier"],-(row["forward_2026"]["win_delta_pct"] or -999),row["factor_id"]))
    exit_comparison = {
        "development_2001_2024":{"fixed":_weighted_exit(annual,range(2001,2025),"fixed"),"trail_8pct":_weighted_exit(annual,range(2001,2025),"close_trail_8pct_after_1r")},
        "validation_2025":{"fixed":_weighted_exit(annual,[2025],"fixed"),"trail_8pct":_weighted_exit(annual,[2025],"close_trail_8pct_after_1r")},
        "forward_2026":{"fixed":trailing["metrics"]["fixed"],"trail_8pct":trailing["metrics"]["close_trail_8pct_after_1r"]},
        "decision":"8%移动止损在三个阶段都提高胜率和中位数，但在2001—2024及2025略微降低平均收益和PF，只在2026全面胜出；因此它是降低盈利回吐的风险管理候选，不是长期收益已验证的无条件替代。"
    }
    payload = {"schema_version":"long-history-factor-study-v1.0.0","generated_at":datetime.now(timezone.utc).isoformat(),"coverage":{"years":"2000—2026","warmup_year":2000,"development":"2001—2024","validation":2025,"forward":2026,"historical_sessions":sum(x["coverage"]["sessions"] for x in annual.values()),"historical_candidates":sum(x["coverage"]["all_candidates"] for x in annual.values()),"weekly_checkpoints":sum(x["coverage"]["weekly_checkpoints"] for x in annual.values()),"factors_compared":len(factors)},"event_gate":"exact completed daily MACD bullish cross","technical_only_primary_test":True,"factor_method":"20-day hit versus same-pool non-hit; robust conclusions use annual win-rate and median-return deltas because raw means contain corporate-action/data outliers","factors":factors,"exit_comparison":exit_comparison,"conclusion":{"tier_a":[],"tier_b":[row["factor_id"] for row in factors if row["tier"]=="B"],"tier_d":[row["factor_id"] for row in factors if row["tier"]=="D"],"plain_zh":"没有单因子达到可无条件正式加权的A级标准。底部看涨吞没、底部放量和上方未填补缺口进入B级复核；双底、更高低点、周线吞没与相对放量应停权。EMA、斐波那契、筹码密集和FVG表现受阶段影响，只作位置证据。"},"limitations":["2019年后缓存股票覆盖明显扩大，已按年度和五年阶段报告而非直接混算","历史退市和更名覆盖仍不完整","重叠MACD事件不是独立交易","原始平均收益受少量公司行动或数据极值污染，因此因子定级以胜率和中位数增量为主","年度PF为年度统计的样本加权描述，不等于逐笔资金曲线PF"]}
    pathlib.Path(out).write_text(json.dumps(payload,ensure_ascii=False,indent=2)+"\n")
    # The website contract is owned by the newest completed audited study.  Do
    # not let rerunning this older annual summary overwrite the V2 conclusions.
    from services.scanner.factor_effectiveness import run as publish_factor_quadrants
    publish_factor_quadrants(out=public)
    return payload


if __name__ == "__main__":
    result=run();print(json.dumps({"coverage":result["coverage"],"conclusion":result["conclusion"],"exit":result["exit_comparison"]},ensure_ascii=False,indent=2))
