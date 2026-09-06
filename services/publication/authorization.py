"""Pure construction of an archived approval; no permission check or I/O."""

from copy import deepcopy
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import publication_authorization_body, validate_contract


def build_publication_authorization(
    evidence: Mapping[str, Any], *, generated_at: str,
) -> dict[str, Any]:
    """Bind trusted approval evidence without enabling any production action."""
    frozen = deepcopy(evidence)
    body = publication_authorization_body(frozen)
    fingerprint = canonical_fingerprint(body)
    payload = {
        **body,
        "authorization_id": "publication-authorization:" + fingerprint,
        "content_fingerprint": fingerprint,
        "generated_at": generated_at,
    }
    validate_contract("PublicationAuthorization", payload, publication_authorization_evidence=frozen)
    return payload
