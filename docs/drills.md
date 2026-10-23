# Incident drills

Three failures injected on purpose into the running system, each with the measured timeline from
injection to alert to recovery. Times are UTC, read from Log Analytics, the Azure alerts API,
the pipeline event log and the mailbox that receives the alerts. Nothing here is simulated.

The alert under test is `collector-unhealthy` (Azure Monitor scheduled-query rule, evaluated
every 15 minutes over a 15-minute window: fires when no execution succeeded or at least three
failed). Its worst-case detection latency is therefore about 15 minutes plus log ingestion.

## Drill 1: feed outage (2026-10-23)
Injection: the Function's `TP_FEED_URLS` app setting points the VBB feed at a URL that answers
404. The collector does not retry a 404 (it will not fix itself), so every execution fails fast.

| Time | Event |
|---|---|
| (filled in below) | |

## Drill 2: collector stopped
Injection: `az functionapp stop`. No executions at all: the "no success in 15 minutes" branch of
the rule.

| Time | Event |
|---|---|
| (filled in below) | |

## Drill 3: poison file in the landing Volume
Injection: a file that is not Parquet, uploaded as `raw/stop_times/.../poison.parquet`. Auto
Loader fails the pipeline update; the job fails; the next refresh is blocked until the file is
removed.

| Time | Event |
|---|---|
| (filled in below) | |
