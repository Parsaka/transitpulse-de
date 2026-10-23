"""Collector measurements for a time window, from Log Analytics (the ground truth of phase 6).

Prints p50/p95 of every step (load_state, fetch, parse, delta, write) and of the whole run, the
rows and bytes written per run, the delta reduction, and the executions per hour. Used before and
after every optimisation so the tables in docs/optimisation.md are reproducible.

Usage:
  python scripts/measure_collector.py --start 2026-10-23T13:00Z --end 2026-10-23T16:00Z [--label baseline]
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import timedelta

from azure.identity import DefaultAzureCredential
from azure.monitor.query import LogsQueryClient, LogsQueryStatus

WORKSPACE = os.environ.get("TP_LOG_ANALYTICS_WORKSPACE_ID", "241c5e3c-67eb-45f2-851d-684280529bd4")

STEPS = """
AppTraces
| where TimeGenerated between (datetime({start}) .. datetime({end}))
| where Message startswith "{{"
| extend d = parse_json(Message)
| where isnotempty(d.step)
| summarize p50 = round(percentile(todouble(d.duration_ms), 50), 0),
            p95 = round(percentile(todouble(d.duration_ms), 95), 0), n = count() by step = tostring(d.step)
| order by step asc
"""

RUNS = """
AppTraces
| where TimeGenerated between (datetime({start}) .. datetime({end}))
| where Message startswith "{{"
| extend d = parse_json(Message)
| where isnotempty(d.summary)
| extend s = d.summary
| where tostring(s.status) == "ok"
| summarize runs = count(),
            total_p50 = round(percentile(todouble(s.total_ms), 50), 0),
            total_p95 = round(percentile(todouble(s.total_ms), 95), 0),
            rows_per_run = round(avg(todouble(s.n_written_stop_times)), 0),
            bytes_per_run = round(avg(todouble(s.bytes_written)), 0),
            reduction = round(avg(todouble(s.reduction)), 4),
            feed_age_p50 = round(percentile(todouble(s.feed_age_s), 50), 1)
"""

REQUESTS = """
AppRequests
| where Name == "collect" and TimeGenerated between (datetime({start}) .. datetime({end}))
| summarize executions = count(), failed = countif(Success == false),
            dur_p50 = round(percentile(DurationMs, 50), 0), dur_p95 = round(percentile(DurationMs, 95), 0),
            dur_max = round(max(DurationMs), 0), hours = round(todouble(datetime_diff('second', max(TimeGenerated), min(TimeGenerated))) / 3600.0, 2)
"""


def query(client: LogsQueryClient, kql: str) -> list[dict]:
    res = client.query_workspace(WORKSPACE, kql, timespan=timedelta(days=7))
    if res.status != LogsQueryStatus.SUCCESS:
        raise SystemExit(f"query failed: {res.partial_error}")
    t = res.tables[0]
    return [dict(zip(t.columns, row, strict=True)) for row in t.rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    client = LogsQueryClient(DefaultAzureCredential(exclude_interactive_browser_credential=True))
    fmt = {"start": a.start, "end": a.end}
    out = {
        "label": a.label,
        "window": [a.start, a.end],
        "steps": {
            r["step"]: {"p50_ms": r["p50"], "p95_ms": r["p95"], "n": r["n"]}
            for r in query(client, STEPS.format(**fmt))
        },
        "runs": query(client, RUNS.format(**fmt))[0],
        "requests": query(client, REQUESTS.format(**fmt))[0],
    }
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
