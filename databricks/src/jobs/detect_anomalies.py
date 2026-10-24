"""Network anomaly detector: is the network right now much later than it usually is at this hour?

Compares the last 30 minutes of observed stop events (average delay, share late) with the
baseline of the same local hour on earlier days (mean and standard deviation per hour), writes
one row per check to ops.network_anomalies and flags a z-score above 3 with at least two extra
minutes of delay. A Databricks SQL alert on that table mails the owner (docs/observability.md).

Arguments: catalog gold_schema ops_schema
"""

import json
import sys
from datetime import UTC, datetime

from pyspark.sql import SparkSession

catalog, gold, ops = sys.argv[1:4]
spark = SparkSession.builder.getOrCreate()

row = spark.sql(f"""
    with now_window as (
        select max(feed_ts) as as_of from {catalog}.{gold}.stg_stop_events
    ),
    current as (
        select
            n.as_of,
            hour(from_utc_timestamp(n.as_of, 'Europe/Berlin')) as hour_local,
            count(*) as events,
            avg(e.delay_s) / 60.0 as avg_delay_min,
            avg(case when e.is_late then 1.0 else 0.0 end) as share_late
        from {catalog}.{gold}.stg_stop_events e cross join now_window n
        where e.feed_ts >= n.as_of - interval 30 minutes
          and e.event_ts between n.as_of - interval 30 minutes and n.as_of
          and not e.is_cancelled and not e.is_skipped_stop and e.delay_s is not null
        group by n.as_of
    ),
    baseline as (
        select hour_of_day,
               avg(avg_delay_min) as base_avg_delay_min, stddev(avg_delay_min) as sd_avg_delay_min,
               avg(1 - punctuality) as base_share_late, stddev(1 - punctuality) as sd_share_late,
               count(*) as base_n
        from {catalog}.{gold}.mart_punctuality_hourly
        where agency_name is not null and date_local < current_date()
        group by hour_of_day
    )
    select c.as_of, c.hour_local, c.events, round(c.avg_delay_min, 2) as avg_delay_min, round(c.share_late, 4) as share_late,
           round(b.base_avg_delay_min, 2) as base_avg_delay_min, round(b.sd_avg_delay_min, 2) as sd_avg_delay_min,
           round(b.base_share_late, 4) as base_share_late, b.base_n,
           round((c.avg_delay_min - b.base_avg_delay_min) / nullif(b.sd_avg_delay_min, 0), 2) as z_delay
    from current c left join baseline b on c.hour_local = b.hour_of_day
""").collect()

checked_at = datetime.now(tz=UTC)
if not row:
    print(
        json.dumps(
            {"checked_at": checked_at.isoformat(), "events": 0, "reason": "no observed events"}
        )
    )
    sys.exit(0)
r = row[0].asDict()
z = r.get("z_delay")
extra_min = (r["avg_delay_min"] or 0) - (r["base_avg_delay_min"] or 0)
is_anomaly = bool(z is not None and z > 3 and extra_min >= 2 and (r["base_n"] or 0) >= 3)
record = {
    **r,
    "checked_at": checked_at,
    "extra_delay_min": round(extra_min, 2),
    "is_anomaly": is_anomaly,
}
spark.createDataFrame([record]).write.mode("append").option("mergeSchema", "true").saveAsTable(
    f"{catalog}.{ops}.network_anomalies"
)
print(json.dumps(record, default=str))
