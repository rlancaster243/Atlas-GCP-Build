-- Fails when mart totals do not reconcile to the accepted fact table.
with fact_count as (
    select count(*) as row_count
    from {{ ref('fct_events') }}
),

mart_total as (
    select coalesce(sum(event_count), 0) as row_count
    from {{ ref('mart_daily_event_metrics') }}
)

select
    fact_count.row_count as fact_rows,
    mart_total.row_count as mart_event_total
from fact_count
cross join mart_total
where fact_count.row_count != mart_total.row_count
