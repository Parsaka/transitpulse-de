# TransitPulse DE

Streaming lakehouse for German public-transport punctuality, built on a zero-cash budget.

Every minute a collector reads the GTFS-Realtime feeds of VBB (Berlin-Brandenburg) and, later,
gtfs.de (all of Germany), keeps only what changed, and lands it in a data lake. Databricks
(Free Edition) turns it into bronze, silver and dbt gold tables: punctuality per line and hour,
delay propagation, cancellations, weather impact and a forward-looking delay forecast. The whole
pipeline watches itself with SLOs and alerts, and every optimisation is measured before and after.

**Status: phases 0–6 and 8 done (2026-10-24).** Project page with live status: https://parsa-kamali.de/projects/transitpulse-de.php · Live status page:
https://sttransitpulsedev3dkkh.z1.web.core.windows.net/ (SLOs, error budgets, network now; the
dbt docs are under `/docs/`). The collector runs every minute in Azure (Functions,
Consumption plan, managed identity), writes deltas to an ADLS Gen2 lake and pushes them into a
Databricks Unity Catalog Volume; a Lakeflow Declarative Pipeline builds bronze and silver tables
with expectations plus the static-schedule dimensions every 15 minutes; dbt builds the gold marts
(punctuality, delay propagation, cancellations, network now, weather impact) and the SLO tables
on the serverless SQL warehouse every two hours, with slim CI on pull requests. Hourly Open-Meteo
weather feeds a LightGBM delay-at-destination model (MLflow, Unity Catalog registry, weekly
retraining behind a skill gate against the naive baseline) whose predictions are logged forward
and scored against outcomes; a z-score anomaly detector raises a SQL alert. Azure is Terraform,
Databricks is a bundle, CI validates and plans both. Four SLOs, three drills, Grafana dashboard
and measured optimisations are documented under docs/.

## What exists today
- `transitpulse collect --feed vbb --once`: fetch with ETag, parse, delta against the previous
  snapshot, write zstd Parquet partitions (`raw/<dataset>/feed=/date=/hour=/`) to a local folder or
  to Azure Blob (managed identity, no keys), JSON logs with per-step durations and a run summary.
- Azure Functions `collect` (every 60 s, VBB and gtfs.de nationwide since phase 8) and `weather`
  (hourly Open-Meteo for nine grid points), schedules from app settings;
  Terraform for the lake, Function, Log Analytics + Application Insights, Key Vault, alert, budget
  and the GitHub OIDC identity ([docs/azure-setup.md](docs/azure-setup.md)).
- CI: ruff, mypy, 42 offline tests on trimmed real feeds, Terraform validate and an OIDC plan,
  and a smoke test that runs the deployable package in the official Functions image with Azurite.
- Databricks Free Edition ([docs/databricks.md](docs/databricks.md)): landing Volume, pipeline
  `bronze_*` → `silver_*` + `dim_*`, job every 15 min, health snapshot; `transitpulse gtfs-static`
  lands the VBB schedule twice a week.
- dbt gold ([docs/dbt.md](docs/dbt.md)): `mart_punctuality_hourly/daily`, `mart_network_now`,
  `mart_delay_propagation`, `mart_cancellations_daily`, `mart_weather_impact_hourly`,
  `mart_feed_daily`, `mart_forecast_quality`, `slo_status`; 54 tests, source freshness, slim CI deferred to the prod
  manifest, two-hourly prod build.
- ML ([docs/ml.md](docs/ml.md)): LightGBM delay-at-destination model on Databricks serverless
  jobs, time-based holdout, skill gate against the naive baseline, MLflow + Unity Catalog registry,
  weekly retraining, forward-looking forecast log scored against outcomes, z-score network anomaly
  detector with a SQL alert. First run: MAE 50.6 s vs naive 52.3 s (skill 3.3 %, two days of data).
- Observability ([docs/observability.md](docs/observability.md)): four SLOs with error budgets
  (`slo_error_budget`), collector executions synced hourly into the lakehouse, alerts on three
  layers, public status site, Grafana dashboard; three incident drills with measured timelines
  ([docs/drills.md](docs/drills.md)); measured cost ([docs/cost.md](docs/cost.md)).
- Measured optimisations ([docs/optimisation.md](docs/optimisation.md)): collector run −20 %
  (p50) after parallel uploads, package −40 % and cold start −75 % without pandas, latest-state
  flow −22 % as AUTO CDC, polling interval experiment (kept 60 s), clustering (no gain, kept).
- Scale ([docs/scale.md](docs/scale.md)): the nationwide feed measured against the regional one;
  case study ([docs/case-study.md](docs/case-study.md)) and CV wording ([docs/cv.md](docs/cv.md)).
- `transitpulse inspect <file.pb>`: delay distribution of a saved feed.

## Measured so far (2026-10-22, laptop, single fetch)
| Feed | Size per fetch | Trip updates | Stop-time updates | Fetch latency |
|---|---|---|---|---|
| VBB | 6.3 MB | 6,455 | 124,193 | 0.9 s |
| gtfs.de (nationwide) | 8.3 MB | 24,957 (+374 alerts) | 191,398 | 1.0 s |

Three consecutive live polls of VBB, 60 s apart, delta mode (same laptop, 2026-10-22 21:51 UTC):

| Poll | Stop-time updates in feed | Rows written | Parquet size | Trips gone | Run time |
|---|---|---|---|---|---|
| 1 (cold store) | 122,775 | 122,775 | 688 KB | 0 | 5.7 s |
| 2 | 122,581 | 793 (0.65%) | 15 KB | 29 | 3.6 s |
| 3 | 122,981 | 1,391 (1.13%) | 24 KB | 22 | 5.0 s |

The delta store suppressed about 99% of the rows.

**Delta state encoding** (same 123k tracked stop-time updates): JSON with full fingerprints
11.7 MB; Parquet with 64-bit hashed fingerprints 0.65 MB, an 18x reduction.

**In Azure** (Function, Consumption plan, 2026-10-22 23:52 to 00:02 UTC, after the deployment fix):
11 of 11 executions succeeded, one per minute; 1.7 to 2.6 s warm, 4.1 s on the cold start; each
run wrote one stop-time delta file of 9 to 13 KB and one gone-trips file of about 1.8 KB; the
state blob is 0.6 MB. Before the fix, 26 executions had failed in 25 ms each (`GLIBC` import
error), which is what the smoke test now catches in CI.

**In Databricks** (prod pipeline, 2026-10-23): first full refresh of 13 flows in 170 s; silver holds
167,625 stop-time updates out of 168,409 bronze rows (784 dropped by the two hard expectations or
as duplicates), 147,385 latest predictions, 1,488 gone trips; dimensions 1,255 routes, 41,929
stops, 184,416 trips.

**First answers from the gold layer** (2026-10-23, about 11 hours of VBB data, so a snapshot, not a
study): network punctuality 98.4 % of 456,692 observed stop events (S-Bahn and U-Bahn at 100 %,
buses 96.5 %, regional rail 91.3 % at 09:30 UTC); buses enter their route with 1.0 min of delay
and leave with 1.5 min; trams had the highest cancellation rate (3.6 % of trips seen). The SLO
table was honest on day one: the pipeline SLO is breached (37 of 47 updates succeeded, the ten
failures being the bootstrap incident) and the first freshness target of 15 min was unreachable
with a 15-minute refresh cadence (recalibrated to 20). Storage per day, GB-seconds against the
free grant and polling trade-offs are measured in phase 6, not estimated.

## Plan and operations
See [docs/roadmap.md](docs/roadmap.md) (phases), [docs/adr/0001-free-tier-architecture.md](docs/adr/0001-free-tier-architecture.md)
(why the collector lives outside Databricks), [docs/budget.md](docs/budget.md) (how it stays at
zero cash), [docs/azure-setup.md](docs/azure-setup.md) (the stack and the lessons from deploying
it), [docs/runbook.md](docs/runbook.md) (alerts, queries, failures) and
[docs/data-sources.md](docs/data-sources.md) (licences).

## Development
```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # offline
pytest -m live              # hits the real feeds
ruff check . && ruff format . && mypy
scripts/smoke_function.sh   # the deployable package in the Functions image (Docker, ~3 min)
```

Data: VBB (CC BY 4.0), gtfs.de (CC BY-SA 4.0), Deutscher Wetterdienst. Code: MIT.
