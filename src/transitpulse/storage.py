"""Parquet landing zone with idempotent, partitioned file names.

Layout (local or, later, ADLS / Unity Catalog Volume):

    raw/<dataset>/feed=<feed>/date=YYYY-MM-DD/hour=HH/<feed>_<unix_feed_ts>.parquet

The file name is derived from the feed header timestamp, so re-running the collector for the same
feed snapshot overwrites the same file instead of appending a duplicate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from transitpulse.gtfsrt.parse import ALERT_COLUMNS, STOP_TIME_COLUMNS

GONE_COLUMNS = ["feed", "feed_ts", "trip_id", "start_date", "last_seen_ts"]

_SCHEMAS: dict[str, pa.Schema] = {
    "stop_times": pa.schema(
        [
            ("feed", pa.string()),
            ("feed_ts", pa.timestamp("us", tz="UTC")),
            ("entity_id", pa.string()),
            ("trip_id", pa.string()),
            ("route_id", pa.string()),
            ("start_date", pa.string()),
            ("start_time", pa.string()),
            ("direction_id", pa.int32()),
            ("trip_schedule_relationship", pa.int32()),
            ("vehicle_id", pa.string()),
            ("trip_ts", pa.timestamp("us", tz="UTC")),
            ("stop_sequence", pa.int32()),
            ("stop_id", pa.string()),
            ("stop_schedule_relationship", pa.int32()),
            ("arrival_delay_s", pa.int32()),
            ("arrival_time", pa.timestamp("us", tz="UTC")),
            ("departure_delay_s", pa.int32()),
            ("departure_time", pa.timestamp("us", tz="UTC")),
        ]
    ),
    "alerts": pa.schema(
        [
            ("feed", pa.string()),
            ("feed_ts", pa.timestamp("us", tz="UTC")),
            ("entity_id", pa.string()),
            ("cause", pa.int32()),
            ("effect", pa.int32()),
            ("active_from", pa.timestamp("us", tz="UTC")),
            ("active_to", pa.timestamp("us", tz="UTC")),
            ("header_text", pa.string()),
            ("description_text", pa.string()),
            ("informed_entities", pa.string()),
        ]
    ),
    "trips_gone": pa.schema(
        [
            ("feed", pa.string()),
            ("feed_ts", pa.timestamp("us", tz="UTC")),
            ("trip_id", pa.string()),
            ("start_date", pa.string()),
            ("last_seen_ts", pa.string()),
        ]
    ),
}
COLUMNS = {"stop_times": STOP_TIME_COLUMNS, "alerts": ALERT_COLUMNS, "trips_gone": GONE_COLUMNS}


def partition_path(root: Path, dataset: str, feed: str, feed_ts: datetime) -> Path:
    ts = feed_ts.astimezone(UTC)
    return (
        root
        / "raw"
        / dataset
        / f"feed={feed}"
        / f"date={ts:%Y-%m-%d}"
        / f"hour={ts:%H}"
        / f"{feed}_{int(ts.timestamp())}.parquet"
    )


def to_table(rows: list[dict[str, Any]], dataset: str) -> pa.Table:
    schema = _SCHEMAS[dataset]
    cols = {name: [r.get(name) for r in rows] for name in COLUMNS[dataset]}
    return pa.table(cols, schema=schema)


def write_rows(
    rows: list[dict[str, Any]], *, root: Path, dataset: str, feed: str, feed_ts: datetime
) -> Path | None:
    """Write rows as one Parquet file (zstd). Returns the path, or None when there is nothing."""
    if not rows:
        return None
    path = partition_path(root, dataset, feed, feed_ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".parquet.tmp")
    pq.write_table(to_table(rows, dataset), tmp, compression="zstd")
    tmp.replace(path)
    return path
