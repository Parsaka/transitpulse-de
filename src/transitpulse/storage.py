"""Parquet encoding and the partition layout of the raw landing zone.

    raw/<dataset>/feed=<feed>/date=YYYY-MM-DD/hour=HH/<feed>_<unix_feed_ts>.parquet

The file name is derived from the feed header timestamp, so re-running the collector for the same
feed snapshot overwrites the same object instead of appending a duplicate.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from transitpulse.gtfsrt.parse import ALERT_COLUMNS, STOP_TIME_COLUMNS

GONE_COLUMNS = ["feed", "feed_ts", "trip_id", "start_date", "last_seen_ts"]

_TS = pa.timestamp("us", tz="UTC")

SCHEMAS: dict[str, pa.Schema] = {
    "stop_times": pa.schema(
        [
            ("feed", pa.string()),
            ("feed_ts", _TS),
            ("entity_id", pa.string()),
            ("trip_id", pa.string()),
            ("route_id", pa.string()),
            ("start_date", pa.string()),
            ("start_time", pa.string()),
            ("direction_id", pa.int32()),
            ("trip_schedule_relationship", pa.int32()),
            ("vehicle_id", pa.string()),
            ("trip_ts", _TS),
            ("stop_sequence", pa.int32()),
            ("stop_id", pa.string()),
            ("stop_schedule_relationship", pa.int32()),
            ("arrival_delay_s", pa.int32()),
            ("arrival_time", _TS),
            ("departure_delay_s", pa.int32()),
            ("departure_time", _TS),
        ]
    ),
    "alerts": pa.schema(
        [
            ("feed", pa.string()),
            ("feed_ts", _TS),
            ("entity_id", pa.string()),
            ("cause", pa.int32()),
            ("effect", pa.int32()),
            ("active_from", _TS),
            ("active_to", _TS),
            ("header_text", pa.string()),
            ("description_text", pa.string()),
            ("informed_entities", pa.string()),
        ]
    ),
    "trips_gone": pa.schema(
        [
            ("feed", pa.string()),
            ("feed_ts", _TS),
            ("trip_id", pa.string()),
            ("start_date", pa.string()),
            ("last_seen_ts", pa.string()),
        ]
    ),
}
COLUMNS = {"stop_times": STOP_TIME_COLUMNS, "alerts": ALERT_COLUMNS, "trips_gone": GONE_COLUMNS}


def partition_key(dataset: str, feed: str, feed_ts: datetime) -> str:
    ts = feed_ts.astimezone(UTC)
    name = f"{feed}_{int(ts.timestamp())}.parquet"
    return f"raw/{dataset}/feed={feed}/date={ts:%Y-%m-%d}/hour={ts:%H}/{name}"


def to_table(rows: list[dict[str, Any]], dataset: str) -> pa.Table:
    cols = {name: [r.get(name) for r in rows] for name in COLUMNS[dataset]}
    return pa.table(cols, schema=SCHEMAS[dataset])


def table_to_bytes(table: pa.Table) -> bytes:
    buf = io.BytesIO()
    pq.write_table(table, buf, compression="zstd")
    return buf.getvalue()


def bytes_to_table(data: bytes) -> pa.Table:
    return pq.read_table(io.BytesIO(data))


def rows_to_parquet(rows: list[dict[str, Any]], dataset: str) -> bytes:
    return table_to_bytes(to_table(rows, dataset))
