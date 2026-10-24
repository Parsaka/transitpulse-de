{{ config(materialized='table') }}

-- Cancelled trips and skipped stops per day, agency, mode and route, against the trips the
-- realtime feed showed at all. Partial cancellations show up as skipped stops.

with trips as (
    select * from {{ ref('stg_trips') }}
    where feed = '{{ var("core_feed") }}'
)

select
    service_date,
    agency_name,
    mode,
    mode_order,
    route_short_name,
    route_id,
    count(*) as trips_seen,
    count(case when is_cancelled then 1 end) as trips_cancelled,
    round(count(case when is_cancelled then 1 end) / count(*), 4) as cancellation_rate,
    sum(n_skipped_stops) as skipped_stops,
    count(case when n_skipped_stops > 0 and not is_cancelled then 1 end) as trips_with_skipped_stops,
    count(case when in_schedule then 1 end) as trips_in_schedule
from trips
group by 1, 2, 3, 4, 5, 6
