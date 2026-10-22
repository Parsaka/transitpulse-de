"""Byte-level storage behind the collector: a local folder or an Azure Blob / ADLS Gen2 container.

Keys are forward-slash paths relative to the lake root, e.g.
``raw/stop_times/feed=vbb/date=2026-10-22/hour=21/vbb_1792705862.parquet`` or ``state/vbb.parquet``.
The Azure backend authenticates with ``DefaultAzureCredential`` (managed identity in the Function,
``az login`` on a laptop); no key is ever configured.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol


class Lake(Protocol):
    def put(self, key: str, data: bytes) -> None: ...

    def get(self, key: str) -> bytes | None: ...

    def describe(self) -> str: ...


class LocalLake:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def _path(self, key: str) -> Path:
        return self.root / Path(*key.split("/"))

    def put(self, key: str, data: bytes) -> None:
        p = self._path(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(p)  # atomic on the same filesystem

    def get(self, key: str) -> bytes | None:
        p = self._path(key)
        return p.read_bytes() if p.exists() else None

    def describe(self) -> str:
        return f"local:{self.root}"


class BlobLake:
    """One container in a storage account; ``put`` overwrites (idempotent re-runs)."""

    def __init__(self, account_url: str, container: str, credential: Any = None) -> None:
        from azure.storage.blob import ContainerClient

        if credential is None:
            from azure.identity import DefaultAzureCredential

            credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self.account_url, self.container = account_url.rstrip("/"), container
        self._client = ContainerClient(account_url, container, credential=credential)

    def put(self, key: str, data: bytes) -> None:
        self._client.upload_blob(key, data, overwrite=True)

    def get(self, key: str) -> bytes | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            return self._client.download_blob(key).readall()
        except ResourceNotFoundError:
            return None

    def describe(self) -> str:
        return f"azure:{self.account_url}/{self.container}"


def make_lake(
    backend: str, *, data_dir: Path, account_url: str = "", container: str = "lake"
) -> Lake:
    if backend == "local":
        return LocalLake(data_dir)
    if backend == "azure":
        if not account_url:
            raise ValueError("TP_ADLS_ACCOUNT_URL is required for the azure lake backend")
        return BlobLake(account_url, container)
    raise ValueError(f"unknown lake backend {backend!r}")
