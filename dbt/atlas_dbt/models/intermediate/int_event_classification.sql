{{
    config(
        materialized='table'
    )
}}

-- Sprint 7 (ADR-006 amendment): duplicate semantics distinguish a WITHIN-BATCH
-- duplicate (a batch-scoped data-quality anomaly — the intentional 50 extras)
-- from a CROSS-BATCH replay (the same event_id reappearing in a later batch,
-- e.g. same-date reprocessing). Canonical selection is first-seen-batch-wins so
-- a replay never disturbs an already-published canonical fact, while within a
-- batch the latest write still wins. Global fact uniqueness is preserved:
-- exactly one canonical row per event_id.

with staged as (
    select * from {{ ref('stg_events') }}
),

valid_countries as (
    select country_code
    from {{ ref('valid_country_codes') }}
    where is_active
),

-- Batch scope: batch_id for orchestrated loads, falling back to pipeline_run_id
-- for legacy Sprint 1 rows (which predate stable batch identity).
scoped as (
    select
        staged.*,
        coalesce(batch_id, pipeline_run_id) as batch_scope
    from staged
),

within_batch as (
    select
        scoped.*,
        -- Latest write wins WITHIN a batch (unchanged tie-break).
        row_number() over (
            partition by batch_scope, event_id
            order by
                ingested_at desc,
                event_timestamp desc,
                source_file desc,
                raw_record_hash desc
        ) as within_batch_duplicate_rank
    from scoped
),

ranked as (
    select
        within_batch.*,
        within_batch_duplicate_rank > 1 as is_within_batch_duplicate,
        -- Canonical selection across batches: within-batch winners first, then
        -- earliest-arriving row (first-seen wins) so replays never flip an
        -- already-canonical prior batch. Deterministic tie-breakers follow.
        row_number() over (
            partition by event_id
            order by
                within_batch_duplicate_rank asc,
                ingested_at asc,
                event_timestamp desc,
                source_file desc,
                raw_record_hash desc
        ) as duplicate_rank
    from within_batch
),

classified as (
    select
        ranked.*,
        duplicate_rank > 1 as is_duplicate_extra,
        valid_countries.country_code is not null as is_valid_country,
        case
            when is_within_batch_duplicate then 'within_batch'
            when duplicate_rank > 1 then 'cross_batch_replay'
            else 'none'
        end as duplicate_scope,
        case
            when ranked.user_id is null then 'missing_user_id'
            when valid_countries.country_code is null then 'invalid_country_code'
            when ranked.is_future_dated then 'future_dated'
            when duplicate_rank > 1 then 'duplicate_extra'
            else 'accepted'
        end as rejection_reason
    from ranked
    left join valid_countries
        on ranked.country_code = valid_countries.country_code
)

select
    * except (batch_scope),
    rejection_reason = 'accepted' as is_accepted,
    current_timestamp() as classified_at
from classified
