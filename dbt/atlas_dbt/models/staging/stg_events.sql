with source as (
    select * from {{ source('atlas_raw', 'events') }}
),

normalized as (
    select
        event_id,
        nullif(trim(user_id), '') as user_id,
        trim(event_name) as event_name,
        event_timestamp,
        event_date,
        upper(nullif(trim(country_code), '')) as country_code,
        lower(nullif(trim(platform), '')) as platform,
        nullif(trim(app_version), '') as app_version,
        ingested_at,
        source_file,
        pipeline_run_id,
        batch_id,
        processing_date,
        farm_fingerprint(
            concat(
                coalesce(event_id, ''),
                '|',
                coalesce(cast(event_timestamp as string), ''),
                '|',
                coalesce(source_file, ''),
                '|',
                coalesce(pipeline_run_id, '')
            )
        ) as raw_record_hash,
        date(event_timestamp) as event_timestamp_date,
        date(ingested_at) as ingested_date,
        -- Temporal quality flags are evaluated against the logical batch
        -- processing_date (falling back to DATE(ingested_at) for legacy rows).
        -- This makes classification reproducible for historical backfills:
        -- the same raw batch yields identical flags regardless of load time.
        date(event_timestamp) > coalesce(processing_date, date(ingested_at)) as is_future_dated,
        date(event_timestamp) < coalesce(processing_date, date(ingested_at)) as is_event_time_late_arriving,
        event_date < coalesce(processing_date, date(ingested_at)) as is_backdated_event_date,
        event_date != date(event_timestamp) as has_event_date_timestamp_mismatch
    from source
)

select * from normalized
