"""The sole M06 producer for objective, score-free ETF context."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from types import MappingProxyType
from typing import Any, Callable, Iterable, Mapping, Sequence

from services.contracts.market_data import canonical_fingerprint
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, validate_contract
from services.factors.producer import TechnicalEvidenceBatch, validate_technical_evidence_batch
from services.gates.producer import require_gate_event_for_path
from services.market_data.consumer import ShadowConsumerInput, require_shadow_rows
from services.selectors.producer import ModelAssessmentBatch, validate_model_assessment

from .registry import select_membership_snapshot, validate_etf_registry, validate_membership_registry


CONTEXT_SCHEMA_VERSION = "2.0.0"
CONTEXT_POLICY_VERSION = "m06-market-industry-context-1.0.0"
ETF_STATE_POLICY_VERSION = "m06-etf-state-1.0.0"
BREAKOUT_LOOKBACK = 60
NEAR_BREAKOUT_DISTANCE = 0.03
PULLBACK_MIN = 0.05
PULLBACK_MAX = 0.25
SUPPORT_DISTANCE = 0.03
MINIMUM_HISTORY = 260
FORBIDDEN_KEYS = frozenset({
    "score", "technical_score", "weight", "rank", "ranking", "trade_plan",
    "entry", "stop", "target", "forward_outcome", "mfe", "mae",
})
BREAKOUT_FACTOR_IDS = frozenset({
    "structure.trendline_three_push",
    "structure.breakout_retest",
    "structure.trendline_three_push_retest",
    "structure.double_bottom_neckline_retest",
})


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({key: _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _all_keys(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, Mapping):
        for key, item in value.items():
            result.add(str(key).lower())
            result.update(_all_keys(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            result.update(_all_keys(item))
    return result


def _ema(values: Sequence[float], period: int) -> float:
    if len(values) < period:
        raise ContractError("ETF state has insufficient completed history")
    alpha = 2.0 / (period + 1.0)
    value = sum(values[:period]) / period
    for item in values[period:]:
        value = alpha * item + (1.0 - alpha) * value
    return value


def evaluate_etf_state(
    rows: Sequence[Mapping[str, Any]],
    *,
    as_of: str,
    etf_id: str,
    market_snapshot_id: str,
) -> Mapping[str, Any]:
    """Describe one ETF from completed point-in-time rows, without scoring it."""

    completed = tuple(row for row in rows if row["date"] <= as_of)
    if not completed or completed[-1]["date"] != as_of:
        raise ContractError("ETF state requires a completed row on as_of")
    if len(completed) < MINIMUM_HISTORY:
        return _freeze({
            "state_id": "etf-state:" + canonical_fingerprint({
                "etf_id": etf_id,
                "as_of": as_of,
                "market_snapshot_id": market_snapshot_id,
                "state_policy_version": ETF_STATE_POLICY_VERSION,
            }),
            "etf_id": etf_id,
            "as_of": as_of,
            "market_snapshot_id": market_snapshot_id,
            "state_policy_version": ETF_STATE_POLICY_VERSION,
            "status": "unavailable",
            "facts": {"completed_sessions": len(completed), "required_sessions": MINIMUM_HISTORY},
            "future_data_used": False,
        })
    closes = [float(row["close"]) for row in completed]
    highs = [float(row["high"]) for row in completed]
    if any(not isfinite(value) or value <= 0 for value in closes + highs):
        raise ContractError("ETF state received invalid adjusted prices")
    close = closes[-1]
    ema21 = _ema(closes, 21)
    ema50 = _ema(closes, 50)
    ema200 = _ema(closes, 200)
    ema200_60 = _ema(closes[:-60], 200)
    ema200_change_60d = ema200 / ema200_60 - 1.0
    prior_high = max(highs[-(BREAKOUT_LOOKBACK + 1):-1])
    distance_to_high = close / prior_high - 1.0
    pullback_depth = max(0.0, 1.0 - close / prior_high)
    support_distance = min(abs(close / level - 1.0) for level in (ema21, ema50, ema200))
    long_uptrend = close >= ema200 * 0.90 and ema200_change_60d >= -0.03
    structural_damage = close < ema200 * 0.90 or ema200_change_60d < -0.03
    confirmed_breakout = close > prior_high
    near_breakout = not confirmed_breakout and -NEAR_BREAKOUT_DISTANCE <= distance_to_high <= 0
    pullback = (
        long_uptrend
        and PULLBACK_MIN <= pullback_depth <= PULLBACK_MAX
        and support_distance <= SUPPORT_DISTANCE
    )
    if structural_damage:
        status = "structural_damage"
    elif confirmed_breakout:
        status = "confirmed_breakout"
    elif near_breakout:
        status = "near_breakout"
    elif pullback:
        status = "pullback"
    elif long_uptrend:
        status = "uptrend"
    else:
        status = "weak"
    identity = {
        "etf_id": etf_id,
        "as_of": as_of,
        "market_snapshot_id": market_snapshot_id,
        "state_policy_version": ETF_STATE_POLICY_VERSION,
    }
    return _freeze({
        "state_id": "etf-state:" + canonical_fingerprint(identity),
        **identity,
        "status": status,
        "facts": {
            "completed_sessions": len(completed),
            "close": close,
            "ema21": ema21,
            "ema50": ema50,
            "ema200": ema200,
            "ema200_change_60d": ema200_change_60d,
            "confirmed_high_60": prior_high,
            "distance_to_confirmed_high": distance_to_high,
            "pullback_depth": pullback_depth,
            "nearest_ema_distance": support_distance,
            "long_uptrend": long_uptrend,
            "pullback": pullback,
            "near_breakout": near_breakout,
            "confirmed_breakout": confirmed_breakout,
            "structural_damage": structural_damage,
        },
        "future_data_used": False,
    })


@dataclass(frozen=True)
class ContextBatch:
    batch_id: str
    as_of: str
    path_status: str
    etf_states: tuple[Mapping[str, Any], ...]
    contexts: tuple[Mapping[str, Any], ...]


def _identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "instrument_id": payload["instrument_id"],
        "as_of": payload["as_of"],
        "path_status": payload["path_status"],
        "input_identity": _plain(payload["input_identity"]),
        "gate_event_id": payload["gate_event_id"],
        "technical_evidence_batch_id": payload["technical_evidence_batch_id"],
        "model_assessment_batch_id": payload["model_assessment_batch_id"],
        "registry_version": payload["registry_version"],
        "membership_links": [
            {"mapping_id": item["mapping_id"], "etf_state_id": item["etf_state_id"]}
            for item in payload["membership_links"]
        ],
    }


def validate_market_industry_context(payload: Mapping[str, Any]) -> None:
    validate_contract("ContextSnapshot", payload)
    if not str(payload["schema_version"]).startswith("2."):
        raise ContractError("formal M06 consumers require ContextSnapshot 2.x")
    forbidden = sorted(FORBIDDEN_KEYS & _all_keys(payload))
    if forbidden:
        raise ContractError(f"M06 context contains out-of-scope fields: {', '.join(forbidden)}")
    expected = "context:" + canonical_fingerprint(_identity(payload))
    if payload["context_id"] != expected:
        raise ContractError("ContextSnapshot id does not match canonical M06 identity")
    semantic = {
        key: _plain(value) for key, value in payload.items()
        if key not in {"generated_at", "context_content_fingerprint"}
    }
    if payload["context_content_fingerprint"] != canonical_fingerprint(semantic):
        raise ContractError("ContextSnapshot content fingerprint does not match facts")


def _alignment(event: Mapping[str, Any], evidence: Sequence[Mapping[str, Any]], etf_status: str) -> str:
    stock_uptrend = bool(event["baseline_passed"])
    stock_breakout = any(
        item["factor_id"] in BREAKOUT_FACTOR_IDS and item["qualified_hit"]
        for item in evidence
    )
    if etf_status == "unavailable":
        return "insufficient_evidence"
    if stock_breakout and etf_status == "near_breakout":
        return "stock_breakout_etf_near_breakout"
    if etf_status == "confirmed_breakout" and not stock_breakout:
        return "etf_breakout_stock_not_confirmed"
    if stock_uptrend and etf_status in {"structural_damage", "weak"}:
        return "stock_strong_etf_weak"
    if stock_uptrend and etf_status in {"uptrend", "pullback", "near_breakout", "confirmed_breakout"}:
        return "aligned_uptrend"
    return "mixed_objective_state"


def produce_market_industry_context(
    stock_input: ShadowConsumerInput,
    etf_input: ShadowConsumerInput,
    *,
    gate_events: Iterable[Mapping[str, Any]],
    technical_evidence: TechnicalEvidenceBatch,
    model_assessments: ModelAssessmentBatch,
    etf_registry: Mapping[str, Any],
    membership_registry: Mapping[str, Any],
    generated_at: str,
    state_evaluator: Callable[..., Mapping[str, Any]] = evaluate_etf_state,
) -> ContextBatch:
    """Join existing stock facts to one cached ETF state per immutable ETF input."""

    for prepared in (stock_input, etf_input):
        if not isinstance(prepared, ShadowConsumerInput) or prepared.mode != "formal":
            raise ContractError("formal M06 producer requires formal M02 inputs")
        if prepared.market_snapshot_id is None:
            raise ContractError("M06 input requires immutable market evidence")
    if stock_input.as_of != etf_input.as_of:
        raise ContractError("stock and ETF context dates do not match")
    validate_etf_registry(etf_registry)
    validate_membership_registry(membership_registry)
    validate_technical_evidence_batch(technical_evidence)
    if technical_evidence.as_of != stock_input.as_of or technical_evidence.path_status != "formal":
        raise ContractError("M04 evidence does not match M06 stock input")
    if not isinstance(model_assessments, ModelAssessmentBatch):
        raise ContractError("M06 requires the M05 ModelAssessmentBatch")
    if model_assessments.as_of != stock_input.as_of or model_assessments.path_status != "formal":
        raise ContractError("M05 assessments do not match M06 stock input")
    for assessment in model_assessments.assessments:
        validate_model_assessment(assessment)
    events = sorted(tuple(gate_events), key=lambda item: str(item.get("instrument_id")))
    events_by_id: dict[str, Mapping[str, Any]] = {}
    for event in events:
        require_gate_event_for_path(event, path_status="formal")
        if event["signal_date"] != stock_input.as_of:
            raise ContractError("GateEvent date does not match M06 input")
        if event["gate_event_id"] in events_by_id:
            raise ContractError("M06 input contains a duplicate GateEvent")
        events_by_id[str(event["gate_event_id"])] = event
    evidence_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for item in technical_evidence.evidence:
        evidence_by_event.setdefault(str(item["gate_event_id"]), []).append(item)
    assessments_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for item in model_assessments.assessments:
        assessments_by_event.setdefault(str(item["gate_event_id"]), []).append(item)
    if set(evidence_by_event) != set(events_by_id) or set(assessments_by_event) != set(events_by_id):
        raise ContractError("M03/M04/M05 references do not form one complete context input")
    registry_by_symbol = {item["symbol"]: item for item in etf_registry["etfs"]}
    etf_rows = require_shadow_rows(etf_input, consumer=etf_input.consumer)
    snapshots = membership_registry["snapshots"]
    selected_by_instrument: dict[str, list[tuple[Mapping[str, Any], Mapping[str, Any]]]] = {}
    needed_symbols = {
        item["symbol"] for item in etf_registry["etfs"]
        if item["category"] == "broad_market" and item["symbol"] in etf_rows
    }
    for symbol in sorted(registry_by_symbol):
        try:
            mapping = select_membership_snapshot(
                snapshots, etf_symbol=symbol, as_of=stock_input.as_of, path_status="formal"
            )
        except ContractError as exc:
            if "membership_unavailable" in str(exc):
                continue
            raise
        needed_symbols.add(symbol)
        for member in mapping["members"]:
            selected_by_instrument.setdefault(member["instrument_id"], []).append(
                (registry_by_symbol[symbol], mapping)
            )
    states: dict[str, Mapping[str, Any]] = {}
    for symbol in sorted(needed_symbols):
        rows = etf_rows.get(symbol)
        if rows is None:
            raise ContractError(f"ETF market evidence is missing for {symbol}")
        item = registry_by_symbol[symbol]
        states[symbol] = state_evaluator(
            rows,
            as_of=etf_input.as_of,
            etf_id=item["etf_id"],
            market_snapshot_id=str(etf_input.market_snapshot_id),
        )
    contexts: list[Mapping[str, Any]] = []
    broad = [
        (registry_by_symbol[symbol], None) for symbol in sorted(states)
        if registry_by_symbol[symbol]["category"] == "broad_market"
    ]
    for event in events:
        event_id = str(event["gate_event_id"])
        links: list[dict[str, Any]] = []
        relationships = broad + selected_by_instrument.get(str(event["instrument_id"]), [])
        seen_etfs: set[str] = set()
        for etf, mapping in sorted(relationships, key=lambda pair: pair[0]["etf_id"]):
            if etf["etf_id"] in seen_etfs:
                continue
            seen_etfs.add(etf["etf_id"])
            state = states[etf["symbol"]]
            links.append({
                "etf_id": etf["etf_id"],
                "etf_symbol": etf["symbol"],
                "category": etf["category"],
                "label": etf["label"],
                "mapping_id": mapping["mapping_id"] if mapping else "broad-market:universal",
                "membership_as_of_date": mapping["membership_as_of_date"] if mapping else stock_input.as_of,
                "membership_weight": next((
                    member.get("weight") for member in mapping["members"]
                    if member["instrument_id"] == event["instrument_id"]
                ), None) if mapping else None,
                "etf_state_id": state["state_id"],
                "etf_status": state["status"],
                "alignment": _alignment(event, evidence_by_event[event_id], str(state["status"])),
            })
        evidence_ids = sorted(str(item["evidence_id"]) for item in evidence_by_event[event_id])
        assessment_ids = sorted(str(item["assessment_id"]) for item in assessments_by_event[event_id])
        payload: dict[str, Any] = {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "as_of": stock_input.as_of,
            "generated_at": generated_at,
            "source_version": {
                "context_policy": CONTEXT_POLICY_VERSION,
                "etf_state_policy": ETF_STATE_POLICY_VERSION,
            },
            "future_data_used": False,
            "context_type": "market_industry",
            "status": "available" if links else "unavailable",
            "instrument_id": event["instrument_id"],
            "path_status": "formal",
            "input_identity": {
                "stock_universe_id": stock_input.universe_id,
                "stock_market_snapshot_id": stock_input.market_snapshot_id,
                "etf_universe_id": etf_input.universe_id,
                "etf_market_snapshot_id": etf_input.market_snapshot_id,
                "adjustment_policy": dict(ADJUSTMENT_POLICY),
            },
            "gate_event_id": event["gate_event_id"],
            "technical_evidence_batch_id": technical_evidence.batch_id,
            "model_assessment_batch_id": model_assessments.batch_id,
            "technical_evidence_ids": evidence_ids,
            "model_assessment_ids": assessment_ids,
            "registry_version": etf_registry["registry_version"],
            "membership_links": links,
            "evidence": {
                "gate_baseline_passed": bool(event["baseline_passed"]),
                "upstream_facts_referenced_only": True,
            },
            "production_effect": False,
            "bias_labels": [],
        }
        payload["context_id"] = "context:" + canonical_fingerprint(_identity(payload))
        semantic = {
            key: value for key, value in payload.items()
            if key not in {"generated_at", "context_content_fingerprint"}
        }
        payload["context_content_fingerprint"] = canonical_fingerprint(semantic)
        validate_market_industry_context(payload)
        contexts.append(_freeze(payload))
    state_list = tuple(states[symbol] for symbol in sorted(states))
    batch_identity = {
        "as_of": stock_input.as_of,
        "path_status": "formal",
        "etf_states": [item["state_id"] for item in state_list],
        "contexts": [item["context_id"] for item in contexts],
    }
    batch = ContextBatch(
        batch_id="context-batch:" + canonical_fingerprint(batch_identity),
        as_of=stock_input.as_of,
        path_status="formal",
        etf_states=state_list,
        contexts=tuple(contexts),
    )
    validate_context_batch(batch)
    return batch


def validate_context_batch(batch: ContextBatch) -> None:
    if not isinstance(batch, ContextBatch):
        raise ContractError("expected an M06 ContextBatch")
    for item in batch.contexts:
        validate_market_industry_context(item)
        if item["as_of"] != batch.as_of or item["path_status"] != batch.path_status:
            raise ContractError("ContextBatch contains mixed identities")
    identity = {
        "as_of": batch.as_of,
        "path_status": batch.path_status,
        "etf_states": [item["state_id"] for item in batch.etf_states],
        "contexts": [item["context_id"] for item in batch.contexts],
    }
    if batch.batch_id != "context-batch:" + canonical_fingerprint(identity):
        raise ContractError("ContextBatch identity does not match its contents")
