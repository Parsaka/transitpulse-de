# dbt gold layer (dbt-databricks on the serverless SQL warehouse)

Project `dbt/`, adapter `dbt-databricks`, warehouse `Serverless Starter Warehouse` (2X-Small) of
the Free Edition workspace. Credentials come only from `DATABRICKS_HOST` and `DATABRICKS_TOKEN`.
Targets: `dev` (schema `tp_gold_dev`), `ci` (`tp_gold_ci`, pull requests), `prod` (`tp_gold`;
ops models in `tp_ops` next to the pipeline event log).

```
sources: tp_silver.silver_* , dim_*            tp_ops.lakeflow_event_log
            │                                        │
   stg_stop_events (view)  stg_trips (view)          │
            │                   │                    │
   mart_punctuality_hourly ─▶ mart_punctuality_daily │
   mart_network_now         mart_delay_propagation   slo_pipeline_updates
                            mart_cancellations_daily slo_expectations_daily
                                                     slo_status (one row, three SLOs)
seed: route_type_modes (VBB extended route types -> mode)
```

## Definitions
- **Stop event**: the last prediction the feed gave for (trip, service date, stop). It counts as
  *observed* once its scheduled time is older than the settle window (20 min), so the prediction
  is as final as GTFS-RT gets. Cancelled trips and skipped stops are excluded from punctuality
  and reported on their own.
- **Punctuality**: share of observed, scored stop events with a delay below 6 minutes (the
  Deutsche Bahn definition for regional traffic, `late_threshold_s = 360`).
- **Delay propagation**: delay at the first versus the last observed stop of completed trips
  (trips that left the feed); "grew" and "recovered" mean a change of more than two minutes.
- **SLOs** (`slo_status`): freshness of silver at most 20 minutes; at least 99 % of pipeline
  updates succeeded in 30 days; at most 1 % of records failed a warning expectation in 7 days.
- **Weather impact** (`mart_weather_impact_hourly`): punctuality and average delay per hour,
  mode and nearest Open-Meteo grid point (`dim_stop_weather_point`, haversine), with the hour's
  precipitation class (dry / light rain / rain / snow) and a "windy" flag (gusts above 50 km/h).
- **Forecast quality** (`mart_forecast_quality`, docs/ml.md): the earliest in-flight prediction
  per trip against the delay the trip ended with, per day, mode and model version, next to the
  naive forecast made at the same moment. Skill = 1 − MAE(model)/MAE(naive).

## Tests
41 data tests: uniqueness of every grain (`dbt_utils.unique_combination_of_columns`), ranges
(punctuality and rates in [0, 1], counts at least 1), accepted modes, not-null keys on the
dimensions, plus two singular tests: at least 70 % of realtime trips must match the static
schedule (warning only: measured 1.00 for yesterday's service date, 0.66 for today and 0.51 for
tomorrow, since trips of the next schedule version reach the realtime feed before the static zip),
and observed events must lie in the past. Source freshness on the five live sources (warn 30 min,
error 2 h).

## First prod build (2026-10-23 09:48 UTC, about 11 hours of data)
- `dbt build --target prod`: 47 nodes (1 seed, 2 views, 8 tables, 34 tests, 2 exposures) in
  51 s, 45 pass, 0 errors. `dbt source freshness`: 4 of 4 pass.
- Network at 09:30 UTC: 3,306 active trips, punctuality 97.2 % (S-Bahn and U-Bahn 100 %, tram
  99.9 %, bus 96.5 %, regional rail 91.3 %).
- Day 2026-10-23 so far: 456,692 scored stop events, punctuality 98.4 %, 3,815 cancelled stop
  events, 38,982 trips. Worst routes with at least 300 events: bus 980 (Frankfurt/Oder) 75.2 %,
  bus 743 (Dahme-Spreewald) 75.6 %, RE2 80.3 %, RE1 80.8 %.
- Delay propagation (completed trips): buses enter with 0.99 min and leave with 1.50 min of delay
  on average (9.6 % of trips lose more than two minutes); regional rail 2.5 to 2.9 min.
- Cancellations: trams 3.6 % of trips seen, buses 0.6 %, U-Bahn 0; 7,182 skipped bus stops.
- SLO status at build time: freshness 17.1 min (the first 15-minute target was breached by the
  refresh cadence itself: the job runs every 15 minutes and takes about 3, so the age oscillates
  between 2 and 18 minutes; target set to 20), pipeline success 37 of 47 updates = 78.7 %
  (**breached**: the ten failed updates are the bootstrap failures on the empty alerts folder,
  see docs/databricks.md; the SLO recovers as updates accumulate), expectation fail rate
  7.2e-5 (588 of 8.16 M records, warning expectations only): quality OK.

## CI and schedule (`.github/workflows/dbt.yml`)
- Pull requests touching `dbt/`: **slim CI**, `dbt build --select state:modified+ --defer
  --state prod-state --favor-state` into `tp_gold_ci`, with the prod manifest fetched from the
  landing Volume (`ops/dbt/manifest.json`); without a manifest it builds everything.
- main and hourly: source freshness, full prod build, `dbt docs generate --static`, manifest
  upload, docs site as a build artifact; GitHub Pages deployment once `PAGES_ENABLED=true`
  (Pages is refused on a private repository with the Free plan, so this waits for the repository
  to go public).
- Why GitHub Actions and not a Databricks dbt task: free minutes, the same workflow for CI and
  schedule, and no extra serverless quota of the Free Edition workspace.

## Local use
```bash
python -m venv .venv-dbt && .venv-dbt/Scripts/pip install "dbt-databricks>=1.10,<1.11"   # own venv: dbt pins protobuf/pathspec
cd dbt && export DATABRICKS_HOST=https://dbc-....cloud.databricks.com DATABRICKS_TOKEN=... DBT_PROFILES_DIR=.
dbt deps && dbt build --target dev && dbt docs generate --static
```
