# Runbook

## Where things are
- Collector: Azure Function `collect` (timer, app setting `TP_SCHEDULE`), logs in Application
  Insights `appi-transitpulse-dev` (`traces` for the JSON lines, `requests` for executions).
- Lake: storage account from `terraform output lake_storage_account`, container `lake`:
  `raw/<dataset>/feed=<feed>/date=/hour=/` and `state/<feed>.parquet`.
- Alerts: `alert-transitpulse-dev-collector-unhealthy` (email), budget alerts (email).

## Alerts
| Alert | Condition | First action |
|---|---|---|
| collector-unhealthy | no successful `collect` execution in 15 min, or 3+ failures | Query below; check the feed provider status page (VBB posts outages on its Atom feed) |
| budget 50/90/100 % | spend in the resource group | Cost analysis blade; the usual suspect is log ingestion above the free 5 GB |

Useful queries (Application Insights, Logs):
```kusto
// last run summaries
traces | where message startswith "{" | extend d = parse_json(message)
| where isnotempty(d.summary) | project timestamp, s = d.summary
| project timestamp, status = s.status, feed = s.feed, http = s.http_status, rows = s.n_written_stop_times,
          gone = s.n_trips_gone, reduction = s.reduction, ms = s.total_ms, err = s.error
| order by timestamp desc | take 20

// executions and failures per 15 min
requests | where name == "collect" | summarize ok = countif(success), failed = countif(not success) by bin(timestamp, 15m)
```

## Common failures
| Symptom | Cause | Fix |
|---|---|---|
| `FeedFetchError: ... HTTP 404/403` | provider changed the URL or blocked the User-Agent | check `docs/data-sources.md`, update `feeds.py`, redeploy |
| `AuthorizationPermissionMismatch` writing the lake | role assignment missing or not yet propagated | `terraform apply`; wait up to 10 min |
| runs succeed but `n_written_stop_times` is 0 for a long time | feed frozen upstream (header timestamp not advancing: `feed_age_s` grows) | nothing to fix locally; note it in the data log |
| state blob grows past a few MB | gone-trip cleanup not running (feed stopped sending trips) | inspect `state/<feed>.parquet` kinds; delete it to reset (one full snapshot follows) |

## Reset the delta state
Delete `state/<feed>.parquet` in the lake. The next run writes a full snapshot (about 700 KB)
and continues with deltas. No data is lost: raw files are never rewritten.

## Local run against the real lake
```bash
az login
TP_LAKE_BACKEND=azure TP_ADLS_ACCOUNT_URL=$(cd infra && terraform output -raw lake_blob_url) \
  transitpulse collect --feed vbb --once
```
Your user needs `Storage Blob Data Contributor` on the lake account (`admin_principal_id` has it).
