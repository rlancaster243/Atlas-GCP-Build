# ADR-016: Governance Source of Truth

- Status: Accepted (Sprint 7)
- Date: 2026-07-19
- Deciders: lead data architect, governance engineer, data engineering

## Context

Through Sprint 6, Atlas ownership, grain, classification, and retention lived
implicitly in code, dbt descriptions, and prose docs. There was no single,
enforceable place that answered "who owns this, what is its grain, who consumes
it, how long is it retained." A governance system that duplicates this metadata
in multiple files rots immediately; a governance system that CI ignores is
decorative.

## Decision

**One source of truth per asset kind, with a generated consolidated catalog.**

1. **dbt models** are governed by their dbt `meta.governance` block in the
   model's property YAML. dbt already owns model grain (via `description`),
   contracts, and tests; governance metadata lives alongside them. The dbt
   `description` is the authoritative `purpose`; it is not duplicated.

2. **Non-dbt assets** (raw/operational tables, buckets, DAGs, dashboards, log
   resources) are governed by `governance/non_dbt_assets.yml`.

3. A **generated catalog** (`governance/generated/catalog.json` + `.md`) is
   derived from both sources by `python -m atlas.governance.catalog generate`.
   It is never hand-edited. CI (`gate_governance`) fails if the committed
   catalog is stale or if an asset id appears in both sources.

Required fields for every major asset: `asset_id`, `asset_type`, `purpose`,
`technical_owner`, `business_owner_or_role`, `grain`, `source`, `consumers`,
`classification`, `retention_class`, `freshness_expectation`, `contract_version`,
`lifecycle_status`, `repository_path`, `runbook`, `last_reviewed`.

Controlled vocabularies (asset types, lifecycle statuses, classifications,
retention classes, compatibility classes) live in `governance/policy.yml` and
are enforced by `atlas.governance.registry.validate_governance`.

Owners must be **role identifiers**, not personal email addresses — this keeps
ownership durable across staffing and avoids committing personal data.

## Alternatives considered

- **A standalone catalog service / metadata platform (DataHub, OpenMetadata).**
  Rejected: explicitly out of scope for Sprint 7; repository artifacts are
  sufficient at this scale and avoid a new operational dependency.
- **A single monolithic governance YAML for everything, including dbt models.**
  Rejected: it would duplicate grain/contract information dbt already owns,
  creating exactly the multi-location drift this ADR prevents.
- **JSON Schema as the only validator.** Kept as optional/documentation
  (`governance/schemas/`), but the authoritative validator is pure-Python
  (`validate_governance`) so the CI gate needs no extra dependency and can
  express cross-file invariants (single source of truth, retention permanence,
  consumer registration).

## Consequences

- Adding/changing an asset is a small, local edit plus a catalog regeneration;
  CI blocks incomplete or drifted governance.
- The catalog is a reliable, machine-readable input for lineage/impact
  (Phase 5), deprecation (Phase 6), and classification/retention (Phase 9).
- Governance validation is offline and credentialless, so it runs in PR CI.

## Honest limitations

- Consumer discovery is limited to what the repository declares
  (`governance/consumers.yml`); external/undeclared consumers are not
  auto-discovered.
- This is project-level governance, not organization-wide governance.
