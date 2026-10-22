"""Command-line interface: ``transitpulse collect`` and ``transitpulse inspect``."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from pathlib import Path

import typer

from transitpulse import __version__
from transitpulse import logging as tplog
from transitpulse.collector import run_once
from transitpulse.config import get_settings
from transitpulse.feeds import FEEDS, get_feed
from transitpulse.gtfsrt.parse import parse_feed

app = typer.Typer(no_args_is_help=True, add_completion=False, help="TransitPulse DE collector")


@app.callback()
def _main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    s = get_settings()
    tplog.configure(s.log_format, logging.DEBUG if verbose else logging.INFO)


@app.command()
def version() -> None:
    typer.echo(__version__)


@app.command()
def collect(
    feed: str = typer.Option("vbb", help=f"one of {sorted(FEEDS)}"),
    once: bool = typer.Option(False, help="single run (default: loop until --runs or Ctrl-C)"),
    interval: int = typer.Option(60, help="seconds between polls"),
    runs: int = typer.Option(0, help="stop after N runs (0 = unlimited)"),
    mode: str = typer.Option("delta", help="delta | snapshot"),
) -> None:
    """Poll a GTFS-RT feed and write Parquet deltas to TP_DATA_DIR."""
    s = get_settings()
    f = get_feed(feed, s.feed_urls)
    if interval < f.min_interval_s:
        raise typer.BadParameter(f"{feed} must not be polled faster than every {f.min_interval_s}s")
    n = 0
    while True:
        summary = run_once(f, s, mode=mode)  # type: ignore[arg-type]
        n += 1
        typer.echo(json.dumps(asdict(summary)))
        if once or (runs and n >= runs):
            raise typer.Exit(code=0 if summary.status != "error" else 1)
        time.sleep(max(0.0, interval - summary.total_ms / 1000))


@app.command()
def inspect(path: Path, feed: str = "vbb") -> None:
    """Summarise a saved .pb feed file (entities, trips, delay distribution)."""
    parsed = parse_feed(path.read_bytes(), feed)
    delays = sorted(
        r["arrival_delay_s"] for r in parsed.stop_times if r["arrival_delay_s"] is not None
    )
    out = {
        "feed_ts": parsed.feed_ts.isoformat(),
        "entities": parsed.n_entities,
        "trips": parsed.n_trips,
        "stop_times": len(parsed.stop_times),
        "alerts": len(parsed.alerts),
        "with_arrival_delay": len(delays),
    }
    if delays:
        q = lambda p: delays[min(len(delays) - 1, int(p * len(delays)))]  # noqa: E731
        out.update(
            delay_p50_s=q(0.5),
            delay_p90_s=q(0.9),
            delay_max_s=delays[-1],
            share_late_over_6min=round(sum(d >= 360 for d in delays) / len(delays), 4),
        )
    typer.echo(json.dumps(out, indent=2))


if __name__ == "__main__":
    app()
