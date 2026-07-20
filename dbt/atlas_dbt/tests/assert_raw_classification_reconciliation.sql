{% set use_batch = var('validated_batch_id', '') != '' %}
{% set scope_column = 'batch_id' if use_batch else 'pipeline_run_id' %}
{% set scope_value = var('validated_batch_id') if use_batch else var('validated_run_id') %}

-- Fails when raw physical rows do not reconcile to classification rows for the validated scope.
with raw_count as (
    select count(*) as row_count
    from {{ source('atlas_raw', 'events') }}
    where {{ scope_column }} = '{{ scope_value }}'
),

classification_count as (
    select count(*) as row_count
    from {{ ref('int_event_classification') }}
    where {{ scope_column }} = '{{ scope_value }}'
)

select
    raw_count.row_count as raw_rows,
    classification_count.row_count as classification_rows
from raw_count
cross join classification_count
where raw_count.row_count != classification_count.row_count
