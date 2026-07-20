"""Event schema-version discrimination and normalization (Sprint 6, ADR-015).

Atlas raw events carry an optional ``schema_version`` discriminator (absent
means version 1, the Sprint 1 contract). Normalization maps every supported
version onto the current logical schema explicitly:

- unknown versions are rejected, never guessed;
- unknown fields are rejected, never silently dropped (no silent coercion);
- fields added by a newer version are backfilled as None for older inputs so
  consumers see one stable shape with explicit nullability.
"""

from __future__ import annotations

from typing import Any

# Version 1: the original Sprint 1 event contract.
_V1_FIELDS = frozenset(
    {
        "event_id",
        "event_type",
        "event_timestamp",
        "user_id",
        "country_code",
        "device_type",
        "session_id",
        "payload_size_bytes",
        "batch_id",
        "processing_date",
    }
)

# Version 2: version 1 plus one approved additive nullable field (S6-SCH-001
# flow). The discriminator itself is part of the v2 contract.
_V2_ONLY_FIELDS = frozenset({"schema_version", "client_app_version"})

SUPPORTED_SCHEMA_VERSIONS: dict[int, frozenset[str]] = {
    1: _V1_FIELDS,
    2: _V1_FIELDS | _V2_ONLY_FIELDS,
}
CURRENT_SCHEMA_VERSION = 2


class SchemaVersionError(ValueError):
    """An event failed schema-version discrimination or normalization."""


def detect_schema_version(event: dict[str, Any]) -> int:
    """Return the event's declared version (absent discriminator == 1)."""
    raw = event.get("schema_version", 1)
    try:
        version = int(raw)
    except (TypeError, ValueError) as exc:
        raise SchemaVersionError(f"schema_version {raw!r} is not an integer") from exc
    if version not in SUPPORTED_SCHEMA_VERSIONS:
        raise SchemaVersionError(
            f"unsupported schema_version {version}; supported: {sorted(SUPPORTED_SCHEMA_VERSIONS)}"
        )
    return version


def normalize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Map one event of any supported version onto the current logical schema."""
    version = detect_schema_version(event)
    allowed = SUPPORTED_SCHEMA_VERSIONS[version]
    unknown = set(event) - allowed
    if unknown:
        raise SchemaVersionError(
            f"fields {sorted(unknown)} are not part of schema version {version}; "
            "unknown fields are rejected, not silently coerced"
        )
    current_fields = SUPPORTED_SCHEMA_VERSIONS[CURRENT_SCHEMA_VERSION]
    normalized = {field: event.get(field) for field in sorted(current_fields)}
    normalized["schema_version"] = version
    return normalized
