{% set use_batch = var('validated_batch_id', '') != '' %}
{% set scope_column = 'batch_id' if use_batch else 'pipeline_run_id' %}
{% set scope_value = var('validated_batch_id') if use_batch else var('validated_run_id') %}

-- Fails when accepted canonical rows plus rejected physical rows do not equal raw rows.
with raw_count as (
    select count(*) as row_count
    from {{ source('atlas_raw', 'events') }}
    where {{ scope_column }} = '{{ scope_value }}'
),

accepted_count as (
    select count(*) as row_count
    from {{ ref('int_accepted_events') }}
    where {{ scope_column }} = '{{ scope_value }}'
),

rejected_count as (
    select count(*) as row_count
    from {{ ref('int_rejected_events') }}
    where {{ scope_column }} = '{{ scope_value }}'
)

select
    raw_count.row_count as raw_rows,
    accepted_count.row_count as accepted_rows,
    rejected_count.row_count as rejected_rows,
    accepted_count.row_count + rejected_count.row_count as accepted_plus_rejected
from raw_count
cross join accepted_count
cross join rejected_count
where raw_count.row_count != accepted_count.row_count + rejected_count.row_count
