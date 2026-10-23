{{ config(materialized='table') }}

-- Collector executions per day (Azure Function, synced from Log Analytics): success rate,
-- durations, rows written and the feed age the collector saw. Source of the collector SLO.

with runs as (
    select * from {{ source('silver', 'silver_collector_runs') }}
)

select
    run_date,
    count(*) as runs,
    count(case when success then 1 end) as succeeded,
    round(count(case when success then 1 end) / count(*), 4) as success_rate,
    count(case when status = 'not_modified' then 1 end) as not_modified_runs,
    round(percentile_approx(duration_ms, 0.5), 0) as p50_duration_ms,
    round(percentile_approx(duration_ms, 0.95), 0) as p95_duration_ms,
    round(max(duration_ms), 0) as max_duration_ms,
    sum(n_written_stop_times) as rows_written,
    sum(bytes_written) as bytes_written,
    round(avg(reduction), 4) as avg_reduction,
    round(avg(feed_age_s), 1) as avg_feed_age_s,
    round(max(feed_age_s), 1) as max_feed_age_s,
    min(started_at) as first_run,
    max(started_at) as last_run
from runs
group by run_date
