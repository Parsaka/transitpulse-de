"""HTTP fetch of a GTFS-RT feed with ETag caching, timeout and retry with backoff."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass

import httpx

log = logging.getLogger(__name__)

RETRY_STATUS = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class FetchResult:
    status: int
    body: bytes  # empty on 304
    etag: str | None
    last_modified: str | None
    latency_ms: float
    attempts: int

    @property
    def not_modified(self) -> bool:
        return self.status == 304


class FeedFetchError(RuntimeError):
    pass


def fetch(
    url: str,
    *,
    user_agent: str,
    etag: str | None = None,
    timeout_s: float = 20.0,
    retries: int = 3,
    client: httpx.Client | None = None,
    sleep: float | None = None,
) -> FetchResult:
    """GET the feed. Sends ``If-None-Match`` when an ETag is known (VBB answers 304).

    Retries on network errors and on 429/5xx with exponential backoff and jitter. Any other
    non-2xx status raises :class:`FeedFetchError` immediately (a 404 will not fix itself).
    """
    headers = {"User-Agent": user_agent, "Accept": "application/x-protobuf, application/protobuf"}
    if etag:
        headers["If-None-Match"] = etag
    own_client = client is None
    cl = client or httpx.Client(timeout=timeout_s, follow_redirects=True)
    t0 = time.perf_counter()
    try:
        for attempt in range(1, retries + 2):
            try:
                r = cl.get(url, headers=headers)
            except httpx.HTTPError as e:
                err: str | None = f"{type(e).__name__}: {e}"
                status = 0
            else:
                err, status = None, r.status_code
                if status in (200, 304):
                    return FetchResult(
                        status=status,
                        body=r.content if status == 200 else b"",
                        etag=r.headers.get("etag"),
                        last_modified=r.headers.get("last-modified"),
                        latency_ms=round((time.perf_counter() - t0) * 1000, 1),
                        attempts=attempt,
                    )
                if status not in RETRY_STATUS:
                    raise FeedFetchError(f"GET {url} -> HTTP {status}")
            if attempt > retries:
                raise FeedFetchError(f"GET {url} failed after {attempt} attempts: {err or status}")
            delay = (
                sleep
                if sleep is not None
                else min(30.0, 2 ** (attempt - 1)) + random.uniform(0, 0.5)
            )
            log.warning(
                "fetch retry",
                extra={
                    "url": url,
                    "attempt": attempt,
                    "status": status,
                    "error": err,
                    "sleep_s": delay,
                },
            )
            time.sleep(delay)
        raise AssertionError("unreachable")
    finally:
        if own_client:
            cl.close()
