"""Point-in-time tracker for the user's preferred daily reversal setup.

This is deliberately a setup state machine, not a production factor or score.
All pivots require two completed bars of right-side confirmation.
"""
from __future__ import annotations

import itertools
from collections import Counter

from .technical import ema, macd


PATTERN_VERSION = "favorite-pattern-v1.0.0"
EXPERIMENT_ID = "favorite-pattern-tracker-v1.0.0-2026-08-29"
REFERENCE_CASES = {
    "BABA": "定义案例：前段上涨后深回调，在Golden Pocket／EMA200附近形成宽双底，再由二底MACD、三推突破和EMA重排共振。",
    "PG": "保留观察案例：即使当前成绩一般也不删除，用来检查规则是否只偏爱最好看的走势。",
}
STAGE_ORDER = {
    "entry_ready": 7,
    "launched": 6,
    "target_reached": 5,
    "waiting_breakout": 4,
    "bottom_confirmed": 3,
    "pullback_forming": 2,
    "discovery": 1,
    "invalidated": 0,
    "unavailable": -1,
}
STAGE_ZH = {
    "entry_ready": "入场就绪",
    "launched": "突破后跟踪",
    "target_reached": "已到前高目标",
    "waiting_breakout": "等待突破",
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


def evaluate(rows, include_chart=False):
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
    if invalidated:
        stage = "invalidated"
    elif target_reached:
        stage = "target_reached"
    elif breakout and ema_realigned and macd_cross_index is not None and bars_since_breakout is not None and bars_since_breakout <= 5:
        stage = "entry_ready"
    elif breakout and current_above_breakout and bars_since_breakout is not None and bars_since_breakout <= 60:
        stage = "launched"
    elif bottom and three_push and macd_cross_index is not None:
        stage = "waiting_breakout"
    elif bottom:
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
        "bottom_confirmed": "双底已确认，但三推／MACD／均线证据尚未齐，不急着买。",
        "pullback_forming": "回调位置接近模板，等待第二底和动能确认。",
        "discovery": "只命中少量早期条件，暂不行动。",
        "invalidated": "价格已经收盘跌破二底失效位，本轮形态结束。",
    }[stage]
    result = {
        "available": True,
        "pattern_version": PATTERN_VERSION,
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


def should_publish(pattern, symbol=None):
    return bool(pattern.get("available") and (pattern.get("match_count", 0) >= 4 or symbol in REFERENCE_CASES))


def build_report(candidates, as_of):
    rows = []
    references = []
    for candidate in candidates:
        pattern = candidate.get("favorite_pattern") or {}
        row = {"symbol": candidate["symbol"], "price": candidate["price"], "dollar_volume": candidate["dollar_volume"], **pattern}
        if should_publish(pattern, candidate["symbol"]) and pattern.get("stage") != "invalidated":
            rows.append(row)
        if candidate["symbol"] in REFERENCE_CASES:
            references.append({**row, "reference_note_zh": REFERENCE_CASES[candidate["symbol"]]})
    rows.sort(key=lambda item: (STAGE_ORDER.get(item["stage"], -1), item["match_count"], item["dollar_volume"], item["symbol"]), reverse=True)
    selected = rows[:24]
    selected_symbols = {item["symbol"] for item in selected}
    for reference in references:
        if reference["symbol"] not in selected_symbols:
            selected.append(reference)
            selected_symbols.add(reference["symbol"])
    watch_counts = Counter(item["stage"] for item in rows)
    reference_map = {item["symbol"]: item for item in references}
    for symbol, note in REFERENCE_CASES.items():
        if symbol not in reference_map:
            reference_map[symbol] = {"symbol": symbol, "available": False, "stage": "unavailable", "stage_zh": STAGE_ZH["unavailable"], "reference_note_zh": note, "reason": "当前活跃缓存中没有可用同日数据"}
    return {
        "pattern_version": PATTERN_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "as_of": as_of,
        "production_scoring_changed": False,
        "primary_ranking_changed": False,
        "summary": {
            "watchlist": len(rows),
            "entry_ready": watch_counts["entry_ready"],
            "waiting_breakout": watch_counts["waiting_breakout"],
            "forming": watch_counts["pullback_forming"] + watch_counts["bottom_confirmed"],
            "launched": watch_counts["launched"],
        },
        "stage_order": ["pullback_forming", "bottom_confirmed", "waiting_breakout", "entry_ready", "launched", "target_reached"],
        "stage_labels": STAGE_ZH,
        "candidates": selected,
        "reference_cases": [reference_map[symbol] for symbol in REFERENCE_CASES],
        "forward_tracking": {
            "starts_after_deployment": True,
            "ledger_source": "favorite_pattern_tracker",
            "recorded_stage": "entry_ready",
            "entry": "next_trading_day_adjusted_open",
            "minimum_conclusion_sample": 100,
            "minimum_months": 6,
            "minimum_market_states": 3,
        },
        "warning_zh": "7项匹配度只表示形态完成度，不是上涨概率；形成中和等待突破都不是买入信号。",
    }
