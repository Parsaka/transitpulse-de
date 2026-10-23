# TransitPulse DE

Streaming lakehouse for German public-transport punctuality, built on a zero-cash budget.

Every minute a collector reads the GTFS-Realtime feeds of VBB (Berlin-Brandenburg) and, later,
gtfs.de (all of Germany), keeps only what changed, and lands it in a data lake. Databricks
(Free Edition) turns it into bronze, silver and dbt gold tables: punctuality per line and hour,
delay propagation, cancellations, weather impact and a forward-looking delay forecast. The whole
pipeline watches itself with SLOs and alerts, and every optimisation is measured before and after.

**Status: phase 1 done (2026-10-22).** The collector runs every minute in Azure (Functions,
Consumption plan, managed identity) and writes deltas to an ADLS Gen2 lake; the whole Azure side
is Terraform, CI plans it through OIDC, and one alert plus a 2-per-month budget watch it. No
Databricks, dbt or dashboards yet: see the roadmap. Nothing below is a claim about anything the
roadmap does not mark done.

## What exists today
- `transitpulse collect --feed vbb --once`: fetch with ETag, parse, delta against the previous
  snapshot, write zstd Parquet partitions (`raw/<dataset>/feed=/date=/hour=/`) to a local folder or
  to Azure Blob (managed identity, no keys), JSON logs with per-step durations and a run summary.
- Azure Function `collect` (timer, schedule from an app setting) running the same code every 60 s;
  Terraform for the lake, Function, Log Analytics + Application Insights, Key Vault, alert, budget
  and the GitHub OIDC identity ([docs/azure-setup.md](docs/azure-setup.md)).
- CI: ruff, mypy, 42 offline tests on trimmed real feeds, Terraform validate and an OIDC plan,
  and a smoke test that runs the deployable package in the official Functions image with Azurite.
- `transitpulse inspect <file.pb>`: delay distribution of a saved feed.

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

The delta store suppressed about 99% of the rows.

**Delta state encoding** (same 123k tracked stop-time updates): JSON with full fingerprints
11.7 MB; Parquet with 64-bit hashed fingerprints 0.65 MB, an 18x reduction.

**In Azure** (Function, Consumption plan, 2026-10-22 23:52 to 00:02 UTC, after the deployment fix):
11 of 11 executions succeeded, one per minute; 1.7 to 2.6 s warm, 4.1 s on the cold start; each
run wrote one stop-time delta file of 9 to 13 KB and one gone-trips file of about 1.8 KB; the
state blob is 0.6 MB. Before the fix, 26 executions had failed in 25 ms each (`GLIBC` import
error), which is what the smoke test now catches in CI. Storage per day, GB-seconds against the
free grant and polling trade-offs are measured in phase 6, not estimated.

## Plan and operations
See [docs/roadmap.md](docs/roadmap.md) (phases), [docs/adr/0001-free-tier-architecture.md](docs/adr/0001-free-tier-architecture.md)
(why the collector lives outside Databricks), [docs/budget.md](docs/budget.md) (how it stays at
zero cash), [docs/azure-setup.md](docs/azure-setup.md) (the stack and the lessons from deploying
it), [docs/runbook.md](docs/runbook.md) (alerts, queries, failures) and
[docs/data-sources.md](docs/data-sources.md) (licences).

## Development
```bash
python -m venv .venv && .venv/Scripts/activate   # or source .venv/bin/activate
pip install -e ".[dev]"
pytest                      # offline
pytest -m live              # hits the real feeds
ruff check . && ruff format . && mypy
scripts/smoke_function.sh   # the deployable package in the Functions image (Docker, ~3 min)
```

Data: VBB (CC BY 4.0), gtfs.de (CC BY-SA 4.0), Deutscher Wetterdienst. Code: MIT.
