"""Parse a GTFS-RT ``FeedMessage`` into flat records (one row per stop-time update / alert).

Only fields the downstream models need are kept. Unknown enum values are stored as integers so
the collector never fails on a feed extension.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from google.transit import gtfs_realtime_pb2 as rt

STOP_TIME_COLUMNS = [
    "feed",
    "feed_ts",
    "entity_id",
    "trip_id",
    "route_id",
    "start_date",
    "start_time",
    "direction_id",
    "trip_schedule_relationship",
    "vehicle_id",
    "trip_ts",
    "stop_sequence",
    "stop_id",
    "stop_schedule_relationship",
    "arrival_delay_s",
    "arrival_time",
    "departure_delay_s",
    "departure_time",
]

ALERT_COLUMNS = [
    "feed",
    "feed_ts",
    "entity_id",
    "cause",
    "effect",
    "active_from",
    "active_to",
    "header_text",
    "description_text",
    "informed_entities",
]


@dataclass
class ParsedFeed:
    feed: str
    feed_ts: datetime
    incrementality: int
    n_entities: int
    stop_times: list[dict[str, Any]] = field(default_factory=list)
    alerts: list[dict[str, Any]] = field(default_factory=list)
    trips_present: set[str] = field(default_factory=set)

    @property
    def n_trips(self) -> int:
        return len(self.trips_present)


def _ts(seconds: int) -> datetime | None:
    return datetime.fromtimestamp(seconds, tz=UTC) if seconds else None


def _translation(ts: Any, prefer: str = "de") -> str | None:
    best = None
    for t in ts.translation:
        if t.language == prefer:
            return t.text
        best = best or t.text
    return best


def parse_feed(data: bytes, feed: str) -> ParsedFeed:
    msg = rt.FeedMessage()
    msg.ParseFromString(data)
    h = msg.header
    feed_ts = _ts(h.timestamp) or datetime.now(tz=UTC)
    out = ParsedFeed(
        feed=feed, feed_ts=feed_ts, incrementality=h.incrementality, n_entities=len(msg.entity)
    )

    for e in msg.entity:
        if e.HasField("trip_update"):
            tu = e.trip_update
            trip = tu.trip
            trip_key = f"{trip.trip_id}|{trip.start_date}"
            out.trips_present.add(trip_key)
            base = {
                "feed": feed,
                "feed_ts": feed_ts,
                "entity_id": e.id,
                "trip_id": trip.trip_id,
                "route_id": trip.route_id or None,
                "start_date": trip.start_date or None,
                "start_time": trip.start_time or None,
                "direction_id": trip.direction_id if trip.HasField("direction_id") else None,
                "trip_schedule_relationship": trip.schedule_relationship,
                "vehicle_id": tu.vehicle.id or None,
                "trip_ts": _ts(tu.timestamp),
            }
            if not tu.stop_time_update:
                # cancelled trips often carry no stop times; keep one row so the cancellation shows
                out.stop_times.append(
                    {
                        **base,
                        "stop_sequence": None,
                        "stop_id": None,
                        "stop_schedule_relationship": None,
                        "arrival_delay_s": None,
                        "arrival_time": None,
                        "departure_delay_s": None,
                        "departure_time": None,
                    }
                )
            for s in tu.stop_time_update:
                out.stop_times.append(
                    {
                        **base,
                        "stop_sequence": s.stop_sequence if s.HasField("stop_sequence") else None,
                        "stop_id": s.stop_id or None,
                        "stop_schedule_relationship": s.schedule_relationship,
                        "arrival_delay_s": s.arrival.delay
                        if s.HasField("arrival") and s.arrival.HasField("delay")
                        else None,
                        "arrival_time": _ts(s.arrival.time) if s.HasField("arrival") else None,
                        "departure_delay_s": s.departure.delay
                        if s.HasField("departure") and s.departure.HasField("delay")
                        else None,
                        "departure_time": _ts(s.departure.time)
                        if s.HasField("departure")
                        else None,
                    }
                )
        if e.HasField("alert"):
            a = e.alert
            periods = list(a.active_period)
            out.alerts.append(
                {
                    "feed": feed,
                    "feed_ts": feed_ts,
                    "entity_id": e.id,
                    "cause": a.cause,
                    "effect": a.effect,
                    "active_from": _ts(periods[0].start) if periods else None,
                    "active_to": _ts(periods[-1].end) if periods else None,
                    "header_text": _translation(a.header_text),
                    "description_text": _translation(a.description_text),
                    "informed_entities": json.dumps(
                        [
                            {
                                k: v
                                for k, v in {
                                    "agency_id": ie.agency_id,
                                    "route_id": ie.route_id,
                                    "stop_id": ie.stop_id,
                                    "trip_id": ie.trip.trip_id,
                                }.items()
                                if v
                            }
                            for ie in a.informed_entity
                        ],
                        ensure_ascii=False,
                    ),
                }
            )
    return out
