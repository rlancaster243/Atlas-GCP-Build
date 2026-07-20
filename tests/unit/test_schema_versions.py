"""Multi-version event schema tests (Sprint 6, S6-SCH-008)."""

from __future__ import annotations

from typing import Any

import pytest

from atlas.validation.schema_versions import (
    CURRENT_SCHEMA_VERSION,
    SchemaVersionError,
    detect_schema_version,
    normalize_event,
)


def _v1_event(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "event_id": "e-1",
        "event_type": "page_view",
        "event_timestamp": "2026-07-19T00:00:00+00:00",
        "user_id": "u-1",
        "country_code": "US",
        "device_type": "mobile",
        "session_id": "s-1",
        "payload_size_bytes": 512,
        "batch_id": "atlas-s6-sch008",
        "processing_date": "2026-07-19",
    }
    base.update(overrides)
    return base


def test_missing_discriminator_means_version_1() -> None:
    assert detect_schema_version(_v1_event()) == 1


def test_v2_discriminator_detected() -> None:
    assert detect_schema_version(_v1_event(schema_version=2, client_app_version="3.1.0")) == 2


def test_unknown_version_rejected_not_guessed() -> None:
    with pytest.raises(SchemaVersionError, match="unsupported schema_version 99"):
        detect_schema_version(_v1_event(schema_version=99))


def test_non_integer_version_rejected() -> None:
    with pytest.raises(SchemaVersionError, match="not an integer"):
        detect_schema_version(_v1_event(schema_version="latest"))


def test_v1_normalizes_with_explicit_nulls_for_newer_fields() -> None:
    normalized = normalize_event(_v1_event())
    assert normalized["schema_version"] == 1
    assert normalized["client_app_version"] is None
    assert normalized["event_id"] == "e-1"


def test_v2_normalizes_to_current_shape() -> None:
    normalized = normalize_event(_v1_event(schema_version=2, client_app_version="3.1.0"))
    assert normalized["schema_version"] == CURRENT_SCHEMA_VERSION
    assert normalized["client_app_version"] == "3.1.0"


def test_normalized_shape_is_identical_across_versions() -> None:
    v1_keys = set(normalize_event(_v1_event()))
    v2_keys = set(normalize_event(_v1_event(schema_version=2, client_app_version=None)))
    assert v1_keys == v2_keys


def test_unknown_field_rejected_no_silent_coercion() -> None:
    with pytest.raises(SchemaVersionError, match="not part of schema version 1"):
        normalize_event(_v1_event(surprise_field="boo"))


def test_v2_only_field_rejected_on_v1_event() -> None:
    """A v1 event smuggling a v2 field is rejected — versions are explicit."""
    with pytest.raises(SchemaVersionError, match="not part of schema version 1"):
        normalize_event(_v1_event(client_app_version="3.1.0"))
