#!/usr/bin/env bash
# Manage Atlas Cloud Monitoring alert policies (Sprint 5, Phase 10).
#
# Policies are defined in observability/alerts/*.json with the notification
# channel as the ${NOTIFICATION_CHANNEL} placeholder — channel resource ids
# and recipients are never committed to Git.
#
# Usage:
#   manage_atlas_alerts.sh plan                       # diff repo vs live
#   manage_atlas_alerts.sh apply                      # create/update all (idempotent)
#   manage_atlas_alerts.sh enable  <policy-file-stem> # e.g. atlas-data-stale
#   manage_atlas_alerts.sh disable <policy-file-stem>
#   manage_atlas_alerts.sh status                     # list live Atlas policies
#   manage_atlas_alerts.sh test    <check_name>       # publish synthetic FAIL (mode=drill)
#   manage_atlas_alerts.sh delete-test-resources      # publish PASS recovery for drill series
#
# apply/enable/disable require ATLAS_APPROVE_PROVISION=true.
# apply requires ATLAS_NOTIFICATION_CHANNEL_ID (projects/.../notificationChannels/...).
set -euo pipefail

PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALERTS_DIR="${SCRIPT_DIR}/../observability/alerts"
export PYTHONPATH="${SCRIPT_DIR}/../src${PYTHONPATH:+:$PYTHONPATH}"

COMMAND="${1:-plan}"
ARG="${2:-}"

require_provision() {
  [[ "${ATLAS_APPROVE_PROVISION:-}" == "true" ]] \
    || { echo "FATAL: $COMMAND requires ATLAS_APPROVE_PROVISION=true" >&2; exit 1; }
}

case "$COMMAND" in
  plan|status)
    python3 - "$COMMAND" "$PROJECT_ID" "$ALERTS_DIR" <<'PYEOF'
import json, sys
from pathlib import Path
from google.cloud import monitoring_v3

command, project_id, alerts_dir = sys.argv[1], sys.argv[2], Path(sys.argv[3])
client = monitoring_v3.AlertPolicyServiceClient()
live = {
    p.display_name: p
    for p in client.list_alert_policies(name=f"projects/{project_id}")
    if p.user_labels.get("managed_by") == "atlas-sprint5"
}
if command == "status":
    print(f"{len(live)} live Atlas policies:")
    for name, p in sorted(live.items()):
        print(f"  {'ENABLED ' if p.enabled else 'DISABLED'}  {name}  ({p.name.split('/')[-1]})")
    sys.exit(0)
repo = {json.loads(f.read_text())["displayName"]: f.name for f in sorted(alerts_dir.glob("*.json"))}
print("PLAN (no changes made):")
for display, fname in repo.items():
    action = "UPDATE" if display in live else "CREATE"
    print(f"  {action}  {display}  <- {fname}")
for display in sorted(set(live) - set(repo)):
    print(f"  ORPHAN (live but not in repo): {display}")
PYEOF
    ;;

  apply)
    require_provision
    [[ -n "${ATLAS_NOTIFICATION_CHANNEL_ID:-}" ]] \
      || { echo "FATAL: apply requires ATLAS_NOTIFICATION_CHANNEL_ID" >&2; exit 1; }
    python3 - "$PROJECT_ID" "$ALERTS_DIR" "$ATLAS_NOTIFICATION_CHANNEL_ID" <<'PYEOF'
import json, sys
from pathlib import Path
from google.cloud import monitoring_v3
from google.protobuf import json_format

project_id, alerts_dir, channel = sys.argv[1], Path(sys.argv[2]), sys.argv[3]
client = monitoring_v3.AlertPolicyServiceClient()
parent = f"projects/{project_id}"
live = {
    p.display_name: p
    for p in client.list_alert_policies(name=parent)
    if p.user_labels.get("managed_by") == "atlas-sprint5"
}
for f in sorted(alerts_dir.glob("*.json")):
    raw = f.read_text().replace("${NOTIFICATION_CHANNEL}", channel)
    desired = json_format.ParseDict(json.loads(raw), monitoring_v3.AlertPolicy()._pb)
    display = desired.display_name
    if display in live:
        desired.name = live[display].name
        # Preserve server-side condition names so updates modify in place.
        existing_conditions = {c.display_name: c.name for c in live[display].conditions}
        for cond in desired.conditions:
            if cond.display_name in existing_conditions:
                cond.name = existing_conditions[cond.display_name]
        client.update_alert_policy(alert_policy=desired)
        print(f"UPDATED  {display}")
    else:
        created = client.create_alert_policy(name=parent, alert_policy=desired)
        print(f"CREATED  {display}  ({created.name.split('/')[-1]})")
PYEOF
    ;;

  enable|disable)
    require_provision
    [[ -n "$ARG" ]] || { echo "FATAL: $COMMAND requires a policy file stem" >&2; exit 1; }
    python3 - "$COMMAND" "$PROJECT_ID" "$ALERTS_DIR" "$ARG" <<'PYEOF'
import json, sys
from pathlib import Path
from google.cloud import monitoring_v3
from google.protobuf import field_mask_pb2

command, project_id, alerts_dir, stem = sys.argv[1:5]
display = json.loads((Path(alerts_dir) / f"{stem}.json").read_text())["displayName"]
client = monitoring_v3.AlertPolicyServiceClient()
for p in client.list_alert_policies(name=f"projects/{project_id}"):
    if p.display_name == display:
        p.enabled = command == "enable"
        client.update_alert_policy(
            alert_policy=p, update_mask=field_mask_pb2.FieldMask(paths=["enabled"])
        )
        print(f"{command.upper()}D  {display}")
        break
else:
    sys.exit(f"policy not found live: {display}")
PYEOF
    ;;

  test)
    [[ -n "$ARG" ]] || { echo "FATAL: test requires a check_name" >&2; exit 1; }
    echo "publishing synthetic FAIL (value 2, mode=drill) for check_name=$ARG"
    python3 - "$PROJECT_ID" "$ARG" <<'PYEOF'
import sys
from atlas.observability.metrics import publish_gauge
project_id, check = sys.argv[1], sys.argv[2]
publish_gauge(
    project_id,
    "custom.googleapis.com/atlas/monitor/check_status",
    2,
    {"environment": "atlas-dev", "check_name": check, "mode": "drill"},
)
print("published; expect the policy to open an incident within ~10 minutes")
PYEOF
    ;;

  delete-test-resources)
    echo "publishing PASS recovery for all drill-mode check series"
    python3 - "$PROJECT_ID" <<'PYEOF'
import sys
from atlas.observability.metrics import publish_gauge_safely
from atlas.observability.monitor import CHECK_NAMES
project_id = sys.argv[1]
for check in CHECK_NAMES:
    publish_gauge_safely(
        project_id,
        "custom.googleapis.com/atlas/monitor/check_status",
        0,
        {"environment": "atlas-dev", "check_name": check, "mode": "drill"},
    )
print("recovery points published; incidents auto-close after cessation (~30 min)")
PYEOF
    ;;

  *)
    echo "FATAL: unknown command: $COMMAND" >&2
    echo "usage: manage_atlas_alerts.sh plan|apply|enable|disable|status|test|delete-test-resources" >&2
    exit 1
    ;;
esac
