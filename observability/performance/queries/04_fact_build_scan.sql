-- Fact build scan (incremental lookback simulation): scan accepted fact rows in
-- a bounded ingested window. Clustered by event_name, country_code.
select event_name, country_code, count(*) as n
from `${PROJECT}.atlas_core.fct_events`
where event_date between DATE '2026-07-15' and DATE '2026-07-17'
group by event_name, country_code
