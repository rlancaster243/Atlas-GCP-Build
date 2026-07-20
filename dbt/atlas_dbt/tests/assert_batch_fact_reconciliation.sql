{% set use_batch = var('validated_batch_id', '') != '' %}
{% set scope_column = 'batch_id' if use_batch else 'pipeline_run_id' %}
{% set scope_value = var('validated_batch_id') if use_batch else var('validated_run_id') %}

-- Fails when batch-scoped fact rows do not reconcile to accepted events (when batch scope active).
with accepted_count as (
    select count(*) as row_count
    from {{ ref('int_accepted_events') }}
    where {{ scope_column }} = '{{ scope_value }}'
),

fact_count as (
    select count(*) as row_count
    from {{ ref('fct_events') }} f
    inner join {{ ref('int_accepted_events') }} a using (event_id)
    where a.{{ scope_column }} = '{{ scope_value }}'
)

select accepted_count.row_count as accepted_rows, fact_count.row_count as fact_rows
from accepted_count
cross join fact_count
where {% if use_batch %}accepted_count.row_count != fact_count.row_count{% else %}1 = 0{% endif %}
