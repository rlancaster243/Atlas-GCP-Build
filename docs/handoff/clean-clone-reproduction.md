# Clean-Clone Reproduction

**Status:** CURRENT · **Audience:** engineer, agent. How to prove Atlas
reproduces from a fresh clone using only documented commands. Automated by
[`../../scripts/validate_clean_clone.sh`](../../scripts/validate_clean_clone.sh);
results recorded in
[`../evidence-sprint8/clean-clone-results.md`](../evidence-sprint8/clean-clone-results.md).

## What "clean" means

A fresh temporary directory that does **not** reuse: the current virtualenv,
generated data, dbt `target/`, cached credentials, local env files, prior test
output, Composer state, or untracked files. The script creates its own venv and
clones the committed state.

## Credentialless procedure

```bash
bash scripts/validate_clean_clone.sh                 # uses current HEAD
bash scripts/validate_clean_clone.sh --ref <commit>  # a specific candidate
```

Steps performed: clone → checkout candidate → fresh venv →
`pip install -r requirements.txt -r requirements-ci.txt` →
`validate_ci.sh --mode static` → `generate_events.py` → `pytest` →
`PYTHONPATH=src python -m atlas.governance.catalog check` →
`... atlas.governance.lineage` → `... atlas.reference.validate` (the script sets
`PYTHONPATH=src` since `atlas.*` lives under `src/` with no installed package). It
records per-step outcome + duration and removes the temp dir (`--keep` to
retain).

**Expected result:** `clean_clone: PASS`. Optional tools absent from
`requirements.txt` (dbt, Airflow) cause their gates to SKIP, not FAIL — install
`dbt` (`scripts/setup_dbt.sh`) and `airflow/requirements-airflow.txt` to exercise
those gates. `yamllint` and `shellcheck` come from `requirements-ci.txt`, so
`workflow_yaml`/`shell_static` run.

## Optional read-only GCP leg

Run only under `ATLAS_APPROVE_HANDOFF_LIVE_READ=true`: documented auth, verify
project, read-only inspection, BigQuery dry-runs only. No resource creation, no
Composer, no billed queries. See
[operator-onboarding](operator-onboarding.md) Mode 2.

## Failure handling

Every failed step becomes a documentation fix, a setup-script fix, an
environment-contract clarification, or a recorded external limitation. **Rerun
from a second fresh directory after fixes** — never declare success from a
repaired dirty clone.
