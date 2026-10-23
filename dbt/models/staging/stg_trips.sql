{{ config(materialized='view') }}

-- One row per realtime trip (trip, service date): first and last observed stop event, delay at
-- both ends, cancellation, and whether the feed has finished with the trip (it left the feed).

with events as (
    select * from {{ ref('stg_stop_events') }}
),

gone as (
    select feed, trip_id, start_date, max(feed_ts) as gone_ts
    from {{ source('silver', 'silver_trips_gone') }}
    group by feed, trip_id, start_date
),

ordered as (
    select
        *,
        row_number() over (partition by feed, trip_id, start_date order by stop_sequence asc) as rn_first,
        row_number() over (partition by feed, trip_id, start_date order by stop_sequence desc) as rn_last
    from events
    where delay_s is not null and not is_skipped_stop
),

ends as (
    select
        feed,
        trip_id,
        start_date,
        max(case when rn_first = 1 then delay_s end) as first_delay_s,
        max(case when rn_first = 1 then event_ts end) as first_event_ts,
        max(case when rn_last = 1 then delay_s end) as last_delay_s,
        max(case when rn_last = 1 then event_ts end) as last_event_ts,
        max(case when rn_last = 1 then stop_sequence end) as last_stop_sequence
    from ordered
    group by feed, trip_id, start_date
),

per_trip as (
    select
        feed,
        trip_id,
        start_date,
        min(service_date) as service_date,
        min(route_id) as route_id,
        min(agency_name) as agency_name,
        min(mode) as mode,
        min(mode_order) as mode_order,
        min(route_short_name) as route_short_name,
        min(trip_headsign) as trip_headsign,
        min(direction_id) as direction_id,
        count(*) as n_stops,
        sum(case when is_skipped_stop then 1 else 0 end) as n_skipped_stops,
        max(is_cancelled) as is_cancelled,
        max(in_schedule) as in_schedule,
        max(feed_ts) as last_feed_ts
    from events
    group by feed, trip_id, start_date
)

select
    p.*,
    e.first_delay_s,
    e.first_event_ts,
    e.last_delay_s,
    e.last_event_ts,
    e.last_stop_sequence,
    e.last_delay_s - e.first_delay_s as delay_change_s,
    g.gone_ts,
    (g.gone_ts is not null) as is_completed
from per_trip as p
left join ends as e on p.feed = e.feed and p.trip_id = e.trip_id and p.start_date = e.start_date
left join gone as g on p.feed = g.feed and p.trip_id = g.trip_id and p.start_date = g.start_date
