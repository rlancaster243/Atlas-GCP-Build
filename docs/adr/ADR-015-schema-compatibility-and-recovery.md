# ADR-015: Schema Compatibility and Recovery

Status: Accepted (Sprint 6)

## Context

Atlas migrations are additive by policy (ADR-010), but reality eventually
demands renames, type changes, and required-field changes. Sprint 6 must
define how such changes are classified, which ones block, and what they do to
rollback eligibility.

## Decision

### Classification (extends the Sprint 5 drift classifier)

| Change | Classification | Handling |
| --- | --- | --- |
| Configured new nullable field | ALLOWED | additive migration + manifest update + `allowed_new_fields` entry |
| Unapproved new nullable field | WARNING | contract update required before adoption |
| New REQUIRED field | BREAKING | blocked unless backfill + consumer compatibility proven |
| Removed field | BREAKING | blocked; consumer impact enumerated in the finding |
| Renamed field | BREAKING | appears as removed+new; requires a compatibility bridge (dual-write or view aliasing) and a documented deprecation period |
| Incompatible type change | BREAKING | blocked; forward migration plan required |
| REQUIRED made nullable | BREAKING | blocked pending consumer review |
| Partition-field change | BREAKING (high-risk) | never automatically applied; manual review + rebuild plan |

### Multi-version inputs

Raw events may carry a `schema_version` discriminator (absent = version 1).
`atlas.validation.schema_versions` normalizes every supported version onto
the current logical shape with explicit NULLs for fields older versions lack.
Unknown versions and unknown fields are rejected — there is no silent
coercion (S6-SCH-008).

### Rollback eligibility across migrations

The migrations manifest supports a `breaking` flag
(`<id>|<path>|breaking`). Rollback to a prior release is evaluated by
`atlas.ops.rollback_compatibility`:

- newer applied migrations that are additive → rollback eligible;
- any newer applied migration flagged `breaking` → rollback **blocked** with
  forward-recovery guidance (`ROLLBACK_INCOMPATIBLE` stage failure in the
  deploy engine);
- applied migrations the current manifest cannot classify → rollback
  **refused** rather than guessed.

Breaking BigQuery migrations are never reversed automatically. Recovery from
a bad release after a breaking migration is always forward: fix on a new
release, backfill if required, reconcile.

## Consequences

- Rollback safety becomes a declared property of the migration history
  instead of operator folklore.
- All eight Sprint 6 schema scenarios (S6-SCH-001…008) are covered by unit
  tests against the classifier, the version normalizer, or the rollback
  compatibility evaluator.
