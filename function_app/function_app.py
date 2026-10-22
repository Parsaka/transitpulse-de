"""Azure Functions entry point: a timer trigger that runs the collector for each configured feed.

Settings come from app settings (``TP_*``). The schedule is an app setting too (``TP_SCHEDULE``,
NCRONTAB, default every minute) so the polling interval can be changed without a deployment,
which is what the phase-6 interval experiment needs. The timer is a singleton: the host never
runs two instances at once, so the delta state cannot be corrupted by overlapping runs.
"""

from __future__ import annotations

import logging
import os

import azure.functions as func

from transitpulse import logging as tplog
from transitpulse.collector import RunSummary, run_once
from transitpulse.config import get_settings
from transitpulse.feeds import get_feed

app = func.FunctionApp()
log = logging.getLogger("transitpulse.function")


def collect_all(feeds: str) -> list[RunSummary]:
    """Run every feed in ``feeds`` (comma separated) and return the summaries."""
    settings = get_settings()
    tplog.configure(settings.log_format)
    lake = settings.lake()
    summaries = []
    for name in [f.strip() for f in feeds.split(",") if f.strip()]:
        summaries.append(run_once(get_feed(name, settings.feed_urls), settings, lake=lake))
    return summaries


@app.timer_trigger(
    schedule="%TP_SCHEDULE%", arg_name="timer", run_on_startup=False, use_monitor=True
)
def collect(timer: func.TimerRequest) -> None:
    if timer.past_due:
        log.warning("timer is past due; running anyway")
    summaries = collect_all(os.environ.get("TP_FEEDS", "vbb"))
    failed = [s for s in summaries if s.status == "error"]
    if failed:
        # Raise so the host records a failed execution (metric alert + Monitor); the summaries
        # were already logged with full detail by the collector.
        raise RuntimeError(f"{len(failed)} of {len(summaries)} feed runs failed: {failed[0].error}")
