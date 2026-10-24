"""Static GTFS schedule (zip of CSV files) -> Parquet, one file per table, landed in the lake.

The realtime feed only carries ids; stops, routes, agencies and the service calendar come from
the static feed, which VBB republishes twice a week. ``stop_times.txt`` (hundreds of MB) is left
out on purpose: the realtime TripUpdates already carry the delay against the schedule.

Landing layout: ``static/gtfs/feed=<feed>/version=<YYYY-MM-DD>/<table>.parquet``.
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
import pyarrow as pa
import pyarrow.csv as pacsv

from transitpulse.lake import Lake
from transitpulse.storage import table_to_bytes

log = logging.getLogger(__name__)

STATIC_URLS = {
    "vbb": "https://unternehmen.vbb.de/gtfs",
    # nationwide DELFI schedule (CC BY 4.0), about 276 MB, regenerated daily
    "gtfsde": "https://download.gtfs.de/germany/free/latest.zip",
}

# table -> columns kept (None = all). Types are inferred by Arrow; ids stay strings.
TABLES: dict[str, list[str] | None] = {
    "agency": ["agency_id", "agency_name", "agency_url", "agency_timezone"],
    "routes": ["route_id", "agency_id", "route_short_name", "route_long_name", "route_type"],
    "stops": [
        "stop_id",
        "stop_name",
        "stop_lat",
        "stop_lon",
        "location_type",
        "parent_station",
        "platform_code",
    ],
    "trips": ["route_id", "service_id", "trip_id", "trip_headsign", "direction_id", "shape_id"],
    "calendar": None,
    "calendar_dates": None,
}
ID_COLUMNS = {
    "agency_id",
    "route_id",
    "stop_id",
    "parent_station",
    "trip_id",
    "service_id",
    "shape_id",
    "platform_code",
    "route_short_name",
}


@dataclass
class StaticResult:
    feed: str
    version: str
    tables: dict[str, int]  # table -> rows
    bytes_written: int
    keys: list[str]


def download(url: str, *, user_agent: str, timeout_s: float = 900.0) -> bytes:
    r = httpx.get(url, headers={"User-Agent": user_agent}, timeout=timeout_s, follow_redirects=True)
    r.raise_for_status()
    return r.content


def read_table(zf: zipfile.ZipFile, table: str) -> pa.Table | None:
    name = f"{table}.txt"
    if name not in zf.namelist():
        return None
    raw = zf.read(name)
    header = next(csv.reader(io.StringIO(raw[:4096].decode("utf-8-sig"), newline="")))
    keep = TABLES[table]
    cols = [c for c in header if keep is None or c in keep]
    types = {c: pa.string() for c in cols if c in ID_COLUMNS}
    return pacsv.read_csv(
        io.BytesIO(raw),
        convert_options=pacsv.ConvertOptions(
            include_columns=cols, column_types=types, strings_can_be_null=True
        ),
    )


def land_static_gtfs(
    zip_bytes: bytes, lake: Lake, *, feed: str, version: str | None = None
) -> StaticResult:
    """Convert the zip to Parquet tables and write them under static/gtfs/."""
    version = version or datetime.now(tz=UTC).strftime("%Y-%m-%d")
    res = StaticResult(feed=feed, version=version, tables={}, bytes_written=0, keys=[])
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for table in TABLES:
            t = read_table(zf, table)
            if t is None:
                log.warning("static table missing", extra={"feed": feed, "table": table})
                continue
            data = table_to_bytes(t)
            key = f"static/gtfs/feed={feed}/version={version}/{table}.parquet"
            lake.put(key, data)
            res.tables[table] = t.num_rows
            res.bytes_written += len(data)
            res.keys.append(key)
    return res
