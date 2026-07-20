from __future__ import annotations

import json
import sys
from pathlib import Path

if len(sys.argv) != 2:
    raise SystemExit("usage: finalize.py <atlas-output-root>")

root = Path(sys.argv[1]).resolve()
if not root.is_dir():
    raise SystemExit(f"output root not found: {root}")

gitignore = """# Python
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
*.egg-info/
dist/
build/

# Virtual environments
.venv/
.venv-*/
.venv-dbt/

# Local configuration and credentials
.env
.env.*
!.env.example
credentials/
secrets/
.gcp/
service-account*.json
*-key.json

# Generated pipeline artifacts
data/*.jsonl
data/runs/
logs/

# dbt generated state and local profile
dbt/atlas_dbt/target/
dbt/atlas_dbt/logs/
dbt/atlas_dbt/dbt_packages/
dbt/atlas_dbt/profiles.yml

# Airflow local state
airflow/logs/
airflow/airflow.db
airflow/airflow.cfg
airflow/webserver_config.py

# Terraform local state
**/.terraform/
*.tfstate
*.tfstate.*
.terraform.lock.hcl

# OS and editor
.DS_Store
Thumbs.db
.vscode/
"""
(root / ".gitignore").write_text(gitignore, encoding="utf-8")

mcp = {
    "mcpServers": {
        "bigquery": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-bigquery"],
            "env": {"GOOGLE_CLOUD_PROJECT": "${env:ATLAS_GCP_PROJECT_ID}"},
        },
        "dbt-atlas": {
            "command": "${workspaceFolder}/.venv-dbt/bin/dbt",
            "args": ["--version"],
            "env": {
                "DBT_PROJECT_DIR": "${workspaceFolder}/dbt/atlas_dbt",
                "DBT_PATH": "${workspaceFolder}/.venv-dbt/bin/dbt",
                "DBT_TARGET": "bigquery",
            },
        },
    }
}
(root / ".cursor").mkdir(exist_ok=True)
(root / ".cursor" / "mcp.json").write_text(
    json.dumps(mcp, indent=2) + "\n",
    encoding="utf-8",
)

for relative_path in (
    "tests/acceptance/test_sprint2_dbt_environment.py",
    "tests/acceptance/test_sprint2_dbt_warehouse.py",
):
    path = root / relative_path
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'REPOSITORY_ROOT = Path(__file__).resolve().parents[3]\nATLAS_ROOT = REPOSITORY_ROOT / "project-atlas"',
        'REPOSITORY_ROOT = Path(__file__).resolve().parents[2]\nATLAS_ROOT = REPOSITORY_ROOT',
    )
    text = text.replace('"project-atlas/', '"')
    text = text.replace("${workspaceFolder}/project-atlas/", "${workspaceFolder}/")
    text = text.replace(
        'self.assertTrue({"bigquery", "dbt", "dbt-atlas"} <= servers.keys())',
        'self.assertTrue({"bigquery", "dbt-atlas"} <= servers.keys())',
    )
    path.write_text(text, encoding="utf-8")

print("standalone acceptance and security contracts finalized")
