{{ config(materialized='table') }}

-- Daily punctuality per agency and mode, with an all-modes row per agency and a network total.

with hourly as (
    select * from {{ ref('mart_punctuality_hourly') }}
)

select
    date_local,
    coalesce(agency_name, '(all agencies)') as agency_name,
    coalesce(mode, '(all modes)') as mode,
    min(mode_order) as mode_order,
    sum(stop_events) as stop_events,
    sum(scored_events) as scored_events,
    sum(late_events) as late_events,
    sum(cancelled_events) as cancelled_events,
    sum(skipped_events) as skipped_events,
    round(1 - sum(late_events) / nullif(sum(scored_events), 0), 4) as punctuality,
    sum(trips) as trips
from hourly
group by date_local, grouping sets ((agency_name, mode), (agency_name), ())
