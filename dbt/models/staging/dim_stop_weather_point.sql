{{ config(materialized='table') }}

-- Nearest weather grid point for every stop (haversine over the nine Open-Meteo points).

with points as (
    select point_id, lat as p_lat, lon as p_lon
    from {{ source('silver', 'silver_weather_hourly') }}
    group by point_id, lat, lon
),

stops as (
    select stop_id, stop_name, stop_lat, stop_lon, parent_station
    from {{ source('silver', 'dim_stops') }}
    where stop_lat is not null and stop_lon is not null
      and feed = '{{ var("core_feed") }}'  -- the grid points cover Berlin-Brandenburg only
),

distances as (
    select
        s.stop_id,
        s.stop_name,
        s.parent_station,
        p.point_id,
        2 * 6371 * asin(sqrt(
            pow(sin(radians(p.p_lat - s.stop_lat) / 2), 2)
            + cos(radians(s.stop_lat)) * cos(radians(p.p_lat)) * pow(sin(radians(p.p_lon - s.stop_lon) / 2), 2)
        )) as distance_km
    from stops as s
    cross join points as p
)

select stop_id, stop_name, parent_station, point_id, round(distance_km, 1) as distance_km
from (
    select *, row_number() over (partition by stop_id order by distance_km asc) as rn
    from distances
)
where rn = 1
