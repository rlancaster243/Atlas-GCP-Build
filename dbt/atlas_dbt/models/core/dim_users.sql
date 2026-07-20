{{
    config(
        materialized='table'
    )
}}

select
    user_id,
    min(event_timestamp) as first_event_at,
    max(event_timestamp) as last_event_at,
    count(*) as event_count,
    current_timestamp() as updated_at
from {{ ref('int_accepted_events') }}
where user_id is not null
group by user_id
