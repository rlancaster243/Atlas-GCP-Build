"""Sprint 7 Phase 5: lineage + consumer-impact tests."""

from __future__ import annotations

import json

from atlas.config.settings import atlas_root
from atlas.governance import impact, lineage


def test_source_reaches_mart() -> None:
    graph = lineage.build_lineage()
    downstream = graph.transitive_downstream("atlas_raw.events")
    assert "stg_events" in downstream
    assert "fct_events" in downstream
    assert "mart_daily_event_metrics" in downstream


def test_fct_events_upstream_includes_source() -> None:
    graph = lineage.build_lineage()
    upstream = graph.transitive_upstream("fct_events")
    assert "stg_events" in upstream
    assert "atlas_raw.events" in upstream


def test_impact_identifies_downstream_models() -> None:
    report = impact.analyze("fct_events")
    assert "mart_daily_event_metrics" in report["transitive_downstream"]
    assert "analytics_mart_readers" in report["affected_consumers"]
    assert "atlas-analytics" in report["owners_to_notify"]
    assert report["affected_tests"], "expected at least one affected test/property file"


def test_impact_of_staging_change_propagates() -> None:
    report = impact.analyze("stg_events")
    # A change to staging must surface the whole downstream chain.
    for expected in ("int_event_classification", "fct_events", "mart_daily_event_metrics"):
        assert expected in report["transitive_downstream"], expected


def test_committed_lineage_matches_fresh_generation() -> None:
    committed = json.loads((atlas_root() / "governance/generated/lineage.json").read_text())
    lineage.build_lineage.cache_clear()
    fresh = lineage.to_dict(lineage.build_lineage())
    assert committed == fresh, "committed lineage.json is stale; regenerate it"
