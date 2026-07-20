# Operator Checklist

**Status:** CURRENT · **Audience:** operator. Answer each per pipeline run. Every
answer has a queryable source — no tribal knowledge required.

| Question | Where to look |
| --- | --- |
| Did the pipeline run? | `atlas_ops.pipeline_runs` (row for the `pipeline_run_id`) |
| Is the data complete? | raw row count vs accepted+rejected reconciliation |
| Is the data correct? | dbt tests + `assert_source_anomaly_profile` |
| Did quality checks pass? | `atlas_ops.quality_results` |
| Were success markers published? | success marker only on pass (INV-D7/L5) |
| Are alerts healthy? | Cloud Monitoring; [alert-catalog-sprint5.md](../alert-catalog-sprint5.md) |
| Who is notified? | notification channel (see security model) |
| What failed? | `atlas_ops.task_events` (FAILED/RETRY w/ timing) |
| How is recovery selected? | [recovery-runbook-sprint6.md](../recovery-runbook-sprint6.md) |
| How is recovery verified? | `validate_warehouse(<batch>)`; `recovery_actions` VERIFIED |
| How is recurrence prevented? | incident report follow-ups + regression tests |
| What will the action cost? | `cost_guard estimate` (dry-run first) |
| What evidence must be preserved? | `atlas_ops.*`, validation reports, incident reports |

If any answer is "unknown", stop and consult the relevant runbook before acting.
Never publish success on a failed run; never run a billed query without a
dry-run and the cost ceiling.
