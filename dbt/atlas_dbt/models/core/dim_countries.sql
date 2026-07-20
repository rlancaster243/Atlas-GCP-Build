{{
    config(
        materialized='table'
    )
}}

select
    country_code,
    is_active,
    current_timestamp() as updated_at
from {{ ref('valid_country_codes') }}
