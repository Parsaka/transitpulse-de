# Budget: zero cash, at most 2 EUR per month from the student credit

| Component | Service | Expected monthly cost | Why it stays free |
|---|---|---|---|
| Lakehouse, pipelines, SQL, dashboards, alerts, MLflow | Databricks Free Edition | 0 | Free forever, serverless only |
| Collector every 60 s | Azure Functions, Consumption plan | 0 | 1M executions and 400k GB-s free per month; we use about 43k executions |
| Raw and state storage | ADLS Gen2 (Standard LRS, Hot) | about 0.20 EUR | raw retention 7 days keeps it under 10 GB |
| Logs | Log Analytics | 0 | 5 GB per month free |
| Cloud alerts | Azure Monitor, 2 to 3 rules | about 0.30 EUR | email and webhook actions free |
| Dashboards, second alert path | Grafana Cloud Free | 0 | free tier with public dashboards |
| CI, watchdog cron, Pages | GitHub (public repo) | 0 | unlimited Actions minutes for public repos |
| Data | VBB, gtfs.de, DWD | 0 | open licences |
| Tier B, once | Azure Databricks trial + Event Hubs, 14 days | 10 to 15 USD from the credit, once | destroyed afterwards |

Guardrails: an Azure budget alert at 2 EUR per month (Terraform), raw retention policy, and the
monthly measured figure recorded in `docs/cost.md`. Measured numbers replace the expectations
above as soon as they exist.
