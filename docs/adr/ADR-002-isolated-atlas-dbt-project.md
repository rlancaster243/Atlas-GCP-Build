# ADR-002: Isolated Atlas dbt Project Location

## Status

Accepted

## Context

The repository already contains a DEOS dbt scaffold at `transform/dbt/`. Sprint 2 needs an
Atlas-specific warehouse with BigQuery datasets, anomaly classification, and quarantine
semantics that must not collide with the DEOS validation project.

## Decision

Create a nested dbt project at `dbt/atlas_dbt/` with its own virtual
environment, package lock, and `dbt-atlas` MCP entry. Leave `transform/dbt/` unchanged.

## Consequences

- Atlas operators use `scripts/setup_dbt.sh` and `.venv-dbt`.
- DEOS operators continue using the root `.venv` and existing dbt MCP server.
- Documentation must clearly distinguish the two projects.
