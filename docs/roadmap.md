# Roadmap (about 8 weeks, each phase in small PRs)

- [x] **Phase 0 – Foundation** (2026-10-22): repo, package, GTFS-RT collector (fetch with ETag, parse, delta
  store, Parquet partitions), offline tests on trimmed real feeds, CI (ruff, mypy, pytest). Open: the 11.7 MB JSON delta state needs a compact encoding before it lives in a blob.
- [x] **Phase 1 – Free-tier Azure with Terraform** (2026-10-22): ADLS Gen2 lake, Function App
  (Linux Consumption, Python 3.11, managed identity), Log Analytics + Application Insights, Key
  Vault, action group + scheduled-query alert (collector silent or failing), budget alert at 2,
  GitHub OIDC identity; 27 resources, re-plan clean, CI plans through OIDC. The collector runs every
  60 s in Azure and writes deltas to the lake (verified, see docs/azure-setup.md). Delta state as
  Parquet: 11.7 MB -> 0.65 MB. Smoke test runs the real package in the Functions image in CI.
  Open: provoke the alert on purpose (phase 4 drill); measure GB-seconds against the free grant.
- [x] **Phase 2 – Databricks Free Edition** (2026-10-23): schemas `workspace.tp_*` and the landing
  Volume from a bundle (dev + prod targets), Files API sink in the Function (token in Key Vault),
  static GTFS landed (32 agencies, 1,255 routes, 41,929 stops, 184,416 trips), Lakeflow pipeline
  bronze → silver with expectations plus dim tables, job every 15 min with a health snapshot
  (`ops/health.json`), event log published to `tp_ops`. First full refresh 170 s, 167,625 silver
  rows. Findings in ADR 0002 (catalog only via UI, SQL statement API unavailable, events API
  without details). Open: token rotation in 90 days; bundle deploy from CI runs on the first push
  to main.
- [x] **Phase 3 – dbt gold** (2026-10-23): dbt-databricks on the serverless warehouse; staging
  views, marts (punctuality hourly/daily, network now, delay propagation, cancellations), ops
  models from the pipeline event log and `slo_status` with three SLOs; seed for VBB route types;
  34 tests + 2 singular + source freshness; slim CI on PRs deferred to the prod manifest kept in
  the Volume; hourly prod build; static docs as an artifact (Pages waits for a public repo).
  First prod build 47 nodes in 51 s. Measured: punctuality 98.4 % (day), pipeline SLO breached by
  the bootstrap failures (78.7 %), freshness target calibrated to 20 min. Weather impact moves to
  phase 5 (needs the weather feed, not landed yet).
- [x] **Phase 4 – Observability** (2026-10-23): four SLOs with error budgets in the lakehouse
  (collector executions synced from Log Analytics by `ops-sync`), alerts on three layers (Azure
  Monitor rule, Databricks job failure mail, dbt/freshness via Actions), public status site on
  Azure static website (`status.json`, status page, dbt docs), Grafana dashboard + provisioning
  script (needs the owner's Grafana Cloud sign-up), three incident drills with measured timelines
  (docs/drills.md), cost page with real figures. Verified end to end from CI on 2026-10-23
  12:31 UTC. Open for the owner: Grafana Cloud sign-up (dashboard and script are ready), verified
  alert email. GitHub watchdog moved to phase 8 with the website.
- [x] **Phase 5 – ML and weather** (2026-10-24, docs/ml.md): Open-Meteo hourly weather for nine
  grid points (Function timer, Auto Loader bronze, AUTO CDC silver, 20,304 rows backfilled),
  `dim_stop_weather_point` + `mart_weather_impact_hourly` (bus: dry 96.9 % punctual vs light rain
  96.0 %; S-Bahn 98.3 % vs 91.1 %); LightGBM delay-at-destination model with a time-based holdout
  and a skill gate against the naive "stays as it is" baseline, MLflow + Unity Catalog registry
  (`tp_ops.delay_model@champion`), weekly retraining job; first run MAE 50.6 s vs naive 52.3 s
  (skill 3.3 %, 75k trips, two days of data: honest, small); forward-looking `forecast_log`
  scored by `mart_forecast_quality`; network anomaly detector (z-score per local hour) with a
  Databricks SQL alert; status page shows forecast quality and anomaly checks.
- [x] **Phase 6 – Measured optimisation** (2026-10-23/24, docs/optimisation.md): parallel uploads
  and warm clients (collector p50 −20 %, p95 −31 %), pandas removed (package −40 %, cold start
  about −75 %), latest-state table as AUTO CDC (flow −22 %), mart clustering (no measurable gain,
  recorded), 60 s versus 120 s polling over 5.5 hours (−35 % GB-s, decision: keep 60 s). Photon and
  cluster size wait for Tier B (phase 7).
- [ ] **Phase 7 – Tier B (two weeks, student credit)**: Azure Databricks Premium via Terraform,
  Event Hubs (Kafka endpoint) → Structured Streaming, DBU cost from system tables, then destroy.
- [x] **Phase 8 – Scale and publish** (2026-10-24, docs/scale.md): gtfs.de nationwide feed
  switched on (first cold poll 412,352 rows in 6.2 s, about 95 % suppressed a minute later; the
  pipeline update took 3.7 min instead of 3.4), nationwide static schedule landed daily (1.9 M
  trips, 687k stops), feed-aware dbt joins, `mart_feed_daily`, core marts pinned to VBB; website
  page with live status (parsa-kamali.de, EN/DE, architecture diagram), docs/case-study.md,
  docs/cv.md. Found and recorded: Free Edition's daily compute quota (warehouse refused at 16:25
  UTC, job tasks starved), refresh job now times out after 14 min.
