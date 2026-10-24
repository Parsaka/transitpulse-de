"""Delta detection between consecutive feed snapshots.

A GTFS-RT feed repeats every active trip on every poll (6 MB a minute for VBB). Most stop-time
updates do not change from one poll to the next, so the collector keeps a fingerprint per
``(trip_id, start_date, stop_sequence|stop_id)`` and emits only rows whose fingerprint changed,
plus one ``trip_gone`` marker when a trip disappears from the feed (completed or dropped).

The store is persisted as one small Parquet object (``state/<feed>.parquet``) with three kinds of
rows: ``fp`` (row key -> 64-bit fingerprint hash), ``trip`` (trip key -> last feed timestamp seen)
and ``etag`` (HTTP ETag of the last body). Hashing the fingerprint and using Parquet instead of
JSON took the VBB state from 11.7 MB to about 1 MB (see docs/optimisation.md).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pyarrow as pa

from transitpulse.lake import Lake
from transitpulse.storage import bytes_to_table, table_to_bytes

FINGERPRINT_FIELDS = (
    "arrival_delay_s",
    "departure_delay_s",
    "arrival_time",
    "departure_time",
    "stop_schedule_relationship",
    "trip_schedule_relationship",
)

STATE_SCHEMA = pa.schema([("kind", pa.string()), ("key", pa.string()), ("value", pa.string())])


def state_key(feed: str) -> str:
    return f"state/{feed}.parquet"


def row_key(row: dict[str, Any]) -> str:
    stop = (
        row["stop_sequence"] if row.get("stop_sequence") is not None else row.get("stop_id") or ""
    )
    return f"{row['trip_id']}|{row.get('start_date') or ''}|{stop}"


def trip_key(row: dict[str, Any]) -> str:
    return f"{row['trip_id']}|{row.get('start_date') or ''}"


def fingerprint(row: dict[str, Any]) -> str:
    """16 hex chars: blake2b-64 of the fields that matter (1e5 keys: collisions negligible)."""
    parts = []
    for f in FINGERPRINT_FIELDS:
        v = row.get(f)
        parts.append(v.isoformat() if isinstance(v, datetime) else str(v))
    return hashlib.blake2b("|".join(parts).encode(), digest_size=8).hexdigest()


@dataclass
class DeltaResult:
    changed: list[dict[str, Any]]
    gone: list[dict[str, Any]]
    n_input: int
    n_tracked: int

    @property
    def reduction(self) -> float:
        """Share of input rows suppressed as unchanged (0..1)."""
        return 0.0 if not self.n_input else 1 - len(self.changed) / self.n_input


@dataclass
class DeltaStore:
    """fingerprints: row_key -> fingerprint; trips: trip_key -> last feed_ts seen (ISO)."""

    fingerprints: dict[str, str] = field(default_factory=dict)
    trips: dict[str, str] = field(default_factory=dict)
    etags: dict[str, str] = field(default_factory=dict)

    # ---- persistence -------------------------------------------------------------------------

    def to_bytes(self) -> bytes:
        kinds, keys, values = [], [], []
        for kind, mapping in (
            ("fp", self.fingerprints),
            ("trip", self.trips),
            ("etag", self.etags),
        ):
            for k, v in mapping.items():
                kinds.append(kind)
                keys.append(k)
                values.append(v)
        return table_to_bytes(
            pa.table({"kind": kinds, "key": keys, "value": values}, schema=STATE_SCHEMA)
        )

    @classmethod
    def from_bytes(cls, data: bytes) -> DeltaStore:
        t = bytes_to_table(data)
        store = cls()
        target = {"fp": store.fingerprints, "trip": store.trips, "etag": store.etags}
        for kind, key, value in zip(
            t.column("kind").to_pylist(),
            t.column("key").to_pylist(),
            t.column("value").to_pylist(),
            strict=True,
        ):
            target[kind][key] = value
        return store

    @classmethod
    def load(cls, lake: Lake, feed: str) -> DeltaStore:
        data = lake.get(state_key(feed))
        return cls.from_bytes(data) if data else cls()

    def save(self, lake: Lake, feed: str) -> int:
        data = self.to_bytes()
        lake.put(state_key(feed), data)
        return len(data)

    # ---- delta -------------------------------------------------------------------------------

    def apply(self, rows: list[dict[str, Any]], feed_ts: datetime, *, feed: str) -> DeltaResult:
        """Return changed rows and gone-trip markers; update the store in place."""
        changed: list[dict[str, Any]] = []
        seen_trips: set[str] = set()
        for row in rows:
            k = row_key(row)
            fp = fingerprint(row)
            seen_trips.add(trip_key(row))
            if self.fingerprints.get(k) != fp:
                self.fingerprints[k] = fp
                changed.append(row)

        gone: list[dict[str, Any]] = []
        prefix = f"{feed}:"
        gone_keys = [
            t for t in self.trips if t.startswith(prefix) and t[len(prefix) :] not in seen_trips
        ]
        if gone_keys:
            # One pass over the store groups the stop fingerprints by trip, so dropping the gone
            # trips is O(store + gone). The previous scan per gone trip was O(store x gone):
            # 1,796 gone trips x 390k fingerprints took 54 s on the nationwide feed (docs/scale.md).
            by_trip: dict[str, list[str]] = {}
            for rk in self.fingerprints:
                by_trip.setdefault(rk.rsplit("|", 1)[0], []).append(rk)
        for tk in gone_keys:
            bare = tk[len(prefix) :]
            trip_id, _, start_date = bare.partition("|")
            gone.append(
                {
                    "feed": feed,
                    "feed_ts": feed_ts,
                    "trip_id": trip_id,
                    "start_date": start_date or None,
                    "last_seen_ts": self.trips.pop(tk),
                }
            )
            # drop the trip's stop fingerprints so memory does not grow without bound
            for rk in by_trip.get(bare, ()):
                del self.fingerprints[rk]
        for t in seen_trips:
            self.trips[prefix + t] = feed_ts.isoformat()

        return DeltaResult(
            changed=changed, gone=gone, n_input=len(rows), n_tracked=len(self.fingerprints)
        )
