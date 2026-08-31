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
ADJUSTED_REQUIRED_FIELDS = {"date", "open", "high", "low", "close", "volume"}


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


def validate_adjusted_rows(
    adjusted_rows: Iterable[Mapping[str, Any]],
) -> tuple[dict[str, Any], ...]:
    """Validate and detach adjusted OHLCV handed to a consumer.

    Repository ingestion validates the full raw cache.  This validator has a
    narrower trust boundary: it validates only the already selected point-in-
    time rows and copies their six contract fields.  A bad future business row
    therefore cannot invalidate an earlier safe read.
    """

    if isinstance(adjusted_rows, (str, bytes, Mapping)):
        raise ContractError("adjusted market rows must be an iterable of objects")
    rows: list[dict[str, Any]] = []
    previous: str | None = None
    for index, raw in enumerate(adjusted_rows):
        if not isinstance(raw, Mapping):
            raise ContractError(f"adjusted row {index} must be an object")
        missing = sorted(ADJUSTED_REQUIRED_FIELDS - raw.keys())
        if missing:
            raise ContractError(f"adjusted row {index} missing fields: {', '.join(missing)}")
        day = _canonical_date(raw["date"])
        if previous is not None and day <= previous:
            reason = "duplicate" if day == previous else "unordered"
            raise ContractError(f"adjusted market dates are {reason}: {day}")
        open_price = _number(raw["open"], "open")
        high = _number(raw["high"], "high")
        low = _number(raw["low"], "low")
        close = _number(raw["close"], "close")
        volume = raw["volume"]
        if isinstance(volume, bool) or not isinstance(volume, int) or volume < 0:
            raise ContractError("volume must be a non-negative integer count")
        if low > min(open_price, close) or high < max(open_price, close) or low > high:
            raise ContractError(f"adjusted OHLC relationship is impossible on {day}")
        rows.append({
            "date": day,
            "open": raw["open"],
            "high": raw["high"],
            "low": raw["low"],
            "close": raw["close"],
            "volume": volume,
        })
        previous = day
    return tuple(rows)


def _raw_rows_through_as_of(
    raw_rows: Iterable[Mapping[str, Any]], *, as_of: str
) -> tuple[Mapping[str, Any], ...]:
    """Split history safely without inspecting future OHLCV values.

    Dates for the complete cache must remain canonical, unique and ordered so
    the split itself is trustworthy.  Business fields after ``as_of`` are not
    validated here: a supplier's later bad bar must not change an earlier
    point-in-time view.  Full-cache validation still belongs at repository
    ingestion before any data is persisted.
    """

    if isinstance(raw_rows, (str, bytes, Mapping)):
        raise ContractError("raw market rows must be an iterable of objects")
    selected: list[Mapping[str, Any]] = []
    previous: str | None = None
    for index, raw in enumerate(raw_rows):
        if not isinstance(raw, Mapping):
            raise ContractError(f"raw row {index} must be an object")
        day = _canonical_date(raw.get("date"))
        if previous is not None and day <= previous:
            reason = "duplicate" if day == previous else "unordered"
            raise ContractError(f"raw market dates are {reason}: {day}")
        if day <= as_of:
            selected.append(raw)
        previous = day
    return tuple(selected)


def adjusted_point_in_time_rows(
    raw_rows: Iterable[Mapping[str, Any]], *, as_of: str
) -> tuple[dict[str, Any], ...]:
    """Return adjusted rows through ``as_of``; there is intentionally no default."""

    as_of = _canonical_date(as_of, "as_of")
    selected = _raw_rows_through_as_of(raw_rows, as_of=as_of)
    validated = validate_raw_rows(selected)
    adjusted: list[dict[str, Any]] = []
    for row in validated:
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
