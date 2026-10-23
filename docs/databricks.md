# Databricks (Free Edition): landing, pipeline, health

Workspace `https://dbc-2fb26299-f7ca.cloud.databricks.com`, catalog `workspace`, schemas `tp_*`
(see ADR 0002 for why not a dedicated catalog). Everything below is created by the bundle in
`databricks/` (`databricks bundle deploy -t prod`); the `dev` target is a prefixed copy with the
schedule paused.

```
Azure Function ──Files API──▶ Volume workspace.tp_landing.raw
                               raw/<dataset>/feed=/date=/hour=/*.parquet   (every minute)
                               static/gtfs/feed=vbb/version=<date>/*.parquet (twice a week)
                                        │ Auto Loader (explicit schemas)
                                        ▼
            tp_bronze.bronze_stop_times / bronze_trips_gone / bronze_alerts        streaming tables
                                        ▼
            tp_silver.silver_stop_time_updates  (expectations)                    streaming table
            tp_silver.silver_trips_gone, silver_alerts                             streaming tables
            tp_silver.silver_stop_time_latest                                      materialized view
            tp_silver.dim_agency/routes/stops/trips/calendar/calendar_dates        materialized views
                                        ▼
            job transitpulse-refresh-prod, every 15 min: pipeline, then health_snapshot.py
            ──▶ /Volumes/workspace/tp_landing/raw/ops/health.json (rows, freshness, expectations)
            tp_ops.lakeflow_event_log (published pipeline event log)
```

## Expectations (silver_stop_time_updates)
| Name | Rule | Action |
|---|---|---|
| trip_id_present | `trip_id IS NOT NULL` | drop |
| feed_ts_present | `feed_ts IS NOT NULL` | drop |
| plausible_arrival_delay | NULL or between -30 min and +10 h | warn |
| plausible_departure_delay | same | warn |
| stop_known_or_cancelled | `stop_id IS NOT NULL OR trip cancelled` | warn |

## First runs (2026-10-23, prod)
- Bundle deploy: 8 resources (5 schemas, Volume, pipeline, job). Backfill of 144 raw delta files
  (1.8 MB) from the Azure lake into the Volume: 12.9 s. Static GTFS landed: 32 agencies, 1,255
  routes, 41,929 stops, 184,416 trips, 1,616 calendar rows, 11,568 exceptions (2.1 MB Parquet).
- First update failed with `CF_EMPTY_DIR_FOR_SCHEMA_INFERENCE` on `raw/alerts` (VBB publishes no
  alerts): fixed with explicit schemas and a `*.parquet` glob filter. The fixed update: 13 flows,
  COMPLETED in 110 s; a full refresh after moving bronze into its own schema: 170 s.
- Health snapshot after the full refresh: `bronze_stop_times` 168,409 rows,
  `silver_stop_time_updates` 167,625 (784 rows dropped by the two `expect_or_drop` rules or as
  duplicates), `silver_stop_time_latest` 147,385, `silver_trips_gone` 1,488, `bronze_alerts` 0.
- The job run that produced it: queued 2.5 min on serverless, pipeline + health 30 s once running.
- **End to end after the merge (02:00 UTC scheduled run):** the Function had been writing to the
  Volume for 4 minutes (`lake: azure ... + volume ...` in its run summaries, 0 sink failures); the
  refresh ingested 4,284 new bronze rows and 4,196 silver rows (88 duplicates removed), every
  expectation passed (`trip_id_present`, `feed_ts_present`, `plausible_arrival_delay`,
  `plausible_departure_delay`, `stop_known_or_cancelled`: 4,196 pass, 0 fail), and
  `health.json` reported the newest stop-time update 2.5 minutes old. Totals at that point:
  172,693 bronze rows, 171,821 silver updates, 150,730 latest predictions, 1,534 gone trips.

## Reading numbers out
Free Edition exposes neither the SQL Statement Execution API nor event details through the
pipelines API, so the health task writes `ops/health.json` and the pipeline publishes its event
log to `tp_ops.lakeflow_event_log`. Read the snapshot from anywhere:
```bash
databricks fs cat dbfs:/Volumes/workspace/tp_landing/raw/ops/health.json --profile transitpulse
```

## Limits that shaped the design
- Serverless only; one active pipeline per type (dev is paused); five concurrent job tasks.
- No outbound internet from compute: ingestion stays in Azure, the Function pushes files in.
- No account API: a 90-day personal access token (Key Vault) instead of a service principal.
- Catalogs with Default Storage can only be created in the UI.
