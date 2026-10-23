from __future__ import annotations

import threading
import time
from pathlib import Path

from transitpulse.lake import LocalLake
from transitpulse.volume import MultiLake


class SlowSink:
    def __init__(self, delay: float, fail: bool = False) -> None:
        self.delay, self.fail, self.calls, self.threads = delay, fail, [], set()

    def put(self, key: str, data: bytes) -> None:
        self.threads.add(threading.get_ident())
        time.sleep(self.delay)
        if self.fail:
            raise RuntimeError("sink down")
        self.calls.append(key)

    def describe(self) -> str:
        return "slow"


def test_sinks_run_concurrently_with_the_primary(tmp_path: Path) -> None:
    a, b = SlowSink(0.3), SlowSink(0.3)
    ml = MultiLake(LocalLake(tmp_path), a, b)
    t0 = time.perf_counter()
    ml.put("raw/x.parquet", b"1")
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.55, f"sequential would take 0.6 s, took {elapsed:.2f}"
    assert a.calls == b.calls == ["raw/x.parquet"]
    assert (tmp_path / "raw" / "x.parquet").read_bytes() == b"1"


def test_failed_sink_does_not_fail_the_primary(tmp_path: Path) -> None:
    ml = MultiLake(LocalLake(tmp_path), SlowSink(0.01, fail=True))
    ml.put("raw/y.parquet", b"2")
    assert (tmp_path / "raw" / "y.parquet").exists()
