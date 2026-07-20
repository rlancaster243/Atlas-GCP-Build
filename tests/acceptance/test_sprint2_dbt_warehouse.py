"""Static acceptance checks for the Sprint 2 Atlas dbt warehouse artifacts."""

from __future__ import annotations

import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
ATLAS_ROOT = REPOSITORY_ROOT
DBT_PROJECT_ROOT = ATLAS_ROOT / "dbt" / "atlas_dbt"


class Sprint2DbtWarehouseAcceptanceTest(unittest.TestCase):
    def test_required_models_seeds_and_tests_exist(self) -> None:
        required_paths = [
            DBT_PROJECT_ROOT / "models/sources/sources.yml",
            DBT_PROJECT_ROOT / "models/staging/stg_events.sql",
            DBT_PROJECT_ROOT / "models/staging/staging.yml",
            DBT_PROJECT_ROOT / "models/intermediate/int_event_classification.sql",
            DBT_PROJECT_ROOT / "models/intermediate/int_accepted_events.sql",
            DBT_PROJECT_ROOT / "models/intermediate/int_rejected_events.sql",
            DBT_PROJECT_ROOT / "models/intermediate/intermediate.yml",
            DBT_PROJECT_ROOT / "models/core/dim_users.sql",
            DBT_PROJECT_ROOT / "models/core/dim_countries.sql",
            DBT_PROJECT_ROOT / "models/core/fct_events.sql",
            DBT_PROJECT_ROOT / "models/core/core.yml",
            DBT_PROJECT_ROOT / "models/marts/mart_daily_event_metrics.sql",
            DBT_PROJECT_ROOT / "models/marts/marts.yml",
            DBT_PROJECT_ROOT / "seeds/valid_country_codes.csv",
            DBT_PROJECT_ROOT / "seeds/seeds.yml",
            DBT_PROJECT_ROOT / "tests/assert_source_anomaly_profile.sql",
            DBT_PROJECT_ROOT / "tests/assert_raw_classification_reconciliation.sql",
            DBT_PROJECT_ROOT / "tests/assert_fact_rejected_reconciliation.sql",
            DBT_PROJECT_ROOT / "tests/assert_mart_fact_reconciliation.sql",
            ATLAS_ROOT / "scripts/run_dbt_sprint2.sh",
            ATLAS_ROOT / "scripts/validate_dbt_sprint2.sh",
            ATLAS_ROOT / "docs/architecture-sprint2.md",
            ATLAS_ROOT / "docs/model-catalog-sprint2.md",
            ATLAS_ROOT / "docs/runbook-sprint2.md",
            ATLAS_ROOT / "docs/validation-report-sprint2.md",
            ATLAS_ROOT / "docs/adr/ADR-002-isolated-atlas-dbt-project.md",
            ATLAS_ROOT / "docs/adr/ADR-003-corrected-temporal-semantics.md",
            ATLAS_ROOT / "docs/adr/ADR-004-no-snapshots-sprint2.md",
        ]
        missing = [str(path.relative_to(REPOSITORY_ROOT)) for path in required_paths if not path.is_file()]
        self.assertEqual([], missing, f"missing Sprint 2 warehouse files: {missing}")

    def test_dbt_project_declares_layer_schemas(self) -> None:
        project = (DBT_PROJECT_ROOT / "dbt_project.yml").read_text(encoding="utf-8")
        for marker in [
            "+schema: staging",
            "+schema: intermediate",
            "+schema: core",
            "+schema: marts",
            "validated_run_id:",
        ]:
            self.assertIn(marker, project)

    def test_classification_and_scripts_are_executable(self) -> None:
        for script_name in ("run_dbt_sprint2.sh", "validate_dbt_sprint2.sh"):
            script_path = ATLAS_ROOT / "scripts" / script_name
            self.assertTrue(script_path.stat().st_mode & 0o100, f"{script_name} must be executable")

        classification = (DBT_PROJECT_ROOT / "models/intermediate/int_event_classification.sql").read_text(
            encoding="utf-8"
        )
        staging = (DBT_PROJECT_ROOT / "models/staging/stg_events.sql").read_text(encoding="utf-8")
        for snippet in [
            "missing_user_id",
            "invalid_country_code",
            "future_dated",
            "duplicate_extra",
        ]:
            self.assertIn(snippet, classification)
        for snippet in [
            "is_backdated_event_date",
            "has_event_date_timestamp_mismatch",
            "is_event_time_late_arriving",
        ]:
            self.assertIn(snippet, staging)


if __name__ == "__main__":
    unittest.main()
