{{
    config(
        materialized='table'
    )
}}

select
    event_date,
    event_name,
    country_code,
    platform,
    count(*) as event_count,
    count(distinct user_id) as distinct_user_count,
    countif(is_backdated_event_date) as backdated_event_date_count,
    countif(has_event_date_timestamp_mismatch) as event_date_timestamp_mismatch_count,
    countif(is_event_time_late_arriving) as event_time_late_arriving_count,
    current_timestamp() as updated_at
from {{ ref('fct_events') }}
group by 1, 2, 3, 4
