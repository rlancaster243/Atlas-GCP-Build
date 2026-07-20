{{
    config(
        materialized='view'
    )
}}

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
    duplicate_rank,
    is_duplicate_extra,
    is_valid_country,
    is_future_dated,
    is_event_time_late_arriving,
    is_backdated_event_date,
    has_event_date_timestamp_mismatch,
    rejection_reason,
    classified_at
from {{ ref('int_event_classification') }}
where rejection_reason = 'accepted'
