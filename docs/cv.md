# CV and LinkedIn wording (EN / DE)

Every figure is measured in this repository and dated; see the linked docs before changing a
number. Keep the wording honest: "measured", "first run", "two days of data" are part of it.

## Project entry, CV (EN)
**TransitPulse DE: streaming data platform for German public transport (personal project, 2026)**
Azure Functions · ADLS Gen2 · Terraform · Databricks (Unity Catalog, Lakeflow Declarative
Pipelines, Asset Bundles, MLflow) · dbt · Log Analytics / Azure Monitor · Grafana · GitHub Actions

- Built a zero-cost streaming lakehouse that polls two GTFS-Realtime feeds (Berlin-Brandenburg
  and nationwide, up to 412k stop-time updates per fetch) every 60 s, keeps only deltas (about
  99 % fewer rows) and lands idempotent Parquet partitions in an Azure lake and a Databricks Volume.
- Designed and operated observability from day one: JSON step logs in Log Analytics, four SLOs
  with error budgets computed in the lakehouse, alerts on three layers (Azure Monitor, Databricks,
  GitHub Actions), a public status page and a Grafana dashboard as code.
- Ran three incident drills and measured the reaction times (feed outage alert after 10 min,
  poison file detected after 2 min, stopped collector after 28 min) and fixed what they exposed.
- Optimised with before/after measurements: collector p50 −20 % (parallel uploads, warm clients),
  deployment package −40 % and cold start about −75 % (dependency removal), pipeline flow −22 %
  (AUTO CDC), a polling-interval experiment (−35 % compute, rejected for freshness).
- Modelled the gold layer in dbt on Databricks: 8 marts, SLO tables, 51 tests, source freshness,
  slim CI deferred to the production manifest, two-hourly production builds.
- Put a LightGBM delay-at-destination model into production behind a skill gate against the naive
  baseline (first run: MAE 50.6 s vs 52.3 s), with MLflow and the Unity Catalog registry, weekly
  retraining, a forward-looking forecast log scored against outcomes and a z-score anomaly alert.
- Total running cost 0.17 EUR per month, measured; infrastructure as code with Terraform and
  bundles, CI/CD via GitHub OIDC, eight phases in small pull requests.

## Projekteintrag, Lebenslauf (DE)
**TransitPulse DE: Streaming-Datenplattform für den deutschen ÖPNV (eigenes Projekt, 2026)**
Azure Functions · ADLS Gen2 · Terraform · Databricks (Unity Catalog, Lakeflow Declarative
Pipelines, Asset Bundles, MLflow) · dbt · Log Analytics / Azure Monitor · Grafana · GitHub Actions

- Kostenloses Streaming-Lakehouse aufgebaut, das zwei GTFS-Realtime-Feeds (Berlin-Brandenburg
  und bundesweit, bis zu 412.000 Halte-Updates pro Abruf) alle 60 s abfragt, nur Deltas behält
  (rund 99 % weniger Zeilen) und idempotente Parquet-Partitionen in einem Azure-Lake und einem
  Databricks-Volume ablegt.
- Monitoring, Logging und Alerting vom ersten Tag an: JSON-Logs pro Schritt in Log Analytics,
  vier SLOs mit Error Budgets im Lakehouse berechnet, Alarme auf drei Ebenen (Azure Monitor,
  Databricks, GitHub Actions), öffentliche Statusseite, Grafana-Dashboard als Code.
- Drei Störfall-Übungen durchgeführt und die Reaktionszeiten gemessen (Feed-Ausfall: Alarm nach
  10 Min, kaputte Datei nach 2 Min erkannt, gestoppter Collector nach 28 Min) und die Befunde
  behoben.
- Performance, Stabilität und Kosten mit Vorher/Nachher-Messungen optimiert: Collector p50 −20 %
  (parallele Uploads, warme Clients), Deployment-Paket −40 % und Kaltstart rund −75 %
  (Abhängigkeit entfernt), Pipeline-Flow −22 % (AUTO CDC), Abfrageintervall-Experiment (−35 %
  Rechenzeit, wegen Aktualität verworfen).
- Gold-Schicht mit dbt auf Databricks modelliert: 8 Marts, SLO-Tabellen, 51 Tests, Source
  Freshness, Slim CI gegen das Produktions-Manifest, zweistündliche Produktions-Builds.
- LightGBM-Verspätungsmodell hinter einem Skill-Gate gegen die naive Baseline in Produktion
  gebracht (erster Lauf: MAE 50,6 s vs. 52,3 s), mit MLflow und Unity-Catalog-Registry,
  wöchentlichem Retraining, vorausschauendem Prognose-Log mit Bewertung gegen die Ergebnisse und
  z-Score-Anomalie-Alarm.
- Gesamte Betriebskosten 0,17 EUR pro Monat, gemessen; Infrastruktur als Code mit Terraform und
  Bundles, CI/CD über GitHub OIDC, acht Phasen in kleinen Pull Requests.

## Short version (two lines, for the skills section or a cover letter)
**EN.** Streaming lakehouse on Azure and Databricks (Terraform, bundles, dbt, MLflow) with four
SLOs, error budgets, alert drills and measured optimisations; 0.17 EUR per month, public status
page, model promoted only when it beats the baseline.

**DE.** Streaming-Lakehouse auf Azure und Databricks (Terraform, Bundles, dbt, MLflow) mit vier
SLOs, Error Budgets, Alarm-Übungen und gemessenen Optimierungen; 0,17 EUR pro Monat, öffentliche
Statusseite, Modell nur befördert, wenn es die Baseline schlägt.

## LinkedIn post (EN)
I built a second data platform to close a specific gap: monitoring, alerting and measured
optimisation. TransitPulse DE polls German public-transport realtime feeds every minute into an
Azure + Databricks lakehouse, models them with dbt, watches itself with four SLOs and error
budgets, and runs a delay model that is only promoted when it beats the naive baseline. Every
optimisation has a before/after table, every alert was rehearsed and timed, and the whole thing
costs 0.17 EUR a month on free tiers. The status page is public, the limits are in the docs.

## Interview talking points (keyword → where the evidence is)
| Keyword in the posting | Say | Show |
|---|---|---|
| Monitoring / Logging / Alerting | SLOs with error budgets, three alert layers, drills with measured latencies | docs/observability.md, docs/drills.md, status page |
| Performance / Stabilität / Kosten | five changes, each with a before/after table, two of them negative results; cost page | docs/optimisation.md, docs/cost.md |
| dbt | 51 tests, freshness, slim CI against the prod manifest, docs | docs/dbt.md, dbt/ |
| Databricks | Lakeflow pipeline, AUTO CDC, Volume landing, bundles from CI, MLflow registry, Free Edition limits and how they were worked around | docs/databricks.md |
| Terraform / CI/CD | OIDC, remote state, Key Vault references, plan in CI, bundle deploy | infra/, .github/workflows/ |
| ML in production | skill gate, forward-looking forecast log, honest 3.3 % | docs/ml.md |
