-- Operational-audit query: recent pipeline run outcomes.
select status, count(*) as runs
from `${PROJECT}.atlas_ops.pipeline_runs`
group by status
order by runs desc
