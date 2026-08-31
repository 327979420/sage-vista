"""Single shadow consumer bridge shared by daily and backtest callers.

Nothing in this module changes a production default.  Callers must explicitly
choose formal or legacy evidence and inject point-in-time repository reads.
The writable repository location is derived from this repository itself; it is
not a CLI/environment/download capability.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping

from services.contracts.market_data import (
    canonical_fingerprint,
    market_data_snapshot_id,
    require_date,
    select_universe_snapshot,
    validate_market_data_snapshot,
)
from services.contracts.validation import ContractError

from .normalization import ADJUSTMENT_POLICY, bars_fingerprint, validate_adjusted_rows
from .repository import MarketDataRepository, MarketDataSource, RepositoryRead


_WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
_SHADOW_REPOSITORY_RELATIVE = Path("work/m02-shadow/market-data")
CONSUMERS = {
    "factor_snapshot",
    "tracker",
    "market_etf",
    "industry_etf",
    "unified_v2_backtest",
}
LEGACY_BIASES = (
    "survivorship_bias",
    "incomplete_membership_evidence",
    "not_formal_point_in_time_universe",
)


def _freeze_json(value: Any) -> Any:
    """Detach and recursively freeze JSON-like evidence before handoff."""

    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze_json(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    return value


@dataclass(frozen=True)
class ShadowConsumerInput:
    """Validated shadow rows plus the identities needed to compare consumers."""

    consumer: str
    mode: str
    as_of: str
    universe_id: str
    market_snapshot_id: str
    adjustment_policy: Mapping[str, Any]
    symbol_rows: Mapping[str, tuple[Mapping[str, Any], ...]]
    bias_labels: tuple[str, ...]
    market_snapshot: Mapping[str, Any]

    def audit(self) -> dict[str, Any]:
        return {
            "consumer": self.consumer,
            "mode": self.mode,
            "as_of": self.as_of,
            "universe_id": self.universe_id,
            "market_snapshot_id": self.market_snapshot_id,
            "adjustment_policy": dict(self.adjustment_policy),
            "bias_labels": list(self.bias_labels),
        }


def open_internal_shadow_repository(source: MarketDataSource) -> MarketDataRepository:
    """Open the sole writable shadow repository without accepting a root capability."""

    root = (_WORKSPACE_ROOT / _SHADOW_REPOSITORY_RELATIVE).resolve()
    return MarketDataRepository(root, source, workspace_root=_WORKSPACE_ROOT)


def require_shadow_rows(
    prepared: ShadowConsumerInput, *, consumer: str
) -> Mapping[str, tuple[Mapping[str, Any], ...]]:
    """Hand rows to exactly the consumer named during preparation."""

    if not isinstance(prepared, ShadowConsumerInput) or prepared.consumer != consumer:
        raise ContractError("shadow input was prepared for a different consumer")
    return prepared.symbol_rows


def prepare_shadow_consumer_input(
    *,
    consumer: str,
    mode: str,
    as_of: str,
    snapshots: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    reader: Callable[..., RepositoryRead],
    generated_at: str,
    data_source: Mapping[str, Any],
    adjustment_policy: Mapping[str, Any] = ADJUSTMENT_POLICY,
) -> ShadowConsumerInput:
    """Prepare one explicit formal or legacy point-in-time input.

    The same function serves daily and backtest shadows, which prevents either
    side from inventing a fallback or a different data identity.  The reader is
    injected for tests and must return the repository's already-adjusted
    ``RepositoryRead``; this layer performs no network or filesystem discovery.
    """

    if consumer not in CONSUMERS:
        raise ContractError(f"unknown M02 shadow consumer: {consumer}")
    if mode not in {"formal", "legacy"}:
        raise ContractError("shadow consumer mode must be explicitly formal or legacy")
    as_of = require_date(as_of, "as_of")
    universe = select_universe_snapshot(snapshots, as_of=as_of, path_status=mode)
    if mode == "formal" and universe["schema_version"].split(".", 1)[0] != "3":
        raise ContractError("formal shadow consumer requires UniverseSnapshot 3.x")
    members = {item["instrument_id"]: item for item in universe["members"]}
    eligible_ids = [
        item["instrument_id"] for item in universe["qualifications"] if item["eligible"]
    ]
    if not eligible_ids:
        raise ContractError("selected universe contains no eligible members")

    symbol_rows: dict[str, tuple[Mapping[str, Any], ...]] = {}
    symbol_evidence: list[dict[str, Any]] = []
    revisions: list[dict[str, str]] = []
    for instrument_id in sorted(eligible_ids):
        member = members[instrument_id]
        result = reader(instrument_id, as_of=as_of)
        if not isinstance(result, RepositoryRead):
            raise ContractError("shadow reader must return RepositoryRead")
        if result.instrument_id != instrument_id or result.as_of != as_of:
            raise ContractError("shadow reader returned the wrong point-in-time identity")
        rows = validate_adjusted_rows(result.rows)
        if not rows:
            raise ContractError("eligible member has no point-in-time market rows")
        dates = [row["date"] for row in rows]
        if dates[-1] > as_of:
            raise ContractError("shadow reader returned future rows")
        actual_fingerprint = bars_fingerprint(rows)
        if result.point_in_time_fingerprint != actual_fingerprint:
            raise ContractError("shadow reader fingerprint does not match delivered rows")
        symbol = member["symbol"]
        if symbol in symbol_rows:
            raise ContractError("selected universe contains duplicate display symbols")
        symbol_rows[symbol] = rows
        symbol_evidence.append({
            "instrument_id": instrument_id,
            "symbol": symbol,
            "row_count": len(rows),
            "first_date": dates[0],
            "max_returned_date": dates[-1],
            "content_fingerprint": actual_fingerprint,
        })
        revisions.append({
            "instrument_id": instrument_id,
            "point_in_time_fingerprint": actual_fingerprint,
        })

    raw_revision = canonical_fingerprint(revisions)
    market_snapshot: dict[str, Any] = {
        "schema_version": "1.0.0",
        "as_of": as_of,
        "generated_at": generated_at,
        "source_version": {"consumer_bridge": "m02-shadow-1.0.0"},
        "future_data_used": False,
        "market": data_source.get("market"),
        "symbols": symbol_evidence,
        "adjustment_policy": dict(adjustment_policy),
        "data_source": {
            "provider": data_source.get("provider"),
            "dataset": data_source.get("dataset"),
        },
        "universe_id": universe["universe_id"],
        "raw_revision": raw_revision,
        "max_returned_date": max(item["max_returned_date"] for item in symbol_evidence),
    }
    market_snapshot["snapshot_id"] = market_data_snapshot_id(market_snapshot)
    validate_market_data_snapshot(market_snapshot)
    return ShadowConsumerInput(
        consumer=consumer,
        mode=mode,
        as_of=as_of,
        universe_id=universe["universe_id"],
        market_snapshot_id=market_snapshot["snapshot_id"],
        adjustment_policy=_freeze_json(adjustment_policy),
        symbol_rows=_freeze_json(symbol_rows),
        bias_labels=() if mode == "formal" else LEGACY_BIASES,
        market_snapshot=_freeze_json(market_snapshot),
    )
