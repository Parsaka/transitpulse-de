# Measured optimisations (phase 6)

Every change below was measured with the same tools before and after, on the production system:
`scripts/measure_collector.py` (per-step timings and bytes from Log Analytics for a time window),
`scripts/bench_sql.py` (warehouse queries and table layout), the pipeline event log (per-flow
durations) and Azure metrics (`FunctionExecutionUnits`). Windows are UTC, 2026-10-23. Where a
change bought nothing measurable, that is written down as well.

## 1. Collector: parallel uploads and warm-instance clients
Before, every run wrote its objects one after another (lake, then Volume, per dataset) and
rebuilt the blob client, the Files API client and the identity token on every invocation.
After: primary and sink written concurrently, all objects of a run uploaded at once, clients and
token kept per worker process.

| Metric (60 s polling, 45 runs each) | Before 12:20–13:05 | After AFTER_WINDOW | Change |
|---|---|---|---|
| total per run p50 / p95 (ms) | 4,895 / 6,131 | AFTER_TOTAL | |
| write step p50 / p95 (ms) | 1,534 / 1,826 | AFTER_WRITE | |
| load_state p50 (ms) | 212 | AFTER_LOAD | |
| fetch / parse / delta p50 (ms) | 647 / 704 / 1,739 | AFTER_FPD | unchanged by design |
| rows / bytes written per run | 3,575 / 52 KB | AFTER_ROWS | traffic dependent |

## 2. Function package: pandas removed
pandas was a declared dependency but never imported; pyarrow does all the Parquet work.

| Metric | Before | After | Change |
|---|---|---|---|
| deployed `.python_packages` | 397 MB | 237 MB | −40 % |
| cold start, first execution after a (re)start | 20,352 ms and 24,394 ms (two samples) | COLD_AFTER | |

## 3. Polling interval: 60 s versus 120 s
The schedule is an app setting (`TP_SCHEDULE`), changed with `terraform apply`. One hour each,
adjacent hours, same weekday afternoon; traffic differs slightly between the hours, so the rows
per hour are indicative, the per-run figures are not.

| Metric | 60 s (WIN60) | 120 s (WIN120) |
|---|---|---|
| executions per hour | P60_EXEC | P120_EXEC |
| rows written per hour | P60_ROWS | P120_ROWS |
| bytes written per hour | P60_BYTES | P120_BYTES |
| delta reduction | P60_RED | P120_RED |
| feed age at fetch p50 (s) | P60_AGE | P120_AGE |
| GB-seconds per hour (Azure metric) | P60_GBS | P120_GBS |

Decision: DECISION_POLLING

## 4. Pipeline: latest-state table as AUTO CDC instead of a materialized view
`silver_stop_time_latest` (latest prediction per trip and stop) was a materialized view that
recomputed a group-by plus self-join over every update on each refresh. It is now a streaming
table fed by `apply_changes` (SCD type 1, sequenced by `feed_ts`), so a refresh applies only the
new updates.

| Metric | Before (24 updates, 6 h) | After (AFTER_UPDATES) |
|---|---|---|
| flow `silver_stop_time_latest` avg / max (s) | 124 / 149 | CDC_FLOW |
| whole update p50 / max (min) | 3.50 / 4.03 | CDC_UPDATE |
| rows in the table | 739,086 (10:00) | CDC_ROWS |

## 5. Warehouse: compaction and clustering
Baseline layout showed that the Lakeflow pipeline already keeps the tables compact: bronze
`stop_times` is one 13.5 MB file, silver `stop_time_updates` three files (34.6 MB) with liquid
clustering on `feed_date, trip_id`, the dbt marts are single small files. The benchmark queries
take 320 to 560 ms on the serverless warehouse (5 runs each, warm). An `OPTIMIZE` has nothing to
compact at this size, so it was not applied; clustering the marts was measured instead:

| Query (median ms, 5 runs) | Before | After |
|---|---|---|
| latest_by_hour_mode | 561 | SQL_AFTER_1 |
| updates_one_day_trip_scan | 360 | SQL_AFTER_2 |
| punctuality_hourly_filter | 341 | SQL_AFTER_3 |
| network_now_full | 319 | SQL_AFTER_4 |
| collector_runs_day | 356 | SQL_AFTER_5 |

Finding: FINDING_SQL
