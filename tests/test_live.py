"""Network tests: run with ``pytest -m live``; skipped in CI."""

from __future__ import annotations

import pytest

from transitpulse.config import get_settings
from transitpulse.feeds import get_feed
from transitpulse.gtfsrt.fetch import fetch
from transitpulse.gtfsrt.parse import parse_feed


@pytest.mark.live
@pytest.mark.parametrize("name", ["vbb", "gtfsde"])
def test_feed_is_reachable_and_fresh(name: str) -> None:
    f = get_feed(name)
    r = fetch(f.url, user_agent=get_settings().user_agent)
    assert r.status == 200 and len(r.body) > 100_000
    p = parse_feed(r.body, name)
    assert p.n_trips > 100
