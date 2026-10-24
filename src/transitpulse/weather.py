"""Weather for the VBB area from Open-Meteo (free, no key, CC BY 4.0): hourly observations and
forecasts at nine grid points, landed as Parquet like every other feed.

One request returns all points; each hour row carries ``is_forecast`` (true when the hour lies
after the fetch time) and ``fetched_at`` so that later fetches override earlier forecasts with
observations (the silver table keeps the latest fetch per point and hour).
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
import pyarrow as pa

from transitpulse.lake import Lake
from transitpulse.storage import table_to_bytes

log = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,precipitation,rain,snowfall,wind_speed_10m,wind_gusts_10m,weather_code"


@dataclass(frozen=True)
class Point:
    point_id: str
    name: str
    lat: float
    lon: float


# Berlin plus a ring of Brandenburg towns: every VBB stop is within about 40 km of one of them.
POINTS: tuple[Point, ...] = (
    Point("berlin", "Berlin-Mitte", 52.52, 13.405),
    Point("potsdam", "Potsdam", 52.40, 13.06),
    Point("cottbus", "Cottbus", 51.76, 14.33),
    Point("frankfurt_oder", "Frankfurt (Oder)", 52.35, 14.55),
    Point("brandenburg", "Brandenburg an der Havel", 52.41, 12.55),
    Point("eberswalde", "Eberswalde", 52.83, 13.80),
    Point("neuruppin", "Neuruppin", 52.92, 12.81),
    Point("luckenwalde", "Luckenwalde", 52.09, 13.17),
    Point("prenzlau", "Prenzlau", 53.32, 13.86),
)

WEATHER_SCHEMA = pa.schema(
    [
        ("point_id", pa.string()),
        ("point_name", pa.string()),
        ("lat", pa.float64()),
        ("lon", pa.float64()),
        ("time", pa.timestamp("us", tz="UTC")),
        ("temp_c", pa.float64()),
        ("precip_mm", pa.float64()),
        ("rain_mm", pa.float64()),
        ("snow_cm", pa.float64()),
        ("wind_kmh", pa.float64()),
        ("gust_kmh", pa.float64()),
        ("weather_code", pa.int32()),
        ("is_forecast", pa.bool_()),
        ("fetched_at", pa.timestamp("us", tz="UTC")),
    ]
)


def fetch_openmeteo(
    points: tuple[Point, ...] = POINTS,
    *,
    past_days: int = 2,
    forecast_days: int = 2,
    user_agent: str,
    timeout_s: float = 60.0,
    client: httpx.Client | None = None,
    retries: int = 3,
    backoff_s: float = 2.0,
) -> list[dict[str, Any]]:
    """One request for all points; returns a list of per-point JSON documents.

    Open-Meteo answers 503 now and then on the full hour (seen on the first timer run,
    2026-10-24 13:07:00 UTC); server errors and transport errors are retried ``retries`` times
    with a growing pause, client errors (4xx) are not.
    """
    params: dict[str, str | int] = {
        "latitude": ",".join(str(p.lat) for p in points),
        "longitude": ",".join(str(p.lon) for p in points),
        "hourly": HOURLY,
        "past_days": past_days,
        "forecast_days": forecast_days,
        "timezone": "UTC",
    }
    cl = client or httpx.Client(timeout=timeout_s)
    try:
        for attempt in range(retries + 1):
            try:
                r = cl.get(OPEN_METEO_URL, params=params, headers={"User-Agent": user_agent})
                r.raise_for_status()
                data = r.json()
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as e:
                status = e.response.status_code if isinstance(e, httpx.HTTPStatusError) else None
                if (status is not None and status < 500) or attempt == retries:
                    raise
                log.warning(
                    "open-meteo retry",
                    extra={"attempt": attempt + 1, "status": status, "error": str(e)[:200]},
                )
                time.sleep(backoff_s * (attempt + 1))
    finally:
        if client is None:
            cl.close()
    return data if isinstance(data, list) else [data]


def rows_from_openmeteo(
    docs: list[dict[str, Any]], points: tuple[Point, ...], fetched_at: datetime
) -> list[dict[str, Any]]:
    """Flatten the per-point hourly arrays into rows; forecast hours are flagged."""
    rows: list[dict[str, Any]] = []
    cutoff = fetched_at.replace(minute=0, second=0, microsecond=0)
    for point, doc in zip(points, docs, strict=True):
        h = doc["hourly"]
        for i, t in enumerate(h["time"]):
            ts = datetime.fromisoformat(t).replace(tzinfo=UTC)
            rows.append(
                {
                    "point_id": point.point_id,
                    "point_name": point.name,
                    "lat": point.lat,
                    "lon": point.lon,
                    "time": ts,
                    "temp_c": h["temperature_2m"][i],
                    "precip_mm": h["precipitation"][i],
                    "rain_mm": h["rain"][i],
                    "snow_cm": h["snowfall"][i],
                    "wind_kmh": h["wind_speed_10m"][i],
                    "gust_kmh": h["wind_gusts_10m"][i],
                    "weather_code": h["weather_code"][i],
                    "is_forecast": ts > cutoff,
                    "fetched_at": fetched_at,
                }
            )
    return rows


def weather_key(fetched_at: datetime) -> str:
    ts = fetched_at.astimezone(UTC)
    name = f"openmeteo_{int(ts.timestamp())}.parquet"
    return f"raw/weather/feed=openmeteo/date={ts:%Y-%m-%d}/hour={ts:%H}/{name}"


def land_weather(rows: list[dict[str, Any]], lake: Lake, fetched_at: datetime) -> tuple[str, int]:
    cols = {f.name: [r.get(f.name) for r in rows] for f in WEATHER_SCHEMA}
    data = table_to_bytes(pa.table(cols, schema=WEATHER_SCHEMA))
    key = weather_key(fetched_at)
    lake.put(key, data)
    return key, len(data)
