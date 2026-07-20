"""Atlas governance package (Sprint 7).

Governance source of truth (ADR-016):
- dbt models are governed by their dbt ``meta.governance`` blocks.
- Non-dbt assets are governed by ``governance/non_dbt_assets.yml``.
- A consolidated catalog is *generated* from both; it is never hand-edited.

This package is import-safe with no cloud dependencies so it can run in
credentialless CI.
"""

from atlas.governance.registry import (
    GovernanceError,
    build_asset_index,
    load_dbt_model_governance,
    load_non_dbt_assets,
    load_policy,
    validate_governance,
)

__all__ = [
    "GovernanceError",
    "build_asset_index",
    "load_dbt_model_governance",
    "load_non_dbt_assets",
    "load_policy",
    "validate_governance",
]
