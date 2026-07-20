# Atlas BigQuery Performance Review (Sprint 7)

Measured before optimizing. Methodology and controls in ADR-020. The suite is
`scripts/run_performance_suite.sh` over `observability/performance/queries/`.

## Methodology

- **Dry-run first** (bills $0) for every representative query → bytes processed.
- **Bounded execution** (gated) under a per-query `maximum_bytes_billed` ceiling
  (1 GiB) and a cumulative suite ceiling (5 GiB), with run labels
  (`atlas_component=perf_suite`), capturing bytes billed, slot-ms, elapsed,
  output rows, cache-hit, and a correctness checksum.
- Correctness verified via row-count/aggregate checksums before and after any
  change.

## Dry-run baseline (live, 2026-07-19, $0)

`observability/performance/results/baseline-dryrun.json`:

| # | Query | Bytes processed (est.) |
| --- | --- | --- |
| 1 | raw batch lookup (partition filter) | 2,315,824 |
| 2 | batch classification (1 partition) | 745,937 |
| 3 | accepted/rejected reconciliation | 795,136 |
| 4 | fact build scan (3-day window) | 2,255,810 |
| 5 | mart aggregation (monthly) | 44,864 |
| 6 | freshness | 4,700,784 |
| 7 | operational audit | 216 |
| 8 | cost monitor (INFORMATION_SCHEMA.JOBS, 7d) | 34,428,633 |
| 9 | lineage/schema metadata | 10,485,760 |

All queries are far below the 1 GiB per-query ceiling.

## Partition pruning evidence

- Bounded raw lookup (`where event_date = …`): **2,315,824 bytes**.
- Unbounded full scan of the same table (no partition filter): **12,659,283
  bytes** (dry-run).

The bounded query scans ~18% of the unbounded scan → **partition pruning is
working** on `atlas_raw.events` (partitioned by `event_date`). `fct_events` is
likewise partitioned by `event_date` and clustered by `event_name,
country_code`, exercised by query 4.

## Performance changes applied (Phase 11)

**None warranted — evidence-backed "no material change" result.** The warehouse
is already partitioned + clustered, all representative queries are bounded and
inexpensive at this scale (~50k rows/batch), and correctness is preserved. The
highest-leverage improvement is *preventing regressions*, which Sprint 7 adds as
the required-partition-filter cost guard rather than a table redesign. Per
ADR-020, we do not optimize merely to produce a percentage.

Comparisons considered and their verdicts (from the baseline evidence):

| Comparison | Verdict |
| --- | --- |
| partitioned vs unbounded raw scan | partitioned wins (2.3 MB vs 12.7 MB) — keep + enforce filter |
| clustered fact scan (query 4) | already clustered; bounded window is cheap |
| mart (table) vs recompute from fact | mart is tiny (44 KB read) — keep materialized |
| INFORMATION_SCHEMA cost monitor | bounded to 7 days — acceptable |

## Blocked completion gate

- **Gate:** full **executed** metrics (bytes billed, slot-ms, elapsed) via
  `run_performance_suite.sh --execute`.
- **Blocking approval:** `ATLAS_APPROVE_PERFORMANCE_TESTS=true` (+ optional
  `ATLAS_MAX_PERFORMANCE_TEST_BYTES`) — not set in this environment.
- **Status:** dry-run baseline (bytes processed) is complete and is sufficient
  to conclude no optimization is warranted; executed slot/elapsed metrics are
  pending approval. The suite runner is ready and enforces the byte ceilings.

## Honest limitations

- ~50k rows/batch: these are engineering demonstrations, not production-scale
  benchmarks. No production-scale performance is claimed.
