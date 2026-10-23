{{ config(materialized='view') }}

-- One row per (trip, service date, stop) with the LAST prediction the feed gave for it, enriched
-- with route, mode and agency. A stop event is "observed" once its scheduled time is older than
-- the settle window: the last prediction is then as close to the truth as GTFS-RT gets.

with latest as (
    select * from {{ source('silver', 'silver_stop_time_latest') }}
),

routes as (
    select
        r.route_id,
        r.agency_id,
        r.route_short_name,
        r.route_long_name,
        r.route_type,
        coalesce(m.mode, 'other') as mode,
        coalesce(m.sort_order, 99) as mode_order,
        a.agency_name
    from {{ source('silver', 'dim_routes') }} as r
    left join {{ ref('route_type_modes') }} as m on r.route_type = m.route_type
    left join {{ source('silver', 'dim_agency') }} as a on r.agency_id = a.agency_id
),

trips as (
    select trip_id, trip_headsign, direction_id as sched_direction_id, service_id
    from {{ source('silver', 'dim_trips') }}
),

max_feed as (
    select max(feed_ts) as max_feed_ts from latest
)

select
    l.feed,
    l.trip_id,
    l.start_date,
    l.service_date,
    l.route_id,
    r.agency_name,
    r.mode,
    r.mode_order,
    r.route_short_name,
    r.route_type,
    t.trip_headsign,
    coalesce(l.direction_id, t.sched_direction_id) as direction_id,
    l.stop_sequence,
    l.stop_id,
    l.feed_ts,
    coalesce(l.arrival_time, l.departure_time) as event_ts,
    coalesce(l.arrival_delay_s, l.departure_delay_s) as delay_s,
    l.arrival_delay_s,
    l.departure_delay_s,
    l.is_cancelled,
    l.is_skipped_stop,
    (coalesce(l.arrival_delay_s, l.departure_delay_s) >= {{ var('late_threshold_s') }}) as is_late,
    (coalesce(l.arrival_time, l.departure_time)
        < mf.max_feed_ts - interval {{ var('settle_minutes') }} minutes) as is_observed,
    (t.trip_id is not null) as in_schedule
from latest as l
cross join max_feed as mf
left join routes as r on l.route_id = r.route_id
left join trips as t on l.trip_id = t.trip_id
where coalesce(l.arrival_time, l.departure_time) is not null
