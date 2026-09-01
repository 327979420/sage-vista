"""Sole M07 producer for immutable score results and the complex main ranking."""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Iterable, Mapping

from services.context import ContextBatch, validate_context_batch, validate_market_industry_context
from services.contracts.market_data import canonical_fingerprint, require_date
from services.contracts.policies import ADJUSTMENT_POLICY
from services.contracts.validation import ContractError, validate_contract
from services.factors import TechnicalEvidenceBatch, validate_technical_evidence_batch
from services.gates.producer import require_gate_event_for_path
from services.scanner.factor_registry import FACTORS_BY_ID, REGISTRY_VERSION
from services.selectors import ModelAssessmentBatch, validate_model_assessment

from .policies import AUTHORITY_POLICY, RANKING_POLICY, SCORE_POLICY, validate_policy


SCORE_RESULT_SCHEMA_VERSION = "2.0.0"
RANKING_SNAPSHOT_SCHEMA_VERSION = "2.0.0"
RANKING_PRODUCER_VERSION = "m07-shadow-1.0.0"
TIMEFRAME_KEYS = {"daily": "daily", "weekly_completed": "weekly", "monthly_completed": "monthly"}


def _plain(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze(item) for item in value)
    return value


def _semantic(payload: Mapping[str, Any], fingerprint_field: str) -> dict[str, Any]:
    return {
        key: _plain(value)
        for key, value in payload.items()
        if key not in {"generated_at", fingerprint_field}
    }


def _score_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema_major": 2,
        "instrument_id": payload["instrument_id"],
        "as_of": payload["as_of"],
        "path_status": payload["path_status"],
        "gate_event_id": payload["gate_event_id"],
        "technical_evidence_ids": list(payload["technical_evidence_ids"]),
        "model_assessment_id": payload["model_assessment_id"],
        "context_snapshot_id": payload["context_snapshot_id"],
        "input_identity": _plain(payload["input_identity"]),
        "score_policy_version": payload["score_policy_version"],
        "score_policy_fingerprint": payload["score_policy_fingerprint"],
    }


def validate_score_result(payload: Mapping[str, Any]) -> None:
    validate_contract("ScoreResult", payload)
    if not str(payload["schema_version"]).startswith("2."):
        raise ContractError("formal M07 consumers require ScoreResult 2.x")
    expected = "score:" + canonical_fingerprint(_score_identity(payload))
    if payload["score_result_id"] != expected:
        raise ContractError("ScoreResult id does not match canonical M07 identity")
    if payload["score_input_fingerprint"] != canonical_fingerprint(_score_identity(payload)):
        raise ContractError("ScoreResult input fingerprint does not match its references")
    if payload["score_content_fingerprint"] != canonical_fingerprint(
        _semantic(payload, "score_content_fingerprint")
    ):
        raise ContractError("ScoreResult content fingerprint does not match its facts")
    if payload["context_reference"].get("score_contribution") != 0:
        raise ContractError("M07 v1 context must remain separate from technical score")
    expected_components = [
        "positive_hit_count",
        "family_count",
        "parent_child_confirmation_bonus",
        "timeframe_resonance_bonus",
    ]
    components = payload["components"]
    if payload["status"] == "scored":
        if [item.get("component_id") for item in components] != expected_components:
            raise ContractError("ScoreResult must preserve the complete approved component order")
        contributions = [item.get("contribution") for item in components]
        if any(isinstance(value, bool) or not isinstance(value, int) for value in contributions):
            raise ContractError("ScoreResult component contributions must be integers")
        if payload["total_score"] != sum(contributions):
            raise ContractError("ScoreResult total does not equal its saved components")
        for field in expected_components:
            if payload["metrics"].get(field) != next(
                item["value"] for item in components if item["component_id"] == field
            ):
                raise ContractError("ScoreResult metrics do not match saved components")
    elif components:
        raise ContractError("unscored ScoreResult cannot carry synthetic score components")


@dataclass(frozen=True)
class ScoreBatch:
    batch_id: str
    as_of: str
    path_status: str
    score_policy_version: str
    score_policy_fingerprint: str
    results: tuple[Mapping[str, Any], ...]


def validate_score_batch(batch: ScoreBatch) -> None:
    if not isinstance(batch, ScoreBatch):
        raise ContractError("expected an M07 ScoreBatch")
    seen: set[str] = set()
    for result in batch.results:
        validate_score_result(result)
        if result["as_of"] != batch.as_of or result["path_status"] != batch.path_status:
            raise ContractError("ScoreBatch contains mixed dates or paths")
        if result["score_policy_version"] != batch.score_policy_version:
            raise ContractError("ScoreBatch contains mixed score policies")
        if result["score_policy_fingerprint"] != batch.score_policy_fingerprint:
            raise ContractError("ScoreBatch contains mixed score policy contents")
        if result["score_result_id"] in seen:
            raise ContractError("ScoreBatch contains a duplicate score identity")
        seen.add(str(result["score_result_id"]))
    identity = {
        "as_of": batch.as_of,
        "path_status": batch.path_status,
        "score_policy_version": batch.score_policy_version,
        "score_policy_fingerprint": batch.score_policy_fingerprint,
        "results": [
            {"id": item["score_result_id"], "content": item["score_content_fingerprint"]}
            for item in batch.results
        ],
    }
    if batch.batch_id != "score-batch:" + canonical_fingerprint(identity):
        raise ContractError("ScoreBatch identity does not match its contents")


def _technical_components(
    evidence: tuple[Mapping[str, Any], ...], score_policy: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    positive = {
        str(item["factor_id"]): item
        for item in evidence
        if item["qualified_hit"]
        and item["factor_id"] not in score_policy["rules"]["gate_factor_ids"]
        and item["family"] != score_policy["rules"]["risk_family"]
    }
    families = {str(item["family"]) for item in positive.values()}
    confirmations: list[dict[str, str]] = []
    for child_id in sorted(positive):
        factor = FACTORS_BY_ID.get(child_id)
        if factor is None:
            raise ContractError("ScoreResult references an unknown factor")
        for parent_id in factor.depends_on:
            if parent_id in positive:
                confirmations.append({"parent": parent_id, "child": child_id})
    family_frames: dict[str, set[str]] = {family: set() for family in families}
    for item in positive.values():
        timeframe = TIMEFRAME_KEYS.get(str(item["timeframe"]))
        if timeframe:
            family_frames[str(item["family"])].add(timeframe)
    resonances: list[dict[str, Any]] = []
    for family, frames in sorted(family_frames.items()):
        if {"daily", "weekly"} <= frames:
            resonances.append({"family": family, "timeframes": ["daily", "weekly"], "bonus": 2})
        if {"weekly", "monthly"} <= frames:
            resonances.append({"family": family, "timeframes": ["weekly", "monthly"], "bonus": 2})
        if {"daily", "monthly"} <= frames:
            resonances.append({"family": family, "timeframes": ["daily", "monthly"], "bonus": 1})
        if {"daily", "weekly", "monthly"} <= frames:
            resonances.append({"family": family, "timeframes": ["daily", "weekly", "monthly"], "bonus": 2})
    metrics = {
        "positive_hit_count": len(positive),
        "family_count": len(families),
        "parent_child_confirmation_bonus": len(confirmations),
        "timeframe_resonance_bonus": sum(item["bonus"] for item in resonances),
    }
    components = [
        {
            "component_id": "positive_hit_count",
            "value": metrics["positive_hit_count"],
            "contribution": metrics["positive_hit_count"],
            "evidence_ids": sorted(str(item["evidence_id"]) for item in positive.values()),
        },
        {
            "component_id": "family_count",
            "value": metrics["family_count"],
            "contribution": metrics["family_count"],
            "families": sorted(families),
        },
        {
            "component_id": "parent_child_confirmation_bonus",
            "value": metrics["parent_child_confirmation_bonus"],
            "contribution": metrics["parent_child_confirmation_bonus"],
            "confirmations": confirmations,
        },
        {
            "component_id": "timeframe_resonance_bonus",
            "value": metrics["timeframe_resonance_bonus"],
            "contribution": metrics["timeframe_resonance_bonus"],
            "resonances": resonances,
        },
    ]
    return components, metrics


def produce_score_results(
    *,
    gate_events: Iterable[Mapping[str, Any]],
    technical_evidence: TechnicalEvidenceBatch,
    model_assessments: ModelAssessmentBatch,
    contexts: ContextBatch,
    generated_at: str,
    score_policy: Mapping[str, Any] = SCORE_POLICY,
) -> ScoreBatch:
    """Score each complex assessment once without recomputing upstream facts."""

    validate_policy(score_policy, expected_kind="score")
    if score_policy["rules"].get("context_effect") != "reference_only_zero":
        raise ContractError("M07 v1 does not approve context scoring")
    if score_policy["rules"].get("factor_registry_version") != REGISTRY_VERSION:
        raise ContractError("score policy does not match the active factor registry")
    validate_technical_evidence_batch(technical_evidence)
    if not isinstance(model_assessments, ModelAssessmentBatch) or model_assessments.path_status != "formal":
        raise ContractError("M07 requires the formal M05 ModelAssessmentBatch")
    validate_context_batch(contexts)
    if technical_evidence.path_status != "formal" or contexts.path_status != "formal":
        raise ContractError("M07 formal scoring cannot consume legacy inputs")
    if len({technical_evidence.as_of, model_assessments.as_of, contexts.as_of}) != 1:
        raise ContractError("M07 input batches do not share one as_of date")
    events: dict[str, Mapping[str, Any]] = {}
    for event in gate_events:
        require_gate_event_for_path(event, path_status="formal")
        event_id = str(event["gate_event_id"])
        if event_id in events:
            raise ContractError("M07 input contains a duplicate GateEvent")
        events[event_id] = event
    evidence_by_event: dict[str, list[Mapping[str, Any]]] = {}
    for item in technical_evidence.evidence:
        evidence_by_event.setdefault(str(item["gate_event_id"]), []).append(item)
    complex_by_event: dict[str, Mapping[str, Any]] = {}
    for assessment in model_assessments.assessments:
        validate_model_assessment(assessment)
        if assessment["model_id"] != "complex_multifactor":
            continue
        event_id = str(assessment["gate_event_id"])
        if event_id in complex_by_event:
            raise ContractError("M07 input contains duplicate complex assessments")
        complex_by_event[event_id] = assessment
    contexts_by_event: dict[str, Mapping[str, Any]] = {}
    for context in contexts.contexts:
        validate_market_industry_context(context)
        event_id = str(context["gate_event_id"])
        if event_id in contexts_by_event:
            raise ContractError("M07 input contains duplicate contexts")
        contexts_by_event[event_id] = context
    if not (set(events) == set(evidence_by_event) == set(complex_by_event) == set(contexts_by_event)):
        raise ContractError("M03-M06 inputs do not form one complete M07 batch")
    results: list[Mapping[str, Any]] = []
    for event_id in sorted(events):
        event = events[event_id]
        assessment = complex_by_event[event_id]
        context = contexts_by_event[event_id]
        evidence = tuple(sorted(evidence_by_event[event_id], key=lambda item: str(item["factor_id"])))
        if str(event["signal_date"]) != technical_evidence.as_of:
            raise ContractError("GateEvent date does not match M07 batch")
        if assessment["instrument_id"] != event["instrument_id"] or context["instrument_id"] != event["instrument_id"]:
            raise ContractError("M07 upstream instrument identities do not match")
        event_identity = event["input_identity"]
        assessment_identity = assessment["input_identity"]
        context_identity = context["input_identity"]
        if (
            assessment_identity["universe_id"] != event_identity["universe_id"]
            or assessment_identity["market_snapshot_id"] != event_identity["market_snapshot_id"]
            or context_identity["stock_universe_id"] != event_identity["universe_id"]
            or context_identity["stock_market_snapshot_id"] != event_identity["market_snapshot_id"]
            or _plain(event_identity["adjustment_policy"]) != ADJUSTMENT_POLICY
            or _plain(assessment_identity["adjustment_policy"]) != ADJUSTMENT_POLICY
            or _plain(context_identity["adjustment_policy"]) != ADJUSTMENT_POLICY
        ):
            raise ContractError("M07 upstream market identities do not match")
        evidence_ids = sorted(str(item["evidence_id"]) for item in evidence)
        if assessment["evidence_batch_id"] != technical_evidence.batch_id:
            raise ContractError("complex assessment does not reference this evidence batch")
        if context["technical_evidence_batch_id"] != technical_evidence.batch_id:
            raise ContractError("context does not reference this evidence batch")
        if context["model_assessment_batch_id"] != model_assessments.batch_id:
            raise ContractError("context does not reference this assessment batch")
        if evidence_ids != list(assessment["technical_evidence_ids"]):
            raise ContractError("complex assessment does not reference the complete evidence set")
        if assessment["assessment_id"] not in context["model_assessment_ids"]:
            raise ContractError("context does not reference the complex assessment")
        if evidence_ids != list(context["technical_evidence_ids"]):
            raise ContractError("context does not reference the complete evidence set")
        missing = sorted(str(item["factor_id"]) for item in evidence if not item["available"])
        status = "scored"
        reason = None
        components: list[dict[str, Any]] = []
        metrics: dict[str, int] = {
            "positive_hit_count": 0,
            "family_count": 0,
            "parent_child_confirmation_bonus": 0,
            "timeframe_resonance_bonus": 0,
        }
        total: int | None = None
        if not assessment["eligible"]:
            status, reason = "excluded", str(assessment["status"] or "model_not_eligible")
        elif missing:
            status, reason = "unavailable", "missing_technical_evidence"
        else:
            components, metrics = _technical_components(evidence, score_policy)
            total = sum(int(item["contribution"]) for item in components)
        warnings = sorted(set(str(item) for item in assessment["warnings"]))
        risks = sorted(
            str(item["factor_id"])
            for item in evidence
            if item["family"] == "risk" and item["raw_hit"]
        )
        warnings.extend(item for item in (f"risk:{factor_id}" for factor_id in risks) if item not in warnings)
        if context["status"] == "unavailable":
            warnings.append("context_unavailable")
        payload: dict[str, Any] = {
            "schema_version": SCORE_RESULT_SCHEMA_VERSION,
            "as_of": technical_evidence.as_of,
            "generated_at": generated_at,
            "source_version": {"ranking_producer": RANKING_PRODUCER_VERSION},
            "future_data_used": False,
            "instrument_id": event["instrument_id"],
            "gate_event_id": event["gate_event_id"],
            "path_status": "formal",
            "input_identity": {
                "universe_id": event_identity["universe_id"],
                "market_snapshot_id": event_identity["market_snapshot_id"],
                "adjustment_policy": dict(ADJUSTMENT_POLICY),
                "technical_evidence_batch_id": technical_evidence.batch_id,
                "model_assessment_batch_id": model_assessments.batch_id,
                "context_batch_id": contexts.batch_id,
            },
            "technical_evidence_batch_id": technical_evidence.batch_id,
            "technical_evidence_ids": evidence_ids,
            "model_assessment_id": assessment["assessment_id"],
            "context_snapshot_id": context["context_id"],
            "score_policy_version": score_policy["policy_version"],
            "score_policy_fingerprint": score_policy["policy_fingerprint"],
            "components": components,
            "total_score": total,
            "metrics": metrics,
            "warnings": sorted(set(warnings)),
            "missing_facts": missing,
            "exclusion_reason": reason,
            "status": status,
            "context_reference": {
                "context_snapshot_id": context["context_id"],
                "status": context["status"],
                "membership_link_count": len(context["membership_links"]),
                "score_contribution": 0,
            },
        }
        identity = _score_identity(payload)
        payload["score_result_id"] = "score:" + canonical_fingerprint(identity)
        payload["score_input_fingerprint"] = canonical_fingerprint(identity)
        payload["score_content_fingerprint"] = canonical_fingerprint(
            _semantic(payload, "score_content_fingerprint")
        )
        validate_score_result(payload)
        results.append(_freeze(payload))
    results.sort(key=lambda item: str(item["instrument_id"]))
    batch_identity = {
        "as_of": technical_evidence.as_of,
        "path_status": "formal",
        "score_policy_version": score_policy["policy_version"],
        "score_policy_fingerprint": score_policy["policy_fingerprint"],
        "results": [
            {"id": item["score_result_id"], "content": item["score_content_fingerprint"]}
            for item in results
        ],
    }
    batch = ScoreBatch(
        batch_id="score-batch:" + canonical_fingerprint(batch_identity),
        as_of=technical_evidence.as_of,
        path_status="formal",
        score_policy_version=str(score_policy["policy_version"]),
        score_policy_fingerprint=str(score_policy["policy_fingerprint"]),
        results=tuple(results),
    )
    validate_score_batch(batch)
    return batch


def build_authority_activation(
    *,
    effective_from: str,
    approval_ref: str,
    score_policy: Mapping[str, Any] = SCORE_POLICY,
    ranking_policy: Mapping[str, Any] = RANKING_POLICY,
    authority_policy: Mapping[str, Any] = AUTHORITY_POLICY,
) -> Mapping[str, Any]:
    """Create explicit future-only authority evidence; latest never wins implicitly."""

    require_date(effective_from, "effective_from")
    if not isinstance(approval_ref, str) or not approval_ref.strip():
        raise ContractError("authority activation requires an approval reference")
    for policy, kind in ((score_policy, "score"), (ranking_policy, "ranking"), (authority_policy, "authority")):
        validate_policy(policy, expected_kind=kind)
    evidence = {
        "effective_from": effective_from,
        "approval_ref": approval_ref,
        "score_policy_version": score_policy["policy_version"],
        "score_policy_fingerprint": score_policy["policy_fingerprint"],
        "ranking_policy_version": ranking_policy["policy_version"],
        "ranking_policy_fingerprint": ranking_policy["policy_fingerprint"],
        "authority_policy_version": authority_policy["policy_version"],
        "authority_policy_fingerprint": authority_policy["policy_fingerprint"],
    }
    return _freeze({"activation_id": "activation:" + canonical_fingerprint(evidence), **evidence})


def _validate_authority_activation(
    activation: Mapping[str, Any],
    *,
    score_batch: ScoreBatch,
    ranking_policy: Mapping[str, Any],
    authority_policy: Mapping[str, Any],
) -> None:
    if not isinstance(activation, Mapping):
        raise ContractError("authoritative ranking requires explicit activation evidence")
    require_date(activation.get("effective_from"), "activation.effective_from")
    approval_ref = activation.get("approval_ref")
    if not isinstance(approval_ref, str) or not approval_ref:
        raise ContractError("authority activation lacks approval evidence")
    expected_values = {
        "score_policy_version": score_batch.score_policy_version,
        "score_policy_fingerprint": score_batch.score_policy_fingerprint,
        "ranking_policy_version": ranking_policy["policy_version"],
        "ranking_policy_fingerprint": ranking_policy["policy_fingerprint"],
        "authority_policy_version": authority_policy["policy_version"],
        "authority_policy_fingerprint": authority_policy["policy_fingerprint"],
    }
    for field, expected in expected_values.items():
        if activation.get(field) != expected:
            raise ContractError("authority activation does not match ranking policies")
    evidence = {
        "effective_from": activation["effective_from"],
        "approval_ref": approval_ref,
        **expected_values,
    }
    if activation.get("activation_id") != "activation:" + canonical_fingerprint(evidence):
        raise ContractError("authority activation identity is invalid")


def _ranking_identity(payload: Mapping[str, Any]) -> dict[str, Any]:
    activation = payload["activation"]
    return {
        "schema_major": 2,
        "as_of": payload["as_of"],
        "path_status": payload["path_status"],
        "authority_scope": payload["authority_scope"],
        "ranking_role": payload["ranking_role"],
        "input_identity": _plain(payload["input_identity"]),
        "score_result_ids": list(payload["score_result_ids"]),
        "score_policy_version": payload["score_policy_version"],
        "score_policy_fingerprint": payload["score_policy_fingerprint"],
        "ranking_policy_version": payload["ranking_policy_version"],
        "ranking_policy_fingerprint": payload["ranking_policy_fingerprint"],
        "authority_policy_version": payload["authority_policy_version"],
        "authority_policy_fingerprint": payload["authority_policy_fingerprint"],
        "activation_id": activation["activation_id"] if activation else None,
        "comparison_to_snapshot_id": payload["comparison_to_snapshot_id"],
    }


def validate_ranking_snapshot(payload: Mapping[str, Any]) -> None:
    validate_contract("RankingSnapshot", payload)
    if not str(payload["schema_version"]).startswith("2."):
        raise ContractError("formal M07 consumers require RankingSnapshot 2.x")
    if payload["ranking_snapshot_id"] != "ranking:" + canonical_fingerprint(_ranking_identity(payload)):
        raise ContractError("RankingSnapshot id does not match canonical M07 identity")
    if payload["ranking_content_fingerprint"] != canonical_fingerprint(
        _semantic(payload, "ranking_content_fingerprint")
    ):
        raise ContractError("RankingSnapshot content fingerprint does not match entries")
    ranked = payload["ranked_entries"]
    results = {str(item["score_result_id"]): item for item in payload["score_results"]}
    for result in results.values():
        validate_score_result(result)
        if (
            result["score_policy_version"] != payload["score_policy_version"]
            or result["score_policy_fingerprint"] != payload["score_policy_fingerprint"]
        ):
            raise ContractError("RankingSnapshot embeds a different score policy")
    expected_ranked = sorted(
        (item for item in results.values() if item["status"] == "scored"),
        key=lambda item: (
            -int(item["total_score"]),
            -int(item["metrics"]["timeframe_resonance_bonus"]),
            -int(item["metrics"]["family_count"]),
            -int(item["metrics"]["positive_hit_count"]),
            str(item["instrument_id"]),
        ),
    )
    if [item["score_result_id"] for item in expected_ranked] != [
        item["score_result_id"] for item in ranked
    ]:
        raise ContractError("RankingSnapshot order does not follow its saved policy keys")
    for entry in ranked:
        keys = entry.get("sort_key")
        if not isinstance(keys, (list, tuple)) or not keys:
            raise ContractError("ranked entry must save its complete sort key")
        if keys[-1].get("field") != "instrument_id":
            raise ContractError("instrument_id must be the final deterministic tie breaker")
        result = results[str(entry["score_result_id"])]
        expected_values = [
            result["total_score"],
            result["metrics"]["timeframe_resonance_bonus"],
            result["metrics"]["family_count"],
            result["metrics"]["positive_hit_count"],
            result["instrument_id"],
        ]
        if [item.get("value") for item in keys] != expected_values:
            raise ContractError("ranked entry sort key does not match its ScoreResult")
        if (
            entry.get("instrument_id") != result["instrument_id"]
            or entry.get("gate_event_id") != result["gate_event_id"]
            or entry.get("total_score") != result["total_score"]
            or _plain(entry.get("components")) != _plain(result["components"])
            or list(entry.get("warnings", ())) != list(result["warnings"])
        ):
            raise ContractError("ranked entry does not faithfully preserve its ScoreResult")
    expected_excluded = [
        item for item in results.values() if item["status"] != "scored"
    ]
    expected_excluded.sort(key=lambda item: str(item["instrument_id"]))
    excluded = payload["excluded_entries"]
    if [item["score_result_id"] for item in excluded] != [
        item["score_result_id"] for item in expected_excluded
    ]:
        raise ContractError("RankingSnapshot exclusions do not match unscored results")
    for entry, result in zip(excluded, expected_excluded):
        if (
            entry.get("instrument_id") != result["instrument_id"]
            or entry.get("gate_event_id") != result["gate_event_id"]
            or entry.get("reason") != result["exclusion_reason"]
            or list(entry.get("warnings", ())) != list(result["warnings"])
            or list(entry.get("missing_facts", ())) != list(result["missing_facts"])
        ):
            raise ContractError("excluded entry does not faithfully preserve its ScoreResult")
    if [_plain(item) for item in payload["selected_entries"]] != [
        _plain(item) for item in ranked[: len(payload["selected_entries"])]
    ]:
        raise ContractError("selected entries must preserve the exact ranking prefix")


@dataclass(frozen=True)
class RankingRun:
    score_batch: ScoreBatch
    snapshot: Mapping[str, Any]


def produce_ranking_snapshot(
    score_batch: ScoreBatch,
    *,
    generated_at: str,
    ranking_role: str = "shadow",
    activation: Mapping[str, Any] | None = None,
    comparison_to_snapshot_id: str | None = None,
    ranking_policy: Mapping[str, Any] = RANKING_POLICY,
    authority_policy: Mapping[str, Any] = AUTHORITY_POLICY,
) -> Mapping[str, Any]:
    """Create the only complex main ranking from immutable ScoreResults."""

    validate_score_batch(score_batch)
    validate_policy(ranking_policy, expected_kind="ranking")
    validate_policy(authority_policy, expected_kind="authority")
    if ranking_policy["rules"].get("accepted_score_policy_version") != score_batch.score_policy_version:
        raise ContractError("ranking policy does not accept this score policy")
    if ranking_policy["rules"].get("context_effect") != "none":
        raise ContractError("M07 v1 ranking cannot use context to change order")
    if ranking_policy["rules"].get("favorite_pattern_effect") != "none":
        raise ContractError("favorite pattern cannot enter the complex main ranking")
    if ranking_role == "authoritative":
        _validate_authority_activation(
            activation,
            score_batch=score_batch,
            ranking_policy=ranking_policy,
            authority_policy=authority_policy,
        )
        if score_batch.as_of < activation["effective_from"]:
            raise ContractError("V2 cannot become authoritative before its approved effective date")
    elif activation is not None:
        raise ContractError("only authoritative rankings may carry activation")
    if ranking_role == "comparison" and comparison_to_snapshot_id is None:
        raise ContractError("historical V2 comparison must reference the original snapshot")
    if ranking_role != "comparison" and comparison_to_snapshot_id is not None:
        raise ContractError("only comparison rankings may reference an original snapshot")
    scored = [item for item in score_batch.results if item["status"] == "scored"]
    excluded_results = [item for item in score_batch.results if item["status"] != "scored"]
    scored.sort(key=lambda item: (
        -int(item["total_score"]),
        -int(item["metrics"]["timeframe_resonance_bonus"]),
        -int(item["metrics"]["family_count"]),
        -int(item["metrics"]["positive_hit_count"]),
        str(item["instrument_id"]),
    ))
    ranked_entries: list[dict[str, Any]] = []
    for rank, result in enumerate(scored, 1):
        sort_key = [
            {"field": "total_score", "direction": "desc", "value": result["total_score"]},
            {"field": "timeframe_resonance_bonus", "direction": "desc", "value": result["metrics"]["timeframe_resonance_bonus"]},
            {"field": "family_count", "direction": "desc", "value": result["metrics"]["family_count"]},
            {"field": "positive_hit_count", "direction": "desc", "value": result["metrics"]["positive_hit_count"]},
            {"field": "instrument_id", "direction": "asc", "value": result["instrument_id"]},
        ]
        ranked_entries.append({
            "rank": rank,
            "instrument_id": result["instrument_id"],
            "gate_event_id": result["gate_event_id"],
            "score_result_id": result["score_result_id"],
            "total_score": result["total_score"],
            "components": _plain(result["components"]),
            "warnings": list(result["warnings"]),
            "sort_key": sort_key,
        })
    excluded_entries = [
        {
            "instrument_id": result["instrument_id"],
            "gate_event_id": result["gate_event_id"],
            "score_result_id": result["score_result_id"],
            "reason": result["exclusion_reason"],
            "warnings": list(result["warnings"]),
            "missing_facts": list(result["missing_facts"]),
        }
        for result in sorted(excluded_results, key=lambda item: str(item["instrument_id"]))
    ]
    limit = ranking_policy["rules"].get("selected_limit")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
        raise ContractError("ranking selected_limit must be a non-negative integer")
    selected_entries = [dict(item) for item in ranked_entries[:limit]]
    score_ids = sorted(str(item["score_result_id"]) for item in score_batch.results)
    universes = {str(item["input_identity"]["universe_id"]) for item in score_batch.results}
    markets = {str(item["input_identity"]["market_snapshot_id"]) for item in score_batch.results}
    if len(universes) > 1 or len(markets) > 1:
        raise ContractError("RankingSnapshot cannot mix universe or market identities")
    payload: dict[str, Any] = {
        "schema_version": RANKING_SNAPSHOT_SCHEMA_VERSION,
        "as_of": score_batch.as_of,
        "generated_at": generated_at,
        "source_version": {"ranking_producer": RANKING_PRODUCER_VERSION},
        "future_data_used": False,
        "path_status": "formal",
        "authority_scope": "complex_multifactor_main",
        "ranking_role": ranking_role,
        "input_identity": {
            "score_batch_id": score_batch.batch_id,
            "score_policy_fingerprint": score_batch.score_policy_fingerprint,
            "universe_id": next(iter(universes), "universe:empty"),
            "market_snapshot_id": next(iter(markets), "market:empty"),
        },
        "score_policy_version": score_batch.score_policy_version,
        "score_policy_fingerprint": score_batch.score_policy_fingerprint,
        "ranking_policy_version": ranking_policy["policy_version"],
        "ranking_policy_fingerprint": ranking_policy["policy_fingerprint"],
        "authority_policy_version": authority_policy["policy_version"],
        "authority_policy_fingerprint": authority_policy["policy_fingerprint"],
        "activation": _plain(activation) if activation is not None else None,
        "comparison_to_snapshot_id": comparison_to_snapshot_id,
        "score_result_ids": score_ids,
        "score_results": [_plain(item) for item in score_batch.results],
        "input_count": len(score_ids),
        "ranked_entries": ranked_entries,
        "excluded_entries": excluded_entries,
        "selected_entries": selected_entries,
    }
    payload["ranking_snapshot_id"] = "ranking:" + canonical_fingerprint(_ranking_identity(payload))
    payload["ranking_content_fingerprint"] = canonical_fingerprint(
        _semantic(payload, "ranking_content_fingerprint")
    )
    validate_ranking_snapshot(payload)
    return _freeze(payload)


def produce_versioned_ranking(
    *,
    gate_events: Iterable[Mapping[str, Any]],
    technical_evidence: TechnicalEvidenceBatch,
    model_assessments: ModelAssessmentBatch,
    contexts: ContextBatch,
    generated_at: str,
    score_policy: Mapping[str, Any] = SCORE_POLICY,
    ranking_policy: Mapping[str, Any] = RANKING_POLICY,
    authority_policy: Mapping[str, Any] = AUTHORITY_POLICY,
    ranking_role: str = "shadow",
    activation: Mapping[str, Any] | None = None,
    comparison_to_snapshot_id: str | None = None,
) -> RankingRun:
    scores = produce_score_results(
        gate_events=gate_events,
        technical_evidence=technical_evidence,
        model_assessments=model_assessments,
        contexts=contexts,
        generated_at=generated_at,
        score_policy=score_policy,
    )
    snapshot = produce_ranking_snapshot(
        scores,
        generated_at=generated_at,
        ranking_role=ranking_role,
        activation=activation,
        comparison_to_snapshot_id=comparison_to_snapshot_id,
        ranking_policy=ranking_policy,
        authority_policy=authority_policy,
    )
    return RankingRun(score_batch=scores, snapshot=snapshot)


__all__ = [
    "RANKING_PRODUCER_VERSION",
    "RANKING_SNAPSHOT_SCHEMA_VERSION",
    "SCORE_RESULT_SCHEMA_VERSION",
    "RankingRun",
    "ScoreBatch",
    "build_authority_activation",
    "produce_ranking_snapshot",
    "produce_score_results",
    "produce_versioned_ranking",
    "validate_ranking_snapshot",
    "validate_score_batch",
    "validate_score_result",
]
