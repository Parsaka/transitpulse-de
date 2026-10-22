from __future__ import annotations

from pathlib import Path

import pytest
from google.transit import gtfs_realtime_pb2 as rt

from transitpulse.config import Settings

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def vbb_pb() -> bytes:
    return (FIXTURES / "vbb_sample.pb").read_bytes()


@pytest.fixture(scope="session")
def gtfsde_pb() -> bytes:
    return (FIXTURES / "gtfsde_sample.pb").read_bytes()


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=tmp_path / "data", user_agent="tests")


def next_snapshot(
    pb: bytes, *, seconds_later: int = 60, bump_delay_trips: int = 2, drop_trips: int = 1
) -> bytes:
    """Build a plausible follow-up snapshot: later header, a few delays changed, some trips gone."""
    msg = rt.FeedMessage()
    msg.ParseFromString(pb)
    msg.header.timestamp += seconds_later
    bumped = 0
    for e in msg.entity:
        if bumped >= bump_delay_trips or not e.HasField("trip_update"):
            continue
        for s in e.trip_update.stop_time_update:
            if s.HasField("arrival"):
                s.arrival.delay = s.arrival.delay + 120
        bumped += 1
    trip_entities = [i for i, e in enumerate(msg.entity) if e.HasField("trip_update")]
    for i in sorted(trip_entities[-drop_trips:], reverse=True):
        del msg.entity[i]
    return msg.SerializeToString()
