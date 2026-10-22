"""One collector run: fetch → parse → delta → write, with a machine-readable run summary.

The same function is called by the CLI (local), by the Azure Function (phase 1) and by tests.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Literal

from transitpulse import logging as tplog
from transitpulse.config import Settings
from transitpulse.delta import DeltaStore
from transitpulse.feeds import Feed
from transitpulse.gtfsrt.fetch import FetchResult, fetch
from transitpulse.gtfsrt.parse import parse_feed
from transitpulse.storage import write_rows

log = logging.getLogger(__name__)

Mode = Literal["delta", "snapshot"]


@dataclass
class RunSummary:
    run_id: str
    feed: str
    mode: Mode
    started_at: str
    status: str  # ok | not_modified | error
    http_status: int = 0
    fetch_ms: float = 0.0
    bytes: int = 0
    feed_ts: str | None = None
    feed_age_s: float | None = None
    n_entities: int = 0
    n_trips: int = 0
    n_stop_times: int = 0
    n_written_stop_times: int = 0
    n_alerts: int = 0
    n_trips_gone: int = 0
    reduction: float = 0.0
    files: list[str] | None = None
    error: str | None = None
    total_ms: float = 0.0


def run_once(
    feed: Feed,
    settings: Settings,
    *,
    mode: Mode = "delta",
    body: bytes | None = None,
    now: datetime | None = None,
) -> RunSummary:
    """Collect one snapshot of ``feed``. ``body`` bypasses HTTP (tests, replay)."""
    run_id = uuid.uuid4().hex[:12]
    started = now or datetime.now(tz=UTC)
    tplog.bind(run_id=run_id, feed=feed.name)
    summary = RunSummary(
        run_id=run_id,
        feed=feed.name,
        mode=mode,
        started_at=started.isoformat(),
        status="ok",
        files=[],
    )
    state_path = settings.state_dir / f"{feed.name}.json"
    store = DeltaStore.load(state_path)
    try:
        with tplog.Timed(log, "fetch") as t:
            if body is None:
                res = fetch(
                    feed.url,
                    user_agent=settings.user_agent,
                    etag=store.etags.get(feed.name),
                    timeout_s=settings.http_timeout_s,
                    retries=settings.http_retries,
                )
            else:
                res = FetchResult(200, body, None, None, 0.0, 1)
            summary.http_status, summary.fetch_ms, summary.bytes = (
                res.status,
                res.latency_ms,
                len(res.body),
            )
            t.fields.update(http_status=res.status, bytes=len(res.body))
        if res.not_modified:
            summary.status = "not_modified"
            return summary
        if res.etag:
            store.etags[feed.name] = res.etag

        with tplog.Timed(log, "parse") as t:
            parsed = parse_feed(res.body, feed.name)
            summary.feed_ts = parsed.feed_ts.isoformat()
            summary.feed_age_s = round((started - parsed.feed_ts).total_seconds(), 1)
            summary.n_entities, summary.n_trips = parsed.n_entities, parsed.n_trips
            summary.n_stop_times, summary.n_alerts = len(parsed.stop_times), len(parsed.alerts)
            t.fields.update(entities=parsed.n_entities, stop_times=len(parsed.stop_times))

        if mode == "delta":
            with tplog.Timed(log, "delta") as t:
                d = store.apply(parsed.stop_times, parsed.feed_ts, feed=feed.name)
                rows, gone, summary.reduction = d.changed, d.gone, round(d.reduction, 4)
                t.fields.update(changed=len(rows), gone=len(gone), reduction=summary.reduction)
        else:
            rows, gone = parsed.stop_times, []

        with tplog.Timed(log, "write") as t:
            root = settings.data_dir
            for dataset, data in (
                ("stop_times", rows),
                ("alerts", parsed.alerts),
                ("trips_gone", gone),
            ):
                p = write_rows(
                    data, root=root, dataset=dataset, feed=feed.name, feed_ts=parsed.feed_ts
                )
                if p:
                    summary.files.append(str(p))  # type: ignore[union-attr]
            summary.n_written_stop_times, summary.n_trips_gone = len(rows), len(gone)
            t.fields.update(files=len(summary.files or []))
        store.save(state_path)
        return summary
    except Exception as e:  # the Function must log and continue; the summary carries the error
        summary.status, summary.error = "error", f"{type(e).__name__}: {e}"
        log.exception("collector run failed")
        return summary
    finally:
        summary.total_ms = round((datetime.now(tz=UTC) - started).total_seconds() * 1000, 1)
        log.info("run summary", extra={"summary": asdict(summary)})
        tplog.clear()
