from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx
from typer.testing import CliRunner

from transitpulse.cli import app
from transitpulse.feeds import FEEDS

runner = CliRunner()


def test_version() -> None:
    r = runner.invoke(app, ["version"])
    assert r.exit_code == 0 and r.stdout.strip() == "0.1.0"


def test_inspect_fixture() -> None:
    r = runner.invoke(app, ["inspect", "tests/fixtures/vbb_sample.pb"])
    assert r.exit_code == 0, r.stdout
    out = json.loads(r.stdout)
    assert out["trips"] == 40 and out["with_arrival_delay"] > 0 and "delay_p50_s" in out


@respx.mock
def test_collect_once_against_mocked_feed(tmp_path: Path, vbb_pb: bytes, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("TP_DATA_DIR", str(tmp_path / "d"))
    monkeypatch.setenv("TP_LOG_FORMAT", "json")
    respx.get(FEEDS["vbb"].url).mock(return_value=httpx.Response(200, content=vbb_pb))
    r = runner.invoke(app, ["collect", "--feed", "vbb", "--once"])
    assert r.exit_code == 0, r.stdout
    summary = json.loads(r.stdout.strip().splitlines()[-1])
    assert summary["status"] == "ok" and summary["n_trips"] == 40
    assert list((tmp_path / "d" / "raw" / "stop_times").rglob("*.parquet"))


def test_collect_rejects_too_fast_polling() -> None:
    r = runner.invoke(app, ["collect", "--feed", "vbb", "--interval", "5"])
    assert r.exit_code != 0


def test_collect_unknown_feed() -> None:
    r = runner.invoke(app, ["collect", "--feed", "nope", "--once"])
    assert r.exit_code != 0
