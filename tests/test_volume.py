from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from transitpulse.config import Settings
from transitpulse.lake import LocalLake
from transitpulse.volume import MultiLake, VolumeLake

HOST = "https://dbc-test.cloud.databricks.com"


def test_url_encodes_volume_path_and_key() -> None:
    v = VolumeLake(HOST + "/", "tok", "Volumes/transitpulse/landing/raw/")
    assert v.url("raw/stop_times/feed=vbb/date=2026-10-22/hour=21/vbb_1.parquet") == (
        HOST
        + "/api/2.0/fs/files/Volumes/transitpulse/landing/raw/"
        + "raw/stop_times/feed%3Dvbb/date%3D2026-10-22/hour%3D21/vbb_1.parquet?overwrite=true"
    )


@respx.mock
def test_put_sends_bearer_and_bytes_and_skips_state() -> None:
    route = respx.put(url__regex=r".*/api/2.0/fs/files/.*").mock(return_value=httpx.Response(204))
    v = VolumeLake(HOST, "tok", "/Volumes/transitpulse/landing/raw")
    v.put("raw/alerts/feed=vbb/date=2026-10-22/hour=21/vbb_1.parquet", b"abc")
    v.put("state/vbb.parquet", b"state")  # not a landing file: never uploaded
    assert route.call_count == 1
    req = route.calls.last.request
    assert req.headers["authorization"] == "Bearer tok"
    assert req.content == b"abc" and "overwrite=true" in str(req.url)
    assert v.get("raw/anything") is None


@respx.mock
def test_put_raises_on_error() -> None:
    respx.put(url__regex=r".*").mock(return_value=httpx.Response(403, text="PERMISSION_DENIED"))
    v = VolumeLake(HOST, "tok", "/Volumes/x/y/z")
    with pytest.raises(RuntimeError, match="HTTP 403"):
        v.put("raw/a.parquet", b"x")


@respx.mock
def test_multilake_writes_all_reads_primary_and_survives_sink_failure(tmp_path: Path) -> None:
    respx.put(url__regex=r".*").mock(return_value=httpx.Response(500, text="boom"))
    primary = LocalLake(tmp_path)
    ml = MultiLake(primary, VolumeLake(HOST, "tok", "/Volumes/x/y/z"))
    ml.put("raw/a.parquet", b"data")  # sink fails with 500, primary still written, no exception
    assert primary.get("raw/a.parquet") == b"data" and ml.get("raw/a.parquet") == b"data"
    assert ml.describe().startswith("local:") and "volume:" in ml.describe()


def test_settings_build_multilake_only_with_host_and_token(tmp_path: Path) -> None:
    assert isinstance(Settings(data_dir=tmp_path).lake(), LocalLake)
    assert isinstance(Settings(data_dir=tmp_path, databricks_host=HOST).lake(), LocalLake)
    assert isinstance(
        Settings(data_dir=tmp_path, databricks_host=HOST, databricks_token="none").lake(), LocalLake
    )
    ml = Settings(data_dir=tmp_path, databricks_host=HOST, databricks_token="t").lake()
    assert isinstance(ml, MultiLake)
