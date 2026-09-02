"""One deterministic Decimal boundary shared by M10-C creation and validation."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN
from typing import Any

from services.contracts.validation import ContractError


METRIC_QUANTUM = Decimal("0.0000000001")


def decimal_metric(value: Any, field: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise ContractError(f"{field} must be a finite number")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ContractError(f"{field} must be a finite number") from exc
    if not number.is_finite():
        raise ContractError(f"{field} must be a finite number")
    return number


def quantized_metric(value: Decimal) -> float:
    try:
        normalized = value.quantize(METRIC_QUANTUM, rounding=ROUND_HALF_EVEN)
    except InvalidOperation as exc:
        raise ContractError("M10-C metric cannot be represented finitely") from exc
    if not normalized.is_finite():
        raise ContractError("M10-C metric must be finite")
    if normalized == 0:
        normalized = Decimal("0")
    return float(normalized)


def quantized_ratio(numerator: int | Decimal, denominator: int | Decimal) -> float:
    denominator_value = Decimal(denominator)
    if denominator_value == 0:
        raise ContractError("M10-C metric denominator cannot be zero")
    return quantized_metric(Decimal(numerator) / denominator_value)


def profit_factor_semantics(
    gross_profit: Any, gross_loss_abs: Any
) -> tuple[float | None, str | None]:
    """Return the sole approved PF value and its explicit exceptional reason."""

    profit = decimal_metric(gross_profit, "gross_profit")
    loss = decimal_metric(gross_loss_abs, "gross_loss_abs")
    if profit < 0 or loss < 0:
        raise ContractError("gross profit and loss magnitude cannot be negative")
    if loss == 0 and profit > 0:
        return None, "unbounded_no_losses"
    if loss == 0 and profit == 0:
        return None, "undefined_zero_profit_and_loss"
    if profit == 0:
        return 0.0, None
    return quantized_metric(profit / loss), None


__all__ = [
    "METRIC_QUANTUM", "decimal_metric", "profit_factor_semantics",
    "quantized_metric", "quantized_ratio",
]
