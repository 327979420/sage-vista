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
UPSTREAM_NON_EVENT_REASONS = (
    "data_unavailable",
    "not_tradable",
    "insufficient_history",
    "below_price_floor",
    "below_liquidity_floor",
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
    market_snapshot_id: str | None
    adjustment_policy: Mapping[str, Any]
    symbol_rows: Mapping[str, tuple[Mapping[str, Any], ...]]
    universe_member_count: int
    upstream_non_event_reason_counts: Mapping[str, int]
    bias_labels: tuple[str, ...]
    market_snapshot: Mapping[str, Any] | None

    def audit(self) -> dict[str, Any]:
        return {
            "consumer": self.consumer,
            "mode": self.mode,
            "as_of": self.as_of,
            "universe_id": self.universe_id,
            "market_snapshot_id": self.market_snapshot_id,
            "adjustment_policy": dict(self.adjustment_policy),
            "universe_member_count": self.universe_member_count,
            "upstream_non_event_reason_counts": dict(
                self.upstream_non_event_reason_counts
            ),
            "bias_labels": list(self.bias_labels),
        }


def _qualification_non_event_reason(
    qualification: Mapping[str, Any], member: Mapping[str, Any]
) -> str | None:
    """Map already-validated M02 facts to one deterministic M03 audit reason.

    This function does not recalculate price, history, or liquidity.  It only
    classifies the frozen booleans and point-in-time listing status carried by
    UniverseSnapshot.  Unknown exclusions fail instead of being guessed.
    """

    if qualification["eligible"]:
        if member["listing_status"] != "active":
            raise ContractError("eligible qualification has a non-active listing status")
        return None
    if not qualification["price_complete"]:
        return "data_unavailable"
    if (
        member["listing_status"] != "active"
        or set(qualification["exclusion_reasons"])
        & {"not_tradable", "not-tradable"}
    ):
        return "not_tradable"
    if not qualification["history_length_passed"]:
        return "insufficient_history"
    if not qualification["minimum_price_passed"]:
        return "below_price_floor"
    if not qualification["dollar_volume_passed"]:
        return "below_liquidity_floor"
    raise ContractError(
        "excluded qualification has no supported M03 audit reason"
    )


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
    upstream_counts = {reason: 0 for reason in UPSTREAM_NON_EVENT_REASONS}
    eligible_ids: list[str] = []
    for qualification in universe["qualifications"]:
        instrument_id = qualification["instrument_id"]
        reason = _qualification_non_event_reason(
            qualification, members[instrument_id]
        )
        if reason is None:
            eligible_ids.append(instrument_id)
        else:
            upstream_counts[reason] += 1
    if not eligible_ids:
        # This is a complete formal day with zero qualified members, not a
        # missing universe.  Preserve M02's reasons for M03 audit without
        # inventing an empty MarketDataSnapshot or touching the market reader.
        return ShadowConsumerInput(
            consumer=consumer,
            mode=mode,
            as_of=as_of,
            universe_id=universe["universe_id"],
            market_snapshot_id=None,
            adjustment_policy=_freeze_json(adjustment_policy),
            symbol_rows=_freeze_json({}),
            universe_member_count=len(members),
            upstream_non_event_reason_counts=_freeze_json(upstream_counts),
            bias_labels=() if mode == "formal" else LEGACY_BIASES,
            market_snapshot=None,
        )

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
        universe_member_count=len(members),
        upstream_non_event_reason_counts=_freeze_json(upstream_counts),
        bias_labels=() if mode == "formal" else LEGACY_BIASES,
        market_snapshot=_freeze_json(market_snapshot),
    )
