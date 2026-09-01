"""Behavior-equivalent M03 baseline checks, separate from shadow research facts."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from services.scanner.macd_factor_backtest import ema
from services.scanner.technical import macd

MIN_HISTORY_SESSIONS = 420
MIN_CLOSE = 5.0
MIN_DOLLAR_VOLUME = 10_000_000.0


def exact_daily_macd_bull_cross(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Recognize only a cross on the latest completed daily bar."""

    if len(rows) < 2:
        return False
    line, signal = macd([row["close"] for row in rows])
    return line[-1] > signal[-1] and line[-2] <= signal[-2]


def legacy_long_trend_equivalence(rows: Sequence[Mapping[str, Any]]) -> bool:
    """Preserve the existing EMA200 floor and sixty-session slope semantics."""

    end = len(rows) - 1
    if end < 260:
        return False
    closes = [row["close"] for row in rows]
    average = ema(closes, 200)
    return closes[end] >= average[end] * 0.90 and average[end] >= average[end - 60] * 0.97


def creation_boundary_reason(rows: Sequence[Mapping[str, Any]], *, as_of: str) -> str | None:
    """Return the first frozen non-event reason, or None at event boundary."""

    if not rows or rows[-1]["date"] != as_of:
        return "data_unavailable"
    if len(rows) < MIN_HISTORY_SESSIONS:
        return "insufficient_history"
    current = rows[-1]
    if current["close"] < MIN_CLOSE:
        return "below_price_floor"
    if current["close"] * current["volume"] < MIN_DOLLAR_VOLUME:
        return "below_liquidity_floor"
    if not exact_daily_macd_bull_cross(rows):
        return "no_exact_daily_macd_cross"
    return None

