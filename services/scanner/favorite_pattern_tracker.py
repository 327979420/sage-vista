"""Point-in-time tracker for the user's preferred daily reversal setup.

This is deliberately a setup state machine, not a production factor or score.
All pivots require two completed bars of right-side confirmation.
"""
from __future__ import annotations

import itertools
from collections import Counter

from .technical import ema, macd


LEGACY_PATTERN_VERSION = "favorite-pattern-v1.0.1"
V2_PATTERN_VERSION = "favorite-pattern-v2.0.0"
V2_EXPERIMENT_ID = "favorite-pattern-sequence-v2.0.0-2026-08-30"
PATTERN_VERSION = "favorite-pattern-v3.1.0"
EXPERIMENT_ID = "favorite-pattern-macd-gated-v3.1.0-2026-08-30"
GENERALIZATION_VERSION = "favorite-pattern-generalization-v1.0.1"
REFERENCE_CASES = {
    "ADBE": "时序教学：3月先完成趋势转变，5月真实回调后再由新结构、MACD和EMA转强确认；教顺序，不要求复制外形。",
    "BABA": "形态语言教学：位置、底部结构、趋势线突破和均线转强可以共振，但不是其他股票必须照抄的模板。",
    "TTD": "风险回归：底部正面证据不能覆盖多轮空头压力、弱EMA和上方未修复供给。",
    "AEVA": "风险回归：多重顶部供给与顶部耗竭没有修复时，不得把MACD金叉升级为完整做多序列。",
}
LEGACY_ONLY_CASES = ["PG"]
STAGE_ORDER = {
    "entry_ready": 7,
    "risk_blocked": 6,
    "launched": 6,
    "target_reached": 5,
    "waiting_breakout": 4,
    "breakout_incomplete": 3,
    "bottom_confirmed": 3,
    "pullback_forming": 2,
    "discovery": 1,
    "invalidated": 0,
    "unavailable": -1,
}
STAGE_ZH = {
    "entry_ready": "入场就绪",
    "risk_blocked": "风险否决",
    "launched": "突破后跟踪",
    "target_reached": "已到前高目标",
    "waiting_breakout": "等待突破",
    "breakout_incomplete": "已突破但条件不完整",
    "bottom_confirmed": "双底已确认",
    "pullback_forming": "回调形成中",
    "discovery": "早期发现",
    "invalidated": "形态失效",
    "unavailable": "数据不足",
}


def _atr(rows, period=14):
    true_ranges = []
    values = []
    for index, row in enumerate(rows):
        previous_close = rows[index - 1]["close"] if index else row["close"]
        true_ranges.append(max(row["high"] - row["low"], abs(row["high"] - previous_close), abs(row["low"] - previous_close)))
        window = true_ranges[max(0, index - period + 1) : index + 1]
        values.append(sum(window) / len(window))
    return values


def _confirmed_pivots(rows, field, mode, left=2, right=2, window=360):
    start = max(left, len(rows) - window)
    end = len(rows) - right
    found = []
    for index in range(start, end):
        value = rows[index][field]
        neighbors = [rows[j][field] for j in range(index - left, index + right + 1) if j != index]
        if (mode == "low" and value <= min(neighbors)) or (mode == "high" and value >= max(neighbors)):
            found.append(index)
    return found


def _find_double_bottom(rows, atr_values, low_pivots):
    end = len(rows) - 1
    lows = [index for index in low_pivots if index >= end - 200][-20:]
    candidates = []
    for first, second in itertools.combinations(lows, 2):
        separation = second - first
        if not 15 <= separation <= 120:
            continue
        first_price, second_price = rows[first]["low"], rows[second]["low"]
        midpoint = (first_price + second_price) / 2
        tolerance = max(midpoint * 0.08, atr_values[second] * 1.25)
        if abs(first_price - second_price) > tolerance:
            continue
        rebound_high = max(row["high"] for row in rows[first + 1 : second])
        rebound = rebound_high - max(first_price, second_price)
        rebound_required = min(midpoint * 0.08, atr_values[second] * 2)
        if rebound < rebound_required:
            continue
        invalidation = min(first_price, second_price) - atr_values[second] * 0.5
        invalidated = any(row["close"] < invalidation for row in rows[second + 1 :])
        candidates.append(
            {
                "first_index": first,
                "second_index": second,
                "first_date": rows[first]["date"],
                "second_date": rows[second]["date"],
                "first_price": round(first_price, 2),
                "second_price": round(second_price, 2),
                "separation_sessions": separation,
                "spread_pct": round(abs(first_price - second_price) / midpoint * 100, 2),
                "neckline": round(rebound_high, 2),
                "rebound_pct": round(rebound / midpoint * 100, 2),
                "invalidation": round(invalidation, 2),
                "invalidated": invalidated,
            }
        )
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["second_index"], item["rebound_pct"], -item["spread_pct"]))


def _find_impulse(rows, low_pivots, high_pivots, first_bottom_index):
    candidates = []
    for high_index in high_pivots:
        if not max(0, first_bottom_index - 180) <= high_index <= first_bottom_index - 5:
            continue
        for low_index in low_pivots:
            span = high_index - low_index
            if low_index < first_bottom_index - 252 or not 10 <= span <= 180:
                continue
            low_price, high_price = rows[low_index]["low"], rows[high_index]["high"]
            advance = high_price / low_price - 1
            if advance < 0.25:
                continue
            candidates.append(
                {
                    "low_index": low_index,
                    "high_index": high_index,
                    "low_date": rows[low_index]["date"],
                    "high_date": rows[high_index]["date"],
                    "low": round(low_price, 2),
                    "high": round(high_price, 2),
                    "advance_pct": round(advance * 100, 2),
                    "span_sessions": span,
                }
            )
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["advance_pct"], item["high_index"]))


def _find_three_push(rows, high_pivots, bottom=None):
    end = len(rows) - 1
    # The latest 14 confirmed highs still cover a multi-month structure in
    # normal data while keeping a full-universe daily scan bounded.
    highs = [index for index in high_pivots if index >= end - 220][-14:]
    candidates = []
    for first, second, third in itertools.combinations(highs, 3):
        if second - first < 5 or third - second < 5 or third - first > 180:
            continue
        if bottom and (third < bottom["first_index"] or first > bottom["second_index"] or third > bottom["second_index"] + 30):
            continue
        values = [rows[index]["high"] for index in (first, second, third)]
        if not (values[1] <= values[0] * 0.995 and values[2] <= values[1] * 0.995):
            continue
        slope = (values[2] - values[0]) / (third - first)
        projected_second = values[0] + slope * (second - first)
        if abs(values[1] / projected_second - 1) > 0.08:
            continue
        breakout_index = None
        breakout_level = None
        for index in range(third + 1, end + 1):
            level = values[0] + slope * (index - first)
            previous_level = values[0] + slope * (index - 1 - first)
            if rows[index]["close"] > level * 1.01 and rows[index - 1]["close"] <= previous_level * 1.01:
                breakout_index, breakout_level = index, level
                break
        if bottom and breakout_index is not None and breakout_index < bottom["second_index"] - 5:
            breakout_index, breakout_level = None, None
        candidates.append(
            {
                "high_indices": [first, second, third],
                "high_dates": [rows[index]["date"] for index in (first, second, third)],
                "high_prices": [round(value, 2) for value in values],
                "slope_per_session": round(slope, 6),
                "current_line": round(values[0] + slope * (end - first), 2),
                "breakout_index": breakout_index,
                "breakout_date": rows[breakout_index]["date"] if breakout_index is not None else None,
                "breakout_close": round(rows[breakout_index]["close"], 2) if breakout_index is not None else None,
                "breakout_level": round(breakout_level, 2) if breakout_level is not None else None,
                "bars_since_breakout": end - breakout_index if breakout_index is not None else None,
            }
        )
    if not candidates:
        return None
    return max(candidates, key=lambda item: (item["breakout_index"] is not None, item["breakout_index"] or -1, item["high_indices"][-1]))


def _favorite_chart(rows):
    closes = [row["close"] for row in rows]
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    start = max(0, len(rows) - 180)
    return [
        {
            "date": rows[index]["date"],
            "high": round(rows[index]["high"], 2),
            "low": round(rows[index]["low"], 2),
            "close": round(rows[index]["close"], 2),
            "ema20": round(e20[index], 2),
            "ema50": round(e50[index], 2),
            "ema200": round(e200[index], 2),
        }
        for index in range(start, len(rows))
    ]


def _evaluate_v1(rows, include_chart=False):
    """Evaluate a single symbol using completed bars available in ``rows``."""
    if len(rows) < 260:
        return {"available": False, "stage": "unavailable", "stage_zh": STAGE_ZH["unavailable"], "match_count": 0, "total_conditions": 7, "reason": "至少需要260个完整日K"}

    end = len(rows) - 1
    closes = [row["close"] for row in rows]
    atr_values = _atr(rows)
    low_pivots = _confirmed_pivots(rows, "low", "low")
    high_pivots = _confirmed_pivots(rows, "high", "high")
    bottom = _find_double_bottom(rows, atr_values, low_pivots)
    impulse = _find_impulse(rows, low_pivots, high_pivots, bottom["first_index"]) if bottom else None
    three_push = _find_three_push(rows, high_pivots, bottom)

    retracement_pct = None
    golden_pocket = False
    if impulse and bottom:
        denominator = impulse["high"] - impulse["low"]
        if denominator > 0:
            retracement_pct = (impulse["high"] - min(bottom["first_price"], bottom["second_price"])) / denominator * 100
            golden_pocket = 50 <= retracement_pct <= 70

    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    ema200_distances = []
    if bottom:
        for index in (bottom["first_index"], bottom["second_index"]):
            if e200[index]:
                ema200_distances.append(abs(rows[index]["low"] / e200[index] - 1) * 100)
    ema200_support = bool(ema200_distances and min(ema200_distances) <= 6)

    macd_line, signal_line = macd(closes)
    macd_cross_index = None
    if bottom:
        start = max(1, bottom["second_index"] - 5)
        stop = min(end, bottom["second_index"] + 15)
        crosses = [index for index in range(start, stop + 1) if macd_line[index] > signal_line[index] and macd_line[index - 1] <= signal_line[index - 1]]
        if crosses:
            macd_cross_index = min(crosses, key=lambda index: abs(index - bottom["second_index"]))

    ema_cross_index = None
    if bottom:
        start = max(1, bottom["second_index"])
        crosses = [index for index in range(start, end + 1) if e20[index] > e50[index] and e20[index - 1] <= e50[index - 1]]
        ema_cross_index = crosses[-1] if crosses else None
    ema_realigned = e20[end] > e50[end] and ema_cross_index is not None

    breakout = bool(three_push and three_push["breakout_index"] is not None)
    location_support = golden_pocket or ema200_support
    conditions = [
        {"id": "prior_advance", "label": "前段明显上涨", "hit": bool(impulse)},
        {"id": "pullback_location", "label": "Golden Pocket／EMA200回调", "hit": location_support},
        {"id": "broad_double_bottom", "label": "宽口径双底", "hit": bool(bottom)},
        {"id": "second_bottom_macd", "label": "二底附近MACD金叉", "hit": macd_cross_index is not None},
        {"id": "three_push", "label": "三推下降趋势线", "hit": bool(three_push)},
        {"id": "ema_realign", "label": "EMA20重新高于EMA50", "hit": ema_realigned},
        {"id": "close_breakout", "label": "完整收盘突破趋势线", "hit": breakout},
    ]
    match_count = sum(item["hit"] for item in conditions)

    target = impulse["high"] if impulse else None
    target_reached = bool(breakout and target and max(row["high"] for row in rows[three_push["breakout_index"] :]) >= target)
    invalidated = bool(bottom and bottom["invalidated"])
    bars_since_breakout = three_push["bars_since_breakout"] if breakout else None
    current_above_breakout = bool(breakout and closes[end] >= three_push["current_line"])
    complete = all(item["hit"] for item in conditions)
    structure_waiting = bool(impulse and location_support and bottom and macd_cross_index is not None and three_push)
    if invalidated:
        stage = "invalidated"
    elif complete and target_reached:
        stage = "target_reached"
    elif complete and bars_since_breakout is not None and bars_since_breakout <= 5:
        stage = "entry_ready"
    elif complete and current_above_breakout:
        stage = "launched"
    elif breakout:
        stage = "breakout_incomplete"
    elif structure_waiting:
        stage = "waiting_breakout"
    elif impulse and location_support and bottom:
        stage = "bottom_confirmed"
    elif impulse and location_support:
        stage = "pullback_forming"
    else:
        stage = "discovery"

    entry_price = three_push["breakout_close"] if breakout else None
    invalidation = bottom["invalidation"] if bottom else None
    reward_risk = None
    if entry_price and invalidation and target and entry_price > invalidation and target > entry_price:
        reward_risk = round((target - entry_price) / (entry_price - invalidation), 2)
    action = {
        "entry_ready": "突破已经由完整收盘确认；研究口径最早下一交易日开盘进入，先看前高目标与二底失效位。",
        "launched": "已经突破，继续跟踪是否守住趋势线；不是追高提示。",
        "target_reached": "已经触及前段高点目标，记录结果，不再当作新入场。",
        "waiting_breakout": "双底和二底MACD已有，只等待完整收盘突破；盘中刺穿不行动。",
        "breakout_incomplete": "价格已经突破，但至少缺少一项核心位置或结构条件；不归入场就绪，也不进入前向信号。",
        "bottom_confirmed": "双底已确认，但三推／MACD／均线证据尚未齐，不急着买。",
        "pullback_forming": "回调位置接近模板，等待第二底和动能确认。",
        "discovery": "只命中少量早期条件，暂不行动。",
        "invalidated": "价格已经收盘跌破二底失效位，本轮形态结束。",
    }[stage]
    result = {
        "available": True,
        "pattern_version": LEGACY_PATTERN_VERSION,
        "stage": stage,
        "stage_zh": STAGE_ZH[stage],
        "match_count": match_count,
        "total_conditions": len(conditions),
        "match_pct": round(match_count / len(conditions) * 100),
        "conditions": conditions,
        "action_zh": action,
        "prior_advance": impulse,
        "pullback": {
            "retracement_pct": round(retracement_pct, 2) if retracement_pct is not None else None,
            "golden_pocket": golden_pocket,
            "ema200_support": ema200_support,
            "ema200_nearest_distance_pct": round(min(ema200_distances), 2) if ema200_distances else None,
        },
        "double_bottom": bottom,
        "second_bottom_macd": {
            "hit": macd_cross_index is not None,
            "cross_date": rows[macd_cross_index]["date"] if macd_cross_index is not None else None,
            "distance_from_second_bottom_sessions": macd_cross_index - bottom["second_index"] if macd_cross_index is not None and bottom else None,
        },
        "three_push": three_push,
        "ema_realign": {
            "hit": ema_realigned,
            "cross_date": rows[ema_cross_index]["date"] if ema_cross_index is not None else None,
            "ema20": round(e20[end], 2),
            "ema50": round(e50[end], 2),
            "ema200": round(e200[end], 2),
        },
        "trade_map": {
            "signal_close": entry_price,
            "earliest_entry": "next_trading_day_adjusted_open" if stage == "entry_ready" else None,
            "target_previous_high": target,
            "invalidation_second_bottom": invalidation,
            "estimated_reward_risk": reward_risk,
        },
        "audit": {"future_data_used": False, "completed_daily_bars_only": True, "confirmed_pivot_right_bars": 2},
    }
    if include_chart:
        result["chart"] = _favorite_chart(rows)
    return result


def _local_double_bottoms(rows, atr_values, low_pivots, window=260):
    """Return compact, confirmed W-bottom candidates for the V2 sequence."""
    end = len(rows) - 1
    lows = [index for index in low_pivots if index >= end - window][-30:]
    candidates = []
    for first, second in itertools.combinations(lows, 2):
        separation = second - first
        if not 5 <= separation <= 40:
            continue
        first_price, second_price = rows[first]["low"], rows[second]["low"]
        midpoint = (first_price + second_price) / 2
        tolerance = max(midpoint * 0.08, atr_values[second] * 1.25)
        if abs(first_price - second_price) > tolerance:
            continue
        rebound_high = max(row["high"] for row in rows[first + 1 : second])
        if rebound_high - max(first_price, second_price) < atr_values[second]:
            continue
        invalidation = min(first_price, second_price) - atr_values[second] * 0.5
        candidates.append(
            {
                "first_index": first,
                "second_index": second,
                "first_date": rows[first]["date"],
                "second_date": rows[second]["date"],
                "first_price": round(first_price, 2),
                "second_price": round(second_price, 2),
                "separation_sessions": separation,
                "spread_pct": round(abs(first_price - second_price) / midpoint * 100, 2),
                "neckline": round(rebound_high, 2),
                "invalidation": round(invalidation, 2),
                "invalidated": any(row["close"] < invalidation for row in rows[second + 1 :]),
            }
        )
    return candidates


def _bull_crosses(line, signal, start, stop):
    return [
        index
        for index in range(max(1, start), min(len(line) - 1, stop) + 1)
        if line[index] > signal[index] and line[index - 1] <= signal[index - 1]
    ]


def _bearish_risk_gate(rows, atr_values, e20, e50, high_pivots):
    """Point-in-time veto for unresolved sell pressure or top exhaustion.

    This intentionally reports evidence rather than assigning a score.  It is
    narrow enough to keep a single ordinary pullback candle from blocking a
    setup, while preserving the TTD/AEVA failure modes for review.
    """
    end = len(rows) - 1
    start = max(1, end - 50)
    pressure = []
    for index in range(start, end + 1):
        row = rows[index]
        candle_range = max(row["high"] - row["low"], 1e-9)
        body = row["open"] - row["close"]
        close_location = (row["close"] - row["low"]) / candle_range
        if body <= 0 or body < atr_values[index] * 0.75 or body / candle_range < 0.6 or close_location > 0.3:
            continue
        previous = rows[index - 1]
        near_engulf = previous["close"] > previous["open"] and row["open"] >= min(previous["open"], previous["close"]) * 0.995 and row["close"] <= max(previous["open"], previous["close"]) * 1.005
        follow_through = index < end and rows[index + 1]["close"] < row["close"]
        pressure.append(
            {
                "index": index,
                "date": row["date"],
                "high": row["high"],
                "near_engulf": near_engulf,
                "follow_through": follow_through,
                "resolved": any(later["close"] > row["high"] and later["close"] > e50[j] for j, later in enumerate(rows[index + 1 :], start=index + 1)),
            }
        )
    unresolved = [item for item in pressure if not item["resolved"] and (item["near_engulf"] or item["follow_through"])]
    clusters = []
    for item in unresolved:
        if not clusters or item["index"] - clusters[-1][-1]["index"] >= 4:
            clusters.append([item])
        else:
            clusters[-1].append(item)

    recent_highs = [index for index in high_pivots if index >= end - 70][-10:]
    multi_top = None
    for first, second, third in itertools.combinations(recent_highs, 3):
        prices = [rows[index]["high"] for index in (first, second, third)]
        midpoint = sorted(prices)[1]
        if max(prices) - min(prices) > max(midpoint * 0.08, atr_values[third] * 1.5):
            continue
        first_pullback = min(row["low"] for row in rows[first + 1 : second + 1])
        second_pullback = min(row["low"] for row in rows[second + 1 : third + 1])
        if prices[0] - first_pullback < atr_values[second] or prices[1] - second_pullback < atr_values[third]:
            continue
        multi_top = {
            "dates": [rows[index]["date"] for index in (first, second, third)],
            "prices": [round(price, 2) for price in prices],
            "zone_low": round(min(prices), 2),
            "zone_high": round(max(prices), 2),
        }

    exhaustion = []
    for index in range(start, end):
        row, next_row = rows[index], rows[index + 1]
        candle_range = max(row["high"] - row["low"], 1e-9)
        body = abs(row["close"] - row["open"])
        upper_wick = row["high"] - max(row["open"], row["close"])
        next_range = max(next_row["high"] - next_row["low"], 1e-9)
        next_body = next_row["open"] - next_row["close"]
        if body / candle_range <= 0.12 and upper_wick / candle_range >= 0.45 and next_body > 0 and next_body / next_range >= 0.6:
            exhaustion.append({"doji_date": row["date"], "confirmation_date": next_row["date"]})

    weak_ema = e20[end] <= e50[end] or rows[end]["close"] < e50[end]
    pressure_blocked = len(clusters) >= 2 and weak_ema
    top_blocked = bool(multi_top and exhaustion and rows[end]["close"] < multi_top["zone_high"])
    reasons = []
    if pressure_blocked:
        reasons.append("两轮以上未修复空头压力且EMA仍弱")
    if top_blocked:
        reasons.append("多重顶部供给叠加顶部耗竭确认")
    return {
        "clear": not reasons,
        "blocked": bool(reasons),
        "reasons_zh": reasons,
        "unresolved_pressure_rounds": len(clusters),
        "pressure_events": [{k: item[k] for k in ("date", "near_engulf", "follow_through")} for cluster in clusters for item in cluster],
        "multi_top": multi_top,
        "top_exhaustion": exhaustion,
        "ema_weak": weak_ema,
    }


def _evaluate_sequence_v2(rows, legacy):
    end = len(rows) - 1
    closes = [row["close"] for row in rows]
    atr_values = _atr(rows)
    low_pivots = _confirmed_pivots(rows, "low", "low")
    high_pivots = _confirmed_pivots(rows, "high", "high")
    bottoms = _local_double_bottoms(rows, atr_values, low_pivots)
    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    macd_line, signal_line = macd(closes)

    foundations = []
    for bottom in bottoms:
        impulse = _find_impulse(rows, low_pivots, high_pivots, bottom["first_index"])
        macd_crosses = _bull_crosses(macd_line, signal_line, bottom["second_index"] - 5, bottom["second_index"] + 15)
        foundation_end = min(end, bottom["second_index"] + 30)
        foundation_rows = rows[: foundation_end + 1]
        foundation_high_pivots = [index for index in high_pivots if index <= foundation_end - 2]
        three_push = _find_three_push(foundation_rows, foundation_high_pivots, bottom)
        breakout_index = three_push.get("breakout_index") if three_push else None
        timely_breakout = breakout_index is not None and breakout_index <= bottom["second_index"] + 30
        ema_crosses = [
            index
            for index in range(max(1, bottom["second_index"]), min(end, bottom["second_index"] + 30) + 1)
            if e20[index] > e50[index] and e20[index - 1] <= e50[index - 1]
        ]
        hits = [bool(impulse), True, bool(timely_breakout), bool(macd_crosses and ema_crosses)]
        confirmation_index = max(macd_crosses[0], breakout_index, ema_crosses[0]) if all(hits) else None
        foundations.append(
            {
                "hits": hits,
                "confirmation_index": confirmation_index,
                "confirmation_date": rows[confirmation_index]["date"] if confirmation_index is not None else None,
                "bottom": bottom,
                "impulse": impulse,
                "macd_cross_index": macd_crosses[0] if macd_crosses else None,
                "ema_cross_index": ema_crosses[0] if ema_crosses else None,
                "three_push": three_push,
            }
        )

    sequences = []
    for foundation in foundations:
        confirmation_index = foundation["confirmation_index"]
        if confirmation_index is None:
            continue
        for second_bottom in bottoms:
            if second_bottom["first_index"] <= confirmation_index + 3:
                continue
            peak = max(row["high"] for row in rows[confirmation_index : second_bottom["second_index"] + 1])
            trough = min(second_bottom["first_price"], second_bottom["second_price"])
            drawdown_pct = (peak - trough) / peak * 100
            reset_threshold = min(5.0, atr_values[second_bottom["second_index"]] * 2 / peak * 100)
            macd_reset = any(macd_line[index] <= signal_line[index] for index in range(confirmation_index + 1, second_bottom["second_index"] + 1))
            reset = drawdown_pct >= reset_threshold and macd_reset
            breakout_crosses = [
                index
                for index in range(second_bottom["second_index"] + 1, min(end, second_bottom["second_index"] + 15) + 1)
                if rows[index]["close"] > second_bottom["neckline"] * 1.01 and rows[index - 1]["close"] <= second_bottom["neckline"] * 1.01
            ]
            macd_crosses = _bull_crosses(macd_line, signal_line, second_bottom["second_index"] - 5, second_bottom["second_index"] + 15)
            ema_strength = [
                index
                for index in range(max(5, second_bottom["second_index"]), min(end, second_bottom["second_index"] + 15) + 1)
                if rows[index]["close"] > e20[index]
                and rows[index]["close"] > e50[index]
                and e20[index] > e20[index - 1]
                and (e20[index] - e50[index]) > (e20[index - 1] - e50[index - 1])
            ]
            second_reacceleration = bool(breakout_crosses and macd_crosses and ema_strength)
            completion_index = max(breakout_crosses[0], macd_crosses[0], ema_strength[0]) if second_reacceleration else None
            sequences.append(
                {
                    "foundation": foundation,
                    "reset": reset,
                    "reset_drawdown_pct": round(drawdown_pct, 2),
                    "reset_threshold_pct": round(reset_threshold, 2),
                    "macd_reset": macd_reset,
                    "second_bottom": second_bottom,
                    "second_breakout_index": breakout_crosses[0] if breakout_crosses else None,
                    "second_macd_index": macd_crosses[0] if macd_crosses else None,
                    "ema_strength_index": ema_strength[0] if ema_strength else None,
                    "second_reacceleration": second_reacceleration,
                    "completion_index": completion_index,
                }
            )

    def sequence_rank(item):
        hits = sum(item["foundation"]["hits"]) + int(item["reset"]) + 1 + int(item["second_reacceleration"])
        complete = hits == 7
        completion_preference = -(item["completion_index"] or 10**9) if complete else item["completion_index"] or -1
        structurally_valid = not item["second_bottom"]["invalidated"]
        return (item["foundation"]["confirmation_index"] or -1, complete and structurally_valid, complete, hits, completion_preference, item["foundation"]["bottom"]["second_index"], item["second_bottom"]["second_index"], item["second_bottom"]["first_index"])

    sequence = max(sequences, key=sequence_rank) if sequences else None
    foundation = sequence["foundation"] if sequence else (max(foundations, key=lambda item: (sum(item["hits"]), item["confirmation_index"] or -1, item["bottom"]["second_index"])) if foundations else None)
    second_bottom = sequence["second_bottom"] if sequence else None
    foundation_hits = foundation["hits"] if foundation else [False, False, False, False]
    conditions = [
        {"id": "prior_advance_or_turn", "label": "前段上涨／日线转强背景", "hit": foundation_hits[0]},
        {"id": "first_bottom_structure", "label": "第一段局部双底／三底", "hit": foundation_hits[1]},
        {"id": "first_three_push_breakout", "label": "第一段三推收盘突破", "hit": foundation_hits[2]},
        {"id": "first_momentum_trend_turn", "label": "第一段MACD＋EMA趋势转变", "hit": foundation_hits[3]},
        {"id": "independent_reset", "label": "真实回调与动能重置", "hit": bool(sequence and sequence["reset"])},
        {"id": "second_bottom_or_retest", "label": "新的W底／回踩确认", "hit": bool(second_bottom)},
        {"id": "second_reacceleration", "label": "二次突破＋MACD＋EMA转强", "hit": bool(sequence and sequence["second_reacceleration"])},
    ]
    match_count = sum(item["hit"] for item in conditions)
    completion_index = sequence["completion_index"] if sequence else None
    alignment_start = second_bottom["second_index"] if second_bottom else (foundation["bottom"]["second_index"] if foundation else end)
    full_alignment_indexes = [
        index
        for index in range(max(1, alignment_start), end + 1)
        if e20[index] > e50[index] and e20[index - 1] <= e50[index - 1]
    ]
    full_alignment_index = full_alignment_indexes[0] if full_alignment_indexes else None
    risk_gate = _bearish_risk_gate(rows, atr_values, e20, e50, high_pivots)
    complete = match_count == len(conditions)
    invalidated = bool(second_bottom and second_bottom["invalidated"])
    bars_since_completion = end - completion_index if completion_index is not None else None
    if invalidated:
        stage = "invalidated"
    elif complete and risk_gate["blocked"]:
        stage = "risk_blocked"
    elif complete and bars_since_completion is not None and bars_since_completion <= 5:
        stage = "entry_ready"
    elif complete:
        stage = "launched"
    elif match_count >= 6:
        stage = "breakout_incomplete"
    elif match_count >= 5:
        stage = "waiting_breakout"
    elif match_count >= 2:
        stage = "bottom_confirmed"
    else:
        stage = "discovery"

    actions = {
        "entry_ready": "第一次确认、真实重置和第二次启动均已完成；列入人工复核，研究口径最早下一交易日开盘进入。",
        "risk_blocked": "正面时序已完成，但空头压力或顶部供给尚未修复；不进入可行动信号。",
        "launched": "二次启动已经离开最初确认窗口；继续跟踪，不作追高提示。",
        "breakout_incomplete": "第二段已经接近完成，但突破、MACD或EMA转强仍缺一项；只观察。",
        "waiting_breakout": "第一段已确认并出现真实重置，等待第二段完整收盘与动能确认。",
        "bottom_confirmed": "已经出现底部结构，但第一段趋势转变尚未完整；继续观察。",
        "discovery": "只命中少量早期阶段，暂不行动。",
        "invalidated": "新的底部结构已经被收盘破坏，本轮序列失效。",
    }
    impulse = foundation["impulse"] if foundation else None
    target = None
    if sequence:
        start = sequence["foundation"]["confirmation_index"]
        stop = sequence["second_bottom"]["first_index"]
        if stop > start:
            target = round(max(row["high"] for row in rows[start : stop + 1]), 2)
    entry_price = round(rows[completion_index]["close"], 2) if completion_index is not None else None
    invalidation = second_bottom["invalidation"] if second_bottom else None
    reward_risk = None
    if entry_price and invalidation and target and entry_price > invalidation and target > entry_price:
        reward_risk = round((target - entry_price) / (entry_price - invalidation), 2)
    return {
        "pattern_version": V2_PATTERN_VERSION,
        "experiment_id": V2_EXPERIMENT_ID,
        "stage": stage,
        "stage_zh": STAGE_ZH[stage],
        "match_count": match_count,
        "total_conditions": len(conditions),
        "match_pct": round(match_count / len(conditions) * 100),
        "conditions": conditions,
        "action_zh": actions[stage],
        "prior_advance": impulse,
        "double_bottom": second_bottom or (foundation["bottom"] if foundation else None),
        "second_bottom_macd": {
            "hit": bool(sequence and sequence["second_macd_index"] is not None),
            "cross_date": rows[sequence["second_macd_index"]]["date"] if sequence and sequence["second_macd_index"] is not None else None,
            "distance_from_second_bottom_sessions": sequence["second_macd_index"] - second_bottom["second_index"] if sequence and sequence["second_macd_index"] is not None and second_bottom else None,
        },
        "three_push": foundation["three_push"] if foundation else None,
        "ema_realign": {
            "hit": bool(sequence and sequence["ema_strength_index"] is not None),
            "cross_date": rows[full_alignment_index]["date"] if full_alignment_index is not None else None,
            "strength_date": rows[sequence["ema_strength_index"]]["date"] if sequence and sequence["ema_strength_index"] is not None else None,
            "full_alignment": e20[end] > e50[end],
            "ema20": round(e20[end], 2),
            "ema50": round(e50[end], 2),
            "ema200": round(e200[end], 2),
        },
        "sequence": {
            "first_confirmation_date": foundation["confirmation_date"] if foundation else None,
            "first_bottom": foundation["bottom"] if foundation else None,
            "first_macd_date": rows[foundation["macd_cross_index"]]["date"] if foundation and foundation["macd_cross_index"] is not None else None,
            "first_ema_cross_date": rows[foundation["ema_cross_index"]]["date"] if foundation and foundation["ema_cross_index"] is not None else None,
            "reset_drawdown_pct": sequence["reset_drawdown_pct"] if sequence else None,
            "macd_reset": bool(sequence and sequence["macd_reset"]),
            "second_bottom": second_bottom,
            "second_breakout_date": rows[sequence["second_breakout_index"]]["date"] if sequence and sequence["second_breakout_index"] is not None else None,
            "second_macd_date": rows[sequence["second_macd_index"]]["date"] if sequence and sequence["second_macd_index"] is not None else None,
            "ema_strength_date": rows[sequence["ema_strength_index"]]["date"] if sequence and sequence["ema_strength_index"] is not None else None,
            "full_alignment_date": rows[full_alignment_index]["date"] if full_alignment_index is not None else None,
            "completion_date": rows[completion_index]["date"] if completion_index is not None else None,
        },
        "risk_gate": risk_gate,
        "trade_map": {
            "signal_close": entry_price,
            "earliest_entry": "next_trading_day_adjusted_open" if stage == "entry_ready" else None,
            "target_previous_high": target,
            "invalidation_second_bottom": invalidation,
            "estimated_reward_risk": reward_risk,
        },
        "legacy_v1": {
            "pattern_version": legacy.get("pattern_version"),
            "stage": legacy.get("stage"),
            "match_count": legacy.get("match_count"),
            "total_conditions": legacy.get("total_conditions"),
        },
    }


def _evaluate_simple_v3(rows, legacy_v1, legacy_v2):
    """Evaluate the four-condition shape the user wants to review first."""
    end = len(rows) - 1
    closes = [row["close"] for row in rows]
    atr_values = _atr(rows)
    low_pivots = _confirmed_pivots(rows, "low", "low")
    high_pivots = _confirmed_pivots(rows, "high", "high")
    bottom = _find_double_bottom(rows, atr_values, low_pivots)
    impulse = _find_impulse(rows, low_pivots, high_pivots, bottom["first_index"]) if bottom else None
    three_push = _find_three_push(rows, high_pivots, bottom)
    breakout = bool(three_push and three_push.get("breakout_index") is not None)

    # Measure the pullback before the first bottom. Later recovery bars cannot
    # manufacture this condition retroactively.
    prior_high = None
    pullback_pct = None
    if bottom:
        start = max(0, bottom["first_index"] - 60)
        prior_high = max((row["high"] for row in rows[start : bottom["first_index"] + 1]), default=None)
        lower_bottom = min(bottom["first_price"], bottom["second_price"])
        if prior_high and prior_high > 0:
            pullback_pct = (prior_high - lower_bottom) / prior_high * 100
    objective_pullback = pullback_pct is not None and pullback_pct >= 5

    retracement_pct = None
    golden_pocket = False
    if impulse and bottom and impulse["high"] > impulse["low"]:
        retracement_pct = (impulse["high"] - min(bottom["first_price"], bottom["second_price"])) / (impulse["high"] - impulse["low"]) * 100
        golden_pocket = 50 <= retracement_pct <= 70

    e20, e50, e200 = ema(closes, 20), ema(closes, 50), ema(closes, 200)
    ema_matches = []
    if bottom:
        for bottom_name, index in (("第一底", bottom["first_index"]), ("第二底", bottom["second_index"])):
            for period, values in ((20, e20), (50, e50), (200, e200)):
                value = values[index]
                if not value:
                    continue
                distance = abs(rows[index]["low"] / value - 1) * 100
                if distance <= 6:
                    ema_matches.append({"bottom": bottom_name, "bottom_date": rows[index]["date"], "ema": f"EMA{period}", "ema_value": round(value, 2), "distance_pct": round(distance, 2)})
    location_support = golden_pocket or bool(ema_matches)
    conditions = [
        {"id": "objective_pullback", "label": "客观回调至少5%", "hit": objective_pullback},
        {"id": "broad_double_bottom", "label": "宽口径双底", "hit": bool(bottom)},
        {"id": "three_push_close_breakout", "label": "三推趋势线收盘突破", "hit": breakout},
        {"id": "golden_pocket_or_ema", "label": "Golden Pocket／EMA承接", "hit": location_support},
    ]
    match_count = sum(item["hit"] for item in conditions)
    complete = match_count == len(conditions)
    invalidated = bool(bottom and bottom.get("invalidated"))
    bars_since_breakout = three_push.get("bars_since_breakout") if breakout else None
    risk_gate = _bearish_risk_gate(rows, atr_values, e20, e50, high_pivots)
    if invalidated:
        stage = "invalidated"
    elif complete and risk_gate["blocked"]:
        stage = "risk_blocked"
    elif complete and bars_since_breakout is not None and bars_since_breakout <= 5:
        stage = "entry_ready"
    elif complete:
        stage = "launched"
    elif match_count >= 3:
        stage = "waiting_breakout" if not breakout else "breakout_incomplete"
    elif bottom:
        stage = "bottom_confirmed"
    elif objective_pullback:
        stage = "pullback_forming"
    else:
        stage = "discovery"
    actions = {
        "entry_ready": "四项简化形态已完成且风险闸门清除；列入人工复核，研究口径最早下一交易日开盘进入。",
        "risk_blocked": "四项形态已完成，但空头压力或顶部供给仍在；不建立可行动信号。",
        "launched": "四项形态曾完成，但已离开最初五日突破窗口；继续跟踪，不作追高提示。",
        "waiting_breakout": "回调、双底和位置已接近完成，等待三推趋势线的完整收盘突破。",
        "breakout_incomplete": "价格已突破，但回调、双底或支撑位置仍缺一项；只观察。",
        "bottom_confirmed": "已看到双底，但四项形态尚未齐全。",
        "pullback_forming": "已经发生客观回调，等待双底、三推突破和位置承接。",
        "discovery": "只命中少量早期形态，暂不行动。",
        "invalidated": "收盘已破坏双底失效位，本轮形态结束。",
    }
    signal_close = three_push.get("breakout_close") if breakout else None
    target = round(prior_high, 2) if prior_high else None
    invalidation = bottom.get("invalidation") if bottom else None
    reward_risk = None
    if signal_close and invalidation and target and signal_close > invalidation and target > signal_close:
        reward_risk = round((target - signal_close) / (signal_close - invalidation), 2)
    return {
        "available": True,
        "pattern_version": PATTERN_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "stage": stage,
        "stage_zh": STAGE_ZH[stage],
        "match_count": match_count,
        "total_conditions": len(conditions),
        "match_pct": round(match_count / len(conditions) * 100),
        "conditions": conditions,
        "action_zh": actions[stage],
        "prior_advance": impulse,
        "pullback": {"objective_pullback_pct": round(pullback_pct, 2) if pullback_pct is not None else None, "prior_60_session_high": round(prior_high, 2) if prior_high else None, "retracement_pct": round(retracement_pct, 2) if retracement_pct is not None else None, "golden_pocket": golden_pocket, "ema_support": bool(ema_matches), "ema_matches": ema_matches},
        "double_bottom": bottom,
        "three_push": three_push,
        "ema_realign": {"ema20": round(e20[end], 2), "ema50": round(e50[end], 2), "ema200": round(e200[end], 2), "full_alignment": e20[end] > e50[end]},
        "sequence": {"double_bottom_first_date": bottom.get("first_date") if bottom else None, "double_bottom_second_date": bottom.get("second_date") if bottom else None, "breakout_date": three_push.get("breakout_date") if three_push else None, "completion_date": three_push.get("breakout_date") if complete and three_push else None},
        "risk_gate": risk_gate,
        "trade_map": {"signal_close": signal_close, "earliest_entry": "next_trading_day_adjusted_open" if stage == "entry_ready" else None, "target_previous_high": target, "invalidation_second_bottom": invalidation, "estimated_reward_risk": reward_risk},
        "legacy_v1": {"pattern_version": legacy_v1.get("pattern_version"), "stage": legacy_v1.get("stage"), "match_count": legacy_v1.get("match_count"), "total_conditions": legacy_v1.get("total_conditions")},
        "legacy_v2": {"pattern_version": legacy_v2.get("pattern_version"), "stage": legacy_v2.get("stage"), "match_count": legacy_v2.get("match_count"), "total_conditions": legacy_v2.get("total_conditions"), "sequence": legacy_v2.get("sequence")},
        "audit": {"future_data_used": False, "completed_daily_bars_only": True, "confirmed_pivot_right_bars": 2, "legacy_v1_preserved": True, "legacy_v2_preserved": True, "known_cases_excluded_from_effectiveness": ["ADBE", "BABA", "TTD", "AEVA"]},
    }


def evaluate(rows, include_chart=False):
    """Evaluate simple V3 while retaining immutable V1 and V2 comparisons."""
    if len(rows) < 120:
        return {"available": False, "stage": "unavailable", "stage_zh": STAGE_ZH["unavailable"], "match_count": 0, "total_conditions": 4, "reason": "V3至少需要120个完整日K", "pattern_version": PATTERN_VERSION, "experiment_id": EXPERIMENT_ID}
    legacy_v1 = _evaluate_v1(rows, include_chart=include_chart)
    legacy_v2 = _evaluate_sequence_v2(rows, legacy_v1)
    result = _evaluate_simple_v3(rows, legacy_v1, legacy_v2)
    if include_chart:
        result["chart"] = legacy_v1.get("chart") or _favorite_chart(rows)
    return result


def should_publish(pattern, symbol=None):
    return bool(pattern.get("available") and (pattern.get("stage") not in {"discovery", "invalidated"} or symbol in REFERENCE_CASES))


def _mechanism_profile(pattern):
    conditions = pattern.get("conditions") or []
    completed = [{"id": item.get("id"), "label": item.get("label")} for item in conditions if item.get("hit")]
    missing = [{"id": item.get("id"), "label": item.get("label")} for item in conditions if not item.get("hit")]
    risk_gate = pattern.get("risk_gate") or {}
    stage = pattern.get("stage")
    match_count = int(pattern.get("match_count") or 0)
    if stage == "entry_ready":
        status = "formal_signal"
    elif match_count >= max(1, int(pattern.get("total_conditions") or 4) - 1) and stage not in {"launched", "target_reached", "invalidated"}:
        status = "blocked_near_match" if risk_gate.get("blocked") else "near_match"
    else:
        status = "early_observation"
    return {
        "status": status,
        "completed": completed,
        "missing": missing,
        "risk_reasons_zh": list(risk_gate.get("reasons_zh") or []),
        "examples_are_templates": False,
    }


def build_report(candidates, as_of, gate=None):
    rows = []
    references = []
    for candidate in candidates:
        pattern = candidate.get("favorite_pattern") or {}
        row = {"symbol": candidate["symbol"], "price": candidate["price"], "dollar_volume": candidate["dollar_volume"], **pattern}
        row["mechanism_profile"] = _mechanism_profile(pattern)
        if should_publish(pattern, candidate["symbol"]) and pattern.get("stage") != "invalidated":
            rows.append(row)
        if candidate["symbol"] in REFERENCE_CASES:
            references.append({**row, "reference_note_zh": REFERENCE_CASES[candidate["symbol"]]})
    rows.sort(key=lambda item: (STAGE_ORDER.get(item["stage"], -1), item["match_count"], item["dollar_volume"], item["symbol"]), reverse=True)
    entry_ready_candidates = [item for item in rows if item.get("stage") == "entry_ready"][:24]
    near_match_rows = [
        item
        for item in rows
        if item.get("mechanism_profile", {}).get("status") in {"near_match", "blocked_near_match"}
    ]
    clear_near_matches = [item for item in near_match_rows if item["mechanism_profile"]["status"] == "near_match"]
    blocked_near_matches = [item for item in near_match_rows if item["mechanism_profile"]["status"] == "blocked_near_match"]
    near_matches = clear_near_matches[:12] + blocked_near_matches[:6]
    watch_counts = Counter(item["stage"] for item in rows)
    reference_map = {item["symbol"]: item for item in references}
    for symbol, note in REFERENCE_CASES.items():
        if symbol not in reference_map:
            reference_map[symbol] = {"symbol": symbol, "available": False, "stage": "unavailable", "stage_zh": STAGE_ZH["unavailable"], "reference_note_zh": note, "reason": "当前活跃缓存中没有可用同日数据"}
    report = {
        "pattern_version": PATTERN_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "generalization_version": GENERALIZATION_VERSION,
        "as_of": as_of,
        "production_scoring_changed": False,
        "primary_ranking_changed": False,
        "summary": {
            "watchlist": len(rows),
            "entry_ready": watch_counts["entry_ready"],
            "risk_blocked": watch_counts["risk_blocked"],
            "waiting_breakout": watch_counts["waiting_breakout"],
            "breakout_incomplete": watch_counts["breakout_incomplete"],
            "forming": watch_counts["pullback_forming"] + watch_counts["bottom_confirmed"],
            "launched": watch_counts["launched"],
            "near_match": sum(item["mechanism_profile"]["status"] == "near_match" for item in near_match_rows),
            "blocked_near_match": sum(item["mechanism_profile"]["status"] == "blocked_near_match" for item in near_match_rows),
        },
        "stage_order": ["pullback_forming", "bottom_confirmed", "waiting_breakout", "breakout_incomplete", "risk_blocked", "entry_ready", "launched", "target_reached"],
        "stage_labels": STAGE_ZH,
        # The internal ledger receives every publishable gated row. The public
        # page removes this field and uses only the bounded lists below.
        "candidates": rows,
        "entry_ready_candidates": entry_ready_candidates,
        "near_matches": near_matches,
        "reference_cases": [reference_map[symbol] for symbol in REFERENCE_CASES],
        "generalization_policy": {
            "version": GENERALIZATION_VERSION,
            "examples_are_templates": False,
            "mechanism_roles_zh": ["回调", "双底", "三推突破", "Golden Pocket／EMA承接", "供给风险"],
            "near_match_minimum_conditions": 3,
            "near_matches_are_signals": False,
            "legacy_only_cases": LEGACY_ONLY_CASES,
            "teaching_cases": ["ADBE", "BABA"],
            "risk_regression_cases": ["TTD", "AEVA"],
            "review_loop": ["漏检赢家", "误收输家", "门槛边界"],
        },
        "forward_tracking": {
            "starts_after_deployment": True,
            "ledger_source": "favorite_pattern_tracker",
            "recorded_stage": "entry_ready",
            "entry": "next_trading_day_adjusted_open",
            "minimum_conclusion_sample": 100,
            "minimum_months": 6,
            "minimum_market_states": 3,
        },
        "warning_zh": "4/4只表示回调、双底、三推收盘突破和Golden Pocket／EMA承接齐全；风险闸门仍可否决。颗数用于人工复核，不是胜率或自动买入。",
    }
    if gate is not None:
        report["gate"] = gate
    return report


def build_gated_report(snapshot, symbol_rows, as_of):
    """Deep-check the canonical MACD pool without another market-wide pass."""
    if snapshot.get("as_of") != as_of or snapshot.get("future_data_used") is not False:
        raise ValueError("Favorite-pattern gate must be the same safe completed session")
    source_rows = snapshot.get("symbols", [])
    source_symbols = [row.get("symbol") for row in source_rows]
    if None in source_symbols or len(source_symbols) != len(set(source_symbols)):
        raise ValueError("Favorite-pattern gate contains missing or duplicate symbols")
    if snapshot.get("triggered_count") != len(source_symbols):
        raise ValueError("Favorite-pattern gate count does not match its symbols")

    candidates = []
    for source in source_rows:
        trigger = source.get("trigger", {})
        if trigger.get("exact_completed_cross") is not True or trigger.get("date") != as_of:
            raise ValueError("Favorite-pattern received a non-MACD-gated symbol")
        rows = sorted(
            (row for row in symbol_rows.get(source["symbol"], []) if row.get("date") <= as_of),
            key=lambda row: row["date"],
        )
        if not rows or rows[-1].get("date") != as_of:
            raise ValueError(f"Favorite-pattern rows are missing the gate day for {source['symbol']}")
        pattern = evaluate(rows)
        if should_publish(pattern, source["symbol"]):
            # Charting is presentation evidence, so attach it without running
            # the full V1/V2/V3 detector a second time.
            pattern["chart"] = _favorite_chart(rows)
        candidates.append(
            {
                "symbol": source["symbol"],
                "price": source["price"],
                "dollar_volume": source["dollar_volume"],
                "favorite_pattern": pattern,
            }
        )

    gate = {
        "source": "daily-factor-snapshot",
        "source_snapshot_version": snapshot.get("snapshot_mode_version"),
        "factor_id": snapshot.get("trigger_policy", {}).get("factor_id"),
        "event": "exact_completed_daily_bull_cross",
        "source_candidate_count": len(source_symbols),
        "deep_checked_count": len(candidates),
        "deep_checked_symbols": source_symbols,
        "selection_order": "completed_session_dollar_volume_desc",
        "full_market_deep_scan": False,
        "future_data_used": False,
    }
    return build_report(candidates, as_of, gate=gate)
