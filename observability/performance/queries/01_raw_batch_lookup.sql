-- Raw batch lookup: bounded by partition (event_date). Representative of a
-- single-batch investigation. Correctness checksum = row count for the date.
select count(*) as row_count, count(distinct event_id) as distinct_events
from `${PROJECT}.atlas_raw.events`
where event_date = DATE '2026-07-17'
