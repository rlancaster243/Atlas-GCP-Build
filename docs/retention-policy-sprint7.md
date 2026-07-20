# Atlas Classification & Retention Policy (Sprint 7)

Declares how long each category of Atlas data is retained and how it is
disposed. Definitions live in `governance/classifications.yml` and
`governance/retention.yml`; validation is enforced by `gate_governance`
(`atlas.governance.retention.validate_retention_config`). See ADR-019.

## Classification levels

| Level | Meaning | Logging | Atlas use |
| --- | --- | --- | --- |
| PUBLIC | shareable, non-sensitive | none | `dim_countries` (synthetic reference) |
| INTERNAL | operational, non-personal (default) | counts/ids only | events, models, audit tables |
| CONFIDENTIAL | harmful if exposed (tokens, addresses) | sanitized, never verbatim, never committed | notification address (live only), sanitized errors |
| RESTRICTED | real personal/regulated data | never logged, audited | **none present** (Atlas is synthetic) |

## Retention classes and disposal

| Retention class | Applies to | Expiration | Permanent evidence |
| --- | --- | --- | --- |
| `canonical_warehouse` | staging/intermediate/core/mart models | none (rebuildable) | no |
| `raw_landing` | `atlas_raw.events`, raw bucket | none (source of truth) | no |
| `operational_audit` | pipeline_runs, task_events, quality_results, monitor_evaluations, deployments, schema_migrations, recovery_actions | **never** | **yes** |
| `observability_logs` | log bucket + linked dataset | 30 days | no |
| `release_evidence` | immutable release bundles | keep validated | **yes** |
| `temporary_integration` | CI/integration datasets | 1 day | no |
| `test_fixture` | local generated artifacts | ephemeral | no |

## Retention rules distinguish

- **Canonical data** — indefinite, deterministically rebuildable; never auto-expired.
- **Operational evidence** — permanent; CI forbids attaching an expiration.
- **Temporary resources** — carry a mandatory disposal (dataset TTL / bucket
  lifecycle).
- **Release evidence** — validated releases retained.
- **Test fixtures** — not persisted to cloud.

## Enforced invariants

- `policy.retention_classes` matches `retention.yml` keys exactly (no drift).
- A `is_permanent_evidence` class cannot declare an expiration (conflict → CI fail).
- A transient class (`observability_logs`, `temporary_integration`,
  `test_fixture`) must declare an expiration.
- Every governed asset references a defined retention class.

## Disposal planning (dry-run)

```bash
python -c "import json; from atlas.governance.retention import plan_expirations; \
  print(json.dumps(plan_expirations(), indent=2))"
```

Each asset resolves to `keep_forever` (permanent evidence / rebuildable) or
`expire_<n>d`. A live applier asserts it never expires a `keep_forever` asset.

## Live application (gated)

Applying dataset/bucket expiration to temporary resources requires
`ATLAS_APPROVE_RETENTION_MUTATION=true`. Current live state (read-only check):
`atlas_ops`, `atlas_core`, `atlas_raw` have **no** default table expiration
(correct — permanent/rebuildable). No required evidence is deleted during
Sprint 7.

**Blocked gate:** live expiration application to a temporary CI dataset/bucket
prefix is pending `ATLAS_APPROVE_RETENTION_MUTATION`. The safe controls, the
disposal plan, and validation tests are complete; only the live mutation is
deferred. The gate is not weakened.
