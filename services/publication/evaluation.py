"""Read-only evaluation projection; does not run an M10 evaluator or queue."""

from copy import deepcopy
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import evaluation_snapshot_body, validate_contract


def build_evaluation_snapshot(evidence: Mapping[str, Any], *, generated_at: str) -> dict[str, Any]:
    frozen = deepcopy(evidence)
    body = evaluation_snapshot_body(frozen)
    fingerprint = canonical_fingerprint(body)
    payload = {**body, "evaluation_snapshot_id": "evaluation-snapshot:" + fingerprint,
               "content_fingerprint": fingerprint, "generated_at": generated_at}
    validate_contract("EvaluationSnapshot", payload, evaluation_snapshot_evidence=frozen)
    return payload
