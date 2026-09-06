"""Pure construction of an archived approval; no permission check or I/O."""

from copy import deepcopy
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import publication_approval_archive_body, publication_authorization_body, validate_contract


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


def build_publication_authorization_from_archive(
    archive: Mapping[str, Any], approval_evidence_ref: Mapping[str, Any], *,
    history: list[Mapping[str, Any]], generated_at: str,
) -> dict[str, Any]:
    """Require full internally retrieved archive evidence; never register a grant.

    The runtime must supply B2g's controlled read and a trusted complete history.
    This pure constructor does not authenticate arbitrary caller-created bytes.
    """
    frozen_archive = deepcopy(archive)
    frozen_ref = deepcopy(approval_evidence_ref)
    bound = publication_approval_archive_body(frozen_archive, frozen_ref)
    evidence = {**bound, "approval_archive": frozen_archive, "approval_evidence_ref": frozen_ref,
                "history": deepcopy(history)}
    return build_publication_authorization(evidence, generated_at=generated_at)
