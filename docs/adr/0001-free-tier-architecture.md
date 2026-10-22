# ADR 0001: Free-tier architecture with the collector outside Databricks

Date: 2026-10-22. Status: accepted.

## Context
Databricks Free Edition offers Unity Catalog, serverless compute, Lakeflow pipelines, SQL
warehouses, dashboards and alerts at no cost, but outbound internet access from its compute is
limited to trusted domains, there is one active pipeline per type, five concurrent job tasks and no
account-level API. The project budget is zero cash.

## Decision
- The collector runs outside Databricks as an Azure Function (Consumption, free grant), polls the
  GTFS-RT feeds every 60 s, keeps only changed stop-time updates and writes Parquet to our own
  ADLS Gen2 lake (system of record) and to a Unity Catalog Volume through the Files API.
- Databricks reads the Volume with Auto Loader in a single Lakeflow Declarative Pipeline that
  holds every bronze and silver table. Gold is built by dbt-databricks on the SQL warehouse.
- Kafka appears in two places only: Redpanda in Docker for local development and Azure Event Hubs
  (Kafka endpoint) during the two-week Tier B on Azure Databricks Premium.
- Terraform manages every Azure resource (all free-tier eligible) including the budget alert.

## Consequences
- Streaming latency is bounded by the polling interval plus the pipeline trigger, not by a message
  bus; the interval is a measured trade-off (phase 6).
- Four Free Edition details are unverified and checked in phase 2: personal access tokens, Files
  API upload quota, Auto Loader on Volumes with serverless, bundle deploy. Fallbacks are listed in
  `docs/roadmap.md`.
