"""M10 shadow-only immutable evaluation contracts."""

from .baseline import (
    BASELINE_ADAPTER_VERSION,
    BASELINE_ENGINE_NAME,
    BASELINE_ENGINE_VERSION,
    BASELINE_SOURCE_VERSION,
    build_session_calendar_evidence,
    market_snapshot_evidence_fingerprint,
    produce_forward_outcomes,
    produce_trade_outcome,
    validate_session_calendar_evidence,
)
from .contracts import (
    EXPERIMENT_RUN_SCHEMA_VERSION,
    RESULT_SCHEMA_VERSION,
    assert_immutable_compatible,
    build_experiment_run_receipt,
    current_experiment_run,
    current_result,
    finalize_result,
    result_input_fingerprint,
    validate_experiment_run,
    validate_result,
)
from .policies import (
    EVALUATION_POLICY,
    FORWARD_WINDOWS,
    FORWARD_WINDOW_POLICY,
    PARTITION_POLICY,
    UNAPPROVED_COST_REFERENCE,
    ZERO_COST_COMPARISON_POLICY,
)
from .runner import (
    BaselineEvaluationBatch,
    complete_baseline_run,
    evaluate_forward_baseline,
    evaluate_trade_baseline,
    store_baseline_evaluation_batch,
    validate_baseline_evaluation_batch,
)
from .storage import EvaluationShadowStore

__all__ = [
    "BASELINE_ADAPTER_VERSION", "BASELINE_ENGINE_NAME", "BASELINE_ENGINE_VERSION",
    "BASELINE_SOURCE_VERSION", "BaselineEvaluationBatch", "EVALUATION_POLICY",
    "EXPERIMENT_RUN_SCHEMA_VERSION",
    "EvaluationShadowStore",
    "FORWARD_WINDOWS",
    "FORWARD_WINDOW_POLICY", "PARTITION_POLICY", "RESULT_SCHEMA_VERSION",
    "UNAPPROVED_COST_REFERENCE", "ZERO_COST_COMPARISON_POLICY",
    "assert_immutable_compatible", "build_experiment_run_receipt",
    "build_session_calendar_evidence",
    "complete_baseline_run", "current_experiment_run", "current_result",
    "evaluate_forward_baseline", "evaluate_trade_baseline",
    "finalize_result", "market_snapshot_evidence_fingerprint",
    "produce_forward_outcomes", "produce_trade_outcome",
    "result_input_fingerprint", "store_baseline_evaluation_batch",
    "validate_experiment_run", "validate_result",
    "validate_baseline_evaluation_batch",
    "validate_session_calendar_evidence",
]
