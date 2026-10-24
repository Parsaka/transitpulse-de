"""Score the trips currently in the feed with the champion model and append to the forecast log.

Runs after every pipeline refresh. Each row records what was known at prediction time, so the
log can be scored honestly later against the delay the trip ended with (mart_forecast_quality).

Arguments: catalog gold_schema silver_schema ops_schema jobs_dir
"""

import json
import os
import sys

# __file__ is not defined in a Python file task; the bundle passes the jobs folder as argv[5]
sys.path.insert(0, sys.argv[5] if len(sys.argv) > 5 else os.getcwd())
from datetime import UTC, datetime

import mlflow
import pandas as pd
from delay_features import CATEGORICAL, FEATURES, NUMERIC, scoring_sql
from pyspark.sql import SparkSession

catalog, gold, silver, ops = sys.argv[1:5]
spark = SparkSession.builder.getOrCreate()
mlflow.set_registry_uri("databricks-uc")
MODEL_NAME = f"{catalog}.{ops}.delay_model"

client = mlflow.MlflowClient()
try:
    mv = client.get_model_version_by_alias(MODEL_NAME, "champion")
except Exception as e:  # no champion yet (first days): nothing to score, not a failure
    print(json.dumps({"scored": 0, "reason": f"no champion model: {e}"[:200]}))
    sys.exit(0)
model = mlflow.lightgbm.load_model(f"models:/{MODEL_NAME}@champion")

df = spark.sql(scoring_sql(catalog, gold, silver)).toPandas()
if df.empty:
    print(json.dumps({"scored": 0, "reason": "no active trips"}))
    sys.exit(0)
for c in CATEGORICAL:
    df[c] = df[c].fillna("unknown").astype("category")
for c in NUMERIC:
    df[c] = pd.to_numeric(df[c], errors="coerce")

now = datetime.now(tz=UTC)
out = df[
    [
        "feed",
        "trip_id",
        "start_date",
        "mode",
        "first_delay_s",
        "current_delay_s",
        "current_stop_sequence",
        "last_stop_sequence",
        "n_stops",
        "last_feed_ts",
    ]
].copy()
out["predicted_last_delay_s"] = model.predict(df[FEATURES]).round(0)
out["naive_last_delay_s"] = df["current_delay_s"]
out["model_version"] = int(mv.version)
out["predicted_at"] = now
(
    spark.createDataFrame(out)
    .write.mode("append")
    .option("mergeSchema", "true")
    .saveAsTable(f"{catalog}.{ops}.forecast_log")
)
print(
    json.dumps(
        {"scored": len(out), "model_version": int(mv.version), "predicted_at": now.isoformat()}
    )
)
