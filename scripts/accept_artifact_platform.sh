#!/usr/bin/env bash
# Exercise publish, preview, promote, update, rollback, and privacy controls.
set -Eeuo pipefail
IFS=$'\n\t'
umask 077

ATLAS_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ATLAS_ROOT}/.." && pwd)"
DASHBOARD_DIR="${ATLAS_ROOT}/examples/artifact-dashboard"
SITE_SLUG="${ATLAS_ARTIFACT_ACCEPTANCE_SITE:-atlas-dashboard}"
PUBLISHER_URL="${ATLAS_ARTIFACT_PUBLISHER_URL:-}"
HOST_URL="${ATLAS_ARTIFACT_PUBLIC_HOST_URL:-}"
BASELINE_HISTORY_FILE="$(mktemp "${TMPDIR:-/tmp}/atlas-artifact-history-before.XXXXXX")"
FINAL_HISTORY_FILE="$(mktemp "${TMPDIR:-/tmp}/atlas-artifact-history-after.XXXXXX")"

cleanup() {
  rm -f "$BASELINE_HISTORY_FILE" "$FINAL_HISTORY_FILE"
}
trap cleanup EXIT

fail() {
  echo "error: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required but was not found on PATH"
}

atlas() {
  uv run --project "${ATLAS_ROOT}/artifact-platform" atlas-artifact "$@"
}

json_field() {
  local field="$1"
  python3 -c \
    'import json, sys; print(json.load(sys.stdin)[sys.argv[1]])' \
    "$field"
}

confirm_preview() {
  local release="$1"
  local digest="$2"
  atlas preview "$SITE_SLUG" "$digest"
  if [[ "${ATLAS_ACCEPT_PREVIEWS:-}" == "true" ]]; then
    return
  fi
  local answer
  read -r -p "Open the ${release} URL, verify it visually, then type yes: " answer
  [[ "$answer" == "yes" ]] || fail "${release} preview was not confirmed"
}

assert_active_digest() {
  local expected="$1"
  local actual
  actual="$(atlas site show "$SITE_SLUG" | json_field active_digest)"
  [[ "$actual" == "$expected" ]] || fail \
    "active digest mismatch: expected ${expected}, found ${actual}"
}

for command in curl gcloud npm python3 uv; do
  require_command "$command"
done
[[ -n "$PUBLISHER_URL" ]] || fail "ATLAS_ARTIFACT_PUBLISHER_URL is required"
[[ -n "$HOST_URL" ]] || fail "ATLAS_ARTIFACT_PUBLIC_HOST_URL is required"

cd "$REPO_ROOT"

echo "==> Building deterministic dashboard revisions"
npm ci --prefix "$DASHBOARD_DIR"
npm test --prefix "$DASHBOARD_DIR"
npm run typecheck --prefix "$DASHBOARD_DIR"
npm run build --prefix "$DASHBOARD_DIR"

if ! atlas site show "$SITE_SLUG" >/dev/null 2>&1; then
  atlas site create "$SITE_SLUG" --reason "create live acceptance site"
fi
atlas history "$SITE_SLUG" >"$BASELINE_HISTORY_FILE"

echo "==> Publishing dashboard v1"
V1_JSON="$(
  atlas publish "$SITE_SLUG" "${DASHBOARD_DIR}/dist/v1" \
    --label v1 \
    --message "publish fake Atlas dashboard v1"
)"
V1_DIGEST="$(printf '%s' "$V1_JSON" | json_field digest)"
confirm_preview "v1" "$V1_DIGEST"
atlas promote "$SITE_SLUG" "$V1_DIGEST" \
  --reason "acceptance promote v1 after manual preview" \
  --confirm-preview
atlas verify-active "$SITE_SLUG"
assert_active_digest "$V1_DIGEST"

echo "==> Publishing dashboard v2"
V2_JSON="$(
  atlas publish "$SITE_SLUG" "${DASHBOARD_DIR}/dist/v2" \
    --label v2 \
    --message "publish visibly distinct fake Atlas dashboard v2"
)"
V2_DIGEST="$(printf '%s' "$V2_JSON" | json_field digest)"
[[ "$V1_DIGEST" != "$V2_DIGEST" ]] || fail "v1 and v2 unexpectedly share a digest"
confirm_preview "v2" "$V2_DIGEST"
atlas promote "$SITE_SLUG" "$V2_DIGEST" \
  --reason "acceptance update to v2 after manual preview" \
  --confirm-preview
atlas verify-active "$SITE_SLUG"
assert_active_digest "$V2_DIGEST"

echo "==> Rolling back without copying artifact bytes"
atlas rollback "$SITE_SLUG" "$V1_DIGEST" \
  --reason "acceptance rollback from v2 to v1" \
  --confirm-preview
atlas verify-active "$SITE_SLUG"
assert_active_digest "$V1_DIGEST"

echo "==> Re-promoting v2 as the final active revision"
atlas promote "$SITE_SLUG" "$V2_DIGEST" \
  --reason "acceptance restore latest v2" \
  --confirm-preview
atlas verify-active "$SITE_SLUG"
assert_active_digest "$V2_DIGEST"

echo "==> Proving disable and enable preserve the active revision"
atlas disable "$SITE_SLUG" --reason "acceptance privacy stop"
if atlas smoke "$SITE_SLUG" "$V2_DIGEST" >/dev/null 2>&1; then
  fail "disabled revision remained reachable through authenticated IAP"
fi
atlas enable "$SITE_SLUG" --reason "acceptance restore site"
atlas smoke "$SITE_SLUG" "$V2_DIGEST"
atlas verify-active "$SITE_SLUG"

SITE_JSON="$(atlas site show "$SITE_SLUG")"
ACTIVE_DIGEST="$(printf '%s' "$SITE_JSON" | json_field active_digest)"
ENABLED="$(printf '%s' "$SITE_JSON" | json_field enabled)"
[[ "$ACTIVE_DIGEST" == "$V2_DIGEST" ]] || fail "v2 is not the final active digest"
[[ "$ENABLED" == "True" ]] || fail "site was not re-enabled"

echo "==> Confirming the private host does not serve anonymous requests"
anonymous_status() {
  curl --silent --show-error \
    --output /dev/null \
    --write-out "%{http_code}" \
    "$1"
}
ANONYMOUS_ALIAS_STATUS="$(
  anonymous_status "${HOST_URL}/sites/${SITE_SLUG}/"
)"
ANONYMOUS_REVISION_STATUS="$(
  anonymous_status "${HOST_URL}/sites/${SITE_SLUG}/revisions/${V2_DIGEST}/"
)"
for status in "$ANONYMOUS_ALIAS_STATUS" "$ANONYMOUS_REVISION_STATUS"; do
  case "$status" in
    302|401|403) ;;
    *) fail "anonymous host response was not an IAP login or denial: ${status}" ;;
  esac
done

echo "==> Catalog history"
HISTORY_JSON="$(atlas history "$SITE_SLUG")"
printf '%s\n' "$HISTORY_JSON"
printf '%s' "$HISTORY_JSON" >"$FINAL_HISTORY_FILE"
python3 - "$BASELINE_HISTORY_FILE" "$FINAL_HISTORY_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    before_ids = {event["event_id"] for event in json.load(handle)}
with open(sys.argv[2], encoding="utf-8") as handle:
    after = json.load(handle)
new_types = [
    event["event_type"]
    for event in after
    if event["event_id"] not in before_ids
]
required_order = [
    "accepted",
    "smoke_passed",
    "promoted",
    "accepted",
    "smoke_passed",
    "promoted",
    "smoke_passed",
    "rollback",
    "smoke_passed",
    "promoted",
    "disabled",
    "enabled",
]
cursor = iter(new_types)
for required in required_order:
    if not any(actual == required for actual in cursor):
        raise SystemExit(
            f"new lifecycle history lacks ordered {required!r}: {new_types}"
        )
PY

cat <<EOF

LIVE ACCEPTANCE PASS
Site:          ${SITE_SLUG}
Stable URL:    ${HOST_URL}/sites/${SITE_SLUG}/
v1 digest:     ${V1_DIGEST}
v2 digest:     ${V2_DIGEST}
Active digest: ${ACTIVE_DIGEST}
Anonymous alias status: ${ANONYMOUS_ALIAS_STATUS}
Anonymous revision status: ${ANONYMOUS_REVISION_STATUS}

The final active revision is v2. Publisher smoke checks verified authenticated
HTTP status and required security headers before every activation.
EOF
