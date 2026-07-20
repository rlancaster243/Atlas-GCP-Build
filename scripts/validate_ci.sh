#!/usr/bin/env bash
# Canonical Atlas validation entry point (Sprint 4).
#
# The single validation contract shared by Cursor Cloud Agents, local
# developers, GitHub Actions, and release tooling.
#
# Usage:
#   bash scripts/validate_ci.sh --mode static        # no GCP credentials needed
#   bash scripts/validate_ci.sh --mode integration   # isolated GCP resources
#   bash scripts/validate_ci.sh --mode all
#
# Behavior:
#   - exits nonzero when any required gate fails
#   - prints a concise gate summary
#   - writes machine-readable results to logs/ci/validate-ci-results.json
#   - never prints secret values and never mutates canonical GCP data in
#     static mode
set -uo pipefail

ATLAS_ROOT="${ATLAS_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$ATLAS_ROOT" || exit 1

airflow_installed() {
  # The local airflow/ docs folder shadows the package as a namespace import,
  # so probe distribution metadata instead of `import airflow`.
  python3 -c "from importlib.metadata import version; version('apache-airflow')" 2>/dev/null
}

MODE="static"
# Gate group lets one CI job run its slice of the canonical contract:
#   all (default) | security-shell | python | airflow | dbt
# When a specific group is requested, its toolchain is REQUIRED: a missing
# tool fails the gate instead of skipping it.
GROUP="${ATLAS_CI_GATE_GROUP:-all}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --group) GROUP="$2"; shift 2 ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done
case "$MODE" in
  static|integration|all) ;;
  *) echo "Invalid --mode '$MODE' (static|integration|all)" >&2; exit 1 ;;
esac
case "$GROUP" in
  all|security-shell|python|airflow|dbt) ;;
  *) echo "Invalid --group '$GROUP' (all|security-shell|python|airflow|dbt)" >&2; exit 1 ;;
esac

in_group() {
  # in_group <group...>: true when GROUP is all or one of the arguments.
  [[ "$GROUP" == "all" ]] && return 0
  local candidate
  for candidate in "$@"; do
    [[ "$GROUP" == "$candidate" ]] && return 0
  done
  return 1
}

RESULTS_DIR="${ATLAS_ROOT}/logs/ci"
mkdir -p "$RESULTS_DIR"
RESULTS_FILE="${RESULTS_DIR}/validate-ci-results.json"
: >"${RESULTS_FILE}.tmp"

GATE_NAMES=()
GATE_STATUSES=()
FAILED=0

run_gate() {
  # run_gate <name> <command...>
  local name="$1"
  shift
  local started ended status
  started="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo ""
  echo "===== GATE: ${name} ====="
  if "$@"; then
    status="PASS"
  else
    status="FAIL"
    FAILED=1
  fi
  ended="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  GATE_NAMES+=("$name")
  GATE_STATUSES+=("$status")
  printf '{"gate":"%s","status":"%s","started_at":"%s","ended_at":"%s","mode":"%s"}\n' \
    "$name" "$status" "$started" "$ended" "$MODE" >>"${RESULTS_FILE}.tmp"
  echo "----- ${name}: ${status} -----"
}

skip_gate() {
  local name="$1" reason="$2"
  GATE_NAMES+=("$name")
  GATE_STATUSES+=("SKIPPED")
  printf '{"gate":"%s","status":"SKIPPED","reason":"%s","mode":"%s"}\n' \
    "$name" "$reason" "$MODE" >>"${RESULTS_FILE}.tmp"
  echo "===== GATE: ${name} SKIPPED (${reason}) ====="
}

# ---------------------------------------------------------------------------
# Gate implementations
# ---------------------------------------------------------------------------

gate_secret_scan() {
  # Tracked-content scan. Detector patterns and sanitizer fixtures live in
  # audit.py and the artifact-platform tests; exclude only those exact files.
  local matches
  matches="$(git -C "$ATLAS_ROOT/.." grep -nIE \
    '(-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----|AIza[0-9A-Za-z_-]{35}|"type": "service_account")' \
    -- 'project-atlas' \
    ':!scripts/validate_ci.sh' \
    ':!src/atlas/ops/audit.py' \
    ':!tests/unit/test_audit.py' \
    ':!tests/unit/test_security_policy.py' \
    ':!artifact-platform/tests/*' \
    ':!artifact-platform/src/artifact_platform/secrets.py' \
    2>/dev/null || true)"
  if [[ -n "$matches" ]]; then
    echo "Potential credentials detected in tracked files (values not shown):" >&2
    # Print file:line only — never the matched content.
    cut -d: -f1,2 <<<"$matches" >&2
    return 1
  fi
  # Untracked credential files inside the worktree.
  local untracked
  untracked="$(git -C "$ATLAS_ROOT/.." status --porcelain --untracked-files=all \
    | awk '{print $2}' \
    | grep -E '(^|/)(.*service.?account.*\.json|.*credentials.*\.json|.*\.pem|\.gcp/)' || true)"
  if [[ -n "$untracked" ]]; then
    echo "Untracked credential-like files present in the worktree:" >&2
    echo "$untracked" >&2
    return 1
  fi
  echo "No tracked or untracked credential material detected."
}

gate_shell_syntax() {
  find scripts -name '*.sh' -print0 | xargs -0 -n1 bash -n
}

gate_shellcheck() {
  # SC1091: sourced files resolved at runtime. Informational severity only.
  shellcheck --severity=warning --exclude=SC1091 scripts/*.sh
}

gate_python_format() {
  ruff format --check src/atlas scripts dags tests
}

gate_python_lint() {
  ruff check src/atlas scripts dags tests
}

gate_python_types() {
  mypy --config-file mypy.ini
}

gate_python_tests() {
  PYTHONPATH="src:dags" python3 -m pytest tests/unit tests/airflow -q
}

gate_workflow_yaml() {
  local workflows_dir="${ATLAS_ROOT}/../.github/workflows"
  if [[ ! -d "$workflows_dir" ]]; then
    echo "No workflows directory yet"
    return 0
  fi
  yamllint -d "{extends: default, rules: {line-length: {max: 140}, truthy: disable, document-start: disable, comments: {min-spaces-from-content: 1}}}" "$workflows_dir"
}

gate_config_validation() {
  python3 - <<'PY'
import sys

sys.path.insert(0, "src")
from atlas.config.settings import load_settings

settings = load_settings()
assert settings.gcp.project_id, "project_id must resolve"
assert settings.validation.expected_event_count > 0
profile = settings.anomaly_profile
for name in (
    "duplicate_event_ids",
    "null_user_ids",
    "invalid_country_codes",
    "future_timestamps",
    "late_arriving_events",
):
    assert profile.expected_count(name) >= 0, name
print("config OK:", settings.config_path.name, settings.anomaly_path.name)
PY
}

gate_observability_config() {
  # Sprint 5 static validation of observability artifacts (no credentials).
  python3 - <<'PY'
import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, "src")

# 1. observability.yaml parses with sane threshold ordering.
config = yaml.safe_load(Path("config/observability.yaml").read_text())
assert isinstance(config["monitoring_enabled"], bool)
assert config["freshness"]["warn_seconds"] < config["freshness"]["fail_seconds"]
assert config["volume"]["warn_deviation"] < config["volume"]["fail_deviation"]
assert config["rejection_rate"]["warn"] < config["rejection_rate"]["fail"]
assert config["cost"]["warn_ratio"] < config["cost"]["fail_ratio"]
assert config["runtime_mode"] in {"normal", "drill"}
assert config["drill_overrides"] in ({}, None), "drill overrides must never merge to main"

# 2. Metric descriptor catalog loads and stays within the cardinality budget
#    (deep checks live in tests/unit/test_observability_metrics.py).
from atlas.observability.metrics import load_catalog

catalog = load_catalog()
assert len(catalog) >= 10
forbidden = {"pipeline_run_id", "batch_id", "deployment_id", "error_message"}
for metric_type, spec in catalog.items():
    assert not (set(spec["labels"]) & forbidden), metric_type

# 3. Schema manifest parses and covers the governed tables.
manifest = json.loads(Path("observability/schema/expected-schemas.json").read_text())
assert len(manifest["tables"]) >= 10

# 4. Alert policies: valid JSON, channel placeholder only (no committed
#    channel ids/addresses), runbook anchors resolve, required metadata.
runbook = Path("docs/observability-runbook-sprint5.md").read_text().lower()
alert_files = sorted(Path("observability/alerts").glob("*.json"))
assert len(alert_files) == 10, [f.name for f in alert_files]
for f in alert_files:
    raw = f.read_text()
    assert "${NOTIFICATION_CHANNEL}" in raw, f"{f.name}: placeholder missing"
    assert "notificationChannels/" not in raw.replace("${NOTIFICATION_CHANNEL}", ""), f.name
    assert "@" not in raw, f"{f.name}: possible committed address"
    policy = json.loads(raw)
    assert policy["displayName"].startswith("Atlas: ")
    assert policy["userLabels"]["managed_by"] == "atlas-sprint5"
    assert policy["userLabels"]["severity"] in {"critical", "warning"}
    doc = policy["documentation"]["content"]
    anchors = re.findall(r"#(alert-[a-z0-9-]+)", doc)
    assert anchors, f"{f.name}: no runbook anchor"
    for anchor in anchors:
        heading = "## alert: " + anchor.removeprefix("alert-").replace("-", " ")
        assert heading in runbook, f"{f.name}: runbook heading missing for {anchor}"

# 5. Dashboard JSON: parses, stable name, section headers sized correctly.
dashboard = json.loads(Path("observability/dashboards/atlas-operations.json").read_text())
assert dashboard["displayName"] == "Atlas Operations"
tiles = dashboard["mosaicLayout"]["tiles"]
assert len(tiles) >= 20
for tile in tiles:
    if "sectionHeader" in tile["widget"]:
        assert tile["height"] in (3, 4), "section headers need height 3-4"

# 6. Log routing definitions parse; sink filter non-empty after comments.
for name in ("log-bucket.json", "log-view.json"):
    json.loads(Path(f"observability/logging/{name}").read_text())
filter_lines = [
    line
    for line in Path("observability/logging/sink-filter.txt").read_text().splitlines()
    if line.strip() and not line.startswith("--")
]
assert filter_lines, "sink filter empty"

print(
    f"observability OK: config, {len(catalog)} metrics, "
    f"{len(manifest['tables'])} schema tables, {len(alert_files)} alerts, "
    f"{len(tiles)}-tile dashboard, log routing"
)
PY
}

gate_failure_injection() {
  # Sprint 6 static validation: the failure-scenario catalog is schema-valid
  # and fault injection can never activate in normal execution.
  python3 - <<'PY'
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")

# 1. Catalog schema validation (every scenario fully specified, no CRITICAL,
#    injection approval always required, cost/duration ceilings present).
from atlas.failure_injection.registry import load_catalog, validate_catalog

errors = validate_catalog(load_catalog())
if errors:
    for error in errors:
        print(f"INVALID  {error}", file=sys.stderr)
    raise SystemExit(1)

# 2. Default-off proof: with a clean environment, injection is inert.
from atlas.failure_injection.framework import SCENARIO_VAR, injection_active_for, is_injection_requested

assert is_injection_requested(env={}) is False
assert injection_active_for("S6-ING-001", env={}) is False
assert injection_active_for("S6-ING-001", env={"ATLAS_APPROVE_FAILURE_INJECTION": "true"}) is False

# 3. No production file hardcodes the activation variable to a scenario:
#    the explicit test-only parameter must come from the operator, never the
#    repository. (Tests and the framework itself may reference the name.)
pattern = re.compile(rf"{SCENARIO_VAR}\s*=\s*['\"]S6-")
violations = []
for root in ("dags", "scripts", "config", ".env", "airflow"):
    base = Path(root)
    if not base.exists():
        continue
    for path in base.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".sh", ".yaml", ".yml", ".cfg", ".env", ""}:
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, IsADirectoryError):
                continue
            if pattern.search(text):
                violations.append(str(path))
assert not violations, f"fault injection hardcoded in normal execution paths: {violations}"

catalog = load_catalog()
print(f"failure injection OK: {len(catalog['scenarios'])} scenarios valid, disabled by default")
PY
}

gate_sql_migrations() {
  python3 - <<'PY'
from pathlib import Path

sql_dir = Path("sql")
files = sorted(sql_dir.glob("*.sql"))
assert files, "sql/ must contain DDL files"
for path in files:
    content = path.read_text(encoding="utf-8")
    assert content.strip(), f"{path} is empty"
    lowered = content.lower()
    banned = ("drop table", "drop schema", "truncate table", "delete from")
    for phrase in banned:
        assert phrase not in lowered, f"{path} contains destructive statement: {phrase}"
print(f"{len(files)} SQL files validated (non-empty, additive-only)")
PY
}

gate_airflow_environment() {
  python3 - <<'PY' || return 1
from importlib.metadata import version

core = version("apache-airflow")
google_provider = version("apache-airflow-providers-google")
standard_provider = version("apache-airflow-providers-standard")
assert core == "3.1.7", core
assert google_provider == "20.0.0", google_provider
assert standard_provider == "1.12.1", standard_provider
print(f"airflow {core} / google {google_provider} / standard {standard_provider}")
PY
  pip check
}

gate_dag_import() {
  PYTHONPATH="src:dags" python3 - <<'PY'
import os

os.environ.setdefault("AIRFLOW__CORE__LOAD_EXAMPLES", "False")
os.environ.setdefault("AIRFLOW__CORE__DAGS_FOLDER", "dags")

from airflow.models.dagbag import DagBag

# safe_mode=False parses every .py file under dags/, not only files matching
# the "airflow"+"dag" keyword heuristic — a broken helper module must fail CI
# even though the scheduler's safe mode would silently skip it.
bag = DagBag(dag_folder="dags", include_examples=False, safe_mode=False)
if bag.import_errors:
    for path, error in bag.import_errors.items():
        print(f"IMPORT ERROR {path}:\n{error}")
    raise SystemExit(1)
assert "atlas_batch_pipeline" in bag.dags, sorted(bag.dags)
dag = bag.dags["atlas_batch_pipeline"]
required_tasks = {
    "resolve_run_context",
    "ensure_audit_resources",
    "start_run_audit",
    "preflight_environment",
    "generate_events",
    "upload_events",
    "load_bigquery_raw",
    "validate_raw_load",
    "dbt_seed",
    "dbt_source_freshness",
    "dbt_build",
    "validate_warehouse",
    "publish_success_marker",
    "write_run_summary",
}
missing = required_tasks - {t.task_id for t in dag.tasks}
assert not missing, f"missing tasks: {sorted(missing)}"
print(f"atlas_batch_pipeline imported with {len(dag.tasks)} tasks and no import errors")
PY
}

gate_dbt_static() {
  local dbt_dir="${DBT_PROJECT_DIR:-${ATLAS_ROOT}/dbt/atlas_dbt}"
  local profiles_dir="${ATLAS_ROOT}/logs/ci/dbt-profiles"
  mkdir -p "$profiles_dir"
  # Parse-only profile: dbt parse never opens a warehouse connection, so a
  # placeholder oauth profile keeps static mode credential-free.
  cat >"${profiles_dir}/profiles.yml" <<'YML'
atlas_dbt:
  target: ci_static
  outputs:
    ci_static:
      type: bigquery
      method: oauth
      project: ci-static-placeholder
      dataset: atlas_ci_static
      threads: 1
      location: US
YML
  # sources.yml resolves the project from the environment; a placeholder keeps
  # static mode credential-free (parse never opens a connection).
  (cd "$dbt_dir" \
    && ATLAS_GCP_PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-ci-static-placeholder}" dbt deps --quiet \
    && ATLAS_GCP_PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-ci-static-placeholder}" dbt parse --profiles-dir "$profiles_dir" --no-partial-parse)
}

gate_schema_compatibility() {
  # Sprint 7 Phase 4/13: applied-migration checksums are immutable and the
  # committed schema baseline matches a fresh generation. Offline.
  PYTHONPATH="${ATLAS_ROOT}/src" python3 - <<'PY'
import json
import sys
from pathlib import Path

from atlas.config.settings import atlas_root
from atlas.ops.migrations import load_manifest
from atlas.governance import schema_check as sc

root = atlas_root()
failures = []

# 1. Migration checksum immutability against the committed lock.
lock_path = root / "sql/migrations/checksums.lock"
if not lock_path.exists():
    failures.append("sql/migrations/checksums.lock missing")
else:
    lock = json.loads(lock_path.read_text())
    locked = lock.get("checksums", {})
    for m in load_manifest():
        if m.migration_id not in locked:
            failures.append(f"migration {m.migration_id} not in checksum lock (append its entry)")
        elif locked[m.migration_id] != m.checksum:
            failures.append(
                f"migration {m.migration_id} checksum changed "
                f"(lock {locked[m.migration_id][:12]}…, file {m.checksum[:12]}…) — "
                "applied migrations are immutable"
            )

# 2. Schema baseline manifest drift.
baseline_path = root / "governance/schemas/manifests/baseline.json"
if not baseline_path.exists():
    failures.append("governance/schemas/manifests/baseline.json missing")
else:
    committed = json.loads(baseline_path.read_text())
    fresh = sc.generate_manifest()
    if committed != fresh:
        failures.append(
            "schema baseline stale; run "
            "`python -m atlas.governance.schema_check --generate "
            "governance/schemas/manifests/baseline.json`"
        )

if failures:
    print("SCHEMA COMPATIBILITY FAIL:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print("schema compatibility OK: migration checksums locked, baseline current")
PY
}

gate_lineage_impact() {
  # Sprint 7 Phase 5/13: committed lineage matches a fresh generation and the
  # source-to-mart chain is intact. Offline.
  PYTHONPATH="${ATLAS_ROOT}/src" python3 - <<'PY'
import json
import sys

from atlas.config.settings import atlas_root
from atlas.governance import lineage

path = atlas_root() / "governance/generated/lineage.json"
if not path.exists():
    print("lineage.json missing; run `python -m atlas.governance.lineage --output "
          "governance/generated/lineage.json`")
    sys.exit(1)
lineage.build_lineage.cache_clear()
graph = lineage.build_lineage()
fresh = lineage.to_dict(graph)
committed = json.loads(path.read_text())
if committed != fresh:
    print("LINEAGE DRIFT: committed lineage.json is stale; regenerate it")
    sys.exit(1)
downstream = graph.transitive_downstream("atlas_raw.events")
for required in ("stg_events", "fct_events", "mart_daily_event_metrics"):
    if required not in downstream:
        print(f"LINEAGE BROKEN: {required} not reachable from atlas_raw.events")
        sys.exit(1)
print(f"lineage OK: {len(fresh['nodes'])} nodes, {fresh['edge_count']} edges, source->mart intact")
PY
}

gate_security_policy() {
  # Sprint 7 Phase 8/13: managed IAM defs grant no prohibited roles / SA keys,
  # and governed artifacts commit no secret-like values. Offline.
  PYTHONPATH="${ATLAS_ROOT}/src" python3 - <<'PY'
import sys

from atlas.governance.security_policy import scan_data_exposure, scan_managed_iam

findings = scan_managed_iam() + scan_data_exposure()
if findings:
    print("SECURITY POLICY FAIL (values not shown):")
    for path, lineno, reason in findings:
        print(f"  - {path}:{lineno}: {reason}")
    sys.exit(1)
print("security policy OK: no prohibited IAM roles/keys, no secret-like values in governed artifacts")
PY
}

gate_performance_cost() {
  # Sprint 7 Phase 12/13: cost-control config is valid and coherent. Offline.
  PYTHONPATH="${ATLAS_ROOT}/src" python3 - <<'PY'
import sys

from atlas.observability import cost_guard

failures = []
try:
    controls = cost_guard.load_cost_controls()
except Exception as exc:  # noqa: BLE001
    print(f"PERFORMANCE/COST FAIL: cannot load cost_controls.yaml: {exc}")
    sys.exit(1)

envs = controls.get("environments", {})
if not envs:
    failures.append("cost_controls.yaml has no environments")
required = (
    "max_query_bytes",
    "max_performance_suite_bytes",
    "max_backfill_days",
    "require_partition_filter_assets",
    "temporary_dataset_ttl_hours",
    "log_retention_days",
    "release_retention_policy",
)
for env, c in envs.items():
    for f in required:
        if f not in c:
            failures.append(f"{env}: missing '{f}'")
    if isinstance(c.get("max_query_bytes"), int) and isinstance(
        c.get("max_performance_suite_bytes"), int
    ):
        if c["max_query_bytes"] > c["max_performance_suite_bytes"]:
            failures.append(f"{env}: max_query_bytes exceeds suite ceiling")

if failures:
    print("PERFORMANCE/COST FAIL:")
    for f in failures:
        print(f"  - {f}")
    sys.exit(1)
print(f"performance/cost OK: {len(envs)} environments, ceilings coherent")
PY
}

gate_governance() {
  # Sprint 7 Phase 1/13: governance metadata is complete, uses one source of
  # truth, and the generated catalog is not stale. Offline, no credentials.
  PYTHONPATH="${ATLAS_ROOT}/src" python3 - <<'PY'
import sys

from atlas.governance.registry import validate_governance
from atlas.governance.catalog import _committed_matches, build_catalog
from atlas.governance.retention import validate_retention_config

errors = validate_governance() + validate_retention_config()
if errors:
    print("GOVERNANCE INVALID:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
catalog = build_catalog()
if not _committed_matches():
    print("GOVERNANCE DRIFT: committed catalog stale; run "
          "`python -m atlas.governance.catalog generate`")
    sys.exit(1)
print(f"governance OK: {catalog['asset_count']} assets, one source of truth, catalog current")
PY
}

gate_reference_handoff() {
  # Sprint 8 Phase 18: the reference-architecture package and handoff artifacts
  # are internally consistent and free of hidden-context dependencies. Offline.
  PYTHONPATH="${ATLAS_ROOT}/src" python3 -m atlas.reference.validate || return 1
  python3 "${ATLAS_ROOT}/scripts/validate_public_extraction.py" >/dev/null || return 1
  ATLAS_ROOT="${ATLAS_ROOT}" python3 - <<'PY'
import os
import re
import subprocess
import sys
from pathlib import Path

root = Path(os.environ["ATLAS_ROOT"])
errors: list[str] = []

# 1. START_HERE is the canonical entry point.
if not (root / "START_HERE.md").exists():
    errors.append("START_HERE.md is missing")

# 2. Required reference + handoff documents exist.
required = [
    "docs/reference-architecture/README.md",
    "docs/reference-architecture/reference-manifest.yml",
    "docs/reference-architecture/architecture-invariants.md",
    "docs/reference-architecture/evidence-index.md",
    "docs/reference-architecture/unresolved-risks.md",
    "docs/reference-architecture/capability-evidence-map.md",
    "docs/reference-architecture/public-extraction-review.md",
    "docs/handoff/operator-onboarding.md",
    "docs/handoff/agent-onboarding.md",
    "docs/handoff/clean-clone-reproduction.md",
    "docs/handoff/handoff-scorecard.md",
    "docs/evidence-sprint8/clean-clone-results.md",
    "docs/evidence-sprint8/independent-handoff-results.md",
    "governance/unresolved_risks.yml",
    "config/public_extraction_manifest.yml",
]
for rel in required:
    if not (root / rel).exists():
        errors.append(f"required handoff artifact missing: {rel}")

# Scope for current onboarding/reference docs (excludes historical preflight
# and context-pack which legitimately discuss patterns).
scope: list[Path] = [root / "START_HERE.md"]
for sub in ("docs/reference-architecture", "docs/handoff"):
    scope.extend(sorted((root / sub).glob("*.md")))

# 3. No forbidden absolute local paths in current onboarding docs.
abs_re = re.compile(r"/(?:home|Users|workspace)/")
# 4. No dependency on prior conversation context.
convo_re = re.compile(
    r"chatgpt|(?:see|refer to)\s+(?:the\s+)?(?:prior|previous)\s+"
    r"(?:conversation|chat|session)|ask\s+russell",
    re.IGNORECASE,
)
# 5. No unresolved placeholders in current docs.
placeholder_re = re.compile(r"\b(?:TODO|FIXME|XXX|TBD)\b")
for path in scope:
    text = path.read_text(encoding="utf-8")
    rel = path.relative_to(root)
    if abs_re.search(text):
        errors.append(f"{rel}: contains a forbidden absolute local path")
    if convo_re.search(text):
        errors.append(f"{rel}: depends on prior conversation context")
    if placeholder_re.search(text):
        errors.append(f"{rel}: contains an unresolved placeholder")

# 6. Capability evidence contains limitations.
cap = (root / "docs/reference-architecture/capability-evidence-map.md").read_text(encoding="utf-8")
if "imitation" not in cap:
    errors.append("capability-evidence-map.md must record limitations")

# 7. Sprint 8 tag is not claimed before it exists.
readme = (root / "README.md").read_text(encoding="utf-8")
if "atlas-sprint-8-complete" in readme:
    try:
        tags = subprocess.run(
            ["git", "tag", "-l", "atlas-sprint-8-complete"],
            cwd=str(root), capture_output=True, text=True, check=False,
        ).stdout.strip()
    except OSError:
        tags = ""
    if not tags:
        errors.append("README references atlas-sprint-8-complete before the tag exists")

if errors:
    print("reference-handoff gate FAILED:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
print("reference-handoff OK: package consistent, no hidden-context dependencies")
PY
}

# ---------------------------------------------------------------------------
# Mode composition
# ---------------------------------------------------------------------------

if [[ "$MODE" == "static" || "$MODE" == "all" ]]; then
  if in_group security-shell; then
    run_gate secret_scan gate_secret_scan
    run_gate shell_syntax gate_shell_syntax
    if command -v shellcheck >/dev/null 2>&1; then
      run_gate shell_static gate_shellcheck
    elif [[ "$GROUP" == "security-shell" ]]; then
      run_gate shell_static false
    else
      skip_gate shell_static "shellcheck not installed"
    fi
    run_gate workflow_yaml gate_workflow_yaml
    run_gate sql_migrations gate_sql_migrations
  fi
  if in_group python; then
    run_gate python_format gate_python_format
    run_gate python_lint gate_python_lint
    run_gate python_types gate_python_types
    run_gate python_tests gate_python_tests
    run_gate config_validation gate_config_validation
    run_gate observability_config gate_observability_config
    run_gate failure_injection gate_failure_injection
    run_gate governance gate_governance
    run_gate schema_compatibility gate_schema_compatibility
    run_gate lineage_impact gate_lineage_impact
    run_gate security_policy gate_security_policy
    run_gate performance_cost gate_performance_cost
    run_gate reference_handoff gate_reference_handoff
  fi
  if in_group airflow; then
    if airflow_installed; then
      run_gate airflow_environment gate_airflow_environment
      run_gate dag_import gate_dag_import
    elif [[ "$GROUP" == "airflow" ]]; then
      echo "apache-airflow is required for --group airflow" >&2
      run_gate airflow_environment false
      run_gate dag_import false
    else
      skip_gate airflow_environment "apache-airflow not installed in this interpreter"
      skip_gate dag_import "apache-airflow not installed in this interpreter"
    fi
  fi
  if in_group dbt; then
    if command -v dbt >/dev/null 2>&1; then
      run_gate dbt_static gate_dbt_static
    elif [[ "$GROUP" == "dbt" ]]; then
      echo "dbt is required for --group dbt" >&2
      run_gate dbt_static false
    else
      skip_gate dbt_static "dbt not installed"
    fi
  fi
fi

if [[ "$MODE" == "integration" || "$MODE" == "all" ]]; then
  if [[ -x "${ATLAS_ROOT}/scripts/validate_gcp_integration.sh" ]]; then
    run_gate gcp_integration bash "${ATLAS_ROOT}/scripts/validate_gcp_integration.sh"
  else
    skip_gate gcp_integration "scripts/validate_gcp_integration.sh not present yet"
  fi
fi

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

python3 - "$RESULTS_FILE" <<'PY'
import json
import sys
from pathlib import Path

tmp = Path(sys.argv[1] + ".tmp")
gates = [json.loads(line) for line in tmp.read_text().splitlines() if line.strip()]
payload = {
    "overall_status": "FAIL" if any(g["status"] == "FAIL" for g in gates) else "PASS",
    "gates": gates,
}
Path(sys.argv[1]).write_text(json.dumps(payload, indent=2) + "\n")
tmp.unlink()
PY

echo ""
echo "===================== GATE SUMMARY ====================="
for i in "${!GATE_NAMES[@]}"; do
  printf '  %-24s %s\n' "${GATE_NAMES[$i]}" "${GATE_STATUSES[$i]}"
done
echo "========================================================="
echo "Machine-readable results: ${RESULTS_FILE}"

if [[ "$FAILED" -ne 0 ]]; then
  echo "validate_ci: FAIL"
  exit 1
fi
echo "validate_ci: PASS"
