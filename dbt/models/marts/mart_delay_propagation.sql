{{ config(materialized='table') }}

-- How delay develops along a trip: delay at the first versus the last observed stop, per day,
-- mode and route. "Grew" means the trip lost more than two minutes between its ends, "recovered"
-- means it won back more than two minutes. Completed trips only (they left the feed), so both
-- ends are final.

with trips as (
    select * from {{ ref('stg_trips') }}
    where is_completed and not is_cancelled and feed = '{{ var("core_feed") }}'
      and first_delay_s is not null and last_delay_s is not null
      and last_stop_sequence > 1
)

select
    service_date,
    agency_name,
    mode,
    mode_order,
    route_short_name,
    route_id,
    count(*) as trips,
    round(avg(first_delay_s) / 60.0, 2) as avg_first_delay_min,
    round(avg(last_delay_s) / 60.0, 2) as avg_last_delay_min,
    round(avg(delay_change_s) / 60.0, 2) as avg_delay_change_min,
    round(percentile_approx(delay_change_s, 0.5) / 60.0, 2) as p50_delay_change_min,
    round(percentile_approx(delay_change_s, 0.9) / 60.0, 2) as p90_delay_change_min,
    round(count(case when delay_change_s > 120 then 1 end) / count(*), 4) as share_grew,
    round(count(case when delay_change_s < -120 then 1 end) / count(*), 4) as share_recovered,
    round(count(case when last_delay_s >= {{ var('late_threshold_s') }} then 1 end) / count(*), 4) as share_late_at_end,
    round(avg(n_stops), 1) as avg_stops
from trips
group by 1, 2, 3, 4, 5, 6
