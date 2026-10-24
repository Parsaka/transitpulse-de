{{ config(materialized='table') }}

-- Punctuality and delay per hour, mode and weather condition at the stop's nearest grid point.
-- Observed stop events only; the weather row is the latest fetch for that hour (an observation
-- once the hour has passed). Conditions: dry / light rain (< 1 mm/h) / rain (>= 1 mm/h);
-- windy when gusts reach 50 km/h; snow when any snowfall.

with events as (
    select e.*, w.point_id, w.distance_km
    from {{ ref('stg_stop_events') }} as e
    join {{ ref('dim_stop_weather_point') }} as w on e.stop_id = w.stop_id
    where e.is_observed and not e.is_cancelled and not e.is_skipped_stop and e.delay_s is not null
),

weather as (
    select point_id, time as hour_utc, temp_c, precip_mm, rain_mm, snow_cm, wind_kmh, gust_kmh, weather_code
    from {{ source('silver', 'silver_weather_hourly') }}
),

joined as (
    select
        date_trunc('hour', e.event_ts) as hour_utc,
        e.mode,
        e.mode_order,
        e.point_id,
        case
            when w.snow_cm > 0 then 'snow'
            when w.precip_mm >= 1.0 then 'rain'
            when w.precip_mm > 0 then 'light rain'
            else 'dry'
        end as precipitation,
        (w.gust_kmh >= 50) as windy,
        w.temp_c,
        w.precip_mm,
        w.gust_kmh,
        e.delay_s,
        e.is_late
    from events as e
    left join weather as w on w.point_id = e.point_id and w.hour_utc = date_trunc('hour', e.event_ts)
)

select
    hour_utc,
    from_utc_timestamp(hour_utc, 'Europe/Berlin') as hour_local,
    mode,
    mode_order,
    point_id,
    coalesce(precipitation, 'unknown') as precipitation,
    coalesce(windy, false) as windy,
    round(avg(temp_c), 1) as temp_c,
    round(avg(precip_mm), 2) as precip_mm,
    round(avg(gust_kmh), 1) as gust_kmh,
    count(*) as scored_events,
    count(case when is_late then 1 end) as late_events,
    round(1 - count(case when is_late then 1 end) / count(*), 4) as punctuality,
    round(avg(delay_s) / 60.0, 2) as avg_delay_min,
    round(percentile_approx(delay_s, 0.9) / 60.0, 2) as p90_delay_min
from joined
group by 1, 2, 3, 4, 5, 6, 7
