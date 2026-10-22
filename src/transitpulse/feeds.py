"""Registry of GTFS-Realtime feeds (see docs/data-sources.md for licences)."""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Feed:
    name: str
    url: str
    licence: str
    min_interval_s: int  # polite polling interval, never faster
    route_id_present: bool  # gtfs.de leaves route_id empty; join on trip_id later


FEEDS: dict[str, Feed] = {
    "vbb": Feed(
        name="vbb",
        url="https://production.gtfsrt.vbb.de/data",
        licence="CC BY 4.0",
        min_interval_s=30,
        route_id_present=True,
    ),
    "gtfsde": Feed(
        name="gtfsde",
        url="https://realtime.gtfs.de/realtime-free.pb",
        licence="CC BY-SA 4.0",
        min_interval_s=30,
        route_id_present=False,
    ),
}


def get_feed(name: str, url_overrides: dict[str, str] | None = None) -> Feed:
    """Return the feed; ``url_overrides`` (``TP_FEED_URLS``) replaces its URL for replay/tests."""
    try:
        feed = FEEDS[name]
    except KeyError as e:
        raise ValueError(f"unknown feed {name!r}; known: {sorted(FEEDS)}") from e
    if url_overrides and name in url_overrides:
        return replace(feed, url=url_overrides[name])
    return feed
