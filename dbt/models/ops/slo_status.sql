{{ config(materialized='table') }}

-- The three SLOs in one row, evaluated at build time:
--   freshness: newest silver stop-time update at most 20 minutes old (the refresh job runs every
--              15 minutes and takes about 3; measured age oscillates between 2 and 18 minutes)
--   pipeline:  at least 99 % of pipeline updates in the last 30 days succeeded
--   quality:   at most 1 % of records failed a warning expectation in the last 7 days
-- Phase 4 adds the collector SLO (Azure side) and the error budgets.

with freshness as (
    select
        max(feed_ts) as newest_feed_ts,
        round((unix_timestamp(current_timestamp()) - unix_timestamp(max(feed_ts))) / 60.0, 1) as age_min
    from {{ source('silver', 'silver_stop_time_updates') }}
),

pipeline as (
    select
        count(*) as updates_30d,
        count(case when succeeded then 1 end) as succeeded_30d,
        round(count(case when succeeded then 1 end) / nullif(count(*), 0), 4) as success_rate_30d,
        round(avg(case when succeeded then duration_min end), 2) as avg_duration_min_30d
    from {{ ref('slo_pipeline_updates') }}
    where started_at >= current_timestamp() - interval 30 days
      and final_state is not null
),

quality as (
    select
        sum(passed_records) as passed_7d,
        sum(failed_records) as failed_7d,
        round(sum(failed_records) / nullif(sum(passed_records) + sum(failed_records), 0), 6) as fail_rate_7d
    from {{ ref('slo_expectations_daily') }}
    where event_date >= current_date() - interval 7 days
)

select
    current_timestamp() as evaluated_at,
    f.newest_feed_ts,
    f.age_min as freshness_age_min,
    20 as freshness_target_min,
    (f.age_min <= 20) as freshness_ok,
    p.updates_30d,
    p.succeeded_30d,
    p.success_rate_30d,
    0.99 as pipeline_target,
    (coalesce(p.success_rate_30d, 0) >= 0.99) as pipeline_ok,
    p.avg_duration_min_30d,
    q.passed_7d,
    q.failed_7d,
    q.fail_rate_7d,
    0.01 as quality_target,
    (coalesce(q.fail_rate_7d, 0) <= 0.01) as quality_ok
from freshness as f
cross join pipeline as p
cross join quality as q
