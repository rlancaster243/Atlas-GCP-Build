# ADR-019: Classification, Retention, and Disposal

- Status: Accepted (Sprint 7)
- Date: 2026-07-19
- Deciders: governance engineer, data engineering, security reviewer

## Context

Atlas had no declared data classification or retention policy; disposal relied
on GCP defaults and memory. Sprint 7 makes classification and retention explicit,
machine-validated, and safe (permanent evidence can never be accidentally
expired).

## Decision

### Classification

Four levels — PUBLIC, INTERNAL, CONFIDENTIAL, RESTRICTED
(`governance/classifications.yml`). Every governed asset declares one. Atlas
processes only synthetic data, so **no RESTRICTED assets exist**; the policy
asserts this and CI fails if a RESTRICTED asset appears while the assertion
holds. INTERNAL is the default for synthetic events and warehouse models.

### Retention classes

Seven classes (`governance/retention.yml`) with an explicit disposal policy and
an `is_permanent_evidence` flag. Retention rules distinguish canonical
(rebuildable, indefinite), operational evidence (permanent), temporary resources
(mandatory TTL), release evidence (retained), and test fixtures (ephemeral).

### Invariants (enforced by `gate_governance`)

- `policy.retention_classes` == `retention.yml` keys (single source of truth).
- Permanent-evidence classes cannot declare an expiration.
- Transient classes must declare an expiration (disposal is mandatory).
- Every asset references a defined retention class.

### Safe disposal

`atlas.governance.retention.plan_expirations()` produces a dry-run disposition
per asset (`keep_forever` vs `expire_<n>d`). A live applier must assert it never
expires a `keep_forever` asset. Live expiration/lifecycle changes require
`ATLAS_APPROVE_RETENTION_MUTATION=true`; without it, the plan and validations
are produced and the live mutation is a recorded blocked gate.

## Consequences

- Retention is declared, validated, and safe by construction — permanent audit
  and release evidence cannot be accidentally expired.
- Temporary resources have a mandatory, declared disposal.

## Honest limitations

- Retention is declared and validated in configuration; live enforcement on
  temporary datasets/buckets is applied under approval, not automatically during
  Sprint 7.
