"""M04 shadow-only unique TechnicalEvidence boundary."""

from .adapters import adapt_legacy_factor_state
from .producer import (
    DETECTOR_POLICY_VERSION,
    GATE_REFERENCE_FACTOR_IDS,
    TECHNICAL_EVIDENCE_SCHEMA_VERSION,
    TechnicalEvidenceBatch,
    produce_technical_evidence,
    validate_technical_evidence_batch,
    validate_technical_evidence,
)
from .support import (
    SUPPORT_EVIDENCE_SCHEMA_VERSION,
    SupportEvidenceBatch,
    produce_support_evidence,
    validate_support_evidence,
    validate_support_evidence_batch,
)

__all__ = [
    "DETECTOR_POLICY_VERSION",
    "GATE_REFERENCE_FACTOR_IDS",
    "TECHNICAL_EVIDENCE_SCHEMA_VERSION",
    "TechnicalEvidenceBatch",
    "adapt_legacy_factor_state",
    "produce_technical_evidence",
    "validate_technical_evidence_batch",
    "validate_technical_evidence",
    "SUPPORT_EVIDENCE_SCHEMA_VERSION",
    "SupportEvidenceBatch",
    "produce_support_evidence",
    "validate_support_evidence",
    "validate_support_evidence_batch",
]
