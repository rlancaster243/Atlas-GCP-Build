"""BigQuery cost attribution for Atlas (Sprint 5, Phase 7 / ADR-012).

Attribution strategy, in evidence order:
1. Job labels (this module for Python jobs; dbt query-comment job-label for dbt).
2. Runtime identity (atlas-composer-runtime / atlas-github-* service accounts).
3. Referenced/destination Atlas datasets.

``labeled_bigquery_client`` returns a client whose default query job config
carries the bounded attribution labels, so every Atlas Python query is
attributable in region-qualified ``INFORMATION_SCHEMA.JOBS`` without touching
individual call sites' query logic. Run/batch identifiers are deliberately
excluded from job labels (unnecessary cardinality; correlation lives in
Planes 1-2).
"""

from __future__ import annotations

from google.cloud import bigquery

# Bounded label vocabulary (BigQuery label charset: lowercase, digits, _ , -).
ALLOWED_COMPONENTS = frozenset(
    {
        "pipeline",
        "monitor",
        "deployment",
        "validation",
        "audit",
        "migration",
        "ingestion",
        "adhoc",
    }
)


def attribution_labels(component: str, environment: str = "atlas-dev") -> dict[str, str]:
    """Return the standard Atlas job labels for one bounded component."""
    if component not in ALLOWED_COMPONENTS:
        raise ValueError(f"component {component!r} not in bounded set {sorted(ALLOWED_COMPONENTS)}")
    return {"application": "atlas", "component": component, "environment": environment}


def labeled_bigquery_client(
    project_id: str,
    component: str,
    environment: str = "atlas-dev",
) -> bigquery.Client:
    """BigQuery client whose queries default to Atlas attribution labels."""
    return bigquery.Client(
        project=project_id,
        default_query_job_config=bigquery.QueryJobConfig(labels=attribution_labels(component, environment)),
    )
