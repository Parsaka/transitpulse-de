from __future__ import annotations

import json
import logging
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from conftest import next_snapshot
from transitpulse import logging as tplog
from transitpulse.collector import run_once
from transitpulse.config import Settings
from transitpulse.feeds import get_feed


def _files(root: Path, dataset: str) -> list[Path]:
    return sorted((root / "raw" / dataset).rglob("*.parquet"))


def test_first_run_writes_all_rows(settings: Settings, vbb_pb: bytes) -> None:
    s = run_once(get_feed("vbb"), settings, body=vbb_pb)
    assert s.status == "ok" and s.error is None
    assert s.n_written_stop_times == s.n_stop_times > 0
    files = _files(settings.data_dir, "stop_times")
    assert len(files) == 1
    assert (
        files[0].name.startswith("vbb_")
        and "feed=vbb" in str(files[0])
        and "date=" in str(files[0])
    )
    t = pq.read_table(files[0])
    assert t.num_rows == s.n_stop_times
    assert str(t.schema.field("feed_ts").type) == "timestamp[us, tz=UTC]"
    assert (settings.state_dir / "vbb.json").exists()


def test_rerun_same_snapshot_is_idempotent(settings: Settings, vbb_pb: bytes) -> None:
    run_once(get_feed("vbb"), settings, body=vbb_pb)
    first = _files(settings.data_dir, "stop_times")
    s2 = run_once(get_feed("vbb"), settings, body=vbb_pb)
    assert s2.n_written_stop_times == 0 and s2.reduction == 1.0
    assert _files(settings.data_dir, "stop_times") == first, "no second file for the same snapshot"


def test_second_snapshot_writes_only_deltas_and_gone(settings: Settings, vbb_pb: bytes) -> None:
    run_once(get_feed("vbb"), settings, body=vbb_pb)
    s = run_once(
        get_feed("vbb"), settings, body=next_snapshot(vbb_pb, bump_delay_trips=1, drop_trips=2)
    )
    assert 0 < s.n_written_stop_times < s.n_stop_times
    assert s.n_trips_gone == 2
    assert len(_files(settings.data_dir, "stop_times")) == 2
    gone = _files(settings.data_dir, "trips_gone")
    assert len(gone) == 1 and pq.read_table(gone[0]).num_rows == 2


def test_snapshot_mode_writes_everything(settings: Settings, vbb_pb: bytes) -> None:
    run_once(get_feed("vbb"), settings, body=vbb_pb, mode="snapshot")
    s = run_once(
        get_feed("vbb"), settings, body=next_snapshot(vbb_pb, seconds_later=60), mode="snapshot"
    )
    assert s.n_written_stop_times == s.n_stop_times and s.reduction == 0.0


def test_alerts_land_in_their_own_dataset(settings: Settings, gtfsde_pb: bytes) -> None:
    s = run_once(get_feed("gtfsde"), settings, body=gtfsde_pb)
    assert s.n_alerts == 5
    assert len(_files(settings.data_dir, "alerts")) == 1


def test_bad_body_is_reported_not_raised(settings: Settings) -> None:
    s = run_once(get_feed("vbb"), settings, body=b"\xff\xff not protobuf")
    assert s.status == "error" and s.error and "DecodeError" in s.error
    assert _files(settings.data_dir, "stop_times") == []


def test_json_log_carries_run_id_and_summary(
    settings: Settings, vbb_pb: bytes, capsys: pytest.CaptureFixture[str]
) -> None:
    tplog.configure("json")
    try:
        run_once(get_feed("vbb"), settings, body=vbb_pb)
    finally:
        logging.getLogger().handlers.clear()
    lines = [
        json.loads(line) for line in capsys.readouterr().out.splitlines() if line.startswith("{")
    ]
    steps = [line["step"] for line in lines if "step" in line]
    assert steps == ["fetch", "parse", "delta", "write"]
    assert all(line.get("run_id") and line.get("feed") == "vbb" for line in lines)
    summary = next(line["summary"] for line in lines if "summary" in line)
    assert summary["status"] == "ok" and summary["n_written_stop_times"] > 0
