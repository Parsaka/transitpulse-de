{{ config(materialized='table') }}

-- One row per service date, feed and mode (plus an all-modes row per feed): how much each
-- realtime feed delivers and how punctual it is. The nationwide gtfs.de feed overlaps the VBB
-- feed in Berlin-Brandenburg, so the two are never added up; the core marts use the core feed.

with events as (
    select * from {{ ref('stg_stop_events') }}
),

scored as (
    select
        *,
        (is_observed and not is_cancelled and not is_skipped_stop and delay_s is not null) as is_scored
    from events
)

select
    service_date,
    feed,
    coalesce(mode, '(all modes)') as mode,
    min(mode_order) as mode_order,
    count(distinct agency_name) as agencies,
    count(distinct route_id) as routes,
    count(distinct trip_id) as trips_seen,
    count(*) as stop_events,
    count(case when is_scored then 1 end) as scored_events,
    count(case when is_scored and is_late then 1 end) as late_events,
    round(1 - count(case when is_scored and is_late then 1 end) / nullif(count(case when is_scored then 1 end), 0), 4) as punctuality,
    round(avg(case when is_scored then delay_s end) / 60.0, 2) as avg_delay_min,
    count(case when is_cancelled then 1 end) as cancelled_events,
    round(avg(case when in_schedule then 1.0 else 0.0 end), 4) as schedule_match_rate,
    max(feed_ts) as newest_feed_ts
from scored
group by service_date, feed, grouping sets ((mode), ())
