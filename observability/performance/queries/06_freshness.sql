-- Freshness query: latest ingest recency from the fact table.
select
  max(ingested_at) as last_ingest,
  timestamp_diff(current_timestamp(), max(ingested_at), SECOND) as staleness_seconds
from `${PROJECT}.atlas_core.fct_events`
where event_date >= DATE '2026-07-15'
