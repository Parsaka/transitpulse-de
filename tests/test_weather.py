from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pyarrow.parquet as pq
import pytest
import respx

from transitpulse.lake import LocalLake
from transitpulse.weather import (
    OPEN_METEO_URL,
    POINTS,
    Point,
    fetch_openmeteo,
    land_weather,
    rows_from_openmeteo,
    weather_key,
)

TWO = (Point("a", "A", 52.5, 13.4), Point("b", "B", 52.4, 13.0))


def _doc(hours: list[str]) -> dict:
    n = len(hours)
    return {
        "hourly": {
            "time": hours,
            "temperature_2m": [10.0 + i for i in range(n)],
            "precipitation": [0.0, 1.2, 0.0][:n] + [0.0] * max(0, n - 3),
            "rain": [0.0] * n,
            "snowfall": [0.0] * n,
            "wind_speed_10m": [12.0] * n,
            "wind_gusts_10m": [30.0] * n,
            "weather_code": [3] * n,
        }
    }


def test_rows_flag_forecast_hours_and_keep_point_identity() -> None:
    fetched = datetime(2026, 10, 24, 11, 30, tzinfo=UTC)
    hours = ["2026-10-24T10:00", "2026-10-24T11:00", "2026-10-24T12:00"]
    rows = rows_from_openmeteo([_doc(hours), _doc(hours)], TWO, fetched)
    assert len(rows) == 6
    a = [r for r in rows if r["point_id"] == "a"]
    assert [r["is_forecast"] for r in a] == [False, False, True]  # 11:00 is the current hour
    assert a[1]["precip_mm"] == 1.2 and a[0]["time"].tzinfo is UTC and a[0]["fetched_at"] == fetched


def test_land_weather_writes_one_file_per_fetch(tmp_path: Path) -> None:
    fetched = datetime(2026, 10, 24, 11, 30, tzinfo=UTC)
    rows = rows_from_openmeteo([_doc(["2026-10-24T10:00"])], TWO[:1], fetched)
    key, n = land_weather(rows, LocalLake(tmp_path), fetched)
    assert key == "raw/weather/feed=openmeteo/date=2026-10-24/hour=11/openmeteo_1792841400.parquet"
    assert n > 0 and pq.read_table(tmp_path / key).num_rows == 1
    assert weather_key(fetched) == key


@respx.mock
def test_fetch_sends_all_points_in_one_request() -> None:
    route = respx.get(OPEN_METEO_URL).mock(
        return_value=httpx.Response(200, json=[_doc(["2026-10-24T10:00"]) for _ in POINTS])
    )
    docs = fetch_openmeteo(user_agent="ua", past_days=1, forecast_days=1)
    assert len(docs) == len(POINTS) and route.call_count == 1
    url = str(route.calls.last.request.url)
    assert "past_days=1" in url and url.count("52.52") == 1 and "timezone=UTC" in url


@respx.mock
def test_fetch_retries_server_errors_but_not_client_errors(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr("transitpulse.weather.time.sleep", lambda s: None)
    route = respx.get(OPEN_METEO_URL).mock(
        side_effect=[
            httpx.Response(503, text="Service Unavailable"),
            httpx.Response(200, json=[_doc(["2026-10-24T10:00"]) for _ in POINTS]),
        ]
    )
    docs = fetch_openmeteo(user_agent="ua", retries=2)
    assert len(docs) == len(POINTS) and route.call_count == 2

    respx.get(OPEN_METEO_URL).mock(return_value=httpx.Response(400, text="bad request"))
    with pytest.raises(httpx.HTTPStatusError):
        fetch_openmeteo(user_agent="ua", retries=2)
