-- Migration 008 (Sprint 6, Phase 1): timing provenance for task events.
-- Sprint 5 limitation: FAILED rows written by the Airflow failure callback
-- carried NULL started_at/completed_at/duration_ms. Timing is now derived
-- from reliable evidence only (runner clock or Airflow task-instance
-- timestamps) and each row records where its timing came from and how
-- trustworthy it is. NULL timing stays NULL — timestamps are never invented.
ALTER TABLE `atlas_ops.task_events`
  ADD COLUMN IF NOT EXISTS timing_source STRING
  OPTIONS (description = 'Timing evidence origin: step_runner_clock, airflow_task_instance, or finalizer_reconciliation'),
  ADD COLUMN IF NOT EXISTS timing_confidence STRING
  OPTIONS (description = 'Timing trustworthiness: exact, partial (completion bounded by callback clock), or none (no reliable evidence — timing left NULL)');
