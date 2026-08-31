"""Shared, business-neutral data contracts for Sage Vista."""

from .adapters import AdaptedArtifact, adapt_legacy_file
from .manifest import build_shadow_manifest, verify_shadow_manifest, write_shadow_manifest
from .validation import ContractError, validate_contract, validate_contracts

__all__ = [
    "AdaptedArtifact",
    "ContractError",
    "adapt_legacy_file",
    "build_shadow_manifest",
    "validate_contract",
    "validate_contracts",
    "verify_shadow_manifest",
    "write_shadow_manifest",
]
