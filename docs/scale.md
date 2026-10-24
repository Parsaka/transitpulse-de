# Scale: the nationwide feed (phase 8, 2026-10-24)

On 2026-10-24 16:19 UTC the collector switched from one feed (VBB, Berlin-Brandenburg) to two
(`TP_FEEDS=vbb,gtfsde`, Terraform). gtfs.de bundles the realtime streams of about fifteen
providers across Germany (CC BY-SA 4.0, BETA, uneven coverage by their own account) and leaves
`route_id` empty, so routes come from the nationwide static schedule. Everything below is read
from Log Analytics run summaries, Azure Monitor metrics and the Databricks job runs.

## Collector (Azure Function, same 60-second timer, feeds polled one after the other)
| | VBB only (before) | VBB + gtfs.de (after) |
|---|---|---|
| Stop-time updates per fetch | 122,000 to 125,000 | VBB as before + 191,000 to 412,000 (gtfs.de) |
| Rows written per minute | 1,100 to 2,200 (VBB) | VBB as before + about 19,500 (gtfs.de, second poll; first cold poll 412,352) |
| Run time per poll | 2.8 to 3.5 s (VBB) | VBB 3.0 to 3.3 s; gtfs.de 6.2 s (cold) and 9.4 s |
| Function execution units | 131 to 148 GB-s per hour (about 1,750 GB-s per day, 13 % of the free grant) | 729 GB-s for 16:03 to 17:03 UTC with both feeds in 44 of the 60 minutes, so about **940 GB-s per hour** at steady state (about 13 GB-s per gtfs.de poll) |
| Executions | 60 per hour | 60 per hour (one timer, both feeds) |

The delta store does for the nationwide feed what it did for VBB: one minute after the cold
poll about 95 % of the stop-time updates were unchanged and not written.

### Decision: the nationwide feed gets its own timer, every 5 minutes
940 GB-s per hour is about 22,600 GB-s per day or 680,000 GB-s per month: 1.7 times the free
grant (400,000 GB-s), so roughly 4 EUR per month at the Consumption price. That breaks the budget
rule (at most 2 EUR per month). The nationwide feed therefore moved to a second timer
(`collect_national`, `TP_NATIONAL_SCHEDULE`, default every 5 minutes): 12 polls per hour at about
13 GB-s plus the regional minute timer at about 148 GB-s per hour gives about 300 GB-s per hour,
about 220,000 GB-s per month, 55 % of the grant, 0 EUR. The price is a punctuality measure that
is up to 5 minutes staler for the nationwide feed (the last prediction before a stop's scheduled
time), which `mart_feed_daily` reports separately anyway. Measured first, then decided.

## Static schedule (gtfs.de, 276 MB zip, landed 16:32 UTC from a laptop in about 3 minutes)
| Table | Rows |
|---|---|
| agency | 447 |
| routes | 24,900 |
| stops | 687,081 |
| trips | 1,895,037 |
| calendar / calendar_dates | 5,941 / 16,013 |
| Parquet written | 25.3 MB |

The static workflow lands it daily after the VBB schedule (gtfs.de regenerates the zip daily).

## Pipeline and jobs
| | Before (VBB only, 15:00 to 16:00 UTC) | First update with nationwide data (16:15 UTC) |
|---|---|---|
| Lakeflow update (bronze, silver, dimensions) | about 3.4 min (job 5.2 to 5.8 min end to end) | **3.7 min** |
| Python tasks (health, score, anomaly) | 1 to 2 min | did not start: pending 54 minutes, then RESOURCE_EXHAUSTED (daily quota) |

The pipeline absorbed the first cold poll (412k rows), the following deltas and a 1.9-million-row
trips dimension with a 9 % longer update. The Python tasks of the same run never got compute.
At 16:25 UTC the SQL warehouse had already refused to start with "you have hit your free daily
limit. Please come back again tomorrow"; the job run ended after 54 minutes with the same quota
on its serverless compute: `RESOURCE_EXHAUSTED: Sorry, cannot run the resource because you have
hit your free daily limit` (termination code FEATURE_DISABLED, pipeline task SUCCESS).
With `max_concurrent_runs: 1` that run blocked the 16:30, 16:45 and 17:00 refreshes (skipped),
so silver went stale for the rest of the quota day. The refresh job now has a 14-minute timeout:
a compute-starved run fails (one failure mail per run) instead of silently blocking the following
ones, and the pipeline task, which still got compute, keeps silver fresh (docs/databricks.md).

## What this changes
- The core marts, the weather join and the model stay on VBB (`var('core_feed')`); the nationwide
  feed is reported per feed in `mart_feed_daily` and on the status page, never added to VBB.
- Free Edition has a daily compute quota that a busy day (local dbt builds, CI, scheduled builds,
  two feeds) can exhaust. The two-hourly dbt cadence and the job timeout are the compromise; a
  paid tier (phase 7, student credit) would remove it. This is recorded as a limit, not hidden.
- Cost on the Azure side stays inside the free grant for now; the full-hour GB-s figure is the
  number to watch (400,000 GB-s per month free).
