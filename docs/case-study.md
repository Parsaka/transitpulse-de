# Case study: TransitPulse DE

*A zero-cost, production-shaped streaming data platform for German public transport, built in
eight phases between 2026-10-22 and 2026-10-24. Every number below is measured and dated; the
pages it comes from are linked.*

## 1. Why this project exists
A gap analysis of German data-engineering job postings against my CV named one critical gap,
"Monitoring, Logging, Alerting sowie Optimierung von Performance, Stabilität und Kosten", and two
worth improving, dbt and Databricks. GridPulse DE (my first platform project) had a daily batch
rhythm, which cannot show any of that convincingly: nothing breaks fast enough to alert on and
nothing runs often enough to optimise. So the second project had to be *streaming-shaped*, run
continuously, be observable on purpose, and cost nothing: at most 2 EUR per month, student
subscriptions only.

Public transport realtime data fits: GTFS-Realtime feeds change every few seconds, are open
(VBB CC BY 4.0, gtfs.de CC BY-SA 4.0), and produce questions people care about (how punctual,
where do delays grow, does weather matter, what happens next).

## 2. Constraints that shaped the design
| Constraint | Consequence |
|---|---|
| 0 to 2 EUR per month | Azure Functions Consumption (free grant), Databricks Free Edition, GitHub Actions, Grafana Cloud free tier, open data; storage is the only metered cost |
| Databricks Free Edition | single user, serverless only, no catalog creation by API, no SQL statement API, no outbound internet from jobs, 60-second minimum job cadence in practice 15 min; results leave through a JSON file in a Volume |
| GTFS-RT has no ground truth | punctuality is defined on the *last* prediction a feed gave for a stop once its scheduled time is older than a settle window; cancelled trips and skipped stops are reported separately |
| Two feeds that overlap | VBB is the core feed (precise schedule, one region); gtfs.de is reported per feed and never added to VBB |
| Honest numbers only | README, docs and the website carry only measured, dated values; negative results (a change with no gain, a model worse on two modes) stay in |

## 3. Architecture in one paragraph
An Azure Function polls both feeds every 60 s with ETag, parses the protobuf, fingerprints each
stop-time update and writes only the deltas as zstd Parquet into idempotent lake partitions
(`raw/<dataset>/feed=/date=/hour=/`) and, in parallel, into a Unity Catalog Volume. A Lakeflow
Declarative Pipeline (Auto Loader) builds bronze and silver with expectations every 15 minutes
and keeps the latest state per stop as an AUTO CDC table. dbt builds the gold marts and the SLO
tables on the serverless SQL warehouse every two hours, with slim CI on pull requests. Jobs train
(weekly) and score (every refresh) a LightGBM delay model and run a z-score anomaly check. Logs
and run summaries go to Log Analytics; a status page, Grafana and alerts on three layers read the
results. Azure is Terraform, Databricks is an Asset Bundle, both deployed from GitHub Actions via
OIDC. Diagram: the website page; details: [databricks.md](databricks.md),
[azure-setup.md](azure-setup.md), [dbt.md](dbt.md).

## 4. The phases, each a pull request
| Phase | What landed | Measured |
|---|---|---|
| 0 Collector | fetch, parse, delta store, Parquet, JSON logs, 42 offline tests on trimmed real feeds | VBB 6.3 MB per fetch, 124k stop-time updates; delta store suppresses about 99 % of rows after the first poll |
| 1 Azure | Terraform: lake, Function, Log Analytics, Key Vault, alert, budget, OIDC; smoke test in the official Functions image | two silent deploy failures (protobuf, glibc) caught and fixed |
| 2 Databricks | Volume landing, Lakeflow pipeline, bundle from CI, health snapshot | first pipeline runs; 4.3 M bronze stop-time rows by day three |
| 3 dbt | staging, marts, SLO tables, 34 tests, freshness, slim CI, docs | first prod build 47 nodes in 51 s; punctuality 98.4 % (day) |
| 4 Observability | four SLOs with error budgets, alerts on three layers, status site, Grafana as code, three drills, cost page | feed outage alert 10 min, resolve 44 to 50 min; poison file 2 min; stopped collector 28 min |
| 6 Optimisation | parallel uploads, pandas removed, AUTO CDC, clustering, polling interval | p50 −20 % / p95 −31 %; package −40 %, cold start about −75 %; flow −22 %; no gain; −35 % GB-s at 120 s (rejected) |
| 5 ML + weather | Open-Meteo feed, weather marts, LightGBM with skill gate, forecast log, anomaly detector + SQL alert | MAE 50.6 s vs naive 52.3 s (skill 3.3 %); bus dry 96.9 % vs light rain 96.0 % punctual |
| 8 Scale + publish | gtfs.de nationwide feed, per-feed mart, website page with live status, this case study, CV wording | first nationwide poll 412,352 rows in 6.2 s, about 95 % suppressed one minute later |

Phase 7 (Azure Databricks Premium, Event Hubs, Structured Streaming, DBU cost from system
tables) is designed in the roadmap and deliberately not run: it costs student credit.

## 5. Observability, the critical gap
**Signals.** Every collector step logs JSON with durations; every run ends with a summary line
(feed, HTTP status, rows written, trips gone, reduction, total ms, error). Log Analytics keeps
them; a Kusto query in the runbook turns them into a table. The pipeline writes its event log to
a table and a health snapshot to a JSON file; `ops-sync` copies the collector executions from Log
Analytics into the lakehouse so SLOs can be computed where the data is.

**SLOs with error budgets** ([observability.md](observability.md)): silver freshness (95 % of
updates within 20 min), pipeline success (99 %), collector success (99.5 %), data quality (at
most 1 % expectation failures in 7 days). `slo_error_budget` shows events, bad events and budget
left; the status page shows it in red when a budget is gone. Two budgets were blown by the
bootstrap days and stayed red on purpose: that is what a budget is for.

**Alerts on three layers.** Azure Monitor scheduled-query rule (no successful execution or 3+
failures in 15 min), Databricks (job failure mail, SQL alert on `network_anomalies`), GitHub
Actions (dbt test or freshness failure). The alert e-mail address must be verified once by the
owner; the drills showed the rule firing, the mail is the open step.

**Drills** ([drills.md](drills.md)): each incident was caused on purpose and timed from logs.
Feed outage: alert 10 minutes after the first failed execution, resolved 44 to 50 minutes after
the first good one. Poison file: pipeline failed after 2 minutes; `ignoreMissingFiles` and an
explicit schema made the pipeline survive the fix. Stopped collector: 28 minutes to alert, because
the rule needs two empty evaluations; documented as the price of fewer false alarms.

## 6. Performance, stability and cost, measured
[optimisation.md](optimisation.md) has one before/after table per change, each measured on the
running system over comparable windows: parallel uploads and warm clients (collector p50 −20 %,
p95 −31 %), pandas removed from the Function package (397 to 237 MB, cold start about −75 %),
latest-state table as AUTO CDC instead of a rebuild (flow −22 %), liquid clustering on the marts
(no measurable gain, kept as a negative result), and a 5.5-hour polling experiment at 120 s
(−35 % GB-s) that was rejected because freshness is the product. [cost.md](cost.md): 0.0085 EUR
per day, about 0.17 EUR per month, with the budget alert at 2 EUR.

## 7. dbt and Databricks in production
dbt-databricks on the serverless warehouse with three targets (dev, ci, prod), 51 tests, source
freshness, slim CI deferred to the production manifest kept in the Volume, static docs published
with the status site. Marts: punctuality hourly and daily, network now, delay propagation,
cancellations, weather impact, per-feed coverage; ops models: SLO status, error budgets, pipeline
updates, expectation counts, forecast quality. Databricks: Unity Catalog schemas per layer,
Volume landing, Lakeflow pipeline with explicit schemas and expectations, AUTO CDC, dimensions
from the static schedules, serverless jobs with environments, MLflow experiment and registry, all
as a bundle deployed by CI with a dev and a prod target.

## 8. ML that has to earn its place
The model card is [ml.md](ml.md). The question is practical (how late will this trip be at its
last stop?), the baseline is the obvious one (as late as it is now), the split is time-based, and
the skill gate is in the job: no promotion without beating the baseline on the holdout. Version 1
won by 3.3 % (MAE 50.6 vs 52.3 s), better on S-Bahn and bus, worse on tram and U-Bahn, and the
page says exactly that. Predictions are logged forward with what was known at the time and scored
later against outcomes by `mart_forecast_quality`, so the number to quote will be the production
one, not the holdout.

## 9. What went wrong and what it taught
- Two silent zero-function deploys (protobuf clash, glibc) → a smoke test in the official image.
- GitHub cron up to 3 h 50 min late → nothing time-critical on GitHub schedules; the source it
  feeds is warn-only in freshness.
- Open-Meteo 503 on the full hour on the first scheduled fetch → retries with backoff, tested.
- Free Edition limits → health through a JSON file, catalog via UI, explicit schemas.
- `__file__` undefined in Python file tasks → shared code located through a job parameter.
- A false "stale" freshness error caused by the cron, not the collector → severity by cause.

## 10. Outcome and what stays open
A running, public platform where each claim from the gap analysis points to a measured number.
Open, by design or by owner action: the alert e-mail verification, the Grafana Cloud sign-up (the
dashboard and script are ready), making the repository public (then GitHub Pages for the dbt
docs), Tier B (phase 7) with student credit, and more weeks of data for the model.

Links: [README](../README.md) · [roadmap](roadmap.md) · [runbook](runbook.md) ·
status page https://sttransitpulsedev3dkkh.z1.web.core.windows.net/
