-- Lineage/schema metadata query: column inventory for the core dataset via
-- INFORMATION_SCHEMA (metadata only, negligible bytes).
select table_name, count(*) as columns
from `${PROJECT}.atlas_core.INFORMATION_SCHEMA.COLUMNS`
group by table_name
order by table_name
