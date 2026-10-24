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

| Metric (60 s polling) | Before 12:20–13:05 (45 runs) | After 13:25–13:58 (32 runs) | Change |
|---|---|---|---|
| total per run p50 / p95 (ms) | 4,895 / 6,131 | 3,925 / 4,246 | −20 % / −31 % |
| write step p50 / p95 (ms) | 1,534 / 1,826 | 1,020 / 1,192 | −33 % / −35 % |
| load_state p50 (ms) | 212 | 160 | −25 % (reused client) |
| fetch / parse / delta p50 (ms) | 647 / 704 / 1,739 | 597 / 722 / 1,401 | not targeted; delta follows the rows per run |
| rows / bytes written per run | 3,575 / 52 KB | 2,620 / 45 KB | traffic dependent (afternoon lull) |

## 2. Function package: pandas removed
pandas was a declared dependency but never imported; pyarrow does all the Parquet work.

| Metric | Before | After | Change |
|---|---|---|---|
| deployed `.python_packages` | 397 MB | 237 MB | −40 % |
| cold start, first execution after a (re)start | 20,352 and 24,394 ms (two samples) | 6,026, 5,846 and 3,123 ms (three restarts: deploy 13:22, setting change 13:59, revert 19:31) | about −75 % |

## 3. Polling interval: 60 s versus 120 s
The schedule is an app setting (`TP_SCHEDULE`). The 120 s run started 13:59 UTC on 2026-10-23;
a one-off GitHub cron was meant to revert it at 15:40 but GitHub ran it at 19:31 (scheduled
workflows are best effort; a lesson for anything time-critical: use Azure's own scheduler), so
the window was 14:00 to 19:30. All figures from `scripts/measure_collector.py` and the
`FunctionExecutionUnits` metric; traffic differs between hours, so per-hour rows are indicative.

| Metric | 60 s, 13:25–13:59 | 120 s, 14–15 h | 120 s, 15–17 h | 120 s, 17–19 h | 60 s, 20–22 h | 60 s, next day 9–11 h |
|---|---|---|---|---|---|---|
| executions per hour | 62 | 32 | 30 | 30 | 61 | 61 |
| run p50 (ms) | 3,925 | 4,503 | 4,218 | 3,673 | 2,609 | 3,087 |
| rows written per run | 2,613 | 6,221 | 5,067 | 3,751 | 1,116 | 2,024 |
| rows written per hour | 161,531 | 198,815 | 154,325 | 113,897 | 67,636 | 122,667 |
| bytes written per hour | 2.77 MB | 2.64 MB | 2.18 MB | 1.63 MB | 1.29 MB | 2.00 MB |
| delta reduction | 98.6 % | 96.6 % | 97.0 % | 97.3 % | 99.0 % | 98.5 % |
| feed age at fetch p50 (s) | 24 | 15.6 | 14 | 17 | 16.5 | 17.5 |
| GB-s per hour (metric) | 200 (13 h, mixed code) | 110 | 93–99 | 70–81 | 118–125 | 144 |

Reading: halving the polls halves the executions and cuts GB-seconds by roughly a third (the
run itself gets longer because each run carries twice the changes: run p50 4.2–4.5 s against
3.1–3.9 s). What is lost is not visible in these totals: a prediction that changes twice within
two minutes is written once at 120 s, so the per-stop history is coarser; the lake size and the
rows per hour move with the traffic of the hour more than with the interval.

Decision: **keep 60 s.** The saving (about 35 % of GB-seconds) has no monetary value at 13 % of
the free grant, and the one-minute cadence is the product's promise on the status page; the knob
stays documented for a future feed with heavier polls (gtfs.de nationwide, 8 MB per fetch).

## 4. Pipeline: latest-state table as AUTO CDC instead of a materialized view
`silver_stop_time_latest` (latest prediction per trip and stop) was a materialized view that
recomputed a group-by plus self-join over every update on each refresh. It is now a streaming
table fed by `apply_changes` (SCD type 1, sequenced by `feed_ts`), so a refresh applies only the
new updates.

| Metric | Before (24 updates, 6 h) | After (2 incremental updates, 13:30 and 13:45) |
|---|---|---|
| flow `silver_stop_time_latest` avg / max (s) | 124 / 149 | 96.5 / 101 (−22 %) |
| whole update p50 / max (min) | 3.50 / 4.03 | see slo_pipeline_updates after a week of incremental runs |
| rows in the table | 739,086 (10:00) | 1,061,499 (13:52), 1 file, no duplicate keys |

## 5. Warehouse: compaction and clustering
Baseline layout showed that the Lakeflow pipeline already keeps the tables compact: bronze
`stop_times` is one 13.5 MB file, silver `stop_time_updates` three files (34.6 MB) with liquid
clustering on `feed_date, trip_id`, the dbt marts are single small files. The benchmark queries
take 320 to 560 ms on the serverless warehouse (5 runs each, warm). An `OPTIMIZE` has nothing to
compact at this size, so it was not applied; clustering the marts was measured instead:

| Query (median ms, 5 runs) | Before | After |
|---|---|---|
| latest_by_hour_mode | 561 | 505 |
| updates_one_day_trip_scan | 360 | 371 |
| punctuality_hourly_filter | 341 | 321 |
| network_now_full | 319 | 322 |
| collector_runs_day | 356 | 361 |

Finding: no measurable change (all within run-to-run noise of about ±50 ms); at a few MB per table the serverless warehouse is bound by request overhead, not by data layout. The clustering stays because the tables grow by about 1.5 M stop-time rows a day; the benchmark is re-run monthly.

## 6. Delta store: gone-trip cleanup in one pass (phase 8, 2026-10-24)
Found when the nationwide feed moved to its own 5-minute timer: a poll took 58 to 60 s, of which
54.4 s in the `delta` step (step logs in Log Analytics, run 7691af79db0a). For every trip that
had left the feed the store scanned all stop fingerprints to drop that trip's keys, O(store x
gone): 1,796 gone trips x 390k fingerprints. At one poll per minute only about 120 trips leave
the feed, so the scan cost 4.8 s and hid in the noise.

Change: one pass groups the fingerprints by trip (`rsplit('|', 1)`), then each gone trip drops
its keys from that index: O(store + gone).

| | Before | After |
|---|---|---|
| Synthetic, production shape (56k trips, 390k rows, 1,800 gone, 8.5 % changed), laptop | 67.4 s | **1.26 s** |
| Production, gtfs.de 5-minute poll, `delta` step | 54.4 s (17:20 UTC, 1,796 gone) | **1.63 s** (17:35 UTC, 1,682 gone) |
| Production, whole poll | 57.8 to 60.5 s | **7.0 s** (32,239 rows written) |

Why it matters for cost: a 60-second poll every five minutes is about 60 GB-s per poll on the
Consumption plan, more than the minute timer had cost; after the fix a poll takes 7 s,
measured on the first poll after the deploy. The timer stays at 5 minutes until the next full-hour `FunctionExecutionUnits`
reading confirms the arithmetic in docs/scale.md.
