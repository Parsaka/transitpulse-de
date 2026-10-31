# Cost (measured)

Budget rule: zero cash, at most 2 per month from the Azure for Students credit (`docs/budget.md`).
Figures below come from Azure Cost Management and Azure Monitor metrics, not from estimates.

## Azure, resource group `rg-transitpulse-dev`, month to date (2026-10-22 22:00 to 2026-10-23 10:00 UTC)
| Service | Cost (EUR) | Note |
|---|---|---|
| Storage | 0.0055 | lake + Function host account; deltas ~15 MB/day |
| Azure Monitor | 0.0028 | the scheduled-query alert rule |
| Key Vault | 0.0002 | secret reads by the Function |
| Functions | 0.0000 | 1,440 executions/day, inside the free grant |
| App Service, Log Analytics, Bandwidth | 0.0000 | inside the free tiers |
| **Total** | **0.0085** | about **0.17 EUR per month** at this rate |

Function consumption (metric `FunctionExecutionUnits`, 24 h to 2026-10-23 10:00 UTC):
(before the nationwide feed; with gtfs.de on its own 5-minute timer the estimate is about 7,200 GB-s per day, 55 % of the grant, docs/scale.md)
1,795,925,888 MB-ms per day = about **1,750 GB-s per day**, about 52,600 GB-s per month =
**13 % of the free grant** (400,000 GB-s). Execution count about 1,440 per day = 0.14 % of the
free 1 M. Run duration is the lever: p50 4.2 s with the Volume upload versus 1.9 s before it
(phase 6 looks at that).

## Databricks Free Edition
No charge. Serverless compute for the pipeline every 15 minutes (about 3 minutes of serverless
per run) and the SQL warehouse for the hourly dbt build (about 1 minute). Quotas, not money.

## GitHub
Private repository on the Free plan: Actions minutes are capped (2,000 per month). Current use:
CI on pushes and pull requests plus the hourly dbt job (about 4 minutes each = about 2,900 min/
month if every hour ran, so the hourly job alone can exceed the cap). Two ways out: make the
repository public (minutes become unlimited) or run dbt every two hours. The usage is visible in
Settings > Billing; measured figures replace this note at the end of the first full month.

**Measured, October 2026: the cap was hit.** From 2026-10-27 every workflow was refused with "The
job was not started because … your spending limit needs to be increased" (dbt, Static GTFS weekly).
Cause: while the SQL warehouse was unavailable (Free Edition daily limit, 2026-10-24 to 10-27) each
dbt run waited 15 minutes on connector retries instead of 3 to 4. Fix: `timeout-minutes` on both
dbt jobs (12 prod, 10 slim CI). The lasting fix is a public repository (unlimited minutes).

## Grafana Cloud
Free tier (10k series, 50 GB logs, 14-day retention); the dashboard reads `status.json` from the
Azure static website and Azure Monitor through a read-only identity. No cost.

## How to re-measure
```bash
az rest --method post --url "https://management.azure.com/subscriptions/<sub>/resourceGroups/rg-transitpulse-dev/providers/Microsoft.CostManagement/query?api-version=2023-11-01" \
  --body '{"type":"ActualCost","timeframe":"MonthToDate","dataset":{"granularity":"None","aggregation":{"totalCost":{"name":"Cost","function":"Sum"}},"grouping":[{"type":"Dimension","name":"ServiceName"}]}}'
az monitor metrics list --resource <function app id> --metric FunctionExecutionUnits,FunctionExecutionCount --interval PT1H --offset 24h --aggregation Total
```
