"""Shared, business-neutral data contracts for Sage Vista."""

from .adapters import AdaptedArtifact, adapt_legacy_bytes, adapt_legacy_file
from .manifest import build_shadow_manifest, verify_shadow_manifest, write_shadow_manifest
from .market_data import (
    canonical_fingerprint,
    forward_membership_fingerprint,
    forward_universe_snapshot_id,
    market_data_snapshot_id,
    normalize_universe_members,
    normalize_universe_qualifications,
    observed_instrument_id,
    revision_record,
    select_universe_snapshot,
    stable_instrument_id,
    universe_snapshot_id,
    validate_market_data_snapshot,
    validate_revision_chain,
    validate_universe_snapshot,
)
from .validation import ContractError, validate_contract, validate_contracts

__all__ = [
    "AdaptedArtifact",
    "ContractError",
    "adapt_legacy_bytes",
    "adapt_legacy_file",
    "build_shadow_manifest",
    "canonical_fingerprint",
    "forward_membership_fingerprint",
    "forward_universe_snapshot_id",
    "market_data_snapshot_id",
    "normalize_universe_members",
    "normalize_universe_qualifications",
    "observed_instrument_id",
    "revision_record",
    "select_universe_snapshot",
    "stable_instrument_id",
    "universe_snapshot_id",
    "validate_contract",
    "validate_contracts",
    "validate_market_data_snapshot",
    "validate_revision_chain",
    "validate_universe_snapshot",
    "verify_shadow_manifest",
    "write_shadow_manifest",
]
