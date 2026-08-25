"""Versioned factor metadata shared by research, the daily radar and future alerts.

This module describes factors; it deliberately does not replace the existing
MACD calculations or promote research-only observations into validated scores.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


REGISTRY_VERSION = "0.4.0"
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


def factor(id, name, rule, family, timeframe="daily", status="pending", score_mode="display_only", weight=0.0, redundancy=None, refs=(), explanation=None, delay=0, depends_on=()):
    return Factor(id, "1.0.0", name, explanation or name, rule, family, timeframe, True, delay, status, score_mode, weight, redundancy or id, tuple(refs), tuple(depends_on))


FACTORS = (
    factor("qualification.long_trend", "长期趋势资格", "close >= 0.9*EMA200 and EMA200_60d_change >= -3%", "qualification", status="candidate", score_mode="display_only", redundancy="trend_qualification"),
    factor("qualification.pullback_60d", "距60日高点回调", "close <= prior_60d_high*0.95", "qualification", status="candidate", score_mode="display_only", redundancy="pullback"),
    factor("macd.daily_bull_cross", "日线MACD近5日金叉", "a completed daily MACD bullish cross occurred in the latest 5 sessions, including the trigger session, and MACD remains above signal", "macd", status="candidate", score_mode="observational", weight=1, redundancy="macd_daily", refs=("macd-rollout-01-baseline-2026-08-24","macd-five-session-freshness-2026-08-25"), explanation="日线MACD在最近五个完整交易日内金叉，且当前仍维持多头状态。"),
    factor("macd.weekly_histogram_improving", "完整周线MACD柱改善", "latest completed weekly histogram > prior completed weekly histogram", "macd", "weekly_completed", "candidate", "observational", 1, "macd_weekly", ("macd-multifactor-score-v1-2026-08-25",)),
    factor("macd.monthly_bull_cross", "完整月线MACD金叉", "MACD bullish cross on completed month", "macd", "monthly_completed", "candidate", "display_only", 0, "macd_monthly", ("macd-large-cycle-weekly-monthly-2026-08-25",)),
    factor("support.ema_proximity", "EMA21/50/200支撑", "close is within registered tolerance of EMA21, EMA50 or EMA200", "support", status="candidate", score_mode="observational", weight=1, redundancy="moving_average_support", refs=("macd-multifactor-score-v1-2026-08-25",)),
    factor("support.fibonacci_half", "Fibonacci 0.5支撑", "close within 2% of confirmed swing 0.5 retracement", "support", status="rejected", score_mode="observational", weight=1, redundancy="fibonacci_support", refs=("macd-rollout-05-fibonacci-half-2026-08-25",)),
    factor("support.fibonacci_618", "Fibonacci 0.618支撑", "close near confirmed swing 0.618 retracement", "support", status="candidate", score_mode="observational", weight=1, redundancy="fibonacci_support"),
    factor("support.golden_pocket", "Golden Pocket", "close in confirmed swing 0.5 to 0.6182 retracement zone", "support", status="pending", redundancy="fibonacci_support"),
    factor("structure.trendline_three_push", "三推趋势线突破", "confirmed three-push descending trendline close breakout", "price_structure", status="unstable", score_mode="observational", weight=1, redundancy="trendline_breakout", refs=("macd-pattern-v0.6.0-2026-08-24",)),
    factor("structure.double_bottom", "双底", "two confirmed swing lows and objective neckline breakout", "price_structure", status="rejected", redundancy="bottom_structure", refs=("macd-pattern-v0.6.0-2026-08-24",), delay=2),
    factor("structure.higher_low", "更高低点", "latest confirmed swing low exceeds prior confirmed swing low", "price_structure", status="pending", redundancy="bottom_structure", delay=2),
    factor("structure.breakout_retest", "通用突破回踩", "completed close breakout of a registered structure followed by a valid held retest", "price_structure", status="pending", redundancy="breakout_retest"),
    factor("structure.trendline_three_push_retest", "三推突破后回踩确认", "within 10 completed sessions after a confirmed three-push descending-trendline breakout, price touches the projected line within max(2%, 0.5 ATR), does not materially pierce it, and closes on or above it", "price_structure", status="candidate", score_mode="observational", weight=1, redundancy="trendline_breakout", explanation="三推下降趋势线突破后十个交易日内回踩原趋势线并收盘守住，作为突破证据链的附加确认。", depends_on=("structure.trendline_three_push",)),
    factor("structure.bullish_fvg_support", "Bullish FVG支撑", "open daily bullish fair-value gap remains below price as support", "price_structure", status="candidate", score_mode="observational", weight=1, redundancy="imbalance_support", refs=("macd-multifactor-score-v1-2026-08-25",)),
    factor("risk.overhead_unfilled_gap", "上方未补跳空缺口", "unfilled downside gap remains overhead", "risk", status="candidate", score_mode="observational", weight=1, redundancy="overhead_supply", refs=("macd-multifactor-score-v1-2026-08-25",)),
    factor("rsi.oversold_repair", "RSI超卖修复", "RSI exits registered oversold zone on completed close", "rsi", status="pending", redundancy="rsi_reversal"),
    factor("rsi.bullish_divergence", "RSI底背离", "price lower low with confirmed RSI higher low using only known pivots", "rsi", status="unstable", redundancy="rsi_reversal", refs=("macd-pattern-v0.6.0-2026-08-24",), delay=2),
    factor("volume.relative_expansion", "成交量突然放大", "volume / prior completed 20-day average >= configured threshold", "volume", status="testing", redundancy="volume_expansion"),
    factor("volume.bottom_expansion", "支撑位底部放量", "close is in the lower 45% of its trailing 60-session range, at least one registered support context is active, and completed-session volume is at least 1.5 times the prior 20-session average and above prior-session volume", "volume", status="candidate", score_mode="observational", weight=1, redundancy="support_volume_confirmation", refs=("support-confirmation-hypothesis-2026-08-25",), explanation="价格处于底部并命中已登记支撑时，当日成交量显著高于此前20日均量和前一日，作为支撑获得资金响应的观察确认。"),
    factor("volume.pullback_contraction", "缩量回调", "pullback volume contracts versus prior completed average", "volume", status="pending", redundancy="volume_contraction"),
    factor("structure.bottom_doji", "底部Doji", "Doji in lower 30% of trailing 60-day range within four bars before cross", "price_structure", status="rejected", redundancy="bottom_candle", refs=("macd-candle-v0.7.0-2026-08-24",)),
    factor("structure.bottom_bullish_engulfing", "底部看涨吞没", "bullish engulfing in lower 30% of trailing range within four bars before cross", "price_structure", status="rejected", redundancy="bottom_candle", refs=("macd-candle-v0.7.0-2026-08-24",)),
    factor("structure.support_bullish_engulfing", "支撑位看涨吞没", "the latest completed candle is bullish, the prior candle is bearish, the bullish real body fully engulfs the prior bearish real body, and at least one registered support context is active", "price_structure", status="candidate", score_mode="observational", weight=1, redundancy="support_candle_confirmation", refs=("support-confirmation-hypothesis-2026-08-25",), explanation="在已登记支撑附近，后一根阳线实体完整包住前一根阴线实体，作为支撑获得价格响应的观察确认。"),
    factor("structure.hammer", "锤头线", "registered lower-wick/body rejection rule", "price_structure", status="pending", redundancy="bottom_candle"),
    factor("support.close_congestion", "K线聚集区", "at least 15% of prior 250 closes within +/-3%", "support", status="rejected", redundancy="chip_density", refs=("macd-rollout-02-kline-congestion-2026-08-24",)),
    factor("support.volume_profile_proxy", "Volume Profile近似筹码峰", "largest of 40 daily typical-price volume bins is near current price", "support", status="rejected", redundancy="chip_density", refs=("macd-rollout-03-volume-profile-2026-08-25",)),
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


def validate_registry():
    ids = [x.id for x in FACTORS]
    if len(ids) != len(set(ids)):
        raise ValueError("Factor IDs must be unique")
    for item in FACTORS:
        if item.status not in VALID_STATUSES or item.score_mode not in VALID_SCORE_MODES:
            raise ValueError(f"Invalid factor state: {item.id}")
        if item.score_mode == "official" and item.status != "validated":
            raise ValueError(f"Only validated factors may receive official score: {item.id}")
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
