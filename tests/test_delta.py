from __future__ import annotations

from pathlib import Path

from conftest import next_snapshot
from transitpulse.delta import DeltaStore, fingerprint, row_key, state_key
from transitpulse.gtfsrt.parse import parse_feed
from transitpulse.lake import LocalLake


def test_first_snapshot_is_all_changes(vbb_pb: bytes) -> None:
    p = parse_feed(vbb_pb, "vbb")
    store = DeltaStore()
    d = store.apply(p.stop_times, p.feed_ts, feed="vbb")
    assert len(d.changed) == len(p.stop_times)
    assert d.gone == []
    assert d.reduction == 0.0
    assert d.n_tracked == len({row_key(r) for r in p.stop_times})


def test_identical_snapshot_emits_nothing(vbb_pb: bytes) -> None:
    p = parse_feed(vbb_pb, "vbb")
    store = DeltaStore()
    store.apply(p.stop_times, p.feed_ts, feed="vbb")
    d = store.apply(p.stop_times, p.feed_ts, feed="vbb")
    assert d.changed == [] and d.gone == []
    assert d.reduction == 1.0


def test_changed_delays_and_gone_trips(vbb_pb: bytes) -> None:
    p1 = parse_feed(vbb_pb, "vbb")
    p2 = parse_feed(next_snapshot(vbb_pb, bump_delay_trips=2, drop_trips=3), "vbb")
    store = DeltaStore()
    store.apply(p1.stop_times, p1.feed_ts, feed="vbb")
    d = store.apply(p2.stop_times, p2.feed_ts, feed="vbb")
    changed_trips = {r["trip_id"] for r in d.changed}
    assert len(changed_trips) == 2
    assert all(r["arrival_delay_s"] is not None for r in d.changed)
    assert len(d.gone) == 3
    gone_ids = {g["trip_id"] for g in d.gone}
    assert gone_ids.isdisjoint({r["trip_id"] for r in p2.stop_times})
    assert all(g["last_seen_ts"] == p1.feed_ts.isoformat() for g in d.gone)
    # fingerprints of gone trips are dropped so the store does not grow for ever
    assert not any(k.split("|")[0] in gone_ids for k in store.fingerprints)
    assert 0.5 < d.reduction < 1.0


def test_feeds_do_not_interfere(vbb_pb: bytes, gtfsde_pb: bytes) -> None:
    store = DeltaStore()
    a = parse_feed(vbb_pb, "vbb")
    b = parse_feed(gtfsde_pb, "gtfsde")
    store.apply(a.stop_times, a.feed_ts, feed="vbb")
    d = store.apply(b.stop_times, b.feed_ts, feed="gtfsde")
    assert d.gone == [], "trips of another feed must not be reported gone"


def test_store_roundtrip_through_lake(tmp_path: Path, vbb_pb: bytes) -> None:
    p = parse_feed(vbb_pb, "vbb")
    store = DeltaStore()
    store.apply(p.stop_times, p.feed_ts, feed="vbb")
    store.etags["vbb"] = '"abc"'
    lake = LocalLake(tmp_path)
    n = store.save(lake, "vbb")
    assert n > 0 and (tmp_path / "state" / "vbb.parquet").stat().st_size == n
    again = DeltaStore.load(lake, "vbb")
    assert again.fingerprints == store.fingerprints
    assert again.trips == store.trips
    assert again.etags == {"vbb": '"abc"'}
    assert not (tmp_path / "state" / "vbb.parquet.tmp").exists()
    assert DeltaStore.load(lake, "missing").fingerprints == {}
    assert state_key("vbb") == "state/vbb.parquet"


def test_state_is_compact(vbb_pb: bytes) -> None:
    p = parse_feed(vbb_pb, "vbb")
    store = DeltaStore()
    store.apply(p.stop_times, p.feed_ts, feed="vbb")
    per_row = len(store.to_bytes()) / len(store.fingerprints)
    assert per_row < 40, f"{per_row:.1f} bytes per tracked stop-time update"


def test_fingerprint_is_a_short_hash_and_ignores_feed_timestamp() -> None:
    r1 = {"trip_id": "t", "stop_sequence": 1, "arrival_delay_s": 10, "feed_ts": "a"}
    r2 = {**r1, "feed_ts": "b"}
    r3 = {**r1, "arrival_delay_s": 11}
    assert fingerprint(r1) == fingerprint(r2) != fingerprint(r3)
    assert len(fingerprint(r1)) == 16
    assert row_key(r1) == "t||1"
