"""Configuration package for Project Atlas."""

from atlas.config.settings import (
    AtlasSettings,
    load_settings,
    staging_table_id,
    table_fqn,
)

__all__ = [
    "AtlasSettings",
    "load_settings",
    "staging_table_id",
    "table_fqn",
]
