# Clean-Clone Results (Sprint 8, Phase 11)

**Status:** RECORDED. Automated by
[`../../scripts/validate_clean_clone.sh`](../../scripts/validate_clean_clone.sh);
procedure in [../handoff/clean-clone-reproduction.md](../handoff/clean-clone-reproduction.md).
Each attempt uses a fresh temp directory and a brand-new virtualenv — no reuse of
the caller's environment, generated data, or credentials. Credentialless.

## Attempt 1 — candidate `57abf2d` — FAIL (defect found)

Command: `bash scripts/validate_clean_clone.sh --ref 57abf2d`. Duration 42s.

| step | result |
| --- | --- |
| install | PASS |
| static_ci | PASS |
| generate | PASS |
| unit_tests | PASS |
| governance | **FAIL** |
| lineage | **FAIL** |
| reference | **FAIL** |

**Root cause:** documented direct commands `python -m atlas.governance.catalog`,
`atlas.governance.lineage`, `atlas.reference.validate` failed with
`ModuleNotFoundError: No module named 'atlas'`. `atlas.*` lives under `src/` with
no installed package; `pytest.ini` and `validate_ci.sh` set `PYTHONPATH=src`
internally (so tests and static CI passed), but the standalone module commands in
the docs omitted it.

**Fix (documentation/script root cause, commit `e538e99`):** added
`export PYTHONPATH=src` to `validate_clean_clone.sh` and to every documented
`python -m atlas.*` command (START_HERE, operator/agent onboarding, first-hour,
clean-clone doc, evidence index, demo script, context pack).

## Attempt 2 — candidate `e538e99` — PASS (fresh directory)

Command: `bash scripts/validate_clean_clone.sh --ref e538e99`. Duration 43s.

| step | result |
| --- | --- |
| install | PASS |
| static_ci | PASS |
| generate | PASS |
| unit_tests | PASS |
| governance | PASS |
| lineage | PASS |
| reference | PASS |

`clean_clone: PASS`. Success was declared only from a **second fresh directory**
after the fix — not from a repaired dirty clone.

## Notes

- `shell_static` and the Airflow gates SKIP in the clean venv because shellcheck
  and apache-airflow are not in `requirements.txt`; they run in GitHub CI (pinned
  toolchain) and via `airflow/requirements-airflow.txt`. `yamllint`/`shellcheck`
  in `requirements-ci.txt` mean `workflow_yaml` runs.
- No GCP credentials were used or required.
