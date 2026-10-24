{{ config(materialized='table', liquid_clustered_by=['date_local', 'mode']) }}

-- Punctuality per hour (Europe/Berlin), agency, mode and route: share of observed stop events
-- with less than 6 minutes of delay, plus the delay distribution. Only observed events count
-- (scheduled time older than the settle window), cancelled trips and skipped stops are excluded
-- from punctuality and reported separately.

with events as (
    select * from {{ ref('stg_stop_events') }}
    where is_observed and feed = '{{ var("core_feed") }}'
)

select
    date_trunc('hour', from_utc_timestamp(event_ts, 'Europe/Berlin')) as hour_local,
    to_date(from_utc_timestamp(event_ts, 'Europe/Berlin')) as date_local,
    hour(from_utc_timestamp(event_ts, 'Europe/Berlin')) as hour_of_day,
    agency_name,
    mode,
    mode_order,
    route_short_name,
    route_id,
    count(*) as stop_events,
    count(case when not is_cancelled and not is_skipped_stop and delay_s is not null then 1 end) as scored_events,
    count(case when is_late and not is_cancelled and not is_skipped_stop then 1 end) as late_events,
    count(case when is_cancelled then 1 end) as cancelled_events,
    count(case when is_skipped_stop and not is_cancelled then 1 end) as skipped_events,
    round(1 - count(case when is_late and not is_cancelled and not is_skipped_stop then 1 end)
        / nullif(count(case when not is_cancelled and not is_skipped_stop and delay_s is not null then 1 end), 0), 4) as punctuality,
    round(avg(case when not is_cancelled and not is_skipped_stop then delay_s end) / 60.0, 2) as avg_delay_min,
    round(percentile_approx(case when not is_cancelled and not is_skipped_stop then delay_s end, 0.5) / 60.0, 2) as p50_delay_min,
    round(percentile_approx(case when not is_cancelled and not is_skipped_stop then delay_s end, 0.9) / 60.0, 2) as p90_delay_min,
    count(distinct trip_id) as trips
from events
group by 1, 2, 3, 4, 5, 6, 7, 8
