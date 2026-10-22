# TransitPulse DE – guide for Claude Code

Portfolio project: streaming lakehouse for German public-transport punctuality.
Sources: GTFS-Realtime (VBB Berlin-Brandenburg first, gtfs.de nationwide second), DWD weather.
Stack: Python collector (Azure Functions) → ADLS Gen2 + Databricks Free Edition (Unity Catalog,
Lakeflow Declarative Pipelines, dbt-databricks, MLflow) → Grafana Cloud / Azure Monitor alerts →
public project page. Infra with Terraform, CI/CD with GitHub Actions (OIDC), bundles for Databricks.

## Hard constraints
- **Budget: zero cash, at most 2 EUR/month from the Azure for Students credit.** Every Azure resource
  must be free-tier eligible; a budget alert at 2 EUR is part of the Terraform. Ask before creating
  anything that is not in `docs/budget.md`.
- Python 3.11+, `src/` layout, package `transitpulse`. ruff + mypy + pytest. Small PRs per phase
  (`docs/roadmap.md`).
- Writes are **idempotent**: file names derive from the feed header timestamp; re-runs overwrite.
- Collector stores **deltas** (changed stop-time updates) by default; snapshot mode exists only for
  the measured comparison in `docs/optimisation.md`.
- Tests never hit the network (`@pytest.mark.live` for the few that do; skipped in CI). Fixtures are
  trimmed real feed files in `tests/fixtures/`.
- No secrets in Git: `.env` locally, Key Vault / GitHub OIDC in the cloud.
- Every dataset has source + licence in `docs/data-sources.md`. Send an informative User-Agent.
- README numbers must be measured, never estimated. Keep `docs/slo.md`, `docs/optimisation.md`
  and `docs/cost.md` in sync with real runs.

## Commands
- `pip install -e ".[dev]"` · `pytest` · `ruff check . && ruff format .` · `mypy`
- `transitpulse collect --feed vbb --once` · `transitpulse inspect tests/fixtures/vbb_sample.pb`
