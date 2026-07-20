# ADR-007: Durable Operational Audit Table

## Status

Accepted — 2026-07-14

## Context

Sprint 3 requires one auditable row per DAG execution with local JSON reconciliation.

## Decision

Create `atlas_ops.pipeline_runs` now (not deferred to Composer). Split initialization:
`ensure_audit_resources` → `start_run_audit` → `preflight_environment`.
Finalizer upserts terminal status and raises on `FAILED`/`PARTIAL`.

## Consequences

- MERGE keyed on `pipeline_run_id` supports idempotent finalization.
- Error messages sanitized and truncated to 2,000 characters.
