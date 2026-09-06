"""Pure CurrentPointer transitions and minimal public projection; no live CAS."""

from copy import deepcopy
from typing import Any, Mapping

from services.contracts.validation import current_pointer_body, validate_contract


def build_current_pointer(evidence: Mapping[str, Any]) -> dict[str, Any]:
    frozen = deepcopy(evidence)
    payload = current_pointer_body(frozen)
    validate_contract("CurrentPointer", payload, current_pointer_evidence=frozen)
    return payload


def public_current_pointer(payload: Mapping[str, Any], *, current_pointer_evidence: Mapping[str, Any]) -> dict[str, Any]:
    validate_contract("CurrentPointer", payload, current_pointer_evidence=current_pointer_evidence)
    return deepcopy({key: payload[key] for key in ("generation", "visible", "phase")})
