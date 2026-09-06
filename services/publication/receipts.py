"""Construct immutable receipts from trusted observations; never execute actions."""

from copy import deepcopy
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import publication_receipt_body, validate_contract


def build_publication_receipt(evidence: Mapping[str, Any], *, generated_at: str) -> dict[str, Any]:
    frozen = deepcopy(evidence)
    body = publication_receipt_body(frozen)
    fingerprint = canonical_fingerprint(body)
    payload = {**body, "receipt_id": "publication-receipt:" + fingerprint,
               "content_fingerprint": fingerprint, "generated_at": generated_at}
    validate_contract("PublicationReceipt", payload, publication_receipt_evidence=frozen)
    return payload
