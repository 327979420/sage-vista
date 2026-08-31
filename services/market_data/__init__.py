"""Business-neutral, shadow-only market-data tools introduced by M02."""

from .consumer import (
    ShadowConsumerInput,
    open_internal_shadow_repository,
    prepare_shadow_consumer_input,
    require_shadow_rows,
)
from .legacy import LEGACY_ADAPTER_VERSION, LegacyCacheRead, read_legacy_cache
from .normalization import (
    ADJUSTMENT_POLICY,
    adjusted_point_in_time_rows,
    bars_fingerprint,
    validate_adjusted_rows,
    validate_raw_rows,
)
from .repository import MarketDataRepository, MarketDataSource, RepositoryRead
from .universe import (
    UniverseSnapshotStore,
    build_forward_universe_snapshot,
    build_universe_snapshot,
)

__all__ = [
    "ADJUSTMENT_POLICY",
    "LEGACY_ADAPTER_VERSION",
    "LegacyCacheRead",
    "MarketDataRepository",
    "MarketDataSource",
    "RepositoryRead",
    "ShadowConsumerInput",
    "UniverseSnapshotStore",
    "adjusted_point_in_time_rows",
    "bars_fingerprint",
    "build_forward_universe_snapshot",
    "build_universe_snapshot",
    "open_internal_shadow_repository",
    "prepare_shadow_consumer_input",
    "require_shadow_rows",
    "read_legacy_cache",
    "validate_adjusted_rows",
    "validate_raw_rows",
]
