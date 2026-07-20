# ADR-008: GitHub Actions Validation Boundary

## Status

Accepted — 2026-07-18

## Context

Sprint 4 introduces independent CI on GitHub. The delivery system must be
auditable, reproducible outside GitHub, and safe against untrusted
pull-request code and supply-chain drift.

## Decision

### Validation logic lives in repository scripts

`scripts/validate_ci.sh` is the canonical validation contract.
Workflows only provision pinned toolchains and invoke it with a gate group
(`security-shell`, `python`, `airflow`, `dbt`). Consequences:

- Cursor Cloud Agents, local developers, and CI run byte-identical gates.
- Workflow YAML carries no business or validation logic that could drift
  from what engineers run locally.
- A requested gate group whose toolchain is missing **fails** rather than
  skips, so CI cannot silently pass by not installing a tool.

### Pull-request CI is credentialless

`atlas-ci.yml` sets `permissions: contents: read` at the workflow level and
uses no GCP credentials, no service-account JSON, and no repository secrets.
Untrusted pull-request code therefore executes with nothing to exfiltrate.
GCP integration testing runs only from trusted workflow code on `main` (or a
SHA verified reachable from `main`) via Workload Identity Federation
(ADR-009). `pull_request_target` is never used to execute untrusted code
with credentials.

### Version pinning

| Component | Pin | Source |
|---|---|---|
| Python | 3.12 (Composer parity gap with 3.11.8 documented in ADR-005) | `setup-python` |
| apache-airflow | 3.1.7 + official `constraints-3.12.txt` | `airflow/requirements-airflow.txt` |
| Google provider | 20.0.0 | same |
| Standard provider | 1.12.1 | same |
| dbt-core / dbt-bigquery | 1.11.12 / 1.11.3 | `dbt/requirements-dbt.txt` |
| dbt_utils | 1.4.1 | `packages.yml` |
| ruff / mypy / yamllint / shellcheck-py / pytest | see `requirements-ci.txt` | verified locally 2026-07-18 |

Versions are upgraded deliberately, never because newer versions exist;
Composer-target compatibility (ADR-005) always wins.

### Action supply-chain controls

- Every third-party action is pinned to an immutable full commit SHA with a
  comment naming the release tag.
- SHAs were resolved via `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`,
  dereferencing annotated tags to commit objects, on 2026-07-18:
  - `actions/checkout@v5` → `93cb6efe18208431cddfb8368fd83d5badbf9bfd`
  - `actions/setup-python@v6` → `ece7cb06caefa5fff74198d8649806c4678c61a1`
  - `actions/upload-artifact@v4` → `ea165f8d65b6e75b540449e92b4886f43607fa02`
- Floating tags (`@v4`) are never used for execution.

### Cache boundaries

- `setup-python` pip caching is keyed on the pinned requirements files.
- Caches contain only public package downloads — never credentials, tokens,
  or workspace state. No credential material exists in PR CI to leak.

### Trusted versus untrusted execution

| Context | Code | Credentials |
|---|---|---|
| `pull_request` CI | untrusted (fork/branch) | none (read-only token) |
| `push` to `main` CI | trusted, reviewed | none (CI needs none) |
| Deployment / integration workflows | trusted `main`-reachable SHAs only, `workflow_dispatch` | short-lived WIF tokens (ADR-009) |

### Static-mode dbt boundary

`dbt deps` + `dbt parse` run in static CI with a placeholder oauth profile
(parse never opens a warehouse connection). `dbt compile` and dbt unit tests
against BigQuery require a live adapter connection, so they run in
integration mode with isolated `atlas_ci_<run_id>` resources instead of in
credentialless PR CI. This is a deliberate deviation from "compile in static
mode": compiling BigQuery incremental models introspects relations and
cannot be done credential-free without mocking that would weaken the gate.

## Consequences

- A green `atlas-ci-gate` check is reproducible locally with
  `bash scripts/validate_ci.sh --mode static`.
- Adding a new gate means editing one script, and every consumer inherits it.
- Action upgrades are explicit diffs of full SHAs, reviewable against
  upstream release notes.
