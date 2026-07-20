# Atlas On-Call and Ownership Model (Sprint 5)

This is a development-project ownership model, not an organizational on-call
rotation. No 24/7 coverage, paging SLA, or follow-the-sun handoff is claimed.

## Ownership

| Role | Who | Responsibilities |
|---|---|---|
| Primary operator | the primary operator | Receives all alert emails (verified channel), acknowledges incidents, executes runbooks, owns incident reports |
| Escalation | Repository owner / designated reviewer | Engaged when the first recovery attempt fails, for `rollback failed` incidents immediately, and for any IAM or destructive decision |
| External escalation | none configured | Only when an approved real recipient/integration is added (PagerDuty/Slack are out of Sprint 5 scope) |

## Response expectations (development-grade)

- Alerts route to one verified email channel; response happens on a
  best-effort basis during active development windows.
- Critical incidents (`pipeline failed`, `reconciliation failed`,
  `rollback failed`, `breaking schema drift`) take priority over feature
  work when the environment is active.
- Between acceptance windows the Composer environment is intentionally
  deleted and `monitoring_enabled: false`; no alert response is expected and
  absence-prone policies are disabled per the teardown checklist.

## Escalation triggers

1. First recovery attempt failed or the runbook does not match reality.
2. Any `rollback failed` incident (immediately).
3. Suspected credential exposure or IAM regression (also see
   `security-review-sprint5.md`).
4. Any action that would delete data, move release tags, or reverse a
   migration — these always require explicit human approval.

## Incident lifecycle

detect (Cloud Monitoring incident) → acknowledge (email received, incident
noted) → diagnose (runbook first-moves) → contain → recover → verify
(monitor cycle returns PASS, incident closes) → document (incident report
with observation/inference/speculation separated) → prevent (regression
test, alert change, ADR amendment, or runbook fix — every meaningful defect
becomes a reusable control).

## SLO and error-budget candidates (recorded, not committed)

These are candidates for a future production posture, backed only by the
current synthetic workload:

- Pipeline success rate per 30-day window (candidate SLO 99 %).
- Freshness: successful batch within 26 h (warn) / 50 h (fail).
- Deployment success rate and rollback MTTR.

They remain "initial operational thresholds" (see `config/observability.yaml`)
until real usage exists.
