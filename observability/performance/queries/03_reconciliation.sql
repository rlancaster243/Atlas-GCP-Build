-- Accepted/rejected reconciliation for one partition: accepted fact rows vs raw.
-- Correctness: accepted <= raw for the partition.
select
  (select count(*) from `${PROJECT}.atlas_raw.events` where event_date = DATE '2026-07-17') as raw_rows,
  (select count(*) from `${PROJECT}.atlas_core.fct_events` where event_date = DATE '2026-07-17') as fact_rows
