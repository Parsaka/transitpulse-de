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
- [ ] **Phase 2 – Databricks Free Edition**: Unity Catalog layout, Volume landing via Files API,
  Lakeflow Declarative Pipeline (Auto Loader) bronze → silver with expectations, static GTFS
  dimensions, weekly job; deployed with Databricks Asset Bundles from CI.
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
