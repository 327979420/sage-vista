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

from .authority import CaseAuthorityResolver, validate_case_authority
from .contracts import (
    SCHEMA_VERSION,
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


def validate_persisted_proposal_sources(
    proposal: Mapping[str, Any],
    *,
    ledger_store: EventLedgerStore,
    known_approval_refs: AbstractSet[str] = frozenset(),
    case_authority_resolver: CaseAuthorityResolver | None = None,
) -> str:
    """Revalidate a proposal's complete M09 sources from the ledger on disk."""

    validate_strategy_proposal(proposal)
    if proposal["schema_version"] != SCHEMA_VERSION:
        raise ContractError("legacy M11 proposals are read-only and cannot be assessed")
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
        event = events.get(str(case["event_id"]))
        if event is None:
            raise ContractError("proposal case event is not persisted in M09")
        validate_case_authority(case, event, case_authority_resolver)
    return ledger_fingerprint


def assess_persisted_strategy_evidence(
    proposal: Mapping[str, Any],
    *,
    ledger_store: EventLedgerStore,
    evaluation_store: EvaluationShadowStore,
    run_ids: Sequence[str],
    assessed_at: str,
    supersedes_assessment: Mapping[str, Any] | None = None,
    known_approval_refs: AbstractSet[str] = frozenset(),
    case_authority_resolver: CaseAuthorityResolver | None = None,
) -> Mapping[str, Any]:
    """Assess only canonical evidence actually present in the M09/M10 stores."""

    validate_strategy_proposal(proposal)
    events, _, ledger_fingerprint = _ledger_authority(
        ledger_store, known_approval_refs=known_approval_refs
    )
    validate_persisted_proposal_sources(
        proposal,
        ledger_store=ledger_store,
        known_approval_refs=known_approval_refs,
        case_authority_resolver=case_authority_resolver,
    )

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

    scope = proposal["preregistration"]["evidence_scope"]
    expected_run_ids = list(scope["expected_run_ids"])
    required_input_refs = {
        (str(item["id"]), str(item["content_fingerprint"]))
        for item in scope["required_input_refs"]
    }
    required_policy_refs = {
        (
            str(item["policy_kind"]), str(item["policy_version"]),
            str(item["policy_fingerprint"]),
        )
        for item in scope["required_policy_refs"]
    }
    required_partitions = set(proposal["preregistration"]["required_partitions"])
    relevant_run_ids: list[str] = []
    leaf_by_run: dict[str, Mapping[str, Any]] = {}
    for run_id, receipts in sorted(run_groups.items()):
        leaf = current_experiment_run(receipts)
        leaf_by_run[run_id] = leaf
        input_refs = {
            (str(item["id"]), str(item["content_fingerprint"]))
            for item in leaf["input_refs"]
            if str(item["id"]).split(":", 1)[0] in {"market", "universe"}
        }
        policy_refs = {
            (
                str(item["policy_kind"]), str(item["policy_version"]),
                str(item["policy_fingerprint"]),
            )
            for item in leaf["policy_refs"]
        }
        if (
            leaf["config_ref"]["config_version"]
            in {proposal["candidate_version"], proposal["baseline_version"]}
            and leaf["partition_role"] in required_partitions
            and plain(leaf["evidence_window"]) == plain(scope["evidence_window"])
            and required_input_refs == input_refs
            and required_policy_refs == policy_refs
        ):
            relevant_run_ids.append(run_id)
    relevant_run_ids.sort()
    if relevant_run_ids != expected_run_ids:
        raise ContractError(
            "M11 preregistered runs do not equal the complete authoritative scope"
        )

    requested = sorted(set(run_ids))
    if len(requested) != len(run_ids) or not requested:
        raise ContractError("M11 run selection must be non-empty and unique")
    if requested != expected_run_ids:
        raise ContractError("M11 declared run set differs from preregistered authority")
    run_refs: list[dict[str, str]] = []
    selected_results: list[tuple[str, Mapping[str, Any]]] = []
    partitions: set[str] = set()
    config_versions: set[str] = set()
    incomplete: list[str] = []
    for run_id in requested:
        receipts = run_groups.get(run_id)
        if not receipts:
            raise ContractError("M11 cannot assess an unpersisted ExperimentRun")
        leaf = leaf_by_run[run_id]
        if leaf["status"] != "completed":
            incomplete.append("experiment_run_not_completed")
        partitions.add(str(leaf["partition_role"]))
        config_versions.add(str(leaf["config_ref"]["config_version"]))
        if leaf["path_status"] != "formal" or leaf["result_role"] != "authoritative" or leaf["bias_labels"]:
            incomplete.append("nonformal_or_biased_evidence")
        input_roles = {str(item["id"]).split(":", 1)[0] for item in leaf["input_refs"]}
        for reference in leaf["input_refs"]:
            if str(reference["id"]).startswith("opportunity:"):
                event = events.get(str(reference["id"]))
                if event is None or event["event_content_fingerprint"] != reference["content_fingerprint"]:
                    raise ContractError("M10 run event evidence differs from persisted M09")
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

    if not required_partitions.issubset(partitions):
        incomplete.append("required_partition_missing")
    if not {proposal["candidate_version"], proposal["baseline_version"]}.issubset(config_versions):
        incomplete.append("candidate_or_baseline_version_evidence_missing")
    independent_cases = [
        item for item in proposal["case_roles"]
        if item["role"] in {"validation", "forward"} and not item["seen_before"]
    ]
    if not independent_cases:
        incomplete.append("independent_validation_or_forward_missing")

    selected_meta = [_result_meta(name, item) for name, item in selected_results]
    selected_logical_ids = [item["logical_id"] for item in selected_meta]
    if len(selected_logical_ids) != len(set(selected_logical_ids)):
        raise ContractError("M11 evidence repeats a logical result")
    selected_ids = {item["id"] for item in selected_meta}
    required_contracts = set(proposal["preregistration"]["required_result_contracts"])
    required_windows = set(scope["required_window_sessions"])
    for run_id in requested:
        if leaf_by_run[run_id]["status"] != "completed":
            continue
        run_results = [item for item in selected_meta if item["run_id"] == run_id]
        contracts = {item["contract"] for item in run_results}
        if contracts != required_contracts:
            raise ContractError("M11 run result family differs from preregistered scope")
        forward_windows = {
            int(result["window_sessions"])
            for name, result in selected_results
            if str(result["run_id"]) == run_id and name == "ForwardOutcome"
        }
        if "ForwardOutcome" in required_contracts and forward_windows != required_windows:
            raise ContractError("M11 Forward windows differ from preregistered scope")

    case_by_event = {
        str(item["event_id"]): item for item in proposal["case_roles"]
    }
    for _, result in selected_results:
        event_id = result.get("event_id")
        if event_id is None:
            continue
        case = case_by_event.get(str(event_id))
        stored_event = events.get(str(event_id))
        if case is None or stored_event is None:
            raise ContractError("M10 result case is outside the proposal case authority")
        if any((
            result.get("instrument_id") != case["instrument_id"],
            result.get("signal_date") != case["signal_date"],
            result.get("event_content_fingerprint")
            != case["event_content_fingerprint"],
            stored_event["instrument_id"] != case["instrument_id"],
            stored_event["signal_date"] != case["signal_date"],
            stored_event["event_content_fingerprint"]
            != case["event_content_fingerprint"],
        )):
            raise ContractError("M10 result crosses its M09 case instrument or date")
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


__all__ = ["assess_persisted_strategy_evidence", "validate_persisted_proposal_sources"]
