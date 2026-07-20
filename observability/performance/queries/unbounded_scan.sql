-- DELIBERATELY UNBOUNDED: full scan of raw events with no partition filter.
-- Used ONLY to demonstrate that the cost guard blocks it at dry-run before any
-- spend. Never run this as a real workload.
select event_name, country_code, count(*) as n
from `${PROJECT}.atlas_raw.events`
group by event_name, country_code
