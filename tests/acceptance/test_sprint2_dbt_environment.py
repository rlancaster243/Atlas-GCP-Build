"""Static acceptance checks for the Sprint 2 Atlas dbt environment."""

from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ATLAS_ROOT = REPOSITORY_ROOT
DBT_ROOT = ATLAS_ROOT / "dbt"
DBT_PROJECT_ROOT = DBT_ROOT / "atlas_dbt"


def _ignore_rules(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


class Sprint2DbtEnvironmentAcceptanceTest(unittest.TestCase):
    def test_environment_artifacts_exist(self) -> None:
        required_files = [
            DBT_ROOT / "requirements-dbt.txt",
            DBT_PROJECT_ROOT / "dbt_project.yml",
            DBT_PROJECT_ROOT / "packages.yml",
            DBT_PROJECT_ROOT / "package-lock.yml",
            DBT_PROJECT_ROOT / "profiles.yml.example",
            ATLAS_ROOT / "scripts" / "setup_dbt.sh",
        ]

        missing = [str(path.relative_to(REPOSITORY_ROOT)) for path in required_files if not path.is_file()]
        self.assertEqual([], missing, f"missing Sprint 2 dbt environment files: {missing}")

    def test_root_and_atlas_ignore_rules_protect_dbt_secrets_and_artifacts(self) -> None:
        shared_security_rules = {
            ".env.*",
            "credentials/",
            "secrets/",
            "service-account*.json",
            "*-key.json",
        }
        root_rules = _ignore_rules(REPOSITORY_ROOT / ".gitignore")
        atlas_rules = _ignore_rules(ATLAS_ROOT / ".gitignore")

        self.assertTrue(shared_security_rules <= root_rules)
        self.assertTrue(shared_security_rules <= atlas_rules)
        self.assertTrue(
            {
                ".venv-dbt/",
                "dbt/atlas_dbt/target/",
                "dbt/atlas_dbt/logs/",
                "dbt/atlas_dbt/dbt_packages/",
                "dbt/atlas_dbt/profiles.yml",
            }
            <= root_rules
        )
        self.assertTrue(
            {
                ".venv-dbt/",
                "dbt/atlas_dbt/target/",
                "dbt/atlas_dbt/logs/",
                "dbt/atlas_dbt/dbt_packages/",
                "dbt/atlas_dbt/profiles.yml",
            }
            <= atlas_rules
        )

    def test_safe_examples_and_arbitrary_json_remain_trackable(self) -> None:
        safe_paths = [
            ".env.example",
            "dbt/atlas_dbt/profiles.yml.example",
            "config/events.json",
        ]
        for relative_path in safe_paths:
            result = subprocess.run(
                ["git", "check-ignore", "--no-index", "--quiet", relative_path],
                cwd=REPOSITORY_ROOT,
                check=False,
            )
            self.assertEqual(1, result.returncode, f"{relative_path} must remain trackable")

    def test_dbt_versions_package_and_project_defaults_are_pinned(self) -> None:
        requirements = (DBT_ROOT / "requirements-dbt.txt").read_text(encoding="utf-8").splitlines()
        self.assertEqual(["dbt-core==1.11.12", "dbt-bigquery==1.11.3"], requirements)

        packages = (DBT_PROJECT_ROOT / "packages.yml").read_text(encoding="utf-8")
        package_lock = (DBT_PROJECT_ROOT / "package-lock.yml").read_text(encoding="utf-8")
        for content in (packages, package_lock):
            self.assertIn("dbt-labs/dbt_utils", content)
            self.assertIn("version: 1.4.1", content)

        project = (DBT_PROJECT_ROOT / "dbt_project.yml").read_text(encoding="utf-8")
        self.assertIn("name: atlas_dbt", project)
        self.assertIn("profile: atlas_dbt", project)
        self.assertIn("lookback_days: 3", project)
        self.assertIn('validated_run_id: "atlas-20260714T163527Z-19a0e4f6"', project)
        self.assertNotIn("snapshot-paths:", project)
        self.assertFalse((DBT_PROJECT_ROOT / "snapshots").exists())

    def test_profile_example_is_oauth_only_and_uses_environment_variables(self) -> None:
        profile = (DBT_PROJECT_ROOT / "profiles.yml.example").read_text(encoding="utf-8")
        self.assertIn("method: oauth", profile)
        self.assertIn("env_var('ATLAS_GCP_PROJECT_ID')", profile)
        self.assertIn("env_var('ATLAS_DBT_DATASET', 'atlas')", profile)
        self.assertIn("env_var('DBT_LOCATION')", profile)
        self.assertNotIn("service-account", profile)
        self.assertNotIn("keyfile:", profile)

    def test_setup_script_and_atlas_mcp_use_the_isolated_environment(self) -> None:
        setup_script_path = ATLAS_ROOT / "scripts" / "setup_dbt.sh"
        setup_script = setup_script_path.read_text(encoding="utf-8")
        self.assertTrue(setup_script_path.stat().st_mode & 0o100)
        for required_text in [
            "set -Eeuo pipefail",
            "require_command gcloud",
            "require_command bq",
            "require_command git",
            "python3",
            "atlas_raw",
            "DBT_LOCATION",
            ".venv-dbt",
            "import ensurepip",
            "-m pip --version",
            "requirements-dbt.txt",
            'dbt" deps',
            "${DBT_PROFILES_DIR:-$HOME/.dbt}",
            "GOOGLE_APPLICATION_CREDENTIALS",
            "service-account",
            "chmod 600",
            'dbt" debug',
        ]:
            self.assertIn(required_text, setup_script)
        self.assertNotIn("set -x", setup_script)

        mcp_config = json.loads((REPOSITORY_ROOT / ".cursor" / "mcp.json").read_text(encoding="utf-8"))
        servers = mcp_config["mcpServers"]
        self.assertTrue({"bigquery", "dbt-atlas"} <= servers.keys())
        atlas_env = servers["dbt-atlas"]["env"]
        self.assertEqual(
            "${workspaceFolder}/dbt/atlas_dbt",
            atlas_env["DBT_PROJECT_DIR"],
        )
        self.assertEqual(
            "${workspaceFolder}/.venv-dbt/bin/dbt",
            atlas_env["DBT_PATH"],
        )
        self.assertNotIn("DBT_PROFILES_DIR", atlas_env)


if __name__ == "__main__":
    unittest.main()
