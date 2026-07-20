-- Mart aggregation: daily metrics read (small mart). Representative BI query.
select event_date, sum(event_count) as total_events
from `${PROJECT}.atlas_marts.mart_daily_event_metrics`
where event_date between DATE '2026-07-01' and DATE '2026-07-31'
group by event_date
order by event_date
