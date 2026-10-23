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
- [ ] **Phase 3 – dbt gold**: punctuality, delay propagation, cancellations, weather impact, SLO
  tables; tests, source freshness, docs on GitHub Pages, slim CI on PRs.
- [ ] **Phase 4 – Observability**: three SLOs with error budget, five alerts (Azure Monitor,
  Databricks SQL Alert, expectations, job failure, GitHub watchdog), Grafana Cloud public dashboard,
  three documented incident drills, cost page.
- [ ] **Phase 5 – ML**: LightGBM delay-at-destination model with forward-looking forecast log,
  MLflow registry in Unity Catalog, network anomaly detector that raises an alert.
- [ ] **Phase 6 – Measured optimisation**: snapshot vs delta, 60 s vs 120 s polling, OPTIMIZE and
  liquid clustering, Photon and cluster size (Tier B), each with a before/after table.
- [ ] **Phase 7 – Tier B (two weeks, student credit)**: Azure Databricks Premium via Terraform,
  Event Hubs (Kafka endpoint) → Structured Streaming, DBU cost from system tables, then destroy.
- [ ] **Phase 8 – Scale and publish**: gtfs.de nationwide feed, website page with live status,
  case study, architecture diagram, CV wording (EN/DE).
