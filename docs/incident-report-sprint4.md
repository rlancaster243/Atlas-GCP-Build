# Sprint 4 Incident & Failure-Demonstration Report

Deliberate delivery-control failure demonstrations (Phase 16) plus real
defects found and fixed during Sprint 4. Nothing here was merged to `main`;
demonstration branch PR #15 was closed unmerged by design.

## Gate demonstrations (PR #15, branch `cursor/atlas-sprint-4-gate-demos-64a2`)

| # | Injected defect | Expected | Observed | Evidence (workflow run / job) |
|---|---|---|---|---|
| 1 | failing Python unit test (`tests/unit/test_demo_gate.py`) | `atlas-python` + `atlas-ci-gate` fail | confirmed | run `29661079879`: atlas-python **failure**, atlas-ci-gate **failure** |
| 2 | broken DAG import (`dags/demo_broken_dag.py`, nonexistent provider import) | `atlas-airflow` + gate fail | confirmed after hardening (see D1) | run `29661300491`: atlas-airflow **failure**, gate **failure** |
| 3 | failing dbt parse (`demo_broken_model.sql`, unknown `ref`) | `atlas-dbt` + gate fail | confirmed | run `29661397887`: atlas-dbt **failure**, gate **failure** |
| 4 | simulated service-account key (`config/demo-service-account.json`) | secret scan fails **without printing the secret** | confirmed — job log reports file path and detector name only | run `29661467375`, job `88124766823`: atlas-security-shell **failure** |

Demonstrations 5–8 (invalid migration, failed smoke batch, concurrent
deployment, rollback) are covered as follows:

| # | Control | How it is proven |
|---|---|---|
| 5 | invalid migration blocks before DAG promotion | unit tests `test_apply_refuses_changed_recorded_migration`, `test_apply_records_failure_and_blocks`; deploy stage order (`migrations` precedes `promote`) with `fail_stage` recording FAILED |
| 6 | failed smoke ⇒ FAILED record, no success release | **executed live**: defective release `1af166e` (branch `cursor/atlas-sprint-4-defect-demo-64a2`, `inject_failure: true`) failed its smoke batch at `dbt_build`; deployment `atlas-dev-20260719T010538Z-1af166ea` recorded `FAILED` / `failure_stage=smoke_batch`; no success metadata was published. Log: `evidence-sprint4/deploy-defective-1af166ea.log` |
| 7 | concurrent deployment prevented | `concurrency: group: atlas-dev-deployment` with `cancel-in-progress: false` on both deploy and rollback workflows — GitHub queues the second run; no overlapping mutation is possible |
| 8 | rollback restores prior validated release | **executed live**: `rollback_atlas.sh` selected the newest prior SUCCESS (`640cd78`), re-promoted it, ran rollback smoke batch `atlas-smoke-640cd786-local1784423774` (50 000 rows, all 12 checks PASS) and recorded `ROLLED_BACK` with `previous_git_sha=1af166e`. Log: `evidence-sprint4/rollback-640cd786.log` |

## Real defects found by Sprint 4 controls (and fixed)

### D1 — DagBag safe-mode heuristic skipped a broken DAG

Demonstration 2 initially **passed** CI: the injected file did not contain
both "dag" and "airflow" tokens, so DagBag's safe-mode heuristic never parsed
it. Fix: the `dag_import` gate now parses with `safe_mode=False`, so every
`.py` file under `dags/` must import cleanly. The hardening commit landed
after PR #14 was squash-merged and was carried onto the delivery branch
(commit `383ba8a`) so it is part of the Sprint 4 release.

### D2 — Isolated integration runs could write to canonical `atlas_raw`

`sql/migrate_sprint3.sql` hardcoded the `atlas_raw` dataset; the loader's
migration step would have ALTERed the canonical table even when running
against `atlas_ci_*` isolation. Fix: migration SQL parameterized with
`{dataset_id}`; loader renders it from settings. Found by code inspection
while building `validate_gcp_integration.sh`.

### D3 — Event generation was not cross-machine deterministic

The integration determinism gate failed on first live run: `event_id` used
`uuid.uuid4()` (backed by `os.urandom`), so identical batch identities
produced different bytes. Fix: UUIDs now derive from the seeded RNG
(`uuid.UUID(int=rng.getrandbits(128), version=4)`); regression test asserts
byte-identical regeneration to fresh paths. This is exactly the class of
defect the gate exists to catch — reproducible batches are what make smoke
runs and reruns comparable.

### D4 — Error sanitizer leaked values following secret field names

`sanitize_error_message` redacted the token `private_key` but left the value
after it (`{"private_key": "SECRET"}` → SECRET survived). Fix: patterns now
consume the field value; deployment audit tests assert `[REDACTED]` replaces
the value.

### D5 — Composer runtime SA IAM race

`gcloud iam service-accounts create` propagates asynchronously; immediate
role binding failed with "service account does not exist" on the first live
create. Fix: bounded retry with backoff in `manage_atlas_composer.sh`.

## Live deployment failure ledger (every attempt is audited)

The first Composer deployment to reach `SUCCESS` took seven attempts. Each
failure was recorded in `atlas_ops.deployments` with its `failure_stage`,
each exposed a real defect, and each fix is a focused commit on the delivery
branch:

| deployment_id | sha | failure_stage | Root cause → fix |
|---|---|---|---|
| `atlas-dev-20260718T225900Z-dd7dd5d4` | `dd7dd5d` | `fetch_release` | D6 below |
| `atlas-dev-20260718T230144Z-2aeff26e` | `2aeff26` | `dag_parse` | D7 below |
| `atlas-dev-20260718T231842Z-83c0d137` | `83c0d13` | `dag_parse` | D8 below |
| `atlas-dev-20260718T233128Z-74732eee` | `74732ee` | `smoke_batch` | D9 below |
| `atlas-dev-20260719T001246Z-f9959cb6` | `f9959cb` | `smoke_batch` | D10 below (smoke DAG run itself succeeded; poller defect) |
| `atlas-dev-20260719T004112Z-37d4e6aa` | `37d4e6a` | `smoke_validation` | D11 below |
| `atlas-dev-20260719T005308Z-640cd786` | `640cd78` | — | **SUCCESS** — all 12 smoke checks PASS |

### D6 — Checksum verification compared filenames, not digests

The stored `.sha256` records the builder's local filename; the fetched object
is `atlas-bundle.tar.gz`, so `sha256sum -c` failed on every fetch. Fix:
compare digests directly in `fetch_and_verify_release`.

### D7 — DAG imports assumed the repository layout, not Composer's

Locally the DAG sits at the DagBag root, so `atlas_orchestration` and
`atlas` resolved implicitly. On Composer the DAG lives under
`dags/project_atlas/`, which Airflow 3's processor does not put on
`sys.path` — both imports failed. Fix: the DAG file adds its own directory
and `ATLAS_ROOT/src` to `sys.path` before package imports, and
`dags/.airflowignore` stops helper-package modules from being parsed as DAG
files. This is precisely the parity gap the live deploy stage exists to catch.

### D8 — Stale Airflow import-error rows failed a healthy deployment

Airflow retains the previous release's import errors until the processor
re-evaluates each file after GCS sync; the parse gate failed on the first
snapshot even though the DAG parsed cleanly seconds later. Fix:
`wait_for_dag_parse` keeps polling until the deadline and fails only if
errors persist.

### D9 — Bundle stripped `dbt_packages` but the runtime never runs `dbt deps`

Composer workers must not resolve packages from the network, yet the bundle
excluded `dbt_packages` as a build output — `dbt seed` aborted with
"0 package(s) installed". Fix: the bundle build vendors pinned packages
(`dbt deps` against `package-lock.yml`) into the staged tree and guards that
`dbt_utils` is present.

### D10 — Smoke poller never matched Airflow 3 `dags state` output

For runs triggered with `--conf`, Airflow 3 prints `success, {conf json}`;
the anchored regex `^(success|failed|…)$` matched nothing, so the poll spun
until timeout although the smoke run had succeeded. The stuck attempt was
finalized as `FAILED` (error_type `DeploymentTooling`) for audit honesty.
Fix: match the leading state token; log each poll iteration.

### D11 — Deterministic bundles defeated `gcloud storage rsync`

The reproducible tar pins every file mtime, so rsync's size+mtime comparison
skipped changed files whose size didn't change — the promoted runtime kept
the *previous* release's `release-manifest.json` and the `deployed_sha`
smoke check failed (correctly). Fix: promotion rsyncs with
`--checksums-only`. The same deployment also exposed the D10 regex bug in
`validate_atlas_deployment.sh`'s Airflow-state check, fixed the same way.

## Recovery posture

Every deploy-stage failure records `FAILED` with `failure_stage` in
`atlas_ops.deployments`, preserves the immutable bundle, and prints the exact
re-run command. See `ci-cd-runbook-sprint4.md` §9 for the failure table.
