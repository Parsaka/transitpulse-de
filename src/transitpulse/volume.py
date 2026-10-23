"""Second sink: a Unity Catalog Volume, written through the Databricks Files API.

Databricks Free Edition cannot read our Azure lake (its compute has no outbound access), so the
collector pushes every raw delta into a Volume as well; Auto Loader picks it up from there. The
Azure lake stays the system of record and the only place the delta state lives.
"""

from __future__ import annotations

import logging
from typing import Protocol
from urllib.parse import quote

import httpx

from transitpulse.lake import Lake

log = logging.getLogger(__name__)


class Sink(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def describe(self) -> str: ...


class VolumeLake:
    """``put`` only (``get`` always None): the Volume is a landing zone, not the state store."""

    def __init__(
        self,
        host: str,
        token: str,
        volume_path: str,
        *,
        prefixes: tuple[str, ...] = ("raw/", "static/"),
        timeout_s: float = 60.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.host = host.rstrip("/")
        self.volume_path = "/" + volume_path.strip("/")  # /Volumes/<catalog>/<schema>/<volume>
        self.prefixes = prefixes
        self._client = client or httpx.Client(
            timeout=timeout_s, headers={"Authorization": f"Bearer {token}"}
        )

    def url(self, key: str) -> str:
        return f"{self.host}/api/2.0/fs/files{quote(self.volume_path)}/{quote(key)}?overwrite=true"

    def put(self, key: str, data: bytes) -> None:
        if not key.startswith(self.prefixes):
            return
        r = self._client.put(
            self.url(key), content=data, headers={"Content-Type": "application/octet-stream"}
        )
        if r.status_code not in (200, 201, 204):
            raise RuntimeError(f"Files API PUT {key} -> HTTP {r.status_code}: {r.text[:200]}")

    def get(self, key: str) -> bytes | None:
        return None

    def describe(self) -> str:
        return f"volume:{self.host}{self.volume_path}"


class MultiLake:
    """Writes to every sink; reads (state) only from the first one, which must be the real lake."""

    def __init__(self, primary: Lake, *sinks: Sink) -> None:
        self.primary, self.sinks = primary, list(sinks)

    def put(self, key: str, data: bytes) -> None:
        self.primary.put(key, data)
        for s in self.sinks:
            try:
                s.put(key, data)
            except Exception:
                # The primary write is done and the state is consistent; a failed secondary sink
                # is logged (and alerted on through the error count) but must not fail the run.
                log.exception("secondary sink failed", extra={"sink": s.describe(), "key": key})

    def get(self, key: str) -> bytes | None:
        return self.primary.get(key)

    def describe(self) -> str:
        return " + ".join([self.primary.describe(), *(s.describe() for s in self.sinks)])
