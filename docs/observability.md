# Observability: SLOs, error budgets, alerts, status site, Grafana

## Signals and where they live
| Layer | Signal | Where |
|---|---|---|
| Collector (Azure Function) | executions, duration, failures, JSON run summaries (per-step ms, rows, delta reduction, feed age) | Application Insights / Log Analytics (`AppRequests`, `AppTraces`, `AppExceptions`) |
| Collector in the lakehouse | the same executions, synced hourly by `transitpulse ops-sync` | `tp_silver.silver_collector_runs` |
| Pipeline | update states, flow metrics, expectation pass/fail | `tp_ops.lakeflow_event_log` (published event log), `ops/health.json` |
| Gold | punctuality, delays, cancellations | `tp_gold.*` (dbt, hourly) |
| SLOs | one row per SLO with error budget | `tp_ops.slo_error_budget`, `tp_ops.slo_status` |
| Public | `status.json`, status page, dbt docs | Azure static website (free): https://sttransitpulsedev3dkkh.z1.web.core.windows.net/ |

## The four SLOs
| SLO | Objective | Window | Bad event |
|---|---|---|---|
| collector | 99.5 % of collector executions succeed | 30 d | an execution whose run summary is not `ok`/`not_modified` (or, without a summary, a failed request) |
| pipeline | 99 % of pipeline updates succeed | 30 d | an update ending FAILED/CANCELED |
| freshness | 95 % of pipeline updates finish with silver at most 20 min behind the collector | 30 d | an update whose newest collected `feed_ts` is older than 20 min at its end |
| quality | 99 % of records pass the warning expectations | 7 d | a record failing a warning expectation |

`budget_remaining = 1 - bad / ((1 - target) * total)`; below zero the SLO is breached. On
2026-10-23 the collector and pipeline budgets were both negative because of the day-one incidents
(35 glibc failures, 10 empty-folder failures); they recover as the 30-day window moves on. That
is intended: the table shows what happened, not what should have happened.

## Alerts
| Alert | Where | Condition | Delivery |
|---|---|---|---|
| collector-unhealthy | Azure Monitor scheduled-query rule, every 15 min over 15 min | no successful execution, or 3+ failed | email action group (address must be verified once; see docs/drills.md) |
| job failure | Databricks job `transitpulse-refresh-prod` | pipeline or health task failed | email to the owner |
| dbt build / freshness | GitHub Actions `dbt.yml` | test failure or source freshness error | GitHub failure mail to the owner |
| budget 50/90/100 % | Azure Cost Management | spend in the resource group | email |

Measured latencies (docs/drills.md): a feed outage fires the Azure alert 10 minutes after the
first failed execution; a poison file fails the pipeline update after 2 minutes; the Azure alert
resolves about three evaluation periods after the last failure.

## Status site
The hourly workflow publishes `status.json` (SLOs, error budgets, network now, daily punctuality,
collector days, recent updates) with `scripts/publish_status.py`, the page `site/index.html` and
the dbt docs to the `$web` container of the lake storage account. Cost: storage only.

## Grafana Cloud (free tier)
Only the sign-up is manual (Grafana does not offer an API for that). Then:
1. Create a service account with the Admin role and a token (Administration > Users and access
   > Service accounts).
2. Install the plugin "Infinity" (yesoreyeram-infinity-datasource) from the catalog, one click.
3. Run, with the values from `terraform output` (the client secret is a sensitive output):
   ```bash
   export GRAFANA_URL=https://<stack>.grafana.net GRAFANA_TOKEN=...
   export AZURE_TENANT_ID=... AZURE_SUBSCRIPTION_ID=...
   export GRAFANA_AZURE_CLIENT_ID=$(terraform -chdir=infra output -raw grafana_client_id)
   export GRAFANA_AZURE_CLIENT_SECRET=$(terraform -chdir=infra output -raw grafana_client_secret)
   export LOG_ANALYTICS_RESOURCE_ID=/subscriptions/<sub>/resourceGroups/rg-transitpulse-dev/providers/Microsoft.OperationalInsights/workspaces/log-transitpulse-dev
   export STATUS_URL=https://sttransitpulsedev3dkkh.z1.web.core.windows.net
   python scripts/grafana_provision.py
   ```
   The script creates the two data sources (Azure Monitor with the read-only identity; Infinity
   for `status.json`), the dashboard from `grafana/dashboard.json`, and a public dashboard link.
   The Azure identity has only Log Analytics Reader and Monitoring Reader; its secret rotates
   every 180 days through Terraform.
