"""Versioned factor metadata shared by research, the daily radar and future alerts.

This module describes factors; it deliberately does not replace the existing
MACD calculations or promote research-only observations into validated scores.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


REGISTRY_VERSION = "0.9.0"
VALID_STATUSES = {"pending", "testing", "rejected", "unstable", "insufficient_sample", "candidate", "validated", "paused"}
VALID_SCORE_MODES = {"official", "observational", "display_only", "disabled"}


@dataclass(frozen=True)
class Factor:
    id: str
    version: str
    name_zh: str
    explanation: str
    machine_rule: str
    evidence_family: str
    timeframe: str
    lookahead_safe: bool
    confirmation_delay_bars: int
    status: str
    score_mode: str
    weight: float
    redundancy_group: str
    research_refs: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    factor_type: str = "event"
    observation_window_sessions: int = 0
    runtime_status: str = "ready"
    score_tier: str = "display_only"
    experimental_weight: float = 0.0
    dependency_policy: str = "all"


def factor(id, name, rule, family, timeframe="daily", status="pending", score_mode="display_only", weight=0.0, redundancy=None, refs=(), explanation=None, delay=0, depends_on=(), version="1.0.0", factor_type="event", window=0, runtime="ready", tier="display_only", experimental_weight=0.0, dependency_policy="all"):
    return Factor(id, version, name, explanation or name, rule, family, timeframe, True, delay, status, score_mode, weight, redundancy or id, tuple(refs), tuple(depends_on), factor_type, window, runtime, tier, experimental_weight, dependency_policy)


FACTORS = (
    factor("qualification.long_trend", "长期趋势资格", "close >= 0.9*EMA200 and EMA200_60d_change >= -3%", "qualification", status="candidate", score_mode="display_only", redundancy="trend_qualification", factor_type="qualification", tier="auxiliary", experimental_weight=1),
    factor("qualification.pullback_60d", "距60日高点回调", "close <= prior_60d_high*0.95", "qualification", status="candidate", score_mode="display_only", redundancy="pullback", factor_type="qualification"),
    factor("macd.daily_bull_cross", "日线MACD近5日金叉", "a completed daily MACD bullish cross occurred in the latest 5 sessions, including the trigger session, and MACD remains above signal", "macd", status="candidate", score_mode="observational", weight=1, redundancy="macd_daily", refs=("macd-rollout-01-baseline-2026-08-24","macd-five-session-freshness-2026-08-25"), explanation="日线MACD在最近五个完整交易日内金叉，且当前仍维持多头状态。", window=5, tier="core", experimental_weight=2),
    factor("macd.weekly_histogram_improving", "完整周线MACD柱改善", "latest completed weekly histogram > prior completed weekly histogram and prior histogram >= second-prior histogram", "macd", "weekly_completed", "candidate", "observational", 0, "macd_weekly", ("macd-multifactor-score-v1-2026-08-25","macd-factor-history-v2.0.0-2026-08-29"), version="1.0.2", factor_type="state", tier="core", experimental_weight=1),
    factor("macd.monthly_bull_cross", "完整月线MACD金叉", "MACD bullish cross on completed month", "macd", "monthly_completed", "candidate", "display_only", 0, "macd_monthly", ("macd-large-cycle-weekly-monthly-2026-08-25",), factor_type="state"),
    factor("support.ema_proximity", "日线 EMA21/50/200支撑", "daily close is within registered tolerance of daily EMA21, EMA50 or EMA200", "support", status="candidate", score_mode="display_only", weight=0, redundancy="moving_average_support", refs=("macd-multifactor-score-v1-2026-08-25",), factor_type="state"),
    factor("support.weekly_ema_proximity", "完整周线 EMA20/50/200支撑", "current completed daily close is within -2% to +3% of an EMA20, EMA50 or EMA200 calculated only from completed weekly bars", "support", "weekly_completed", "candidate", "display_only", 0, "weekly_moving_average_support", explanation="用已经完整收盘的周K计算 EMA20/50/200；当前价格靠近其中一条周线均线时，记录为更大周期支撑。", factor_type="state"),
    factor("support.monthly_ema_proximity", "完整月线 EMA20/50/200支撑", "current completed daily close is within -2% to +5% of an EMA20, EMA50 or EMA200 calculated only from completed monthly bars", "support", "monthly_completed", "candidate", "display_only", 0, "monthly_moving_average_support", explanation="用已经完整收盘的月K计算 EMA20/50/200；当前价格靠近其中一条月线均线时，记录为长期结构支撑。", factor_type="state"),
    factor("trend.dual_ma_alignment", "双均线多头排列", "EMA21 > EMA50 and both completed-session moving-average slopes are positive", "trend", status="testing", score_mode="display_only", redundancy="dual_ma_trend", explanation="EMA21位于EMA50上方且两条均线同向上行，仅作为趋势状态记录，暂不计分。", factor_type="state", runtime="definition_required"),
    factor("trend.dual_ma_fresh_cross", "双均线近期金叉", "EMA21 crossed above EMA50 within the latest 5 completed sessions and remains above", "trend", status="testing", score_mode="display_only", redundancy="dual_ma_trend", explanation="EMA21在最近5个完整交易日内上穿EMA50且当前仍保持在上方，用于研究交叉事件的时效性。", window=5, runtime="definition_required"),
    factor("structure.dual_ma_pullback_hold", "双均线转多后回踩守住", "after bullish EMA21/EMA50 alignment, price pulls back to EMA21 or EMA50 within registered tolerance and completes a close without losing the tested average", "price_structure", status="testing", score_mode="display_only", redundancy="dual_ma_pullback", explanation="双均线转多后，价格回踩EMA21或EMA50并以完整收盘守住；这是与当前‘长期上涨＋回撤支撑＋MACD改善’主线最匹配的候选。", depends_on=("trend.dual_ma_alignment",), factor_type="event", window=10, runtime="definition_required"),
    factor("support.fibonacci_half", "Fibonacci 0.5支撑", "close within 2% of confirmed swing 0.5 retracement", "support", status="rejected", score_mode="display_only", weight=0, redundancy="fibonacci_support", refs=("macd-rollout-05-fibonacci-half-2026-08-25",), factor_type="state"),
    factor("support.fibonacci_618", "Fibonacci 0.618支撑", "close near confirmed swing 0.618 retracement", "support", status="candidate", score_mode="display_only", weight=0, redundancy="fibonacci_support", factor_type="state"),
    factor("support.golden_pocket", "Golden Pocket", "close in confirmed swing 0.5 to 0.6182 retracement zone", "support", status="pending", redundancy="fibonacci_support", factor_type="state"),
    factor("structure.trendline_three_push", "三推趋势线突破", "confirmed three-push descending trendline close breakout", "price_structure", status="candidate", score_mode="observational", weight=0, redundancy="trendline_breakout", refs=("macd-pattern-v0.6.0-2026-08-24","macd-factor-history-v2.0.0-2026-08-29"), window=10, tier="core", experimental_weight=1),
    factor("structure.double_bottom", "双底", "two confirmed swing lows and objective neckline breakout", "price_structure", status="rejected", redundancy="bottom_structure", refs=("macd-pattern-v0.6.0-2026-08-24",), delay=2, window=10),
    factor("structure.higher_low", "更高低点", "latest confirmed swing low exceeds prior confirmed swing low", "price_structure", status="rejected", redundancy="bottom_structure", refs=("macd-factor-history-v2.0.0-2026-08-29",), delay=2, factor_type="state"),
    factor("structure.breakout_retest", "通用突破回踩", "completed close breakout of a registered structure followed by a valid held retest", "price_structure", status="pending", redundancy="breakout_retest", window=5, runtime="definition_required"),
    factor("structure.trendline_three_push_retest", "三推突破后回踩确认", "within 10 completed sessions after a confirmed three-push descending-trendline breakout, price touches the projected line within max(2%, 0.5 ATR), does not materially pierce it, and closes on or above it", "price_structure", status="candidate", score_mode="display_only", weight=0, redundancy="trendline_breakout", explanation="三推下降趋势线突破后十个交易日内回踩原趋势线并收盘守住，作为突破证据链的附加确认。", depends_on=("structure.trendline_three_push",), window=10),
    factor("structure.bullish_fvg_support", "Bullish FVG支撑", "open daily bullish fair-value gap remains below price as support", "price_structure", status="candidate", score_mode="display_only", weight=0, redundancy="imbalance_support", refs=("macd-multifactor-score-v1-2026-08-25",), factor_type="state"),
    factor("risk.overhead_unfilled_gap", "上方未补跳空缺口", "unfilled downside gap remains overhead", "risk", status="candidate", score_mode="display_only", weight=0, redundancy="overhead_supply", refs=("macd-multifactor-score-v1-2026-08-25","macd-factor-history-v2.0.0-2026-08-29"), factor_type="risk"),
    factor("rsi.oversold_repair", "RSI超卖修复", "RSI exits registered oversold zone on completed close", "rsi", status="pending", redundancy="rsi_reversal", window=5),
    factor("rsi.bullish_divergence", "RSI底背离", "price lower low with confirmed RSI higher low using only known pivots", "rsi", status="unstable", redundancy="rsi_reversal", refs=("macd-pattern-v0.6.0-2026-08-24",), delay=2, window=10),
    factor("volume.relative_expansion", "成交量突然放大", "volume / prior completed 20-day average >= configured threshold", "volume", status="rejected", redundancy="volume_expansion", refs=("macd-factor-history-v2.0.0-2026-08-29",), window=5),
    factor("volume.bottom_expansion", "支撑位底部放量", "close is in the lower 45% of its trailing 60-session range, at least one registered support context is active, and completed-session volume is at least 1.5 times the prior 20-session average and above prior-session volume", "volume", status="candidate", score_mode="observational", weight=0, redundancy="support_volume_confirmation", refs=("support-confirmation-hypothesis-2026-08-25","macd-factor-history-v2.0.0-2026-08-29"), explanation="价格处于底部并命中已登记支撑时，当日成交量显著高于此前20日均量和前一日，作为支撑获得资金响应的观察确认。", window=5, tier="core", experimental_weight=1, dependency_policy="support_context"),
    factor("volume.pullback_contraction", "缩量回调", "pullback volume contracts versus prior completed average", "volume", status="pending", redundancy="volume_contraction", factor_type="state", runtime="definition_required"),
    factor("structure.bottom_doji", "底部Doji", "Doji in lower 30% of trailing 60-day range within four bars before cross", "price_structure", status="rejected", redundancy="bottom_candle", refs=("macd-candle-v0.7.0-2026-08-24",), window=3),
    factor("structure.bottom_bullish_engulfing", "底部看涨吞没", "bullish engulfing in lower 30% of trailing range within four bars before cross", "price_structure", status="candidate", score_mode="observational", weight=0, redundancy="bottom_candle", refs=("macd-candle-v0.7.0-2026-08-24","macd-factor-history-v2.0.0-2026-08-29"), window=5, tier="core", experimental_weight=1),
    factor("structure.support_bullish_engulfing", "支撑位看涨吞没", "the latest completed candle is bullish, the prior candle is bearish, the bullish real body fully engulfs the prior bearish real body, and at least one registered support context is active", "price_structure", status="candidate", score_mode="observational", weight=0, redundancy="support_candle_confirmation", refs=("support-confirmation-hypothesis-2026-08-25","macd-factor-history-v2.0.0-2026-08-29"), explanation="在已登记支撑附近，后一根阳线实体完整包住前一根阴线实体，作为支撑获得价格响应的观察确认。", window=5, tier="core", experimental_weight=1, dependency_policy="support_context"),
    factor("structure.weekly_bullish_engulfing", "完整周线看涨吞没", "the latest completed weekly bullish real body fully engulfs the prior completed weekly bearish real body", "price_structure", "weekly_completed", "rejected", "display_only", 0, "weekly_engulfing_reversal", refs=("macd-factor-history-v2.0.0-2026-08-29",), explanation="长期复核列为D级；继续保留命中事实，但不进入分数或同分排序。", factor_type="state"),
    factor("structure.monthly_bullish_engulfing", "完整月线看涨吞没", "the latest completed monthly bullish real body fully engulfs the prior completed monthly bearish real body", "price_structure", "monthly_completed", "candidate", "display_only", 0, "monthly_engulfing_reversal", explanation="最近一根完整月K阳线实体包住前一根完整月K阴线实体；长期复核列为C级，仅显示上下文。", factor_type="state"),
    factor("structure.weekly_double_bullish_engulfing", "完整周线双看涨吞没", "the latest completed week is a bullish engulfing and a prior bullish engulfing occurred within 26 completed weeks with both lows within 10%", "price_structure", "weekly_completed", "rejected", "display_only", 0, "weekly_engulfing_reversal", refs=("macd-factor-history-v2.0.0-2026-08-29",), explanation="长期复核列为D级；保留审计，不进入分数或同分排序。", depends_on=("structure.weekly_bullish_engulfing",), factor_type="state"),
    factor("structure.monthly_double_bullish_engulfing", "完整月线双看涨吞没", "the latest completed month is a bullish engulfing and a prior bullish engulfing occurred within 12 completed months with both lows within 10%", "price_structure", "monthly_completed", "candidate", "display_only", 0, "monthly_engulfing_reversal", explanation="长期复核列为C级，仅显示上下文。", depends_on=("structure.monthly_bullish_engulfing",), factor_type="state"),
    factor("structure.engulfing_bullish_follow_through", "看涨吞没后K线跟随", "the immediately following completed daily candle closes bullish after a registered support bullish engulfing", "price_structure", status="testing", score_mode="display_only", weight=0, redundancy="engulfing_follow_through", explanation="支撑位看涨吞没后的下一根完整日K线继续收阳，确认短期上涨动能；必须依赖前一日吞没，不能独立触发。本轮仅记录，基准回测完成后再做加分对照。", depends_on=("structure.support_bullish_engulfing",), window=5),
    factor("structure.hammer", "锤头线", "registered lower-wick/body rejection rule", "price_structure", status="pending", redundancy="bottom_candle", window=3),
    factor("support.close_congestion", "K线聚集区", "at least 15% of prior 250 closes within +/-3%", "support", status="rejected", redundancy="chip_density", refs=("macd-rollout-02-kline-congestion-2026-08-24",), factor_type="state"),
    factor("support.volume_profile_proxy", "Volume Profile近似筹码峰", "largest of 40 daily typical-price volume bins is near current price", "support", status="rejected", redundancy="chip_density", refs=("macd-rollout-03-volume-profile-2026-08-25",), factor_type="state"),
)


CURRENT_COMPONENT_IDS = {
    "日线MACD近5日金叉": "macd.daily_bull_cross",
    "Fibonacci支撑": "support.fibonacci_half",
    "EMA支撑": "support.ema_proximity",
    "支撑位底部放量": "volume.bottom_expansion",
    "支撑位看涨吞没": "structure.support_bullish_engulfing",
    "周线MACD改善": "macd.weekly_histogram_improving",
    "三推趋势线突破": "structure.trendline_three_push",
    "三推突破后回踩确认": "structure.trendline_three_push_retest",
    "上方未补跳空缺口": "risk.overhead_unfilled_gap",
    "Bullish FVG支撑": "structure.bullish_fvg_support",
}

FACTORS_BY_ID = {item.id: item for item in FACTORS}
NON_SCORING_RESEARCH_STATUSES = {"pending", "testing", "rejected", "unstable", "insufficient_sample", "paused"}


def validate_registry():
    ids = [x.id for x in FACTORS]
    if len(ids) != len(set(ids)):
        raise ValueError("Factor IDs must be unique")
    for item in FACTORS:
        if item.status not in VALID_STATUSES or item.score_mode not in VALID_SCORE_MODES:
            raise ValueError(f"Invalid factor state: {item.id}")
        if item.score_mode == "official" and item.status != "validated":
            raise ValueError(f"Only validated factors may receive official score: {item.id}")
        if item.status in NON_SCORING_RESEARCH_STATUSES and (item.score_mode in {"official", "observational"} or item.weight):
            raise ValueError(f"Non-promoted factor cannot affect score: {item.id}")
        if item.status in {"rejected", "unstable", "insufficient_sample"} and item.experimental_weight:
            raise ValueError(f"Rejected or unstable factor cannot receive experimental score: {item.id}")
        if item.score_tier == "display_only" and item.experimental_weight:
            raise ValueError(f"Display-only factor cannot receive experimental score: {item.id}")
        if not item.lookahead_safe:
            raise ValueError(f"Unsafe factor cannot enter the registry: {item.id}")
        if any(parent not in ids for parent in item.depends_on):
            raise ValueError(f"Unknown factor dependency: {item.id}")
    return True


def registry_payload():
    validate_registry()
    return {"registry_version": REGISTRY_VERSION, "factor_count": len(FACTORS), "factors": [asdict(x) for x in FACTORS]}


def write_registry(out="public/factor-registry.json"):
    payload = registry_payload()
    Path(out).write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    return payload


if __name__ == "__main__":
    print(json.dumps(write_registry(), ensure_ascii=False, indent=2))
