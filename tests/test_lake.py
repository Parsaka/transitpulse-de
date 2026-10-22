from __future__ import annotations

from pathlib import Path

import pytest

from transitpulse.lake import LocalLake, make_lake


def test_local_lake_put_get(tmp_path: Path) -> None:
    lake = LocalLake(tmp_path)
    assert lake.get("state/x.parquet") is None
    lake.put("raw/a/b=1/c.parquet", b"123")
    assert (tmp_path / "raw" / "a" / "b=1" / "c.parquet").read_bytes() == b"123"
    lake.put("raw/a/b=1/c.parquet", b"4567")  # overwrite, no leftovers
    assert lake.get("raw/a/b=1/c.parquet") == b"4567"
    assert sorted(p.name for p in (tmp_path / "raw" / "a" / "b=1").iterdir()) == ["c.parquet"]
    assert lake.describe().startswith("local:")


def test_make_lake(tmp_path: Path) -> None:
    assert isinstance(make_lake("local", data_dir=tmp_path), LocalLake)
    with pytest.raises(ValueError, match="TP_ADLS_ACCOUNT_URL"):
        make_lake("azure", data_dir=tmp_path)
    with pytest.raises(ValueError, match="unknown lake backend"):
        make_lake("s3", data_dir=tmp_path)


def test_blob_lake_against_fake_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """BlobLake talks to ContainerClient only through upload_blob/download_blob."""
    from transitpulse import lake as lake_mod

    class FakeDownload:
        def __init__(self, data: bytes) -> None:
            self._d = data

        def readall(self) -> bytes:
            return self._d

    class FakeContainer:
        store: dict[str, bytes] = {}

        def __init__(self, url: str, container: str, credential: object = None) -> None:
            self.url, self.container = url, container

        def upload_blob(self, name: str, data: bytes, overwrite: bool = False) -> None:
            assert overwrite
            self.store[name] = data

        def download_blob(self, name: str) -> FakeDownload:
            from azure.core.exceptions import ResourceNotFoundError

            if name not in self.store:
                raise ResourceNotFoundError("nope")
            return FakeDownload(self.store[name])

    import azure.storage.blob as blob

    monkeypatch.setattr(blob, "ContainerClient", FakeContainer)
    lk = lake_mod.BlobLake("https://acct.blob.core.windows.net", "lake", credential=object())
    assert lk.get("state/vbb.parquet") is None
    lk.put("state/vbb.parquet", b"zz")
    assert lk.get("state/vbb.parquet") == b"zz"
    assert lk.describe() == "azure:https://acct.blob.core.windows.net/lake"
