"""Pure M02 validation, adjustment and point-in-time slicing.

The caller must inject rows and an explicit ``as_of``.  This module knows
nothing about EODHD credentials, Git, cache paths, clocks, scanners or
backtests.  Valid provider rows use the same adjustment formula as the legacy
scanner: ``ratio = adjusted_close / close`` and every OHLC value is multiplied
by that ratio.
"""

from __future__ import annotations

from datetime import date
import math
from typing import Any, Iterable, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError


ADJUSTMENT_POLICY = {
    "version": "eodhd-adjusted-ratio-1.0.0",
    "formula": "ratio=adjusted_close/close; adjusted_ohlc=raw_ohlc*ratio",
}
REQUIRED_FIELDS = {"date", "open", "high", "low", "close", "adjusted_close", "volume"}


def _canonical_date(value: Any, field: str = "date") -> str:
    if not isinstance(value, str):
        raise ContractError(f"{field} must be YYYY-MM-DD")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ContractError(f"{field} must be YYYY-MM-DD") from exc
    if parsed.isoformat() != value:
        raise ContractError(f"{field} must be canonical YYYY-MM-DD")
    return value


def _number(value: Any, field: str, *, positive: bool = True) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContractError(f"{field} must be numeric")
    number = float(value)
    if not math.isfinite(number) or (number <= 0 if positive else number < 0):
        boundary = "positive" if positive else "non-negative"
        raise ContractError(f"{field} must be finite and {boundary}")
    return number


def validate_raw_rows(raw_rows: Iterable[Mapping[str, Any]]) -> tuple[dict[str, Any], ...]:
    """Fail closed on missing, duplicate, unordered or impossible raw bars."""

    if isinstance(raw_rows, (str, bytes, Mapping)):
        raise ContractError("raw market rows must be an iterable of objects")
    rows: list[dict[str, Any]] = []
    previous: str | None = None
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping):
            raise ContractError(f"raw row {index} must be an object")
        missing = sorted(REQUIRED_FIELDS - raw.keys())
        if missing:
            raise ContractError(f"raw row {index} missing fields: {', '.join(missing)}")
        day = _canonical_date(raw["date"])
        if previous is not None and day <= previous:
            reason = "duplicate" if day == previous else "unordered"
            raise ContractError(f"raw market dates are {reason}: {day}")
        open_price = _number(raw["open"], "open")
        high = _number(raw["high"], "high")
        low = _number(raw["low"], "low")
        close = _number(raw["close"], "close")
        adjusted_close = _number(raw["adjusted_close"], "adjusted_close")
        volume = _number(raw["volume"], "volume", positive=False)
        if not volume.is_integer():
            raise ContractError("volume must be an integer count")
        if low > min(open_price, close) or high < max(open_price, close) or low > high:
            raise ContractError(f"raw OHLC relationship is impossible on {day}")
        rows.append({
            "date": day,
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["close"],
            "adjusted_close": raw["adjusted_close"],
            "volume": int(volume),
        })
        previous = day
    return tuple(rows)


def adjusted_point_in_time_rows(
    raw_rows: Iterable[Mapping[str, Any]], *, as_of: str
) -> tuple[dict[str, Any], ...]:
    """Return adjusted rows through ``as_of``; there is intentionally no default."""

    as_of = _canonical_date(as_of, "as_of")
    validated = validate_raw_rows(raw_rows)
    adjusted: list[dict[str, Any]] = []
    for row in validated:
        if row["date"] > as_of:
            continue
        ratio = row["adjusted_close"] / row["close"]
        adjusted.append({
            "date": row["date"],
            "open": row["open"] * ratio,
            "high": row["high"] * ratio,
            "low": row["low"] * ratio,
            "close": row["adjusted_close"],
            "volume": int(row["volume"]),
        })
    return tuple(adjusted)


def bars_fingerprint(rows: Iterable[Mapping[str, Any]]) -> str:
    """Fingerprint a supplied point-in-time view without reading any external state."""

    return canonical_fingerprint(list(rows))
