{{ config(materialized='table') }}

-- One row per SLO with its error budget: how much of the allowed failure the window has already
-- consumed. budget_remaining < 0 means the SLO is breached.
--   collector:  >= 99.5 % of collector executions succeed (30 days, event based)
--   pipeline:   >= 99 % of pipeline updates succeed (30 days, event based)
--   freshness:  silver at most 20 minutes old, evaluated per pipeline update (30 days):
--               an update that ends with data older than 20 minutes is a bad event
--   quality:    <= 1 % of records failing warning expectations (7 days, record based)

with collector as (
    select
        'collector' as slo,
        0.995 as target,
        '30d' as window,
        count(*) as total_events,
        count(case when not success then 1 end) as bad_events
    from {{ source('silver', 'silver_collector_runs') }}
    where started_at >= current_timestamp() - interval 30 days
),

pipeline as (
    select
        'pipeline' as slo,
        0.99 as target,
        '30d' as window,
        count(*) as total_events,
        count(case when not succeeded then 1 end) as bad_events
    from {{ ref('slo_pipeline_updates') }}
    where started_at >= current_timestamp() - interval 30 days
      and final_state is not null
),

-- freshness per pipeline update: the newest feed_ts in silver at the time the update finished.
-- Approximated with the collector feed_ts closest before the update end minus the end time.
freshness as (
    select
        'freshness' as slo,
        0.95 as target,
        '30d' as window,
        count(*) as total_events,
        count(case when age_min > 20 then 1 end) as bad_events
    from (
        select
            u.update_id,
            (unix_timestamp(u.last_event_at) - unix_timestamp(max(r.feed_ts))) / 60.0 as age_min
        from {{ ref('slo_pipeline_updates') }} as u
        left join {{ source('silver', 'silver_collector_runs') }} as r
            on r.started_at <= u.last_event_at and r.started_at >= u.last_event_at - interval 2 hours
        where u.succeeded and u.started_at >= current_timestamp() - interval 30 days
        group by u.update_id, u.last_event_at
    )
),

quality as (
    select
        'quality' as slo,
        0.99 as target,
        '7d' as window,
        sum(passed_records) + sum(failed_records) as total_events,
        sum(failed_records) as bad_events
    from {{ ref('slo_expectations_daily') }}
    where event_date >= current_date() - interval 7 days
),

unioned as (
    select * from collector
    union all select * from pipeline
    union all select * from freshness
    union all select * from quality
)

select
    slo,
    target,
    window,
    total_events,
    bad_events,
    round(1 - bad_events / nullif(total_events, 0), 5) as achieved,
    round((1 - target) * total_events, 2) as budget_events,
    round(1 - bad_events / nullif((1 - target) * total_events, 0), 4) as budget_remaining,
    (bad_events <= (1 - target) * total_events) as slo_ok,
    current_timestamp() as evaluated_at
from unioned
