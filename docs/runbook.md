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
| transitpulse-network-anomaly (Databricks SQL alert) | a 30-minute window flagged `is_anomaly` in `tp_ops.network_anomalies` | `select * from workspace.tp_ops.network_anomalies order by checked_at desc limit 5`; compare with `mart_network_now` and the VBB disruption notices; a data problem (duplicate events, late static dimensions) shows as an `events` count far above the usual |
| transitpulse-train-prod failed | weekly training error, or "model not promoted" (skill gate) | the run output prints MAE versus naive; a non-promotion keeps the previous champion, nothing to do unless it repeats |

Useful queries (Log Analytics workspace `log-transitpulse-dev`; the Application Insights blade may lag):
```kusto
// last run summaries
AppTraces | where Message startswith "{" | extend d = parse_json(Message)
| where isnotempty(d.summary) | extend s = d.summary
| project TimeGenerated, status = s.status, feed = s.feed, http = s.http_status, rows = s.n_written_stop_times,
          gone = s.n_trips_gone, reduction = s.reduction, ms = s.total_ms, err = s.error
| order by TimeGenerated desc | take 20

// executions and failures per 15 min
AppRequests | where Name == "collect" | summarize ok = countif(Success), failed = countif(not Success) by bin(TimeGenerated, 15m)

// the Python error of a failed execution
AppExceptions | order by TimeGenerated desc | take 1 | project TimeGenerated, InnermostMessage
```

## Common failures
| Symptom | Cause | Fix |
|---|---|---|
| deployed, `az functionapp function list` empty, nothing in logs | the Python worker could not import `function_app.py` (dependency clash, missing module) | run `scripts/smoke_function.sh`; it prints the worker's Python error |
| executions fail in a few ms with `ImportError ... GLIBC` | wheels built on a newer glibc than the host image | build inside the Functions image (deploy workflow does) |
| `FeedFetchError: ... HTTP 404/403` | provider changed the URL or blocked the User-Agent | check `docs/data-sources.md`, update `feeds.py`, redeploy |
| `AuthorizationPermissionMismatch` writing the lake | role assignment missing or not yet propagated | `terraform apply`; wait up to 10 min |
| runs succeed but `n_written_stop_times` is 0 for a long time | feed frozen upstream (header timestamp not advancing: `feed_age_s` grows) | nothing to fix locally; note it in the data log |
| state blob grows past a few MB | gone-trip cleanup not running (feed stopped sending trips) | inspect `state/<feed>.parquet` kinds; delete it to reset (one full snapshot follows) |

## Poison file in the landing Volume (drill 3)
Symptom: pipeline updates fail with `FAILED_READ_FILE` naming a file under `raw/...`; the job
retries up to five times, then stops; the owner gets the job failure mail. Fix: delete the file
(`databricks fs rm dbfs:/Volumes/...` or the Files API) and start an update. Auto Loader skips
the deleted file (`ignoreMissingFiles`); before that option existed every later update failed
with `CloudFileNotFoundException` until a full refresh.

## Azure Monitor emails need a verified address
Azure Monitor sends notifications to an action-group email only after the owner clicks the
verification link in "Action required: Verify your email for Azure Monitor action group". Until
then an alert fires (visible in the portal and the alerts API) but no mail arrives (drill 1).

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

## Databricks
- Workspace `https://dbc-2fb26299-f7ca.cloud.databricks.com`, CLI profile `transitpulse`
  (`databricks auth login --host ... --profile transitpulse`, browser approval).
- Landing Volume `/Volumes/workspace/tp_landing/raw` (`raw/...` deltas, `static/gtfs/...`).
- Pipeline `transitpulse-lakeflow-prod`, job `transitpulse-refresh-prod` every 15 minutes.
  `databricks pipelines start-update <id>` runs it by hand; `list-pipeline-events` shows errors
  and expectation metrics.
- **Token rotation (every 90 days):** `databricks tokens create --lifetime-seconds 7776000`,
  put the value into `infra/terraform.tfvars` (`databricks_token`) and `terraform apply`
  (Key Vault secret + Function restart), then `gh secret set DATABRICKS_TOKEN`. Revoke the old
  token with `databricks tokens delete <id>`.
- **ML:** job `transitpulse-train-prod` trains weekly (Sunday 04:00 Berlin) and registers
  `workspace.tp_ops.delay_model@champion` only if it beats the naive baseline; `score` and
  `anomaly` run after every refresh. `databricks bundle run transitpulse_train -t prod` trains by
  hand. The SQL alert lives in `databricks/alerts/network_anomaly.json` (`alerts-v2 create-alert
  --json @...`). See docs/ml.md.
- Backfill the Volume from the lake (if the Volume was ever emptied): copy `raw/` blobs with
  `BlobLake.get` -> `VolumeLake.put` (see the phase-2 PR for the one-off script), then
  `transitpulse gtfs-static --feed vbb` for the dimensions.

## dbt
- Hourly prod build in GitHub Actions (`dbt.yml`); a failed run means a test or freshness error:
  open the run, the failing node is named. Rebuild by hand: `dbt build --target prod` with the
  env vars from `docs/dbt.md`.
- Slim CI writes into `tp_gold_ci` / `tp_gold_ci_ops`; drop them when they get in the way
  (`databricks schemas delete workspace.tp_gold_ci --force`).
- `slo_status` shows the three SLOs; `slo_pipeline_updates` lists every pipeline update with its
  state and duration, `slo_expectations_daily` the expectation counts per day.
