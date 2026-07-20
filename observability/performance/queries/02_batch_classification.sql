-- Batch classification profile: duplicate/quality flags for one partition.
-- Representative of the anomaly-profile workload.
select
  countif(user_id is null) as null_user,
  count(*) as total
from `${PROJECT}.atlas_raw.events`
where event_date = DATE '2026-07-17'
