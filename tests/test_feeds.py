from __future__ import annotations

import pytest

from transitpulse.config import Settings
from transitpulse.feeds import FEEDS, get_feed


def test_known_feeds_have_licence_and_polite_interval() -> None:
    for f in FEEDS.values():
        assert f.licence.startswith("CC BY") and f.min_interval_s >= 30


def test_unknown_feed() -> None:
    with pytest.raises(ValueError, match="unknown feed"):
        get_feed("nope")


def test_url_override_from_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TP_FEED_URLS", '{"vbb": "http://fixture:8000/vbb_sample.pb"}')
    s = Settings()
    assert get_feed("vbb", s.feed_urls).url == "http://fixture:8000/vbb_sample.pb"
    assert get_feed("gtfsde", s.feed_urls).url == FEEDS["gtfsde"].url
    assert get_feed("vbb").url == FEEDS["vbb"].url, "the registry itself is untouched"
