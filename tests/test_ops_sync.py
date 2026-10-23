from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pyarrow.parquet as pq

from transitpulse.lake import LocalLake
from transitpulse.ops_sync import rows_from_query, write_windows


def _summary(run_id: str, **kw: object) -> str:
    base = {
        "run_id": run_id,
        "feed": "vbb",
        "status": "ok",
        "http_status": 200,
        "fetch_ms": 500.0,
        "feed_ts": "2026-10-23T10:00:30+00:00",
        "feed_age_s": 12.0,
        "n_stop_times": 120000,
        "n_written_stop_times": 800,
        "n_trips_gone": 20,
        "reduction": 0.993,
        "bytes_written": 12000,
        "state_bytes": 600000,
        "total_ms": 1800.0,
        "lake": "azure:... + volume:...",
        "error": None,
    }
    base.update(kw)
    return json.dumps(base)


RECORDS = [
    {
        "req_id": "r1",
        "started_at": "2026-10-23T10:00:00Z",
        "success": True,
        "duration_ms": 1900.0,
        "summary": _summary("a1"),
    },
    {
        "req_id": "r2",
        "started_at": "2026-10-23T10:01:00Z",
        "success": False,
        "duration_ms": 25.0,
        "summary": None,
    },
    {
        "req_id": "r3",
        "started_at": datetime(2026, 10, 23, 11, 0, tzinfo=UTC),
        "success": True,
        "duration_ms": 300.0,
        "summary": _summary("a3", status="not_modified", http_status=304, n_written_stop_times=0),
    },
]


def test_rows_from_query_merges_summary_or_falls_back_to_request_id() -> None:
    rows = rows_from_query(RECORDS)
    assert [r["run_id"] for r in rows] == ["a1", "r2", "a3"]
    assert rows[0]["feed_ts"] == datetime(2026, 10, 23, 10, 0, 30, tzinfo=UTC)
    assert rows[1]["status"] is None and rows[1]["success"] is False
    assert rows[2]["http_status"] == 304 and rows[2]["started_at"].tzinfo is not None


def test_write_windows_one_file_per_hour_idempotent(tmp_path: Path) -> None:
    lake = LocalLake(tmp_path)
    res = write_windows(rows_from_query(RECORDS), lake)
    assert res.windows == 2 and res.rows == 3 and res.bytes_written > 0
    files = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.parquet"))
    assert files == [
        "raw/collector_runs/date=2026-10-23/hour=10/runs_1792749600.parquet",
        "raw/collector_runs/date=2026-10-23/hour=11/runs_1792753200.parquet",
    ]
    t = pq.read_table(tmp_path / files[0])
    assert t.num_rows == 2 and str(t.schema.field("started_at").type) == "timestamp[us, tz=UTC]"
    write_windows(rows_from_query(RECORDS), lake)  # same windows again: still two files
    assert len(list(tmp_path.rglob("*.parquet"))) == 2


def test_write_windows_empty(tmp_path: Path) -> None:
    res = write_windows([], LocalLake(tmp_path))
    assert res.windows == 0 and res.first is None
