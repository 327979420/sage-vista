"""M11 evidence gate over persisted M09 and M10 authority stores."""

from __future__ import annotations

import json
from pathlib import Path
import stat
from typing import AbstractSet, Any, Mapping, Sequence

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import ContractError
from services.evaluation import EvaluationShadowStore, current_experiment_run, validate_result
from services.evaluation.contracts import RESULT_TYPES
from services.ledger import EventLedgerStore, validate_human_review, validate_opportunity_event

from .contracts import (
    build_strategy_evidence_assessment,
    current_strategy_assessment,
    plain,
    validate_strategy_proposal,
)


def _read_object(path: Path) -> Mapping[str, Any]:
    try:
        mode = path.lstat().st_mode
        raw = path.read_bytes()
    except OSError as exc:
        raise ContractError("M11 persisted evidence cannot be read") from exc
    if path.is_symlink() or not stat.S_ISREG(mode):
        raise ContractError("M11 persisted evidence must be a regular file")
    try:
        payload = json.loads(raw, parse_constant=lambda value: (_ for _ in ()).throw(ContractError(f"non-finite JSON {value}")))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ContractError("M11 persisted evidence is not valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise ContractError("M11 persisted evidence must be an object")
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"
    if raw != canonical:
        raise ContractError("M11 persisted evidence must be canonical JSON")
    return payload


def _ledger_authority(
    store: EventLedgerStore,
    *,
    known_approval_refs: AbstractSet[str],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, Mapping[str, Any]], str]:
    events: dict[str, Mapping[str, Any]] = {}
    event_root = store.root / "events"
    if event_root.exists():
        for path in sorted(event_root.glob("*/*.json")):
            event = _read_object(path)
            validate_opportunity_event(event)
            event_id = str(event["event_id"])
            if event_id in events:
                raise ContractError("M11 found duplicate persisted M09 events")
            events[event_id] = event
    reviews: dict[str, Mapping[str, Any]] = {}
    review_root = store.root / "human-reviews"
    if review_root.exists():
        for path in sorted(review_root.glob("*/*.json")):
            review = _read_object(path)
            validate_human_review(
                review,
                known_event_ids=set(events),
                known_approval_refs=known_approval_refs,
                require_known_subject=True,
            )
            review_id = str(review["review_id"])
            if review_id in reviews:
                raise ContractError("M11 found duplicate persisted M09 reviews")
            reviews[review_id] = review
    fingerprint = canonical_fingerprint({
        "events": [{"id": key, "content_fingerprint": value["event_content_fingerprint"]} for key, value in sorted(events.items())],
        "reviews": [{"id": key, "content_fingerprint": value["review_content_fingerprint"]} for key, value in sorted(reviews.items())],
    })
    return events, reviews, fingerprint


def _result_meta(contract_name: str, result: Mapping[str, Any]) -> dict[str, str]:
    id_field, fingerprint_field, _, _ = RESULT_TYPES[contract_name]
    return {
        "contract": contract_name,
        "id": str(result[id_field]),
        "logical_id": str(result["logical_result_id"]),
        "content_fingerprint": str(result[fingerprint_field]),
        "run_id": str(result["run_id"]),
    }


def _criterion_result(criterion: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    field = str(criterion["field"])
    if "." in field or field not in result:
        actual = None
        status = "unavailable"
    else:
        actual = result[field]
        expected = criterion["expected"]
        operator = criterion["operator"]
        if actual is None:
            status = "unavailable"
        elif operator == "eq":
            status = "passed" if actual == expected else "failed"
        elif isinstance(actual, bool) or isinstance(expected, bool):
            status = "failed"
        elif operator == "gte":
            status = "passed" if actual >= expected else "failed"
        else:
            status = "passed" if actual <= expected else "failed"
    return {
        "criterion_id": criterion["criterion_id"],
        "status": status,
        "actual": actual,
        "evidence_ref": plain(criterion["result_ref"]),
    }


def assess_persisted_strategy_evidence(
    proposal: Mapping[str, Any],
    *,
    ledger_store: EventLedgerStore,
    evaluation_store: EvaluationShadowStore,
    run_ids: Sequence[str],
    assessed_at: str,
    supersedes_assessment: Mapping[str, Any] | None = None,
    known_approval_refs: AbstractSet[str] = frozenset(),
) -> Mapping[str, Any]:
    """Assess only canonical evidence actually present in the M09/M10 stores."""

    validate_strategy_proposal(proposal)
    events, reviews, ledger_fingerprint = _ledger_authority(
        ledger_store, known_approval_refs=known_approval_refs
    )
    for expected in proposal["m09_review_refs"]:
        actual = reviews.get(str(expected["id"]))
        if actual is None:
            raise ContractError("proposal M09 review is not persisted")
        if (
            actual["review_content_fingerprint"] != expected["content_fingerprint"]
            or actual["review_type"] != expected["review_type"]
        ):
            raise ContractError("proposal M09 review evidence does not match storage")
    for case in proposal["case_roles"]:
        if str(case["event_id"]) not in events:
            raise ContractError("proposal case event is not persisted in M09")

    inventory = evaluation_store.capture_inventory()
    run_groups: dict[str, list[Mapping[str, Any]]] = {}
    for receipt in inventory.run_receipts:
        run_groups.setdefault(str(receipt["run_id"]), []).append(receipt)
    result_by_id: dict[str, tuple[str, Mapping[str, Any]]] = {}
    result_by_run: dict[str, list[tuple[str, Mapping[str, Any]]]] = {}
    for contract_name, result in inventory.result_records:
        validate_result(contract_name, result)
        id_field, _, _, _ = RESULT_TYPES[contract_name]
        result_by_id[str(result[id_field])] = (contract_name, result)
        result_by_run.setdefault(str(result["run_id"]), []).append((contract_name, result))

    requested = sorted(set(run_ids))
    if len(requested) != len(run_ids) or not requested:
        raise ContractError("M11 run selection must be non-empty and unique")
    run_refs: list[dict[str, str]] = []
    selected_results: list[tuple[str, Mapping[str, Any]]] = []
    partitions: set[str] = set()
    incomplete: list[str] = []
    for run_id in requested:
        receipts = run_groups.get(run_id)
        if not receipts:
            raise ContractError("M11 cannot assess an unpersisted ExperimentRun")
        leaf = current_experiment_run(receipts)
        if leaf["status"] != "completed":
            incomplete.append("experiment_run_not_completed")
        partitions.add(str(leaf["partition_role"]))
        if leaf["path_status"] != "formal" or leaf["result_role"] != "authoritative" or leaf["bias_labels"]:
            incomplete.append("nonformal_or_biased_evidence")
        input_roles = {str(item["id"]).split(":", 1)[0] for item in leaf["input_refs"]}
        policy_kinds = {str(item["policy_kind"]) for item in leaf["policy_refs"]}
        if not {"market", "universe"}.issubset(input_roles) or "adjustment" not in policy_kinds:
            incomplete.append("data_universe_or_adjustment_evidence_missing")
        if proposal["preregistration"]["requires_cost_policy"] and "cost_slippage" not in policy_kinds:
            incomplete.append("cost_slippage_evidence_missing")
        actual_for_run = result_by_run.get(run_id, [])
        actual_refs = sorted(
            [{"id": _result_meta(name, item)["id"], "content_fingerprint": _result_meta(name, item)["content_fingerprint"]} for name, item in actual_for_run],
            key=lambda item: (item["id"], item["content_fingerprint"]),
        )
        if actual_refs != plain(leaf["result_refs"]):
            raise ContractError("M11 completed run does not conserve persisted results")
        selected_results.extend(actual_for_run)
        run_refs.append({
            "run_id": str(leaf["run_id"]),
            "run_receipt_id": str(leaf["run_receipt_id"]),
            "content_fingerprint": str(leaf["run_content_fingerprint"]),
            "partition_role": str(leaf["partition_role"]),
        })

    required_partitions = set(proposal["preregistration"]["required_partitions"])
    if not required_partitions.issubset(partitions):
        incomplete.append("required_partition_missing")
    independent_cases = [
        item for item in proposal["case_roles"]
        if item["role"] in {"validation", "forward"} and not item["seen_before"]
    ]
    if not independent_cases:
        incomplete.append("independent_validation_or_forward_missing")

    selected_meta = [_result_meta(name, item) for name, item in selected_results]
    selected_ids = {item["id"] for item in selected_meta}
    required_contracts = set(proposal["preregistration"]["required_result_contracts"])
    if not required_contracts.issubset({item["contract"] for item in selected_meta}):
        incomplete.append("required_result_contract_missing")
    criteria_results: list[dict[str, Any]] = []
    for criterion in proposal["preregistration"]["criteria"]:
        evidence_id = str(criterion["result_ref"]["id"])
        stored = result_by_id.get(evidence_id)
        if stored is None or evidence_id not in selected_ids:
            criteria_results.append({
                "criterion_id": criterion["criterion_id"], "status": "unavailable",
                "actual": None, "evidence_ref": plain(criterion["result_ref"]),
            })
            incomplete.append("criterion_evidence_missing")
            continue
        _, result = stored
        meta = _result_meta(stored[0], result)
        if meta["content_fingerprint"] != criterion["result_ref"]["content_fingerprint"]:
            raise ContractError("criterion reference fingerprint differs from persisted result")
        criteria_results.append(_criterion_result(criterion, result))

    statuses = {item["status"] for item in criteria_results}
    if incomplete or "unavailable" in statuses:
        evidence_state = "evidence_incomplete"
        reasons = sorted(set(incomplete or ["criterion_unavailable"]))
    elif "failed" in statuses:
        evidence_state = "invalidated" if supersedes_assessment is not None and supersedes_assessment["evidence_state"] == "validated" else "not_validated"
        reasons = ["preregistered_criterion_failed"]
    else:
        evidence_state = "validated"
        reasons = []
    if supersedes_assessment is not None:
        current_strategy_assessment([supersedes_assessment])
        if supersedes_assessment["proposal_id"] != proposal["proposal_id"]:
            raise ContractError("assessment revision crosses proposals")

    missing_count = sum(
        item["status"] in {"pending", "unavailable", "no_trade"}
        for _, item in selected_results
    )
    combined_inventory = canonical_fingerprint({
        "m09": ledger_fingerprint,
        "m10": inventory.evidence["source_inventory_fingerprint"],
    })
    return build_strategy_evidence_assessment(
        as_of=assessed_at[:10], generated_at=assessed_at, assessed_at=assessed_at,
        supersedes_assessment_id=(supersedes_assessment["assessment_id"] if supersedes_assessment else None),
        proposal_id=proposal["proposal_id"],
        proposal_content_fingerprint=proposal["proposal_content_fingerprint"],
        strategy_id=proposal["strategy_id"], strategy_version=proposal["strategy_version"],
        candidate_version=proposal["candidate_version"], baseline_version=proposal["baseline_version"],
        preregistration_ref={"id": proposal["preregistration"]["preregistration_id"], "content_fingerprint": proposal["preregistration"]["content_fingerprint"]},
        inventory_fingerprint=combined_inventory,
        run_refs=run_refs, result_refs=selected_meta, partitions=sorted(partitions),
        criteria_results=criteria_results,
        case_roles=[{"event_id": item["event_id"], "role": item["role"]} for item in proposal["case_roles"]],
        sample_count=len(selected_results), missing_count=missing_count,
        cost_policy_status=("approved" if proposal["preregistration"]["requires_cost_policy"] else "not_required"),
        evidence_state=evidence_state, state_reasons=reasons,
        bias_labels=([] if not incomplete else sorted(set(reason for reason in incomplete if "biased" in reason))),
    )


__all__ = ["assess_persisted_strategy_evidence"]
