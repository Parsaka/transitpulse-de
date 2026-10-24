"""Build status.json for the public status page from the gold and ops tables.

Runs in the hourly dbt workflow after the prod build. Reads through the SQL warehouse (the same
credentials dbt uses) and writes one small JSON document that the static website serves and
Grafana reads. Nothing personal, nothing secret: aggregates only.

Usage: python scripts/publish_status.py <out_path>
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime

from databricks import sql

HOST = os.environ["DATABRICKS_HOST"].replace("https://", "").strip("/")
HTTP_PATH = os.environ.get("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/a25edf12d5fff14a")


def rows(cur: sql.client.Cursor, statement: str) -> list[dict]:
    cur.execute(statement)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r, strict=True)) for r in cur.fetchall()]


def main(out_path: str) -> None:
    with sql.connect(
        server_hostname=HOST, http_path=HTTP_PATH, access_token=os.environ["DATABRICKS_TOKEN"]
    ) as conn:
        cur = conn.cursor()
        status = {
            "generated_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "slo": rows(cur, "select * from workspace.tp_ops.slo_status")[0],
            "error_budget": rows(
                cur,
                "select slo, target, window, total_events, bad_events, achieved, budget_remaining,"
                " slo_ok from workspace.tp_ops.slo_error_budget order by slo",
            ),
            "network_now": rows(
                cur,
                "select as_of, mode, active_trips, stop_events, avg_delay_min, p90_delay_min,"
                " punctuality_now from workspace.tp_gold.mart_network_now order by mode_order",
            ),
            "punctuality_daily": rows(
                cur,
                "select date_local, mode, stop_events, scored_events, late_events,"
                " cancelled_events, punctuality, trips from workspace.tp_gold.mart_punctuality_daily"
                " where agency_name = '(all agencies)' and date_local >= current_date() - interval 14 days"
                " order by date_local, mode_order",
            ),
            "collector_daily": rows(
                cur,
                "select run_date, runs, succeeded, success_rate, p50_duration_ms, p95_duration_ms,"
                " rows_written, avg_reduction from workspace.tp_ops.slo_collector_daily"
                " where run_date >= current_date() - interval 14 days order by run_date",
            ),
            "forecast_quality": rows(
                cur,
                "select service_date, mode, model_version, trips_scored, mae_model_min, mae_naive_min,"
                " skill, avg_stops_ahead from workspace.tp_ops.mart_forecast_quality"
                " where service_date >= current_date() - interval 14 days order by service_date, mode",
            ),
            "anomalies_recent": rows(
                cur,
                "select checked_at, as_of, hour_local, events, avg_delay_min, base_avg_delay_min, z_delay,"
                " is_anomaly from workspace.tp_ops.network_anomalies order by checked_at desc limit 12",
            ),
            "pipeline_updates_recent": rows(
                cur,
                "select started_at, final_state, succeeded, duration_min from"
                " workspace.tp_ops.slo_pipeline_updates where final_state is not null"
                " order by started_at desc limit 48",
            ),
        }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(status, f, indent=1, default=str)
    print(json.dumps({k: (len(v) if isinstance(v, list) else "1 row") for k, v in status.items()}))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "status.json")
