from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import respx

from transitpulse.gtfs_static import STATIC_URLS, download, land_static_gtfs
from transitpulse.lake import LocalLake


def _zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, text in files.items():
            zf.writestr(name, text)
    return buf.getvalue()


SAMPLE = {
    "agency.txt": "agency_id,agency_name,agency_url,agency_timezone,agency_lang\n"
    "1,S-Bahn Berlin GmbH,https://sbahn.berlin,Europe/Berlin,de\n",
    "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type,route_color\n"
    "10148_109,1,S1,Wannsee <> Oranienburg,109,DD6CA6\n"
    "17289_700,1,100,Alexanderplatz <> Zoo,700,\n",
    "stops.txt": "﻿stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,platform_code\n"
    "de:11000:900100003,S+U Alexanderplatz,52.521512,13.411267,1,,\n"
    "de:11000:900100003::1,S+U Alexanderplatz,52.521512,13.411267,0,de:11000:900100003,1\n",
    "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id,wheelchair_accessible\n"
    "10148_109,1,222333,S Oranienburg,0,shp1,1\n",
    "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\n"
    "1,1,1,1,1,1,0,0,20261001,20261231\n",
    "calendar_dates.txt": "service_id,date,exception_type\n1,20261225,2\n",
    "stop_times.txt": "trip_id,arrival_time,departure_time,stop_id,stop_sequence\n222333,08:00:00,08:00:30,de:11000:900100003::1,1\n",
}


def test_land_static_gtfs_writes_selected_tables_with_string_ids(tmp_path: Path) -> None:
    lake = LocalLake(tmp_path)
    res = land_static_gtfs(_zip(SAMPLE), lake, feed="vbb", version="2026-10-23")
    assert res.tables == {
        "agency": 1,
        "routes": 2,
        "stops": 2,
        "trips": 1,
        "calendar": 1,
        "calendar_dates": 1,
    }
    assert "stop_times" not in res.tables and res.bytes_written > 0
    assert res.keys[0] == "static/gtfs/feed=vbb/version=2026-10-23/agency.parquet"
    routes = pq.read_table(tmp_path / "static/gtfs/feed=vbb/version=2026-10-23/routes.parquet")
    assert routes.column_names == [
        "route_id",
        "agency_id",
        "route_short_name",
        "route_long_name",
        "route_type",
    ]
    assert str(routes.schema.field("route_short_name").type) == "string"  # "100" stays text
    assert str(routes.schema.field("route_type").type).startswith("int")
    stops = pq.read_table(tmp_path / "static/gtfs/feed=vbb/version=2026-10-23/stops.parquet")
    assert stops.column_names[0] == "stop_id", "UTF-8 BOM stripped from the header"
    assert str(stops.schema.field("stop_lat").type) == "double"
    assert stops.column("parent_station").to_pylist() == [None, "de:11000:900100003"]


def test_missing_table_is_skipped(tmp_path: Path) -> None:
    res = land_static_gtfs(
        _zip({"agency.txt": SAMPLE["agency.txt"]}), LocalLake(tmp_path), feed="vbb"
    )
    assert res.tables == {"agency": 1}


@respx.mock
def test_download_follows_redirect_and_sends_user_agent() -> None:
    respx.get(STATIC_URLS["vbb"]).mock(
        return_value=httpx.Response(302, headers={"location": "https://cdn.test/GTFS.zip"})
    )
    respx.get("https://cdn.test/GTFS.zip").mock(return_value=httpx.Response(200, content=b"PK..."))
    assert download(STATIC_URLS["vbb"], user_agent="ua") == b"PK..."
    assert respx.calls[0].request.headers["user-agent"] == "ua"


def test_column_types_are_fixed_even_for_empty_columns(tmp_path: Path) -> None:
    # gtfs.de leaves route_long_name empty for every route: without fixed types Arrow wrote a
    # Parquet "null" (INT32) column and the pipeline's schema inference broke (2026-10-27).
    zip_bytes = _zip(
        {
            "agency.txt": "agency_id,agency_name,agency_url,agency_timezone\n1,A,http://a,Europe/Berlin\n",
            "routes.txt": "route_id,agency_id,route_short_name,route_long_name,route_type\nr1,1,10,,3\nr2,1,11,,700\n",
            "stops.txt": "stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,platform_code\ns1,S,52.5,13.4,,,\n",
            "trips.txt": "route_id,service_id,trip_id,trip_headsign,direction_id,shape_id\nr1,sv,t1,,,\n",
            "calendar.txt": "service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date\nsv,1,1,1,1,1,0,0,20261001,20261231\n",
            "calendar_dates.txt": "service_id,date,exception_type\nsv,20261003,2\n",
        }
    )
    lake = LocalLake(tmp_path)
    land_static_gtfs(zip_bytes, lake, feed="x", version="v1")
    import pyarrow as pa

    def schema(table: str) -> dict[str, pa.DataType]:
        s = pq.read_schema(
            tmp_path / "static" / "gtfs" / "feed=x" / "version=v1" / f"{table}.parquet"
        )
        return {n: s.field(n).type for n in s.names}

    assert schema("routes")["route_long_name"] == pa.string()
    assert schema("routes")["route_type"] == pa.int64()
    assert schema("stops")["stop_lat"] == pa.float64()
    assert schema("stops")["location_type"] == pa.int64()
    assert schema("trips")["direction_id"] == pa.int64()
    assert schema("trips")["trip_headsign"] == pa.string()
    assert (
        schema("calendar")["monday"] == pa.int64()
        and schema("calendar")["start_date"] == pa.string()
    )
    assert schema("calendar_dates")["exception_type"] == pa.int64()
