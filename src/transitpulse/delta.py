"""Delta detection between consecutive feed snapshots.

A GTFS-RT feed repeats every active trip on every poll (6 MB a minute for VBB). Most stop-time
updates do not change from one poll to the next, so the collector keeps a fingerprint per
``(trip_id, start_date, stop_sequence|stop_id)`` and emits only rows whose fingerprint changed,
plus one ``trip_gone`` marker when a trip disappears from the feed (completed or dropped). The
store is a plain dict persisted as JSON; the Azure Function keeps it in a blob (phase 1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

FINGERPRINT_FIELDS = (
    "arrival_delay_s",
    "departure_delay_s",
    "arrival_time",
    "departure_time",
    "stop_schedule_relationship",
    "trip_schedule_relationship",
)


def row_key(row: dict[str, Any]) -> str:
    stop = (
        row["stop_sequence"] if row.get("stop_sequence") is not None else row.get("stop_id") or ""
    )
    return f"{row['trip_id']}|{row.get('start_date') or ''}|{stop}"


def trip_key(row: dict[str, Any]) -> str:
    return f"{row['trip_id']}|{row.get('start_date') or ''}"


def fingerprint(row: dict[str, Any]) -> str:
    parts = []
    for f in FINGERPRINT_FIELDS:
        v = row.get(f)
        parts.append(v.isoformat() if isinstance(v, datetime) else str(v))
    return "|".join(parts)


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

    @classmethod
    def load(cls, path: Path) -> DeltaStore:
        if not path.exists():
            return cls()
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            fingerprints=raw.get("fingerprints", {}),
            trips=raw.get("trips", {}),
            etags=raw.get("etags", {}),
        )

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(
            json.dumps(
                {"fingerprints": self.fingerprints, "trips": self.trips, "etags": self.etags}
            ),
            encoding="utf-8",
        )
        tmp.replace(path)  # atomic on the same filesystem

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
        for tk in [t for t in self.trips if t.startswith(prefix)]:
            bare = tk[len(prefix) :]
            if bare not in seen_trips:
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
                tp = f"{trip_id}|{start_date}|"
                for rk in [r for r in self.fingerprints if r.startswith(tp)]:
                    del self.fingerprints[rk]
        for t in seen_trips:
            self.trips[prefix + t] = feed_ts.isoformat()

        return DeltaResult(
            changed=changed, gone=gone, n_input=len(rows), n_tracked=len(self.fingerprints)
        )
