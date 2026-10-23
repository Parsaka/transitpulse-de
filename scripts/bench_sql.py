"""SQL benchmark on the serverless warehouse: typical gold queries, N runs each, plus table layout.

Reports median and p95 wall time per query (client side, warm warehouse) and, for each table,
the number of files, size and clustering columns from DESCRIBE DETAIL. Run before and after
OPTIMIZE / liquid clustering changes.

Usage: python scripts/bench_sql.py [--runs 5] [--label before]
Env: DATABRICKS_HOST, DATABRICKS_TOKEN (same as dbt)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import time

from databricks import sql

HOST = os.environ["DATABRICKS_HOST"].replace("https://", "").strip("/")
HTTP_PATH = os.environ.get("DATABRICKS_HTTP_PATH", "/sql/1.0/warehouses/a25edf12d5fff14a")

QUERIES = {
    "latest_by_hour_mode": """
        select date_trunc('hour', coalesce(arrival_time, departure_time)) as h, r.route_type,
               count(*) n, avg(coalesce(arrival_delay_s, departure_delay_s)) d
        from workspace.tp_silver.silver_stop_time_latest l
        join workspace.tp_silver.dim_routes r on l.route_id = r.route_id
        group by 1, 2""",
    "updates_one_day_trip_scan": """
        select trip_id, count(*) n, max(arrival_delay_s) m
        from workspace.tp_silver.silver_stop_time_updates
        where feed_date = current_date() group by trip_id order by n desc limit 20""",
    "punctuality_hourly_filter": """
        select mode, sum(scored_events) ev, sum(late_events) late
        from workspace.tp_gold.mart_punctuality_hourly
        where date_local = current_date() and mode = 'bus' group by mode""",
    "network_now_full": "select * from workspace.tp_gold.mart_network_now",
    "collector_runs_day": """
        select run_date, count(*) n, avg(duration_ms) d
        from workspace.tp_silver.silver_collector_runs group by run_date""",
}

TABLES = [
    "workspace.tp_bronze.bronze_stop_times",
    "workspace.tp_silver.silver_stop_time_updates",
    "workspace.tp_silver.silver_stop_time_latest",
    "workspace.tp_gold.mart_punctuality_hourly",
    "workspace.tp_gold.mart_punctuality_daily",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    out: dict = {"label": a.label, "runs": a.runs, "queries": {}, "tables": {}}
    with sql.connect(
        server_hostname=HOST, http_path=HTTP_PATH, access_token=os.environ["DATABRICKS_TOKEN"]
    ) as conn:
        cur = conn.cursor()
        cur.execute("select 1")  # warm the warehouse and the session
        cur.fetchall()
        for name, q in QUERIES.items():
            times = []
            for _ in range(a.runs):
                t0 = time.perf_counter()
                cur.execute(q)
                cur.fetchall()
                times.append((time.perf_counter() - t0) * 1000)
            out["queries"][name] = {
                "median_ms": round(statistics.median(times)),
                "p95_ms": round(sorted(times)[max(0, int(len(times) * 0.95) - 1)]),
                "min_ms": round(min(times)),
            }
        for t in TABLES:
            try:
                cur.execute(f"describe detail {t}")
            except Exception as e:  # materialized views have no DESCRIBE DETAIL
                out["tables"][t.split(".", 1)[1]] = {"note": str(e).split(";")[0][:80]}
                continue
            cols = [d[0] for d in cur.description]
            row = dict(zip(cols, cur.fetchone(), strict=True))
            out["tables"][t.split(".", 1)[1]] = {
                "num_files": row.get("numFiles"),
                "size_mb": round((row.get("sizeInBytes") or 0) / 1e6, 1),
                "clustering": row.get("clusteringColumns"),
            }
    print(json.dumps(out, indent=1, default=str))


if __name__ == "__main__":
    main()
