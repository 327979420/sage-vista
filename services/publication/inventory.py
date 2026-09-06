"""Construct M12 inventory from a trusted, lock-frozen index; no I/O."""

from copy import deepcopy
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import source_inventory_body, validate_contract


def build_source_inventory(
    evidence: Mapping[str, Any], *, generated_at: str,
) -> dict[str, Any]:
    """Use the unique contract derivation; never infer roots from a supplied list.

    The future production adapter must inject an authenticated frozen index.
    This builder alone is not an authorization or publication receipt.
    """
    frozen = deepcopy(evidence)
    body = source_inventory_body(frozen)
    fingerprint = canonical_fingerprint(body)
    payload = {
        **body,
        "inventory_id": "source-inventory:" + fingerprint,
        "content_fingerprint": fingerprint,
        "generated_at": generated_at,
    }
    validate_contract("SourceInventory", payload, source_inventory_evidence=frozen)
    return payload
