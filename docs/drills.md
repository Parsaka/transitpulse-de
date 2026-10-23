# Incident drills

Three failures injected on purpose into the running system, each with the measured timeline from
injection to detection to recovery. Times are UTC, read from Log Analytics, the Azure alerts API,
the pipeline event log and the mailbox that receives the alerts. Nothing here is simulated, and
what did not work is written down too.

The Azure alert under test is `collector-unhealthy`: a scheduled-query rule evaluated every
15 minutes over a 15-minute window, firing when no execution succeeded or at least three failed.
Its worst-case detection latency is therefore about 15 minutes plus log ingestion.

## Drill 1: feed outage (2026-10-23)
Injection: the Function's `TP_FEED_URLS` app setting points the VBB feed at a URL that answers
404. The collector does not retry a 404 (it will not fix itself), so every execution fails fast.

| Time | Event |
|---|---|
| 10:28:10 | App setting applied; the Function host restarts |
| 10:28–10:30 | Three more executions still succeed (the old host finished its runs) |
| 10:32:15 | First failed execution (`FeedFetchError: GET ... -> HTTP 404`, 400 ms) |
| 10:42:18 | Alert **fired** (Sev1), 10 min after the first failure, 14 min after injection |
| 10:42 | **No email arrived.** The action-group address had never been verified (Azure Monitor sends a verification mail first; it was in the inbox since 2026-10-22 22:12, unanswered). The alert exists in the portal and the alerts API only. |
| 10:51:31 | Fix: app setting removed; host restarts |
| 10:53:00 | Last failed execution |
| 10:55:00 | First successful execution after the fix (about 3.5 min of restart) |
| 11:43:14 | Alert **auto-resolved**, 50 min after the last failed execution and 48 min after the first good one (Azure resolves a log alert only after several clean evaluations; the same lag, 50 min, was seen on the real incident of 2026-10-22, fired 22:27, resolved 00:43) |

Findings: detection latency is set by the rule cadence, not by the pipeline (fine for a
15-minute SLO). Early request telemetry showed `Success = true` for failing executions for about
a minute before the final rows arrived; the collector's own run summary (`status: error`) is the
more reliable signal, and `ops-sync` now prefers it. The missing email is the one real gap:
verifying the address is a one-click action that only the owner can do.

## Drill 3: poison file in the landing Volume (2026-10-23)
Injection: a text file uploaded as `raw/stop_times/.../poison.parquet` through the Files API,
then a pipeline update.

| Time | Event |
|---|---|
| 10:36:26 | Poison file uploaded |
| 10:36:28 | Pipeline update started |
| 10:38:41 | Update **failed**: `FAILED_READ_FILE ... poison.parquet` (2 min 15 s; the error names the file) |
| 10:38–10:47 | Four automatic retries, each failing within 1.5 to 3 minutes |
| 10:50:42 | Fix attempt 1: file deleted |
| 10:55:24 | Manual update started |
| 10:58:11 | Update failed again: `CloudFileNotFoundException` for the deleted file. Auto Loader had already listed it and insisted on reading it. |
| 10:59 | Fix 2: `ignoreMissingFiles=true` added to the Auto Loader stream, bundle deployed |
| 11:00:00 | Automatic retry started |
| 11:02:56 | Update **completed**; silver fresh again. Total time degraded: 26.5 minutes, of which 9 were spent on the wrong fix. |

Findings: the pipeline's own retries are a liability with a poison file (five identical failures),
so the job now mails the owner on failure (bundle, prod target). Deleting a listed file needs
`ignoreMissingFiles`, which is now in the pipeline; corrupt files still fail loudly on purpose.

## Drill 2: collector stopped
Injection: `az functionapp stop`. No executions at all: the "no success in 15 minutes" branch of
the rule.

| Time | Event |
|---|---|
| 11:44:03 | `az functionapp stop`; the running host still completed three executions (last at 11:45:59), then silence |
| 12:12:11 | Alert **fired**, 28 min after the stop: the rule needs a full 15-minute window without a success, and then its next evaluation |
| 12:13:20 | Fix: `az functionapp start` |
| 12:14:15 | First successful execution after the start (the timer catches up at the next minute; the delta store simply continues, the 28 missed minutes are a gap in the raw data, nothing is corrupted) |
| 12:58:11 | Alert **auto-resolved**, 44 min after the first good execution (same lag as drill 1) |

Findings: a dead collector is detected within 15 to 30 minutes by the Azure rule and, independently,
by the silver freshness SLO (`slo_status.freshness_ok`) at the next pipeline refresh and by the
dbt source freshness check in the next scheduled build. The gap in the lake is visible in
`slo_collector_daily` (runs per day below 1,440).
