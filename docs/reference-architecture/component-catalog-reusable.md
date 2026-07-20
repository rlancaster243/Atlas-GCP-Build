# Component Catalog — Reusable

**Status:** CURRENT · **Audience:** engineer, reviewer, template author. These
components are candidates for a future reusable template (see
**reusable** only if its value is independent of Atlas's synthetic domain — not
merely "it is Python/YAML". Each entry records the extraction action required to
generalize it. No component here is claimed to be *already* a template.

Fields: purpose · implementation · dependencies · configuration surface ·
hardcoded Atlas assumptions · security boundary · tests · evidence · limitations
· template-extraction action.

## CI & delivery

- **RC-01 canonical CI entry point** — one script all actors run.
  `scripts/validate_ci.sh` (`--mode`, `--group`). Deps: ruff/mypy/pytest/yamllint/
  shellcheck/dbt. Config: gate groups, `ATLAS_CI_GATE_GROUP`. Atlas assumptions:
  gate list, dbt project path. Security: credentialless in static mode. Tests: the
  gates themselves. Evidence: green CI runs. Limits: gate set is Atlas-tuned.
  Extraction: parameterize project paths + gate registry.
- **RC-02 credentialless PR validation** — untrusted PRs never touch GCP.
  Workflow split + static mode. Extraction: keep workflow topology, swap names.
  ADR-008.
- **RC-03 WIF deployment authentication** — keyless GitHub→GCP.
  `scripts/bootstrap_github_wif.sh`, workflow OIDC. Atlas assumptions: SA names,
  project id, pool id. Extraction: parameterize identity/project. ADR-009.
- **RC-04 immutable release bundles** — content-pinned deploy artifact.
  `build_deployment_bundle.sh`. Extraction: parameterize bundle contents.
- **RC-05 migration ledger + checksum lock** — applied migrations immutable.
  `sql/migrations/` + `checksums.lock` + `gate_schema_compatibility`. Extraction:
  keep mechanism, swap DDL. ADR-017.
- **RC-06 deployment audit** — `atlas_ops.deployments` + `apply_atlas_migrations.sh`.
  Extraction: keep schema, rename dataset.
- **RC-07 smoke validation contract** — `validate_atlas_deployment.sh`. Extraction:
  parameterize checks.
- **RC-08 rollback controls** — `rollback_atlas.sh` w/ schema-compat check. ADR-010/015.

## Observability & operations

- **RC-09 structured logging contract** — correlation ids, redaction.
  `src/atlas/logging`, `src/atlas/observability/logging`. Extraction: keep
  contract, swap log/dataset names. ADR-011.
- **RC-10 operational audit tables** — `atlas_ops.{pipeline_runs,task_events,
  quality_results,monitor_evaluations,deployments,schema_migrations,recovery_actions}`.
  Extraction: keep schemas, rename dataset.
- **RC-11 observability monitor pattern** — `atlas_observability_monitor` DAG +
  `monitor_evaluations`. Extraction: parameterize checks/thresholds.
- **RC-12 alert ↔ runbook linkage** — `observability/alerts/*.json` map to runbook
  sections. Extraction: keep linkage rule (INV-O6).
- **RC-13 recovery-action audit** — verified targeted repair. `recovery_actions`.
  ADR-014.
- **RC-14 failure-injection safeguards** — disabled by default, gated.
  `src/atlas/failure_injection`, `gate_failure_injection`. ADR-013.
- **RC-15 cost guards** — dry-run-first ceilings. `config/cost_controls.yaml`,
  `src/atlas/observability/cost_guard.py`. Extraction: parameterize ceilings.
  ADR-020.

## Governance

- **RC-16 governance registry** — one source of truth + catalog + drift check.
  `src/atlas/governance/{registry,catalog}.py`, `governance/*.yml`. ADR-016.
- **RC-17 schema compatibility checker** — `schema_check.py` + baseline manifest.
  ADR-017.
- **RC-18 lineage + impact analysis** — repository-artifact lineage.
  `lineage.py`/`impact.py`. Extraction: keep dbt-ref parsing, swap consumers.
- **RC-19 retention validation** — `retention.py` + `governance/retention.yml`.
  ADR-019.
- **RC-20 evidence-index pattern** — claim→evidence map + validator.
  `governance/generated/evidence-index.json`, `atlas.reference.validate`.
- **RC-21 handoff validation** — `gate_reference_handoff` + `validate_clean_clone.sh`.
- **RC-22 public-extraction validator** — secret/PII disposition scanner.
  `scripts/validate_public_extraction.py`, `config/public_extraction_manifest.yml`.

## Reuse guidance

Every reusable component carries **Atlas assumptions** (dataset names, SA names,
lists exactly which of these become parameters. Until that extraction is
performed and validated by a separate generated project, these are reusable
*candidates*, not a template.
