"""Pure construction of M12 manifests over already prepared immutable bytes."""

from copy import deepcopy
from typing import Any, Mapping

from services.contracts.market_data import canonical_fingerprint
from services.contracts.validation import release_manifest_body, validate_contract


def build_release_manifest(evidence: Mapping[str, Any], *, generated_at: str) -> dict[str, Any]:
    frozen = deepcopy(evidence)
    body = release_manifest_body(frozen)
    fingerprint = canonical_fingerprint(body)
    payload = {**body, "release_id": "release:" + fingerprint,
               "content_fingerprint": fingerprint, "generated_at": generated_at}
    validate_contract("ReleaseManifest", payload, release_manifest_evidence=frozen)
    return payload
