from __future__ import annotations

import httpx
import pytest
import respx

from transitpulse.gtfsrt.fetch import FeedFetchError, fetch

URL = "https://example.test/data"


@respx.mock
def test_ok_with_etag_header() -> None:
    respx.get(URL).mock(
        return_value=httpx.Response(200, content=b"\x0a\x00", headers={"ETag": '"e1"'})
    )
    r = fetch(URL, user_agent="ua", sleep=0)
    assert r.status == 200 and r.body == b"\x0a\x00" and r.etag == '"e1"' and r.attempts == 1
    sent = respx.calls.last.request
    assert sent.headers["user-agent"] == "ua"
    assert "if-none-match" not in sent.headers


@respx.mock
def test_not_modified_sends_if_none_match() -> None:
    respx.get(URL).mock(return_value=httpx.Response(304))
    r = fetch(URL, user_agent="ua", etag='"e1"', sleep=0)
    assert r.not_modified and r.body == b""
    assert respx.calls.last.request.headers["if-none-match"] == '"e1"'


@respx.mock
def test_retries_on_503_then_succeeds() -> None:
    route = respx.get(URL)
    route.side_effect = [
        httpx.Response(503),
        httpx.Response(503),
        httpx.Response(200, content=b"ok"),
    ]
    r = fetch(URL, user_agent="ua", retries=3, sleep=0)
    assert r.status == 200 and r.attempts == 3


@respx.mock
def test_gives_up_after_retries() -> None:
    respx.get(URL).mock(return_value=httpx.Response(503))
    with pytest.raises(FeedFetchError, match="after 3 attempts"):
        fetch(URL, user_agent="ua", retries=2, sleep=0)


@respx.mock
def test_404_is_not_retried() -> None:
    route = respx.get(URL).mock(return_value=httpx.Response(404))
    with pytest.raises(FeedFetchError, match="HTTP 404"):
        fetch(URL, user_agent="ua", retries=3, sleep=0)
    assert route.call_count == 1


@respx.mock
def test_network_error_is_retried() -> None:
    route = respx.get(URL)
    route.side_effect = [httpx.ConnectError("boom"), httpx.Response(200, content=b"ok")]
    r = fetch(URL, user_agent="ua", sleep=0)
    assert r.status == 200 and r.attempts == 2
