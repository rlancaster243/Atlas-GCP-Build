from __future__ import annotations

import json
import os
import re
import shutil
import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit('usage: build_atlas_template.py <source-atlas-dir> <output-dir>')

SRC = Path(sys.argv[1]).resolve()
DST = Path(sys.argv[2]).resolve()

if not SRC.is_dir():
    raise SystemExit(f'source directory not found: {SRC}')

if DST.exists():
    shutil.rmtree(DST)
shutil.copytree(SRC, DST, copy_function=shutil.copy2)

# Remove the separate artifact-hosting product and raw implementation evidence.
remove_paths = [
    'artifact-platform',
    'infra/artifact-platform',
    'examples/artifact-dashboard',
    'scripts/release_artifact_platform.sh',
    'scripts/deploy_artifact_platform.sh',
    'scripts/manage_artifact_platform.sh',
    'scripts/test_artifact_platform.sh',
    'docs/artifact-platform-runbook.md',
    'docs/superpowers/specs/2026-07-17-atlas-artifact-platform-design.md',
    'docs/superpowers/plans/2026-07-17-atlas-artifact-platform.md',
    'docs/superpowers/plans/2026-07-18-atlas-artifact-platform-implementation.md',
    'docs/context-packs',
    'docs/game-day-evidence',
    'docs/incidents/evidence',
    'observability/evidence',
    'observability/performance/results',
]
for rel in remove_paths:
    path = DST / rel
    if path.is_dir():
        shutil.rmtree(path)
    elif path.exists():
        path.unlink()

# Remove nested-project-only and generated/private extraction metadata.
for rel in [
    'config/public_extraction_manifest.yml',
    'scripts/validate_public_extraction.py',
    'docs/reference-architecture/public-extraction-review.md',
    'docs/reference-architecture/template-extraction-plan.md',
    'docs/validation-report-sprint8.md',
    'docs/handoff/agent-handoff-assignment.md',
    'docs/handoff/agent-handoff-results.md',
    'docs/handoff/clean-clone-results.md',
    'docs/handoff/token-efficiency-ledger.md',
]:
    path = DST / rel
    if path.exists():
        path.unlink()

# Remove files that refer to the excluded artifact platform from generated catalogs.
for rel in [
    'governance/generated/asset-catalog.json',
    'governance/generated/evidence-index.json',
    'governance/generated/lineage-graph.json',
    'governance/generated/lineage-graph.mmd',
    'governance/generated/performance-baselines.json',
    'governance/generated/schema-baseline.json',
    'governance/generated/schema-candidate.json',
]:
    path = DST / rel
    if path.exists():
        path.unlink()

# Exclude local/generated outputs if they were ever tracked.
for pattern in [
    '**/__pycache__',
    '**/.pytest_cache',
    '**/target',
    '**/logs',
    '**/dist',
    '**/.venv',
    '**/node_modules',
]:
    for path in list(DST.glob(pattern)):
        if path.is_dir():
            shutil.rmtree(path)

TEXT_SUFFIXES = {
    '.md', '.py', '.sh', '.yaml', '.yml', '.json', '.sql', '.txt', '.cfg',
    '.ini', '.toml', '.example', '.jinja', '.j2', '.csv', '.properties',
}
TEXT_NAMES = {
    'Dockerfile', 'Makefile', '.gitignore', '.env.example', 'profiles.yml',
}

# Repository-wide substitutions: remove personal/sandbox identifiers and nested paths.
replacements = [
    ('vital-scout-479118-n7', 'example-gcp-project'),
    ('911571548652', '123456789012'),
    ('rlancaster243/DE-project-1', 'YOUR_GITHUB_OWNER/YOUR_REPOSITORY'),
    ('rlancaster243', 'YOUR_GITHUB_OWNER'),
    ('russell_lancaster243@gmail.com', '<operator-email>'),
    ('Russell Lancaster', 'the primary operator'),
    ('Russell', 'the primary operator'),
    ('~/DE-project-1/project-atlas', '~/Atlas-GCP-Build'),
    ('~/DE-project-1', '~/Atlas-GCP-Build'),
    ('cd project-atlas', 'cd Atlas-GCP-Build'),
    ('project-atlas/', ''),
    ('../.cursor/mcp.json', '.cursor/mcp.json'),
]

for path in DST.rglob('*'):
    if not path.is_file():
        continue
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
        continue
    try:
        text = path.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        continue
    original = text
    for old, new in replacements:
        text = text.replace(old, new)
    if text != original:
        path.write_text(text, encoding='utf-8')

# Rename dbt project package from Atlas-specific nesting only where safe.
# We preserve atlas naming as the reference implementation namespace; runtime cloud
# identifiers remain configurable through environment variables and template config.

# Standalone root GitHub workflows.
workflows = DST / '.github' / 'workflows'
workflows.mkdir(parents=True, exist_ok=True)

(workflows / 'atlas-ci.yml').write_text('''# Credentialless pull-request CI for the standalone Atlas production template.\nname: atlas-ci\n\non:\n  pull_request:\n  push:\n    branches: [main]\n  workflow_dispatch:\n\npermissions:\n  contents: read\n\nconcurrency:\n  group: atlas-ci-${{ github.ref }}\n  cancel-in-progress: true\n\nenv:\n  PYTHON_VERSION: "3.12"\n\njobs:\n  atlas-security-shell:\n    name: atlas-security-shell\n    runs-on: ubuntu-latest\n    timeout-minutes: 15\n    steps:\n      - name: Checkout\n        uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd\n      - name: Set up Python\n        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n        with:\n          python-version: ${{ env.PYTHON_VERSION }}\n          cache: pip\n          cache-dependency-path: requirements-ci.txt\n      - name: Install validation toolchain\n        run: pip install -r requirements-ci.txt\n      - name: Dependency-file sanity\n        run: |\n          python - <<'PY'\n          from pathlib import Path\n          for name in (\n              "requirements.txt",\n              "requirements-ci.txt",\n              "airflow/requirements-airflow.txt",\n              "dbt/requirements-dbt.txt",\n          ):\n              content = Path(name).read_text(encoding="utf-8")\n              assert content.strip(), f"{name} is empty"\n          print("dependency manifests present and non-empty")\n          PY\n      - name: Security and shell gates\n        run: bash scripts/validate_ci.sh --mode static --group security-shell\n      - name: Upload gate results\n        if: always()\n        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n        with:\n          name: security-shell-gate-results\n          path: logs/ci/validate-ci-results.json\n\n  atlas-python:\n    name: atlas-python\n    runs-on: ubuntu-latest\n    timeout-minutes: 20\n    steps:\n      - name: Checkout\n        uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd\n      - name: Set up Python\n        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n        with:\n          python-version: ${{ env.PYTHON_VERSION }}\n          cache: pip\n          cache-dependency-path: |\n            requirements.txt\n            requirements-ci.txt\n      - name: Install locked dependencies\n        run: pip install -r requirements.txt -r requirements-ci.txt\n      - name: Python gates\n        run: bash scripts/validate_ci.sh --mode static --group python\n      - name: Upload gate results\n        if: always()\n        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n        with:\n          name: python-gate-results\n          path: logs/ci/validate-ci-results.json\n\n  atlas-dbt:\n    name: atlas-dbt\n    runs-on: ubuntu-latest\n    timeout-minutes: 20\n    steps:\n      - name: Checkout\n        uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd\n      - name: Set up Python\n        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n        with:\n          python-version: ${{ env.PYTHON_VERSION }}\n          cache: pip\n          cache-dependency-path: dbt/requirements-dbt.txt\n      - name: Install pinned dbt environment\n        run: pip install -r dbt/requirements-dbt.txt\n      - name: dbt static gates\n        run: bash scripts/validate_ci.sh --mode static --group dbt\n      - name: Upload dbt manifest\n        if: always()\n        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n        with:\n          name: dbt-manifest\n          path: dbt/atlas_dbt/target/manifest.json\n          if-no-files-found: warn\n\n  atlas-airflow:\n    name: atlas-airflow\n    runs-on: ubuntu-latest\n    timeout-minutes: 25\n    steps:\n      - name: Checkout\n        uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd\n      - name: Set up Python\n        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n        with:\n          python-version: ${{ env.PYTHON_VERSION }}\n          cache: pip\n          cache-dependency-path: |\n            airflow/requirements-airflow.txt\n            requirements.txt\n            requirements-ci.txt\n      - name: Install pinned Airflow with official constraints\n        run: |\n          pip install "apache-airflow==3.1.7" \\\n            --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.1.7/constraints-3.12.txt"\n          pip install -r airflow/requirements-airflow.txt -r requirements.txt -r requirements-ci.txt\n      - name: pip check\n        run: pip check\n      - name: Airflow gates\n        run: bash scripts/validate_ci.sh --mode static --group airflow\n      - name: DAG tests\n        run: PYTHONPATH=src:dags python -m pytest tests/airflow -q\n      - name: Upload gate results\n        if: always()\n        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n        with:\n          name: airflow-gate-results\n          path: logs/ci/validate-ci-results.json\n\n  atlas-ci-gate:\n    name: atlas-ci-gate\n    runs-on: ubuntu-latest\n    timeout-minutes: 5\n    needs: [atlas-security-shell, atlas-python, atlas-dbt, atlas-airflow]\n    if: always()\n    steps:\n      - name: Require every job to succeed\n        run: |\n          results='${{ toJSON(needs) }}'\n          echo "$results"\n          failed="$(echo "$results" | python3 -c 'import json,sys; n=json.load(sys.stdin); print(" ".join(k for k,v in n.items() if v["result"] != "success"))')"\n          test -z "$failed" || { echo "Failed or skipped required jobs: $failed"; exit 1; }\n          echo "All required Atlas CI jobs succeeded"\n''', encoding='utf-8')

(workflows / 'atlas-integration.yml').write_text('''# Trusted, manually triggered GCP integration validation.\nname: atlas-integration\n\non:\n  workflow_dispatch:\n    inputs:\n      target_sha:\n        description: "Commit SHA to test; empty means main HEAD"\n        required: false\n        default: ""\n\npermissions:\n  contents: read\n  id-token: write\n\nconcurrency:\n  group: atlas-integration\n  cancel-in-progress: false\n\nenv:\n  PYTHON_VERSION: "3.12"\n\njobs:\n  atlas-gcp-integration:\n    name: atlas-gcp-integration\n    runs-on: ubuntu-latest\n    timeout-minutes: 45\n    steps:\n      - name: Checkout main\n        uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd\n        with:\n          ref: main\n          fetch-depth: 0\n      - name: Resolve trusted target\n        run: |\n          target="${{ github.event.inputs.target_sha }}"\n          if [ -z "$target" ]; then target="$(git rev-parse HEAD)"; fi\n          git cat-file -e "${target}^{commit}"\n          git merge-base --is-ancestor "$target" origin/main\n          git checkout "$target"\n      - name: Set up Python\n        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n        with:\n          python-version: ${{ env.PYTHON_VERSION }}\n          cache: pip\n          cache-dependency-path: |\n            requirements.txt\n            dbt/requirements-dbt.txt\n      - name: Install runtime and dbt toolchains\n        run: |\n          pip install -r requirements.txt\n          python -m venv /tmp/dbt-venv\n          /tmp/dbt-venv/bin/pip install -r dbt/requirements-dbt.txt\n          echo "/tmp/dbt-venv/bin" >> "$GITHUB_PATH"\n      - name: Require WIF configuration\n        run: |\n          test -n "${{ vars.ATLAS_WIF_PROVIDER }}"\n          test -n "${{ vars.ATLAS_INTEGRATION_SERVICE_ACCOUNT }}"\n      - name: Authenticate to GCP\n        uses: google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093\n        with:\n          workload_identity_provider: ${{ vars.ATLAS_WIF_PROVIDER }}\n          service_account: ${{ vars.ATLAS_INTEGRATION_SERVICE_ACCOUNT }}\n      - name: Set up gcloud\n        uses: google-github-actions/setup-gcloud@aa5489c8933f4cc7a4f7d45035b3b1440c9c10db\n      - name: Run isolated integration test\n        run: bash scripts/validate_gcp_integration.sh\n      - name: Upload integration results\n        if: always()\n        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n        with:\n          name: integration-results\n          path: logs/ci/integration-results.json\n''', encoding='utf-8')

(workflows / 'atlas-deploy.yml').write_text('''# Controlled deployment. Configure WIF repository variables before use.\nname: atlas-deploy\n\non:\n  workflow_dispatch:\n    inputs:\n      confirm:\n        description: 'Type "deploy-atlas-dev" to confirm'\n        required: true\n      target_sha:\n        description: "Commit SHA to deploy; empty means main HEAD"\n        required: false\n        default: ""\n      create_composer:\n        description: "Create ephemeral Composer if missing"\n        type: boolean\n        default: false\n      leave_paused:\n        description: "Leave DAG paused after smoke validation"\n        type: boolean\n        default: true\n\npermissions:\n  contents: read\n  id-token: write\n\nconcurrency:\n  group: atlas-dev-deployment\n  cancel-in-progress: false\n\nenv:\n  PYTHON_VERSION: "3.12"\n\njobs:\n  atlas-deploy:\n    name: atlas-deploy\n    runs-on: ubuntu-latest\n    timeout-minutes: 120\n    environment: atlas-dev\n    steps:\n      - name: Verify typed confirmation\n        run: test "${{ github.event.inputs.confirm }}" = "deploy-atlas-dev"\n      - name: Checkout main\n        uses: actions/checkout@93cb6efe18208431cddfb8368fd83d5badbf9bfd\n        with:\n          ref: main\n          fetch-depth: 0\n      - name: Resolve trusted target\n        id: sha\n        run: |\n          target="${{ github.event.inputs.target_sha }}"\n          if [ -z "$target" ]; then target="$(git rev-parse HEAD)"; fi\n          git cat-file -e "${target}^{commit}"\n          git merge-base --is-ancestor "$target" origin/main\n          git checkout "$target"\n          echo "sha=$target" >> "$GITHUB_OUTPUT"\n      - name: Set up Python\n        uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1\n        with:\n          python-version: ${{ env.PYTHON_VERSION }}\n          cache: pip\n          cache-dependency-path: requirements.txt\n      - name: Install and validate\n        run: |\n          pip install -r requirements.txt -r requirements-ci.txt\n          bash scripts/validate_ci.sh --mode static --group security-shell\n          bash scripts/validate_ci.sh --mode static --group python\n      - name: Require WIF configuration\n        run: |\n          test -n "${{ vars.ATLAS_WIF_PROVIDER }}"\n          test -n "${{ vars.ATLAS_DEPLOYER_SERVICE_ACCOUNT }}"\n      - name: Authenticate to GCP\n        uses: google-github-actions/auth@7c6bc770dae815cd3e89ee6cdf493a5fab2cc093\n        with:\n          workload_identity_provider: ${{ vars.ATLAS_WIF_PROVIDER }}\n          service_account: ${{ vars.ATLAS_DEPLOYER_SERVICE_ACCOUNT }}\n      - name: Set up gcloud\n        uses: google-github-actions/setup-gcloud@aa5489c8933f4cc7a4f7d45035b3b1440c9c10db\n      - name: Ensure Composer environment\n        if: ${{ github.event.inputs.create_composer == 'true' }}\n        run: ATLAS_APPROVE_COMPOSER_CREATE=true bash scripts/manage_atlas_composer.sh create\n      - name: Build and upload immutable release\n        run: bash scripts/build_deployment_bundle.sh --upload\n      - name: Deploy release\n        run: |\n          FLAGS=""\n          if [ "${{ github.event.inputs.leave_paused }}" = "true" ]; then FLAGS="--leave-paused"; fi\n          ATLAS_APPROVE_DEPLOY=true bash scripts/deploy_atlas_release.sh \\\n            --git-sha "${{ steps.sha.outputs.sha }}" $FLAGS\n      - name: Upload deployment evidence\n        if: always()\n        uses: actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02\n        with:\n          name: deployment-evidence\n          path: |\n            dist/release-manifest-*.json\n            /tmp/smoke-warehouse.json\n          if-no-files-found: warn\n''', encoding='utf-8')

# Standalone Cursor MCP configuration: template-safe, no credentials stored.
cursor_dir = DST / '.cursor'
cursor_dir.mkdir(exist_ok=True)
(cursor_dir / 'mcp.json').write_text('''{\n  "mcpServers": {\n    "bigquery": {\n      "command": "uvx",\n      "args": ["mcp-server-bigquery"],\n      "env": {\n        "PROJECT_ID": "${env:ATLAS_GCP_PROJECT_ID}",\n        "LOCATION": "${env:ATLAS_GCP_LOCATION}"\n      }\n    },\n    "dbt-atlas": {\n      "command": "${env:DBT_PATH}",\n      "args": [\n        "--project-dir", "dbt/atlas_dbt",\n        "--profiles-dir", "dbt/atlas_dbt",\n        "--target", "${env:DBT_TARGET}"\n      ]\n    }\n  }\n}\n''', encoding='utf-8')

# Template environment sample.
(DST / '.env.example').write_text('''# Atlas production-template configuration\nATLAS_PROJECT_NAME=atlas\nATLAS_ENVIRONMENT=dev\nATLAS_GCP_PROJECT_ID=example-gcp-project\nATLAS_GCP_PROJECT_NUMBER=123456789012\nATLAS_GCP_LOCATION=US\nATLAS_GCP_REGION=us-central1\nATLAS_DATASET_PREFIX=atlas\nATLAS_RAW_DATASET=atlas_raw\nATLAS_DBT_DATASET=atlas\nATLAS_OPS_DATASET=atlas_ops\nATLAS_GCS_BUCKET=atlas-raw-events-example-gcp-project\nATLAS_RELEASE_BUCKET=atlas-releases-example-gcp-project\nATLAS_SERVICE_ACCOUNT_PREFIX=atlas\nATLAS_DAG_ID=atlas_batch_pipeline\nATLAS_SCHEDULE=@daily\nATLAS_NOTIFICATION_EMAIL=<operator-email>\nATLAS_COST_CEILING_BYTES=1000000000\nDBT_TARGET=bigquery\nDBT_PATH=.venv/bin/dbt\n''', encoding='utf-8')

# Standalone repository ignore rules.
(DST / '.gitignore').write_text('''# Python\n__pycache__/\n*.py[cod]\n.pytest_cache/\n.mypy_cache/\n.ruff_cache/\n.venv/\n*.egg-info/\ndist/\nbuild/\n\n# Generated pipeline data and evidence\ndata/*.jsonl\ndata/runs/\nlogs/\n.gcp/\n.env\n\n# dbt / Airflow\ndbt/**/target/\ndbt/**/logs/\nairflow/airflow.db\nairflow/logs/\nairflow/standalone_admin_password.txt\n\n# OS / IDE\n.DS_Store\nThumbs.db\n.idea/\n.vscode/\n''', encoding='utf-8')

# Rewrite top-level documentation for adoption rather than the original learning chronology.
(DST / 'README.md').write_text('''# Atlas GCP Production Data Platform Template\n\nAtlas is a reusable, production-oriented batch data platform foundation for Google\nCloud. It combines Python ingestion, Cloud Storage, BigQuery, dbt, Airflow,\ncredentialless CI, controlled deployment, observability, recovery, governance,\nand cost controls in one repository.\n\nThis is not a claim that cloning a repository magically makes a system production\nready. It provides enforced engineering defaults and operating artifacts that a\nteam must configure, validate, deploy, and own.\n\n## Architecture\n\n```text\nSource / synthetic events\n        ↓\nPython ingestion → immutable Cloud Storage objects\n        ↓\nBigQuery raw tables\n        ↓\ndbt staging → classification/quarantine → facts/dimensions/marts\n        ↓\nAirflow orchestration, audit, retries, backfills, and recovery\n        ↓\nLogging, metrics, alerts, governance, lineage, cost guards, runbooks\n```\n\n## Included capabilities\n\n- Deterministic sample event generation and idempotent batch ingestion\n- Partitioned and clustered BigQuery storage\n- Governed dbt layers, tests, contracts, and incremental processing\n- Airflow DAGs with stable batch identity, retries, auditing, and backfills\n- Credentialless pull-request CI\n- Optional keyless GitHub-to-GCP delivery through Workload Identity Federation\n- Immutable release bundles, migrations, smoke validation, and rollback\n- Structured telemetry, metrics, alerts, dashboards, and runbooks\n- Failure injection, recovery auditing, schema compatibility, and cost guards\n- Ownership, lineage, consumer-impact, retention, security, and evidence controls\n\n## Start here\n\n1. Read [`START_HERE.md`](START_HERE.md).\n2. Copy `.env.example` to `.env` and replace every example value.\n3. Create a Python virtual environment and install dependencies.\n4. Run credentialless static validation.\n5. Run the local sample pipeline.\n6. Configure an isolated GCP project before any approved cloud mutation.\n\n```bash\ncp .env.example .env\npython3 -m venv .venv\nsource .venv/bin/activate\npip install -r requirements.txt -r requirements-ci.txt\nexport PYTHONPATH=src\nbash scripts/validate_ci.sh --mode static\npython scripts/generate_events.py\npytest\n```\n\n## Configuration\n\nThe template keeps the `atlas` reference namespace in code and sample assets,\nwhile cloud identities and runtime resources are configured through environment\nvariables. See [`docs/template-configuration.md`](docs/template-configuration.md).\n\nNever deploy the example values. Configure project IDs, buckets, datasets,\nservice accounts, notification channels, cost ceilings, retention, and schedules\nfor the adopting environment.\n\n## CI and delivery\n\nPull requests run credentialless validation. Trusted integration and deployment\nworkflows are manual and require repository variables for Workload Identity\nFederation:\n\n- `ATLAS_WIF_PROVIDER`\n- `ATLAS_INTEGRATION_SERVICE_ACCOUNT`\n- `ATLAS_DEPLOYER_SERVICE_ACCOUNT`\n\nThe bootstrap scripts are plan-first and mutation-gated. Review IAM, cost, and\ncleanup behavior before applying anything.\n\n## Evidence and limitations\n\nThe original Atlas reference implementation was tested with synthetic workloads,\nclean-clone validation, CI, controlled cloud deployments, failure drills, and\noperator handoff. Those historical reports remain in `docs/` as engineering\nevidence. They do not prove that a new adoption has passed the same gates.\n\nA new deployment is complete only after its own CI, isolated cloud validation,\nincident drill, recovery exercise, security review, cost review, and handoff.\n\n## License\n\nApache License 2.0. See [`LICENSE`](LICENSE).\n''', encoding='utf-8')

(DST / 'START_HERE.md').write_text('''# Start Here\n\nAtlas is a production-data-platform template, not a one-command production\nservice. Begin with the route matching your responsibility.\n\n## Adopter / platform engineer\n\n1. Read `README.md` and `docs/template-configuration.md`.\n2. Review `docs/reference-architecture/architecture-invariants.md`.\n3. Replace all sample environment values.\n4. Run `bash scripts/validate_ci.sh --mode static`.\n5. Exercise the local pipeline and tests.\n6. Provision an isolated GCP namespace using plan mode first.\n7. Run one batch, one deliberate failure, one recovery, and cleanup.\n8. Record environment-specific evidence instead of inheriting the reference\n   implementation's claims.\n\n## Operator\n\nRead:\n\n- `docs/handoff/operator-onboarding.md`\n- `docs/runbook.md`\n- `docs/runbook-sprint3.md`\n- `docs/observability-runbook-sprint5.md`\n- `docs/recovery-runbook-sprint6.md`\n\nBe able to answer: Did the pipeline run? Is the data correct and complete? Who is\nalerted? How is it recovered? How is recurrence prevented?\n\n## Reviewer / architect\n\nStart with:\n\n- `docs/reference-architecture/README.md`\n- `docs/reference-architecture/system-context.md`\n- `docs/reference-architecture/interfaces-and-contracts.md`\n- `docs/reference-architecture/security-and-identity-model.md`\n- `docs/reference-architecture/reliability-and-recovery-model.md`\n- `docs/reference-architecture/unresolved-risks.md`\n\n## Coding agent\n\nRead `docs/handoff/agent-onboarding.md`. Treat generated code as provisional.\nState assumptions, risks, affected files, test plan, and rollback considerations\nbefore major changes. Do not claim production readiness without environment-specific\nevidence.\n\n## Credentialless verification\n\n```bash\npython3 -m venv .venv\nsource .venv/bin/activate\npip install -r requirements.txt -r requirements-ci.txt\nexport PYTHONPATH=src\nbash scripts/validate_ci.sh --mode static\n```\n''', encoding='utf-8')

(DST / 'CONTRIBUTING.md').write_text('''# Contributing\n\nUse a branch → pull request → CI → review → merge workflow.\n\nEvery material change must include:\n\n- declared purpose and affected components\n- tests or an explicit reason tests are unchanged\n- documentation for changed behavior or operations\n- migration and rollback considerations\n- no secrets or personal data\n- evidence that the canonical CI entry point passes\n\nGenerated code must be read, explained, modified where necessary, and tested by\nthe contributor.\n''', encoding='utf-8')

(DST / 'SECURITY.md').write_text('''# Security Policy\n\nDo not commit credentials, service-account keys, API keys, OAuth secrets, webhook\nURLs, personal notification addresses, or production data.\n\nUse Workload Identity Federation for GitHub-to-GCP authentication. Keep pull\nrequest CI credentialless. Apply least privilege, plan IAM changes before\nmutation, and review the security and identity documentation before deployment.\n\nReport security issues privately to the repository owner rather than opening a\npublic issue containing exploit details or credentials.\n''', encoding='utf-8')

config_doc = DST / 'docs' / 'template-configuration.md'
config_doc.parent.mkdir(parents=True, exist_ok=True)
config_doc.write_text('''# Template Configuration\n\n## Required runtime parameters\n\n| Parameter | Purpose |\n| --- | --- |\n| `ATLAS_GCP_PROJECT_ID` | Target GCP project |\n| `ATLAS_GCP_PROJECT_NUMBER` | Numeric project identifier for WIF/IAM |\n| `ATLAS_GCP_LOCATION` | BigQuery multi-region or region |\n| `ATLAS_GCP_REGION` | Regional services such as Composer |\n| `ATLAS_GCS_BUCKET` | Immutable raw-ingestion bucket |\n| `ATLAS_RELEASE_BUCKET` | Immutable release-bundle bucket |\n| `ATLAS_DATASET_PREFIX` | Prefix for BigQuery datasets |\n| `ATLAS_SERVICE_ACCOUNT_PREFIX` | Prefix for provisioned identities |\n| `ATLAS_DAG_ID` | Airflow DAG identifier |\n| `ATLAS_SCHEDULE` | Airflow schedule |\n| `ATLAS_NOTIFICATION_EMAIL` | Operator notification destination |\n| `ATLAS_COST_CEILING_BYTES` | Pre-execution query guard |\n\n## GitHub repository variables\n\nTrusted workflows require:\n\n- `ATLAS_WIF_PROVIDER`\n- `ATLAS_INTEGRATION_SERVICE_ACCOUNT`\n- `ATLAS_DEPLOYER_SERVICE_ACCOUNT`\n\nPull-request CI must remain credentialless. Do not add cloud credentials to PR\nworkflows merely because authentication is annoying. Authentication is supposed\nto be annoying when the alternative is accidental infrastructure mutation.\n\n## Adoption gate\n\nBefore calling an adoption complete, prove:\n\n1. clean clone and static CI\n2. isolated GCP deployment\n3. successful batch and warehouse reconciliation\n4. deliberate failure and targeted recovery\n5. alerts and runbook routing\n6. schema compatibility behavior\n7. IAM and secret review\n8. cost ceiling and cleanup\n9. operator handoff\n''', encoding='utf-8')

# Parameterize WIF bootstrap script defaults and repository claims.
wif = DST / 'scripts' / 'bootstrap_github_wif.sh'
if wif.exists():
    text = wif.read_text(encoding='utf-8')
    text = re.sub(r'REPO="[^\n]*"', 'REPO="${ATLAS_GITHUB_REPOSITORY:-YOUR_GITHUB_OWNER/YOUR_REPOSITORY}"', text)
    text = text.replace('PROJECT_ID="example-gcp-project"', 'PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-}"')
    text = text.replace('PROJECT_NUMBER="123456789012"', 'PROJECT_NUMBER="${ATLAS_GCP_PROJECT_NUMBER:-}"')
    text = text.replace('POOL_ID="atlas-github-pool"', 'POOL_ID="${ATLAS_WIF_POOL_ID:-atlas-github-pool}"')
    text = text.replace('PROVIDER_ID="atlas-github-provider"', 'PROVIDER_ID="${ATLAS_WIF_PROVIDER_ID:-atlas-github-provider}"')
    text = text.replace('INTEGRATION_SA="atlas-github-integration"', 'INTEGRATION_SA="${ATLAS_INTEGRATION_SA_NAME:-atlas-github-integration}"')
    text = text.replace('DEPLOYER_SA="atlas-github-deployer"', 'DEPLOYER_SA="${ATLAS_DEPLOYER_SA_NAME:-atlas-github-deployer}"')
    marker = 'set -euo pipefail\n'
    guard = '''set -euo pipefail\n\n: "${ATLAS_GCP_PROJECT_ID:?Set ATLAS_GCP_PROJECT_ID}"\n: "${ATLAS_GCP_PROJECT_NUMBER:?Set ATLAS_GCP_PROJECT_NUMBER}"\n: "${ATLAS_GITHUB_REPOSITORY:?Set ATLAS_GITHUB_REPOSITORY as owner/repo}"\n'''
    if marker in text and 'Set ATLAS_GITHUB_REPOSITORY as owner/repo' not in text:
        text = text.replace(marker, guard, 1)
    wif.write_text(text, encoding='utf-8')

# Adapt clean-clone validation from nested source repo to standalone repository.
clean_clone = DST / 'scripts' / 'validate_clean_clone.sh'
if clean_clone.exists():
    text = clean_clone.read_text(encoding='utf-8')
    text = text.replace('CLONE_DIR="$TEMP_ROOT/repo"\nATLAS_DIR="$CLONE_DIR/project-atlas"', 'CLONE_DIR="$TEMP_ROOT/repo"\nATLAS_DIR="$CLONE_DIR"')
    text = text.replace('test -d "$CLONE_DIR/project-atlas"', 'test -f "$CLONE_DIR/README.md"')
    clean_clone.write_text(text, encoding='utf-8')

# Canonical CI script had nested-repository assumptions: make paths repository-root relative.
validate_ci = DST / 'scripts' / 'validate_ci.sh'
if validate_ci.exists():
    text = validate_ci.read_text(encoding='utf-8')
    text = text.replace('git grep -nE "$SECRET_RE" -- project-atlas', 'git -C "$ATLAS_ROOT" grep -nE "$SECRET_RE" -- .')
    text = text.replace('"$ATLAS_ROOT/../.github/workflows"', '"$ATLAS_ROOT/.github/workflows"')
    text = text.replace("root = Path('.github/workflows')", "root = Path(os.environ['ATLAS_ROOT']) / '.github/workflows'")
    text = text.replace('import pathlib, re, sys', 'import os, pathlib, re, sys')
    validate_ci.write_text(text, encoding='utf-8')

# Update acceptance tests that intentionally asserted the old nested workspace.
for path in (DST / 'tests').rglob('*.py'):
    text = path.read_text(encoding='utf-8')
    text = text.replace("REPO_ROOT / 'project-atlas'", 'REPO_ROOT')
    text = text.replace('REPO_ROOT.parent / ".cursor" / "mcp.json"', 'REPO_ROOT / ".cursor" / "mcp.json"')
    text = text.replace("assert {\"bigquery\", \"dbt\", \"dbt-atlas\"}.issubset(servers)", "assert {\"bigquery\", \"dbt-atlas\"}.issubset(servers)")
    path.write_text(text, encoding='utf-8')

# Remove stale broken references to excluded artifacts from reference index docs.
for path in (DST / 'docs').rglob('*.md'):
    text = path.read_text(encoding='utf-8')
    filtered = []
    for line in text.splitlines():
        low = line.lower()
        if 'artifact-platform' in low or 'public-extraction-review' in low or 'template-extraction-plan' in low:
            continue
        filtered.append(line)
    path.write_text('\n'.join(filtered).rstrip() + '\n', encoding='utf-8')

# Ensure no personal email/project remains in public candidate.
for path in DST.rglob('*'):
    if not path.is_file():
        continue
    if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in TEXT_NAMES:
        continue
    text = path.read_text(encoding='utf-8', errors='ignore')
    forbidden = [
        'vital-scout-479118-n7',
        '911571548652',
        'rlancaster243',
        'DE-project-1',
        'russell_lancaster243@gmail.com',
    ]
    hits = [value for value in forbidden if value in text]
    if hits:
        raise SystemExit(f'{path.relative_to(DST)} still contains private/source identifiers: {hits}')

print(f'Built standalone Atlas template at {DST}')
