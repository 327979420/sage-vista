"""M05 shadow-only unique ModelAssessment boundary."""

from .adapters import adapt_legacy_model_assessment
from .producer import (
    MODEL_ASSESSMENT_SCHEMA_VERSION,
    SELECTOR_POLICY_VERSION,
    ModelAssessmentBatch,
    produce_model_assessments,
    validate_model_assessment,
    validate_model_assessment_batch,
)

__all__ = [
    "MODEL_ASSESSMENT_SCHEMA_VERSION",
    "SELECTOR_POLICY_VERSION",
    "ModelAssessmentBatch",
    "adapt_legacy_model_assessment",
    "produce_model_assessments",
    "validate_model_assessment",
    "validate_model_assessment_batch",
]
