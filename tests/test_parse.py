from __future__ import annotations

from datetime import UTC

from transitpulse.gtfsrt.parse import ALERT_COLUMNS, STOP_TIME_COLUMNS, parse_feed


def test_vbb_fixture_parses_trip_updates(vbb_pb: bytes) -> None:
    p = parse_feed(vbb_pb, "vbb")
    assert p.feed == "vbb"
    assert p.feed_ts.tzinfo is UTC
    assert p.n_entities == 40
    assert p.n_trips == 40
    assert len(p.stop_times) > 100
    assert set(p.stop_times[0]) == set(STOP_TIME_COLUMNS)
    # VBB carries route_id and start_date on every trip
    assert all(r["route_id"] for r in p.stop_times)
    assert all(r["start_date"] for r in p.stop_times)


def test_cancelled_trips_are_kept(vbb_pb: bytes) -> None:
    p = parse_feed(vbb_pb, "vbb")
    cancelled = [r for r in p.stop_times if r["trip_schedule_relationship"] == 3]
    assert len({r["trip_id"] for r in cancelled}) == 3, "fixture keeps three cancelled trips"


def test_trip_without_stop_times_keeps_one_row() -> None:
    from google.transit import gtfs_realtime_pb2 as rt

    m = rt.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    m.header.timestamp = 1_700_000_000
    e = m.entity.add()
    e.id = "x"
    e.trip_update.trip.trip_id = "t1"
    e.trip_update.trip.start_date = "20261022"
    e.trip_update.trip.schedule_relationship = 3  # CANCELED
    p = parse_feed(m.SerializeToString(), "vbb")
    assert len(p.stop_times) == 1
    row = p.stop_times[0]
    assert row["trip_id"] == "t1" and row["stop_id"] is None and row["stop_sequence"] is None
    assert row["trip_schedule_relationship"] == 3


def test_delays_are_plausible(vbb_pb: bytes) -> None:
    p = parse_feed(vbb_pb, "vbb")
    delays = [r["arrival_delay_s"] for r in p.stop_times if r["arrival_delay_s"] is not None]
    assert delays
    assert max(delays) >= 360, "fixture keeps late trips"
    assert all(-1800 <= d <= 36000 for d in delays)
    assert any(r["arrival_time"] is not None for r in p.stop_times)


def test_gtfsde_fixture_has_alerts_and_no_route_id(gtfsde_pb: bytes) -> None:
    p = parse_feed(gtfsde_pb, "gtfsde")
    assert len(p.alerts) == 5
    assert set(p.alerts[0]) == set(ALERT_COLUMNS)
    assert all(r["route_id"] is None for r in p.stop_times)
    assert all(a["header_text"] or a["description_text"] for a in p.alerts)
    assert p.alerts[0]["informed_entities"].startswith("[")


def test_empty_feed() -> None:
    from google.transit import gtfs_realtime_pb2 as rt

    m = rt.FeedMessage()
    m.header.gtfs_realtime_version = "2.0"
    p = parse_feed(m.SerializeToString(), "vbb")
    assert p.n_entities == 0 and p.stop_times == [] and p.alerts == []
