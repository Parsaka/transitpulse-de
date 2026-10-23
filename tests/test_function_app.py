"""The Function entry point, exercised without the Functions host."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import httpx
import pytest
import respx

from transitpulse.feeds import FEEDS

FUNCTION_APP = Path(__file__).resolve().parents[1] / "function_app" / "function_app.py"


@pytest.fixture(scope="module")
def function_app():  # type: ignore[no-untyped-def]
    pytest.importorskip("azure.functions")
    spec = importlib.util.spec_from_file_location("function_app", FUNCTION_APP)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["function_app"] = mod
    spec.loader.exec_module(mod)
    return mod


class FakeTimer:
    past_due = False


@pytest.fixture(autouse=True)
def _reset_runtime_cache(function_app):  # type: ignore[no-untyped-def]
    function_app._cache.clear()
    yield
    function_app._cache.clear()


@respx.mock
def test_collect_runs_every_configured_feed(
    function_app, tmp_path: Path, vbb_pb: bytes, gtfsde_pb: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TP_LOG_FORMAT", "json")
    monkeypatch.setenv("TP_FEEDS", "vbb, gtfsde")
    respx.get(FEEDS["vbb"].url).mock(return_value=httpx.Response(200, content=vbb_pb))
    respx.get(FEEDS["gtfsde"].url).mock(return_value=httpx.Response(200, content=gtfsde_pb))
    function_app.collect(FakeTimer())
    assert (tmp_path / "state" / "vbb.parquet").exists()
    assert (tmp_path / "state" / "gtfsde.parquet").exists()


@respx.mock
def test_failed_feed_raises_so_the_host_counts_a_failure(
    function_app, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TP_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("TP_FEEDS", "vbb")
    monkeypatch.setenv("TP_HTTP_RETRIES", "0")
    respx.get(FEEDS["vbb"].url).mock(return_value=httpx.Response(404))
    with pytest.raises(RuntimeError, match="1 of 1 feed runs failed"):
        function_app.collect(FakeTimer())


def test_timer_binding_uses_the_schedule_app_setting(function_app) -> None:  # type: ignore[no-untyped-def]
    text = FUNCTION_APP.read_text(encoding="utf-8")
    assert 'schedule="%TP_SCHEDULE%"' in text and "run_on_startup=False" in text
