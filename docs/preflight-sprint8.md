# Atlas Sprint 8 Preflight — Reference Architecture, Reproducibility & Handoff

Verified against `origin/main` on 2026-07-19. Repository truth overrides the
master prompt; every value below was resolved from Git, tags, PRs, and file
contents, not from prior conversation memory. No repository content was changed
before this preflight was written (the Sprint 8 branch was created first, which
is not a content change).

## 1. Verified repository baseline

| Item | Verified value | Prompt expectation | Match |
| --- | --- | --- | --- |
| Current branch | `cursor/atlas-sprint-8-reference-handoff-64a2` (fresh off main) | new S8 branch | ✓ |
| `origin/main` HEAD | `3f986aaa703d9d7da10b94ecf6fba753fec2a80d` | `3f986aa` (release-row commit) | ✓ |
| Sprint 7 merge commit | `9d031c99cacefbd6be461f6e8f7b16bb963c3ab9` (PR #22, squash) | `9d031c9` | ✓ |
| `atlas-sprint-7-complete` | resolves to `9d031c9` | tag on merge commit | ✓ |
| PR #22 | **MERGED**, mergeCommit `9d031c9` | merged | ✓ |
| Working tree | clean | — | ✓ |
| Stale Sprint 8 branch/PR | none (`refs/heads/*sprint-8*` empty) | none to resume | ✓ |
| Open PRs | #2, #3, #6 — unrelated non-Atlas/setup PRs, not to be resumed | — | ✓ |

Sprint 1–7 tags all resolve: `270e7d5`, `5135778`, `8aa1d7a`, `b609ac1`,
`476e20a`, `48da9d2`, `9d031c9`. README release table lists all seven rows
consistently. Sprint 1–7 tags will not be moved.

## 2. Sprint 1–7 capability summary (what exists)

| Sprint | Capability | Primary evidence |
| --- | --- | --- |
| 1 | Deterministic 50k-event generation → immutable GCS → partitioned BigQuery raw → validation | `validation-report-sprint1.md`, `src/atlas/{generator,ingestion,loader,validation}` |
| 2 | Governed dbt warehouse: staging → classification → accepted/rejected → core (fact/dims) → marts; contracts, tests, reconciliation, incremental | `dbt/atlas_dbt`, `validation-report-sprint2.md` |
| 3 | Airflow 3.1.7 orchestration, stable `batch_id`, retries/reruns/backfills, `pipeline_runs` audit | `dags/`, `validation-report-sprint3.md`, ADR-006/007 |
| 4 | GitHub CI/CD, keyless WIF, immutable release bundles, migrations, ephemeral Composer deploy, smoke validation, rollback | `validation-report-sprint4.md`, ADR-008/009/010 |
| 5 | Structured observability, task/quality telemetry, Cloud Logging+Monitoring, alerts, dashboard, runbooks, drills | `validation-report-sprint5.md`, ADR-011/012 |
| 6 | Failure taxonomy, controlled fault injection, recovery audit, game days, cost guards, schema-version handling | `validation-report-sprint6.md`, ADR-013/014/015 |
| 7 | Governance source of truth, contracts, schema compatibility, lineage/impact, deprecation, IAM review, retention, BigQuery perf baseline, cost controls, 5 CI gates | `validation-report-sprint7.md`, ADR-016–020 |

Codebase scan: `src/atlas/` has 13 modules (batch, config, failure_injection,
generator, ingestion, loader, logging, observability, ops, pipeline, validation,
governance + `__init__`). `governance/` has registry, catalog, lineage, impact,
schema_check, retention, security_policy. 41 scripts. **282 unit tests.** 61
docs, 19 ADRs, 4 evidence directories (sprint4–7).

## 3. Sprint 7 unresolved-gate summary (must remain visibly blocked)

Recorded in `validation-report-sprint7.md` §18 as blocked on unset approvals:

| Blocked gate | Approval required | Sprint 8 disposition |
| --- | --- | --- |
| Live IAM reduction + positive/negative test (`atlas-github-integration` dataEditor) | `ATLAS_APPROVE_IAM` | Retain as BLOCKED risk; preserve plan; execute only if approval present |
| Executed (billed) BigQuery performance suite | `ATLAS_APPROVE_PERFORMANCE_TESTS` (+ `ATLAS_MAX_PERFORMANCE_TEST_BYTES`) | Retain as BLOCKED risk; dry-run baseline already exists |
| Live retention/expiration application | `ATLAS_APPROVE_RETENTION_MUTATION` | Retain as BLOCKED risk; disposal dry-run plan exists |

These are optional Sprint 8 closure improvements, **not** automatic requirements.
No claim will be made that a blocked control was executed.

## 4. Reproducibility state

| Facet | Verified value |
| --- | --- |
| Python | `requires-python = ">=3.12,<3.13"` (pyproject); mypy target 3.12 |
| Runtime deps | `requirements.txt` (google-cloud-bigquery/storage/monitoring/logging, PyYAML, pytest) |
| CI toolchain (pinned) | `requirements-ci.txt` — ruff 0.15.22, mypy 2.3.0, **yamllint 1.38.0, shellcheck-py 0.11.0.1**, pytest 9.1.1, types-PyYAML |
| dbt | 1.11.12, BigQuery adapter (`dbt/atlas_dbt`) |
| Airflow | pinned `apache-airflow==3.1.7` + providers-google 20.0.0 (`airflow/requirements-airflow.txt`); Composer `composer-3-airflow-3.1.7-build.13` |
| Credentialless path | `bash scripts/validate_ci.sh --mode static` (no GCP creds) |
| Credentialed read-only | `verify_mcp_access.sh`; BigQuery dry-run via `cost_guard` |
| Test count | 282 collected |
| Generated/gitignored | `data/`, `logs/`, dbt `target/`, `.venv`, `.gcp/` |

**Reproducibility note (root cause captured for clean-clone):** yamllint and
shellcheck are pinned in `requirements-ci.txt`. A clone that installs only
`requirements.txt` will `SKIP` `workflow_yaml`/`shell_static`; installing
`requirements-ci.txt` makes those gates run. The clean-clone doc must direct
installing **both** files, matching the Sprint 4 quick start.

## 5. CI gate inventory (21 gates in `validate_ci.sh`)

`secret_scan, shell_syntax, shell_static, workflow_yaml, sql_migrations,
python_format, python_lint, python_types, python_tests, config_validation,
observability_config, failure_injection, governance, schema_compatibility,
lineage_impact, security_policy, performance_cost, airflow_environment,
dag_import, dbt_static, gcp_integration`. Sprint 8 adds exactly one focused gate:
`gate_reference_handoff` (Phase 18). No validation logic will be duplicated in
workflow YAML.

## 6. Reference-architecture readiness & risks found in preflight

- **Docs are conversation-independent:** grep for `/home/ubuntu`, `/workspace`,
  `/Users/`, `ChatGPT`, "prior conversation", "previous session" across `docs/`
  → **0 matches.** Good baseline for the handoff CI gate.
- **Public-extraction finding (feeds Phase 14):** operator name / notification
  email (`the primary operator…@gmail.com`) appears in ~35 files — concentrated in
  `observability/alerts/*.json` (notification channel), Sprint 4/5 WIF & IAM docs,
  `bootstrap_github_wif.sh`, and setup guides. These need REDACT/REPLACE_WITH_SAMPLE
  dispositions. Private project id `example-gcp-project` and bucket/SA names are
  pervasive and expected (REPLACE_WITH_SAMPLE at template time).
- **Composer customer-project task-log limitation** (Sprint 5) and **synthetic
  50k-row scale** are standing honest limitations → unresolved-risk register.
- Stable architecture decisions live in ADR-002…020; invariants are implied
  across sprints and must be consolidated (Phase 4).

## 7. Proposed Sprint 8 file structure

```

  START_HERE.md
  docs/
    preflight-sprint8.md            (this)
    sprint8-context-pack.md
    token-efficiency-sprint8.md
    validation-report-sprint8.md
    reference-architecture/         (18 curated map docs + reference-manifest.yml)
    handoff/                        (operator ×3, agent ×2, clean-clone, handoff ×3, evidence ledger)
    evidence-sprint8/               (clean-clone-results.md, independent-handoff-results.md)
    presentation/                   (presentation, demo-script, question-bank)
    adr/ADR-021-reference-architecture-and-handoff-contract.md
  governance/
    unresolved_risks.yml
    generated/evidence-index.json
  config/public_extraction_manifest.yml
  scripts/
    validate_clean_clone.sh
    validate_public_extraction.py
    validate_ci.sh                  (+ gate_reference_handoff)
  src/atlas/reference/              (validate.py — `python -m atlas.reference.validate`)
```

## 8. Bounded execution sequence

P0 preflight+context (this) → P1 START_HERE → P2–7 reference package (manifest +
17 docs) → P8 evidence index + `atlas.reference.validate` → P9–10 operator/agent
onboarding → P11 clean-clone script + 2 fresh-dir runs → P12 independent handoff
test + scorecard → P13 unresolved-risk register + S7 disposition → P14
public-extraction review + validator → P15 template-extraction plan → P16–17
capability ledger + presentation → P18 `gate_reference_handoff` → P19 final CI +
clean-clone + docs → close out on `ATLAS_APPROVE_RELEASE`.

## 9. Token & cloud-cost envelope

Target: **50–65% of Sprint 7** agent consumption. 1 primary scan (done) + 1
targeted closeout scan. **0 Composer cycles, 0 deployment cycles, ~$0 cloud**
(only optional read-only dry-runs under `ATLAS_APPROVE_HANDOFF_LIVE_READ`). Link
to existing docs rather than duplicating Sprint 1–7 prose. One handoff gate, not
many. Tripwire: stop and report if projected work nears 75% of Sprint 7.

## 10. Required approvals (all currently UNSET unless noted)

| Variable | Gates | Needed for |
| --- | --- | --- |
| `ATLAS_APPROVE_HANDOFF_LIVE_READ` | optional read-only GCP leg of clean-clone/handoff | not required for green |
| `ATLAS_APPROVE_IAM` | Sprint 7 IAM leg | stays BLOCKED if unset |
| `ATLAS_APPROVE_PERFORMANCE_TESTS` (+ byte ceiling) | Sprint 7 billed perf | stays BLOCKED if unset |
| `ATLAS_APPROVE_RETENTION_MUTATION` | Sprint 7 retention | stays BLOCKED if unset |
| `ATLAS_APPROVE_PUBLIC_EXTRACTION` | local extraction candidate dir | dry-run works without it |
| `ATLAS_APPROVE_RELEASE` | final `atlas-sprint-8-complete` tag | closeout only |

`ATLAS_APPROVE_PROVISION/DEPLOY/TEARDOWN=true` are present in the environment but
Sprint 8 requires no provisioning, deployment, or teardown.

## 11. Known risks entering Sprint 8

1. Clean-clone may reveal an undocumented setup step (that is the point — fix
   root cause in docs/scripts, rerun from a fresh directory).
2. Independent handoff may score < 25/30 on first attempt; repair docs, rerun
   affected portions with fresh context.
3. Personal-email/name spread is wider than one file; the public-extraction
   validator must catch all of it without printing values.
4. This agent cannot fully guarantee "independent" handoff without a separate
   tester context; the handoff will use a subagent with only the repo +
   START_HERE + assignment, and any assistance will be recorded as an
   intervention honestly.
