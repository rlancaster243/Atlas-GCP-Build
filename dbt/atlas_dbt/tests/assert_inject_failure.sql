-- Fails when inject_failure var is enabled (local failure simulation only).
select 1 as failure_injected
from unnest([1])
where {{ var('inject_failure', false) }}
