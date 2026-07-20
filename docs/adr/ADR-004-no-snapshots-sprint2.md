# ADR-004: Omission of dbt Snapshots in Sprint 2

## Status

Accepted

## Context

Project Atlas Sprint 2 focuses on governed staging, classification, quarantine, and trusted
facts/marts over an immutable raw landing table. Historical slowly-changing tracking for
users and countries is out of scope for the first warehouse sprint.

## Decision

Do not add dbt snapshots in Sprint 2. User and country dimensions are rebuilt from accepted
events and the country seed on each build. Incremental behavior is limited to `fct_events`.

## Consequences

- Faster delivery of classification and reconciliation gates.
- Future sprints can introduce snapshots or Type 2 dimensions if product requirements change.
- Airflow handoff can trigger full dimension rebuilds until snapshot coverage exists.
