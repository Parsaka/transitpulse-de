"""Collector run metrics from Log Analytics -> Parquet in the lake and the Volume.

The collector runs in Azure, the SLO tables live in Databricks. Every hour this pulls the
executions (``AppRequests``) and the collector's own run summaries (``AppTraces`` JSON lines) of
the last few hours, joins them per execution, and writes one Parquet file per hour window
(``raw/collector_runs/date=/hour=/runs_<hour_start>.parquet``). Re-running overwrites the same
windows, so overlapping pulls are idempotent and late-arriving telemetry is picked up.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pyarrow as pa

from transitpulse.lake import Lake
from transitpulse.storage import table_to_bytes

log = logging.getLogger(__name__)

RUNS_SCHEMA = pa.schema(
    [
        ("run_id", pa.string()),
        ("started_at", pa.timestamp("us", tz="UTC")),
        ("success", pa.bool_()),
        ("duration_ms", pa.float64()),
        ("feed", pa.string()),
        ("status", pa.string()),
        ("http_status", pa.int32()),
        ("fetch_ms", pa.float64()),
        ("feed_ts", pa.timestamp("us", tz="UTC")),
        ("feed_age_s", pa.float64()),
        ("n_stop_times", pa.int64()),
        ("n_written_stop_times", pa.int64()),
        ("n_trips_gone", pa.int64()),
        ("reduction", pa.float64()),
        ("bytes_written", pa.int64()),
        ("state_bytes", pa.int64()),
        ("total_ms", pa.float64()),
        ("lake", pa.string()),
        ("error", pa.string()),
    ]
)

# One row per execution; the collector's run summary (a JSON log line) shares the execution's
# OperationId, so the two join exactly.
QUERY = """
let reqs = AppRequests
  | where Name == "collect" and TimeGenerated > ago({hours}h)
  | project OperationId, req_id = Id, started_at = TimeGenerated, success = Success,
            duration_ms = DurationMs;
let sums = AppTraces
  | where TimeGenerated > ago({hours}h) and Message startswith "{{"
  | extend d = parse_json(Message)
  | where isnotempty(d.summary)
  | project OperationId, summary = tostring(d.summary);
reqs
| join kind=leftouter sums on OperationId
| project req_id, started_at, success, duration_ms, summary
| order by started_at asc
"""


@dataclass
class SyncResult:
    windows: int
    rows: int
    bytes_written: int
    first: str | None
    last: str | None


def _parse_ts(v: Any) -> datetime | None:
    if not v:
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=UTC)
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


def rows_from_query(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flatten query records (req_id, started_at, success, duration_ms, summary JSON) to rows."""
    out = []
    for r in records:
        s = json.loads(r["summary"]) if r.get("summary") else {}
        out.append(
            {
                "run_id": s.get("run_id") or r["req_id"],
                "started_at": _parse_ts(r["started_at"]),
                "success": bool(r["success"]),
                "duration_ms": float(r["duration_ms"])
                if r.get("duration_ms") is not None
                else None,
                "feed": s.get("feed"),
                "status": s.get("status"),
                "http_status": s.get("http_status"),
                "fetch_ms": s.get("fetch_ms"),
                "feed_ts": _parse_ts(s.get("feed_ts")),
                "feed_age_s": s.get("feed_age_s"),
                "n_stop_times": s.get("n_stop_times"),
                "n_written_stop_times": s.get("n_written_stop_times"),
                "n_trips_gone": s.get("n_trips_gone"),
                "reduction": s.get("reduction"),
                "bytes_written": s.get("bytes_written"),
                "state_bytes": s.get("state_bytes"),
                "total_ms": s.get("total_ms"),
                "lake": s.get("lake"),
                "error": s.get("error"),
            }
        )
    return out


def write_windows(rows: list[dict[str, Any]], lake: Lake) -> SyncResult:
    """Group rows by hour of ``started_at`` and write one Parquet object per hour (overwrite)."""
    by_hour: dict[datetime, list[dict[str, Any]]] = {}
    for r in rows:
        h = r["started_at"].astimezone(UTC).replace(minute=0, second=0, microsecond=0)
        by_hour.setdefault(h, []).append(r)
    total = 0
    for h, hour_rows in sorted(by_hour.items()):
        cols = {f.name: [r.get(f.name) for r in hour_rows] for f in RUNS_SCHEMA}
        data = table_to_bytes(pa.table(cols, schema=RUNS_SCHEMA))
        key = f"raw/collector_runs/date={h:%Y-%m-%d}/hour={h:%H}/runs_{int(h.timestamp())}.parquet"
        lake.put(key, data)
        total += len(data)
    starts = sorted(r["started_at"] for r in rows)
    return SyncResult(
        windows=len(by_hour),
        rows=len(rows),
        bytes_written=total,
        first=starts[0].isoformat() if starts else None,
        last=starts[-1].isoformat() if starts else None,
    )


def fetch_records(workspace_id: str, hours: int, credential: Any = None) -> list[dict[str, Any]]:
    """Run the query against Log Analytics and return plain dict records."""
    from azure.monitor.query import LogsQueryClient, LogsQueryStatus

    if credential is None:
        from azure.identity import DefaultAzureCredential

        credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
    client = LogsQueryClient(credential)
    res = client.query_workspace(
        workspace_id, QUERY.format(hours=hours), timespan=timedelta(hours=hours + 1)
    )
    if res.status != LogsQueryStatus.SUCCESS:
        raise RuntimeError(f"Log Analytics query failed: {res.partial_error}")
    table = res.tables[0]
    return [dict(zip(table.columns, row, strict=True)) for row in table.rows]
