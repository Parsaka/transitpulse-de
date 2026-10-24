"""Train the delay-at-destination model (LightGBM), evaluate against the naive baseline on a
time-based holdout, log everything to MLflow and promote to the Unity Catalog registry only when
the model beats the baseline (skill gate).

Serverless Python task. Arguments: catalog gold_schema silver_schema ops_schema jobs_dir
"""

import json
import os
import sys

# __file__ is not defined in a Python file task; the bundle passes the jobs folder as argv[5]
sys.path.insert(0, sys.argv[5] if len(sys.argv) > 5 else os.getcwd())
from datetime import UTC, datetime

import lightgbm as lgb
import mlflow
import numpy as np
import pandas as pd
from delay_features import CATEGORICAL, FEATURES, NUMERIC, TARGET, training_sql
from pyspark.sql import SparkSession

catalog, gold, silver, ops = sys.argv[1:5]
spark = SparkSession.builder.getOrCreate()
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment("/Shared/transitpulse-delay-model")
MODEL_NAME = f"{catalog}.{ops}.delay_model"

df = spark.sql(training_sql(catalog, gold, silver)).toPandas()
df = df.sort_values("first_event_ts").reset_index(drop=True)
for c in CATEGORICAL:
    df[c] = df[c].fillna("unknown").astype("category")
for c in NUMERIC:
    df[c] = pd.to_numeric(df[c], errors="coerce")

# time-based split: the newest 20 % of trips are the holdout (never seen in training)
cut = int(len(df) * 0.8)
train, test = df.iloc[:cut], df.iloc[cut:]
naive_mae = float(np.mean(np.abs(test[TARGET] - test["first_delay_s"])))

params = {
    "objective": "regression_l1",  # MAE: delays are heavy-tailed
    "learning_rate": 0.05,
    "num_leaves": 63,
    "min_data_in_leaf": 50,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "verbose": -1,
    "seed": 42,
}
with mlflow.start_run(run_name=datetime.now(tz=UTC).strftime("train-%Y%m%d-%H%M")) as run:
    dtrain = lgb.Dataset(train[FEATURES], train[TARGET], categorical_feature=CATEGORICAL)
    dvalid = lgb.Dataset(
        test[FEATURES], test[TARGET], reference=dtrain, categorical_feature=CATEGORICAL
    )
    booster = lgb.train(
        params,
        dtrain,
        num_boost_round=2000,
        valid_sets=[dvalid],
        callbacks=[lgb.early_stopping(100, verbose=False)],
    )
    pred = booster.predict(test[FEATURES], num_iteration=booster.best_iteration)
    mae = float(np.mean(np.abs(test[TARGET] - pred)))
    skill = 1 - mae / naive_mae if naive_mae else 0.0
    per_mode = (
        test.assign(
            err=np.abs(test[TARGET] - pred), naive=np.abs(test[TARGET] - test["first_delay_s"])
        )
        .groupby("mode", observed=True)[["err", "naive"]]
        .mean()
        .round(1)
    )
    metrics = {
        "mae_s": round(mae, 1),
        "naive_mae_s": round(naive_mae, 1),
        "skill": round(skill, 4),
        "n_train": len(train),
        "n_test": len(test),
        "best_iteration": int(booster.best_iteration),
        "test_from": str(test["first_event_ts"].min()),
        "test_to": str(test["first_event_ts"].max()),
    }
    mlflow.log_params({**params, "n_features": len(FEATURES)})
    mlflow.log_metrics({k: v for k, v in metrics.items() if isinstance(v, (int, float))})
    mlflow.log_dict({"per_mode_mae_s": per_mode.to_dict(orient="index")}, "per_mode.json")
    importance = dict(
        zip(FEATURES, booster.feature_importance("gain").round(0).tolist(), strict=True)
    )
    mlflow.log_dict(importance, "feature_importance_gain.json")
    signature = mlflow.models.infer_signature(test[FEATURES].head(50), pred[:50])
    info = mlflow.lightgbm.log_model(
        booster, "model", signature=signature, input_example=test[FEATURES].head(5)
    )

    promoted = skill > 0
    version = None
    if promoted:
        from mlflow import MlflowClient

        mv = mlflow.register_model(info.model_uri, MODEL_NAME)
        MlflowClient().set_registered_model_alias(MODEL_NAME, "champion", mv.version)
        version = int(mv.version)
    record = {
        "trained_at": datetime.now(tz=UTC).isoformat(timespec="seconds"),
        "run_id": run.info.run_id,
        "model_name": MODEL_NAME,
        "model_version": version,
        "promoted": promoted,
        **metrics,
        "per_mode": json.dumps(per_mode.to_dict(orient="index")),
        "importance": json.dumps(importance),
    }
    spark.createDataFrame(pd.DataFrame([record])).write.mode("append").option(
        "mergeSchema", "true"
    ).saveAsTable(f"{catalog}.{ops}.model_metrics")
    print(json.dumps(record, default=str))
    if not promoted:
        raise SystemExit(
            f"model not promoted: MAE {mae:.1f}s is not better than naive {naive_mae:.1f}s"
        )
