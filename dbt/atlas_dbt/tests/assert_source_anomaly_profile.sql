{% set use_batch = var('validated_batch_id', '') != '' %}
{% set scope_column = 'batch_id' if use_batch else 'pipeline_run_id' %}
{% set scope_value = var('validated_batch_id') if use_batch else var('validated_run_id') %}

-- Fails when the validated scope does not match the corrected Sprint 2 anomaly profile.
with scoped as (
    select *
    from {{ ref('int_event_classification') }}
    where {{ scope_column }} = '{{ scope_value }}'
),

counts as (
    select
        -- Sprint 7: the anomaly profile measures WITHIN-BATCH duplicates (the
        -- intentional 50 extras). Cross-batch replays are excluded so that a
        -- same-date reprocessing batch does not corrupt this batch-scoped
        -- assertion (INC-S6-001).
        countif(is_within_batch_duplicate) as duplicate_extra_count,
        countif(user_id is null) as null_user_count,
        countif(not is_valid_country) as invalid_country_count,
        countif(is_future_dated) as future_dated_count,
        countif(is_event_time_late_arriving) as event_time_late_count,
        countif(is_backdated_event_date) as backdated_event_date_count,
        countif(has_event_date_timestamp_mismatch) as date_timestamp_mismatch_count,
        -- Temporal flags are only reproducible when every scoped row carries a
        -- processing_date reference. Legacy rows without it fall back to
        -- DATE(ingested_at), which is load-time dependent, so the temporal
        -- assertions are skipped for those scopes (graceful degradation).
        countif(processing_date is null) as missing_processing_date_count
    from scoped
)

select *
from counts
where duplicate_extra_count != 50
   or null_user_count != 500
   or invalid_country_count != 200
   or date_timestamp_mismatch_count != 300
   or (
        missing_processing_date_count = 0
        and (
            future_dated_count != 150
            or event_time_late_count != 0
            or backdated_event_date_count != 300
        )
   )
