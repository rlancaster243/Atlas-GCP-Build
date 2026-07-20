-- Atlas BigQuery cost attribution queries (Sprint 5, Phase 7 / ADR-012).
-- All queries are region-qualified (`region-us`: Atlas datasets live in US)
-- and bounded to a trailing window; INFORMATION_SCHEMA.JOBS retains ~180 days.
-- Attribution: job label application=atlas (Python via labeled clients, dbt
-- via query-comment job-label). Parent multi-statement rows are excluded
-- (statement_type = 'SCRIPT') to prevent double counting.
-- Full query text is intentionally never copied into Atlas tables.

-- 1. Daily Atlas bytes processed and billed (last 14 days)
SELECT
  DATE(creation_time) AS usage_date,
  COUNT(*) AS job_count,
  SUM(total_bytes_processed) AS bytes_processed,
  SUM(total_bytes_billed) AS bytes_billed,
  ROUND(SUM(total_bytes_billed) / POW(2, 40) * 6.25, 4) AS approx_usd_on_demand
FROM `example-gcp-project.region-us.INFORMATION_SCHEMA.JOBS`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
  AND ('application', 'atlas') IN (SELECT (key, value) FROM UNNEST(labels))
  AND statement_type != 'SCRIPT'
GROUP BY usage_date
ORDER BY usage_date DESC;

-- 2. Daily slot milliseconds (last 14 days)
SELECT
  DATE(creation_time) AS usage_date,
  SUM(total_slot_ms) AS slot_ms
FROM `example-gcp-project.region-us.INFORMATION_SCHEMA.JOBS`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
  AND ('application', 'atlas') IN (SELECT (key, value) FROM UNNEST(labels))
  AND statement_type != 'SCRIPT'
GROUP BY usage_date
ORDER BY usage_date DESC;

-- 3. Job failures (last 7 days)
SELECT
  DATE(creation_time) AS usage_date,
  error_result.reason AS error_reason,
  COUNT(*) AS failed_jobs
FROM `example-gcp-project.region-us.INFORMATION_SCHEMA.JOBS`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND ('application', 'atlas') IN (SELECT (key, value) FROM UNNEST(labels))
  AND error_result IS NOT NULL
GROUP BY usage_date, error_reason
ORDER BY usage_date DESC, failed_jobs DESC;

-- 4. Usage by Atlas component (last 14 days)
SELECT
  (SELECT value FROM UNNEST(labels) WHERE key = 'component') AS component,
  COUNT(*) AS job_count,
  SUM(total_bytes_billed) AS bytes_billed,
  SUM(total_slot_ms) AS slot_ms
FROM `example-gcp-project.region-us.INFORMATION_SCHEMA.JOBS`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
  AND ('application', 'atlas') IN (SELECT (key, value) FROM UNNEST(labels))
  AND statement_type != 'SCRIPT'
GROUP BY component
ORDER BY bytes_billed DESC;

-- 5. Unusually expensive jobs (last 7 days; adjust threshold to baseline)
SELECT
  creation_time,
  job_id,
  user_email,
  (SELECT value FROM UNNEST(labels) WHERE key = 'component') AS component,
  total_bytes_billed,
  total_slot_ms
FROM `example-gcp-project.region-us.INFORMATION_SCHEMA.JOBS`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  AND ('application', 'atlas') IN (SELECT (key, value) FROM UNNEST(labels))
  AND statement_type != 'SCRIPT'
  AND total_bytes_billed > 1 * POW(2, 30)  -- > 1 GiB billed
ORDER BY total_bytes_billed DESC
LIMIT 50;

-- 6. Trend: weekly bytes billed, labeled vs identity-attributed fallback
--    (catches jobs that escaped labeling; identities are the Atlas SAs)
SELECT
  TIMESTAMP_TRUNC(creation_time, WEEK) AS week_start,
  COUNTIF(('application', 'atlas') IN (SELECT (key, value) FROM UNNEST(labels))) AS labeled_jobs,
  COUNTIF(('application', 'atlas') NOT IN (SELECT (key, value) FROM UNNEST(labels))) AS unlabeled_jobs,
  SUM(total_bytes_billed) AS bytes_billed
FROM `example-gcp-project.region-us.INFORMATION_SCHEMA.JOBS`
WHERE creation_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 42 DAY)
  AND statement_type != 'SCRIPT'
  AND (
    ('application', 'atlas') IN (SELECT (key, value) FROM UNNEST(labels))
    OR user_email IN (
      'atlas-composer-runtime@example-gcp-project.iam.gserviceaccount.com',
      'atlas-github-integration@example-gcp-project.iam.gserviceaccount.com',
      'atlas-github-deployer@example-gcp-project.iam.gserviceaccount.com'
    )
  )
GROUP BY week_start
ORDER BY week_start DESC;
