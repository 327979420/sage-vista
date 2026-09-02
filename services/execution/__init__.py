"""M08 shadow-only versioned trade planning and exit-state boundary."""

from .adapters import LegacyExecutionEvidence, adapt_legacy_support_plan_bytes
from .policies import EXIT_POLICY, PLAN_POLICY, build_policy, validate_policy
from .producer import (
    EXIT_STATE_SCHEMA_VERSION,
    TRADE_PLAN_SCHEMA_VERSION,
    TradePlanBatch,
    advance_exit_state,
    current_exit_state,
    produce_trade_plans,
    validate_exit_state,
    validate_trade_plan,
    validate_trade_plan_batch,
)
from .storage import ExecutionShadowStore

__all__ = [
    "EXIT_POLICY", "PLAN_POLICY", "EXIT_STATE_SCHEMA_VERSION",
    "TRADE_PLAN_SCHEMA_VERSION", "TradePlanBatch", "advance_exit_state",
    "current_exit_state",
    "ExecutionShadowStore", "LegacyExecutionEvidence", "adapt_legacy_support_plan_bytes",
    "build_policy", "produce_trade_plans", "validate_exit_state",
    "validate_policy", "validate_trade_plan",
    "validate_trade_plan_batch",
]
