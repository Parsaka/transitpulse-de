# TransitPulse DE

Streaming lakehouse for German public-transport punctuality, built on a zero-cash budget.

Every minute a collector reads the GTFS-Realtime feeds of VBB (Berlin-Brandenburg) and, later,
gtfs.de (all of Germany), keeps only what changed, and lands it in a data lake. Databricks
(Free Edition) turns it into bronze, silver and dbt gold tables: punctuality per line and hour,
delay propagation, cancellations, weather impact and a forward-looking delay forecast. The whole
pipeline watches itself with SLOs and alerts, and every optimisation is measured before and after.

**Status: phase 0 (foundation).** Only the collector exists so far. Nothing below is a claim
about production until the roadmap marks it done.

## What exists today
- `transitpulse collect --feed vbb --once`: fetch with ETag, parse, delta against the previous
  snapshot, write zstd Parquet partitions (`raw/<dataset>/feed=/date=/hour=/`), JSON logs with
  per-step durations and a run summary.
- `transitpulse inspect <file.pb>`: delay distribution of a saved feed.
- Offline test suite on trimmed real feeds (`tests/fixtures/`), ruff, mypy, CI.

## Measured so far (2026-10-22, laptop, single fetch)
| Feed | Size per fetch | Trip updates | Stop-time updates | Fetch latency |
|---|---|---|---|---|
| VBB | 6.3 MB | 6,455 | 124,193 | 0.9 s |
| gtfs.de (nationwide) | 8.3 MB | 24,957 (+374 alerts) | 191,398 | 1.0 s |

Three consecutive live polls of VBB, 60 s apart, delta mode (same laptop, 2026-10-22 21:51 UTC):

| Poll | Stop-time updates in feed | Rows written | Parquet size | Trips gone | Run time |
|---|---|---|---|---|---|
| 1 (cold store) | 122,775 | 122,775 | 688 KB | 0 | 5.7 s |
| 2 | 122,581 | 793 (0.65%) | 15 KB | 29 | 3.6 s |
| 3 | 122,981 | 1,391 (1.13%) | 24 KB | 22 | 5.0 s |

The delta store suppressed about 99% of the rows. Open issue carried into phase 1: the state file
(fingerprints for 123k stop-time updates as JSON) is 11.7 MB; the Azure Function will need a
compact encoding. Storage per day and polling trade-offs are measured in phase 6, not estimated.

## Plan
See [docs/roadmap.md](docs/roadmap.md) (phases), [docs/adr/0001-free-tier-architecture.md](docs/adr/0001-free-tier-architecture.md)
(why the collector lives outside Databricks), [docs/budget.md](docs/budget.md) (how it stays at
zero cash) and [docs/data-sources.md](docs/data-sources.md) (licences).

## Development
```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # offline
pytest -m live              # hits the real feeds
ruff check . && ruff format . && mypy
```

Data: VBB (CC BY 4.0), gtfs.de (CC BY-SA 4.0), Deutscher Wetterdienst. Code: MIT.
