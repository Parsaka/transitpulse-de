# ML: delay at destination, weather impact, network anomalies (phase 5)

Three things run in production, all on Databricks Free Edition (serverless jobs), all measured
against a baseline before they are allowed to be called an improvement.

## 1. Weather feed
Open-Meteo hourly values (temperature, precipitation, wind gusts, weather code) for nine grid
points over Berlin-Brandenburg, fetched every hour by the Function (`weather` timer, minute 7)
with two days of history and two days of forecast; each row carries `is_forecast`. A one-off
backfill with `past_days=92` landed 20,304 rows. Lakeflow builds `bronze_weather` (Auto Loader)
and `silver_weather_hourly` (AUTO CDC, SCD type 1 on point and hour, so a forecast row is replaced
by the observation when it arrives). dbt joins every stop to its nearest grid point
(`dim_stop_weather_point`, haversine; 41,929 stops, median 12.5 km, maximum 201.6 km for stops
far outside the VBB core) and builds `mart_weather_impact_hourly`.

First measured impact (VBB, 2026-10-22 to 2026-10-24 12:40 UTC, prod build):

| Mode | Hour weather | Scored stop events | Punctual (< 6 min) | Average delay |
|---|---|---|---|---|
| bus | dry | 1,070,589 | 96.9 % | 0.91 min |
| bus | light rain | 57,100 | 96.0 % | 1.19 min |
| S-Bahn | dry | 89,357 | 98.3 % | 0.82 min |
| S-Bahn | light rain | 3,640 | 91.1 % | 1.89 min |

Two days of weather and one rainy morning are not a study; the mart keeps accumulating and the page shows the current
numbers. Licence: Open-Meteo CC BY 4.0 (docs/data-sources.md).

## 2. Delay-at-destination model (model card)
**Question.** A trip has just been seen for the first time with a delay of *x* seconds. How late
will it be at its last stop? The honest baseline is "as late as it is now" (`first_delay_s`).
Dispatchers and passengers only gain something if the model beats that.

**Data.** `training_sql()` in `databricks/src/jobs/delay_features.py`: completed, not cancelled
trips from `stg_trips` with more than three observed stops, delay at the first observed stop
within one hour, final delay within two hours. Weather of the first stop's hour and nearest grid
point is joined in.

**Features (12).** Categorical: mode, agency, route short name. Numeric: delay at first stop,
local hour, weekday, number of observed stops, last stop sequence, direction, temperature,
precipitation, gusts. Target: delay at the last observed stop (seconds).

**Model.** LightGBM, L1 objective (delays are heavy-tailed, so MAE is the loss and the metric),
63 leaves, learning rate 0.05, early stopping on the holdout, seed 42.

**Split.** Time-based: trips sorted by first observation, the newest 20 % are the holdout and
never seen in training. A random split would leak the same hour of the same day into both sides.

**Skill gate.** The model is registered in Unity Catalog (`workspace.tp_ops.delay_model`) and
gets the alias `champion` only if skill = 1 − MAE(model)/MAE(naive) is positive on the holdout.
Otherwise the run fails loudly (job failure mail) and the previous champion stays in place.

**First training run (2026-10-24 12:48 UTC, version 1, promoted).**

| | Train | Holdout |
|---|---|---|
| Trips | 60,211 | 15,053 (2026-10-24 04:15 to 12:19 UTC) |
| MAE model | | 50.6 s |
| MAE naive | | 52.3 s |
| Skill | | **3.3 %** |
| Best iteration | 922 | |

Per mode on the holdout (MAE model / naive, seconds): bus 51.4 / 52.7, S-Bahn 47.9 / 67.1,
regional rail 186.1 / 191.7, regional express 28.1 / 28.4, tram 43.3 / 41.2, U-Bahn 23.4 / 21.9.
So the model earns its keep on S-Bahn and bus and is slightly worse than the baseline on tram and
U-Bahn, where delays are small and the current delay is already the best guess. Feature gain is
dominated by the route (route_short_name), then temperature, first delay, gusts and local hour;
precipitation and weekday contribute almost nothing with two days of data.

**Limits, stated plainly.** Two days of training data; one weather regime; the target is the
delay at the *last observed* stop, which is the terminus only when the feed kept the trip to the
end; no holiday calendar; no disruption notices (ServiceAlerts) as features yet. The weekly
retraining (Sunday 04:00 Berlin, `transitpulse_train`) will show whether the skill grows with
more weeks; `tp_ops.model_metrics` keeps one row per run, so the trend is a query.

**Scoring and the forward-looking log.** After every 15-minute refresh, `score_delay_model.py`
predicts the final delay for every trip still in the feed (first seen in the last hour, not yet
gone) and appends what was known at that moment to `tp_ops.forecast_log`: current stop, current
delay, naive forecast, model forecast, model version, timestamp (first prod run: 2,533 trips
in one scoring pass). Nothing is ever back-filled with hindsight. `mart_forecast_quality` (dbt) later joins the *earliest* prediction per trip to
the delay it actually ended with and reports MAE model vs naive per day and mode; the status page
shows it. This is the number to quote, not the holdout.

## 3. Network anomaly detector
`detect_anomalies.py` runs after every refresh: average delay and late share of the last 30
minutes of observed stop events versus the mean and standard deviation of the same local hour on
earlier days (`mart_punctuality_hourly`). One row per check goes to `tp_ops.network_anomalies`;
`is_anomaly` needs z > 3, at least two extra minutes and at least three baseline days, so the
first days produce checks but no alerts by design (first checks on 2026-10-24: 11k to 20k events
per 30-minute window, average delay 1.2 to 1.5 min against a usual 2.0 min, z about −0.1). A Databricks SQL alert
(`databricks/alerts/network_anomaly.json`, every 15 minutes) mails the owner when a flagged check
appears and again when it clears. It is a statistical "the network is unusually late right now"
signal, not a root-cause finder; the runbook says what to look at next.

## Reproduce
```bash
databricks bundle run transitpulse_train -t prod          # train + skill gate + registry
databricks bundle run transitpulse_refresh -t prod        # pipeline, health, score, anomaly
dbt build --target prod --select mart_forecast_quality    # score the log against outcomes
```
MLflow experiment: `/Shared/transitpulse-delay-model` (params, metrics, per-mode MAE, feature
gain, model with signature). Registry: `workspace.tp_ops.delay_model`, alias `champion`.
