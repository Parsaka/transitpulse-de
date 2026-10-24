{{ config(materialized='table') }}

-- The network right now, per mode plus a total row: trips active within the last 30 minutes of
-- feed time, their current delay and the share that is late. One small table, read by the
-- status page and the SLO check.

with events as (
    select * from {{ ref('stg_stop_events') }}
    where feed = '{{ var("core_feed") }}'
),

now_ts as (
    select max(feed_ts) as as_of from events
),

active as (
    select e.*
    from events as e
    cross join now_ts as n
    where e.feed_ts >= n.as_of - interval 30 minutes
      and e.event_ts between n.as_of - interval 30 minutes and n.as_of + interval 60 minutes
      and not e.is_cancelled and not e.is_skipped_stop and e.delay_s is not null
)

select
    n.as_of,
    coalesce(a.mode, '(all modes)') as mode,
    min(a.mode_order) as mode_order,
    count(distinct a.trip_id) as active_trips,
    count(*) as stop_events,
    round(avg(a.delay_s) / 60.0, 2) as avg_delay_min,
    round(percentile_approx(a.delay_s, 0.9) / 60.0, 2) as p90_delay_min,
    round(1 - count(case when a.is_late then 1 end) / count(*), 4) as punctuality_now
from active as a
cross join now_ts as n
group by n.as_of, grouping sets ((a.mode), ())
