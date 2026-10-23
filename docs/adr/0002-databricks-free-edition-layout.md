# ADR 0002: Databricks Free Edition layout and the bridge from the Azure lake

Date: 2026-10-23. Status: accepted.

## Context
Databricks Free Edition (workspace `dbc-2fb26299-f7ca`, the same account that ran the two AWS
portfolio projects in July 2026) was checked against the four open questions of ADR 0001:

| Question | Result |
|---|---|
| Non-interactive auth | Personal access tokens work (`databricks tokens create`, 90 days). OAuth U2M works for the CLI. No account API, so no service principal with OAuth secret. |
| Files API upload into a Volume | Works (`PUT /api/2.0/fs/files/Volumes/...?overwrite=true`, HTTP 204, directories created on the fly). |
| Bundle deploy | Works with serverless: schemas, Volume, pipeline and job from `databricks bundle deploy`. |
| Catalog creation | **Not** through the API (`Metastore storage root URL does not exist. Default Storage is enabled`) and the SQL Statement Execution endpoint answers 404 on Free Edition. A catalog can only be created in the UI. |
| Auto Loader on a Volume with serverless | see docs/databricks.md (first pipeline run) |

## Decision
- The project lives in the built-in `workspace` catalog with prefixed schemas `tp_landing`,
  `tp_bronze`, `tp_silver`, `tp_gold`, `tp_ops` (bundle variables `catalog`, `schema_prefix`).
  The earlier retail project owns `bronze`, `silver`, `gold`, `monitoring`, `retail_forecasting` in
  the same catalog; the prefix keeps them apart. Moving to a dedicated catalog later is a variable.
- Development mode prefixes resource names with `dev_<user>_`; every reference inside the bundle
  therefore goes through `${resources.schemas.<x>.name}`, never through the literal name.
- The Azure Function pushes each raw delta and the static schedule into the landing Volume through
  the Files API with a 90-day token kept in Key Vault; the Azure lake stays the system of record
  and the only home of the delta state. A failing Volume write is logged and counted, never fatal.
- One pipeline per target (`dev` paused, `prod` scheduled every 15 minutes). The Free Edition
  limit of one active pipeline per type is respected because `dev` only runs by hand.

## Consequences
- Token rotation every 90 days is an operational task (runbook); the alert fires if the Function
  starts failing to upload (phase 4 adds a specific check on landing freshness).
- The workspace shares quota with the earlier projects; nothing else runs there on a schedule.
