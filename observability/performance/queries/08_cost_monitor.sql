-- Cost-monitor query: recent Atlas BigQuery jobs bytes billed via
-- INFORMATION_SCHEMA (region-scoped, last 7 days, bounded).
select
  count(*) as jobs,
  sum(total_bytes_billed) as bytes_billed
from `${PROJECT}`.`region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
where creation_time >= timestamp_sub(current_timestamp(), interval 7 day)
  and job_type = 'QUERY'
