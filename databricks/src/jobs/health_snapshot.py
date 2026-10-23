"""Health snapshot: row counts, freshness and expectation results -> JSON in the landing Volume.

Runs as a serverless Python task after each pipeline refresh. Free Edition exposes neither the
SQL statement API nor event details through the pipelines API, so this file is how numbers get
out of the lakehouse without a notebook: the Files API can read it from anywhere.
"""

import json
import os
import sys
from datetime import UTC, datetime

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

spark = SparkSession.builder.getOrCreate()
catalog, bronze, silver, ops, out_path = sys.argv[1:6]

TABLES = {
    f"{catalog}.{bronze}.bronze_stop_times": "feed_ts",
    f"{catalog}.{bronze}.bronze_trips_gone": "feed_ts",
    f"{catalog}.{bronze}.bronze_alerts": "feed_ts",
    f"{catalog}.{silver}.silver_stop_time_updates": "feed_ts",
    f"{catalog}.{silver}.silver_trips_gone": "feed_ts",
    f"{catalog}.{silver}.silver_alerts": "feed_ts",
    f"{catalog}.{silver}.silver_stop_time_latest": "feed_ts",
    f"{catalog}.{silver}.dim_agency": None,
    f"{catalog}.{silver}.dim_routes": None,
    f"{catalog}.{silver}.dim_stops": None,
    f"{catalog}.{silver}.dim_trips": None,
    f"{catalog}.{silver}.dim_calendar": None,
    f"{catalog}.{silver}.dim_calendar_dates": None,
}

now = datetime.now(tz=UTC)
snapshot = {"generated_at": now.isoformat(timespec="seconds"), "tables": {}, "expectations": []}

for name, ts_col in TABLES.items():
    df = spark.table(name)
    aggs = [F.count(F.lit(1)).alias("rows")]
    if ts_col:
        aggs.append(F.max(ts_col).alias("max_ts"))
    row = df.agg(*aggs).collect()[0]
    entry = {"rows": row["rows"]}
    if ts_col and row["max_ts"] is not None:
        entry["max_ts"] = row["max_ts"].isoformat()
        entry["age_min"] = round((now - row["max_ts"].replace(tzinfo=UTC)).total_seconds() / 60, 1)
    snapshot["tables"][name.split(".", 1)[1]] = entry

# Expectation metrics of the latest update, from the published event log.
try:
    log = spark.table(f"{catalog}.{ops}.lakeflow_event_log")
    # the most recent update that actually processed rows (an idle incremental update has no
    # data_quality block, so it would hide the last real numbers)
    latest = (
        log.where(
            (F.col("event_type") == "flow_progress") & F.col("details").contains("data_quality")
        )
        .orderBy(F.col("timestamp").desc())
        .select("origin.update_id")
        .first()[0]
    )
    exp = (
        log.where((F.col("event_type") == "flow_progress") & (F.col("origin.update_id") == latest))
        .select(
            F.col("origin.flow_name").alias("flow"),
            F.explode(
                F.from_json(
                    F.get_json_object("details", "$.flow_progress.data_quality.expectations"),
                    "array<struct<name:string,dataset:string,passed_records:long,failed_records:long>>",
                )
            ).alias("e"),
        )
        .groupBy("flow", "e.name")
        .agg(F.sum("e.passed_records").alias("passed"), F.sum("e.failed_records").alias("failed"))
        .collect()
    )
    snapshot["update_id"] = latest
    # per-flow metrics of that update (rows written, rows dropped or warned by expectations)
    flows = (
        log.where((F.col("event_type") == "flow_progress") & (F.col("origin.update_id") == latest))
        .select(
            F.col("origin.flow_name").alias("flow"),
            F.get_json_object("details", "$.flow_progress.metrics.num_output_rows")
            .cast("long")
            .alias("rows"),
            F.get_json_object("details", "$.flow_progress.data_quality.dropped_records")
            .cast("long")
            .alias("dropped"),
            F.get_json_object("details", "$.flow_progress.data_quality.warned_records")
            .cast("long")
            .alias("warned"),
        )
        .groupBy("flow")
        .agg(
            F.sum("rows").alias("rows"),
            F.sum("dropped").alias("dropped"),
            F.sum("warned").alias("warned"),
        )
        .collect()
    )
    snapshot["flows"] = {
        r["flow"].split(".")[-1]: {
            "rows": r["rows"],
            "dropped": r["dropped"],
            "warned": r["warned"],
        }
        for r in flows
        if r["flow"] and r["flow"] != "missingFlowName"
    }
    snapshot["expectations"] = [
        {
            "flow": r["flow"].split(".")[-1],
            "expectation": r["name"],
            "passed": r["passed"],
            "failed": r["failed"],
        }
        for r in exp
    ]
except Exception as e:  # the event log table appears after the first update with event_log set
    snapshot["expectations_error"] = f"{type(e).__name__}: {e}"[:300]

os.makedirs(os.path.dirname(out_path), exist_ok=True)  # Volumes are FUSE-mounted: plain file I/O
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(snapshot, f, indent=1, default=str)
print(json.dumps(snapshot, default=str)[:2000])
