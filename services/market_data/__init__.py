"""Business-neutral, shadow-only market-data tools introduced by M02."""

from .legacy import LEGACY_ADAPTER_VERSION, LegacyCacheRead, read_legacy_cache
from .normalization import (
    ADJUSTMENT_POLICY,
    adjusted_point_in_time_rows,
    bars_fingerprint,
    validate_raw_rows,
)

__all__ = [
    "ADJUSTMENT_POLICY",
    "LEGACY_ADAPTER_VERSION",
    "LegacyCacheRead",
    "adjusted_point_in_time_rows",
    "bars_fingerprint",
    "read_legacy_cache",
    "validate_raw_rows",
]
