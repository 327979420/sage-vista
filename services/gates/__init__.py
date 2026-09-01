"""M03 shadow-only unique gate and long-term fact boundary."""

from .producer import (
    GATE_POLICY_VERSION,
    GateBatch,
    GateEventStore,
    produce_gate_batch,
    require_gate_event_for_path,
    validate_gate_event,
)

__all__ = [
    "GATE_POLICY_VERSION",
    "GateBatch",
    "GateEventStore",
    "produce_gate_batch",
    "require_gate_event_for_path",
    "validate_gate_event",
]

