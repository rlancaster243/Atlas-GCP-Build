#!/usr/bin/env bash
# Bootstrap the Atlas observability logging plane (Sprint 5, Phase 5).
#
# Creates, idempotently, in project example-gcp-project:
#   1. Log bucket  atlas-observability (us-central1, 30d retention, Log Analytics)
#   2. Log sink    atlas-observability-sink (filter: observability/logging/sink-filter.txt)
#   3. Sink writer IAM (roles/logging.bucketWriter for the sink identity)
#   4. Log view    atlas-runtime on the bucket
#   5. Linked read-only BigQuery dataset atlas_logs
#
# Usage: bootstrap_observability.sh --plan | --apply | --status
#   --apply requires ATLAS_APPROVE_PROVISION=true
#   the IAM grant in --apply additionally requires ATLAS_APPROVE_IAM=true
set -euo pipefail

PROJECT_ID="${ATLAS_GCP_PROJECT_ID:-example-gcp-project}"
LOCATION="us-central1"
BUCKET_ID="atlas-observability"
SINK_ID="atlas-observability-sink"
VIEW_ID="atlas-runtime"
LINK_ID="atlas_logs"
RETENTION_DAYS=30

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FILTER_FILE="${SCRIPT_DIR}/../observability/logging/sink-filter.txt"

MODE="${1:---plan}"

log() { printf '[bootstrap-observability] %s\n' "$*"; }
fatal() { printf '[bootstrap-observability] FATAL: %s\n' "$*" >&2; exit 1; }

[[ -f "$FILTER_FILE" ]] || fatal "sink filter file missing: $FILTER_FILE"
# Strip comment lines; the remainder is the actual filter expression.
SINK_FILTER="$(grep -v '^--' "$FILTER_FILE" | sed '/^[[:space:]]*$/d')"
[[ -n "$SINK_FILTER" ]] || fatal "sink filter is empty after stripping comments"

bucket_exists() {
  gcloud logging buckets describe "$BUCKET_ID" --location="$LOCATION" \
    --project="$PROJECT_ID" >/dev/null 2>&1
}

sink_exists() {
  gcloud logging sinks describe "$SINK_ID" --project="$PROJECT_ID" >/dev/null 2>&1
}

view_exists() {
  gcloud logging views describe "$VIEW_ID" --bucket="$BUCKET_ID" \
    --location="$LOCATION" --project="$PROJECT_ID" >/dev/null 2>&1
}

link_exists() {
  gcloud logging links describe "$LINK_ID" --bucket="$BUCKET_ID" \
    --location="$LOCATION" --project="$PROJECT_ID" >/dev/null 2>&1
}

print_status() {
  log "project=$PROJECT_ID location=$LOCATION"
  if bucket_exists; then
    log "bucket $BUCKET_ID: EXISTS"
    gcloud logging buckets describe "$BUCKET_ID" --location="$LOCATION" \
      --project="$PROJECT_ID" --format='value(retentionDays,analyticsEnabled,lifecycleState)' \
      | awk '{printf "[bootstrap-observability]   retentionDays=%s analytics=%s state=%s\n", $1, $2, $3}'
  else
    log "bucket $BUCKET_ID: MISSING"
  fi
  if sink_exists; then
    log "sink $SINK_ID: EXISTS (writer: $(gcloud logging sinks describe "$SINK_ID" --project="$PROJECT_ID" --format='value(writerIdentity)'))"
  else
    log "sink $SINK_ID: MISSING"
  fi
  if view_exists; then log "view $VIEW_ID: EXISTS"; else log "view $VIEW_ID: MISSING"; fi
  if link_exists; then log "linked dataset $LINK_ID: EXISTS"; else log "linked dataset $LINK_ID: MISSING"; fi
}

print_plan() {
  log "PLAN (no changes made):"
  bucket_exists || log "  CREATE log bucket $BUCKET_ID location=$LOCATION retention=${RETENTION_DAYS}d analytics=enabled"
  sink_exists || log "  CREATE sink $SINK_ID -> logging.googleapis.com/projects/$PROJECT_ID/locations/$LOCATION/buckets/$BUCKET_ID"
  sink_exists || log "  GRANT roles/logging.bucketWriter to the sink writer identity (requires ATLAS_APPROVE_IAM=true)"
  view_exists || log "  CREATE view $VIEW_ID on $BUCKET_ID"
  link_exists || log "  CREATE linked BigQuery dataset $LINK_ID (read-only) from $BUCKET_ID"
  log "  sink filter: $SINK_FILTER"
  dashboard_validate
  log "  CREATE-OR-UPDATE dashboard 'Atlas Operations' from observability/dashboards/atlas-operations.json"
  if bucket_exists && sink_exists && view_exists && link_exists; then
    log "  logging resources all exist — only dashboard/descriptor sync would run"
  fi
}

apply() {
  [[ "${ATLAS_APPROVE_PROVISION:-}" == "true" ]] \
    || fatal "--apply requires ATLAS_APPROVE_PROVISION=true"

  if ! bucket_exists; then
    log "creating log bucket $BUCKET_ID"
    gcloud logging buckets create "$BUCKET_ID" \
      --location="$LOCATION" \
      --retention-days="$RETENTION_DAYS" \
      --enable-analytics \
      --description="Atlas runtime logs (Sprint 5). Composer + structured Atlas events." \
      --project="$PROJECT_ID"
  else
    log "bucket $BUCKET_ID already exists — leaving as-is"
  fi

  if ! sink_exists; then
    log "creating sink $SINK_ID"
    gcloud logging sinks create "$SINK_ID" \
      "logging.googleapis.com/projects/$PROJECT_ID/locations/$LOCATION/buckets/$BUCKET_ID" \
      --log-filter="$SINK_FILTER" \
      --description="Routes Atlas runtime logs to the atlas-observability bucket (additive; _Default unaffected)" \
      --project="$PROJECT_ID"
  else
    log "sink $SINK_ID already exists — leaving as-is"
  fi

  # Sinks writing to a log bucket in the same project usually need no extra
  # grant, but we verify and grant explicitly so routing cannot fail silently.
  local writer
  writer="$(gcloud logging sinks describe "$SINK_ID" --project="$PROJECT_ID" --format='value(writerIdentity)')"
  if [[ -n "$writer" ]]; then
    if gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten='bindings[].members' \
        --filter="bindings.role=roles/logging.bucketWriter AND bindings.members=$writer" \
        --format='value(bindings.role)' | grep -q .; then
      log "sink writer $writer already has roles/logging.bucketWriter"
    elif [[ "${ATLAS_APPROVE_IAM:-}" == "true" ]]; then
      log "granting roles/logging.bucketWriter to $writer"
      gcloud projects add-iam-policy-binding "$PROJECT_ID" \
        --member="$writer" --role='roles/logging.bucketWriter' \
        --condition=None --format='none'
    else
      log "WARNING: sink writer $writer lacks roles/logging.bucketWriter and ATLAS_APPROVE_IAM!=true — routing may fail"
    fi
  fi

  if ! view_exists; then
    log "creating view $VIEW_ID"
    gcloud logging views create "$VIEW_ID" \
      --bucket="$BUCKET_ID" --location="$LOCATION" \
      --log-filter="SOURCE(\"projects/$PROJECT_ID\")" \
      --description="Least-privilege Atlas runtime view (grant roles/logging.viewAccessor here)" \
      --project="$PROJECT_ID"
  else
    log "view $VIEW_ID already exists — leaving as-is"
  fi

  if ! link_exists; then
    log "creating linked BigQuery dataset $LINK_ID (read-only)"
    gcloud logging links create "$LINK_ID" \
      --bucket="$BUCKET_ID" --location="$LOCATION" \
      --description="Read-only linked dataset over the atlas-observability log bucket" \
      --project="$PROJECT_ID"
  else
    log "linked dataset $LINK_ID already exists — leaving as-is"
  fi

  # 6. Custom metric descriptors from the versioned catalog (idempotent).
  if python3 -c 'import google.cloud.monitoring_v3' 2>/dev/null; then
    log "ensuring Atlas metric descriptors (observability/metrics/metric-descriptors.json)"
    PYTHONPATH="${SCRIPT_DIR}/../src${PYTHONPATH:+:$PYTHONPATH}" \
      python3 -m atlas.observability.metrics --ensure-descriptors --project-id "$PROJECT_ID"
  else
    log "WARNING: google-cloud-monitoring not installed — skipping metric descriptors (run 'python -m atlas.observability.metrics --ensure-descriptors' from an environment that has it)"
  fi

  apply_dashboard

  log "apply complete"
  print_status
}

DASHBOARD_FILE="${SCRIPT_DIR}/../observability/dashboards/atlas-operations.json"

dashboard_validate() {
  python3 -c "
import json, sys
d = json.load(open('$DASHBOARD_FILE'))
assert d.get('displayName') == 'Atlas Operations', 'unexpected displayName'
tiles = d['mosaicLayout']['tiles']
assert len(tiles) >= 20, 'dashboard suspiciously small'
print(f'[bootstrap-observability] dashboard JSON valid: {len(tiles)} tiles')
"
}

apply_dashboard() {
  dashboard_validate
  local token existing_name
  token="$(gcloud auth print-access-token)"
  existing_name="$(curl -sf -H "Authorization: Bearer $token" \
    "https://monitoring.googleapis.com/v1/projects/$PROJECT_ID/dashboards" \
    | python3 -c "import json,sys; ds=json.load(sys.stdin).get('dashboards',[]); print(next((d['name'] for d in ds if d.get('displayName')=='Atlas Operations'), ''))")"
  if [[ -n "$existing_name" ]]; then
    log "updating existing dashboard $existing_name"
    # PATCH requires etag; fetch, merge repo definition over live identity fields.
    curl -sf -H "Authorization: Bearer $token" \
      "https://monitoring.googleapis.com/v1/$existing_name" > /tmp/atlas-dashboard-live.json
    python3 - "$DASHBOARD_FILE" /tmp/atlas-dashboard-live.json > /tmp/atlas-dashboard-merged.json <<'PYEOF'
import json, sys
repo = json.load(open(sys.argv[1]))
live = json.load(open(sys.argv[2]))
repo["name"] = live["name"]
repo["etag"] = live["etag"]
print(json.dumps(repo))
PYEOF
    curl -sf -X PATCH -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
      -d @/tmp/atlas-dashboard-merged.json \
      "https://monitoring.googleapis.com/v1/$existing_name" > /dev/null
    log "dashboard updated"
  else
    log "creating dashboard 'Atlas Operations'"
    curl -sf -X POST -H "Authorization: Bearer $token" -H "Content-Type: application/json" \
      -d @"$DASHBOARD_FILE" \
      "https://monitoring.googleapis.com/v1/projects/$PROJECT_ID/dashboards" \
      | python3 -c "import json,sys; print('[bootstrap-observability] created:', json.load(sys.stdin)['name'])"
  fi
}

case "$MODE" in
  --plan) print_plan ;;
  --apply) apply ;;
  --status) print_status ;;
  *) fatal "unknown mode: $MODE (use --plan | --apply | --status)" ;;
esac
