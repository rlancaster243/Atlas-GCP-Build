{{
    config(
        materialized='incremental',
        incremental_strategy='merge',
        unique_key='event_id',
        partition_by={'field': 'event_date', 'data_type': 'date'},
        cluster_by=['event_name', 'country_code'],
        on_schema_change='fail'
    )
}}

with accepted as (
    select *
    from {{ ref('int_accepted_events') }}
    where 1 = 1
    {% if is_incremental() %}
        and ingested_at >= timestamp_sub(
            coalesce((select max(ingested_at) from {{ this }}), timestamp('1970-01-01')),
            interval {{ var('lookback_days') }} day
        )
    {% endif %}
    {% if var('start_date', none) is not none %}
        and event_date >= date('{{ var("start_date") }}')
    {% endif %}
    {% if var('end_date', none) is not none %}
        and event_date <= date('{{ var("end_date") }}')
    {% endif %}
)

select
    event_id,
    user_id,
    event_name,
    event_timestamp,
    event_date,
    country_code,
    platform,
    app_version,
    ingested_at,
    source_file,
    pipeline_run_id,
    batch_id,
    raw_record_hash,
    is_backdated_event_date,
    has_event_date_timestamp_mismatch,
    is_event_time_late_arriving,
    classified_at as loaded_to_core_at,
    current_timestamp() as updated_at
from accepted
