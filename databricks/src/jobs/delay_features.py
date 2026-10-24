"""Feature definitions shared by training and scoring (one source of truth).

A trip is described at the moment of its first observed stop: the delay there, where and when
it runs, how long it is, and the weather at the nearest grid point in that hour. The target is
the delay at the last observed stop once the trip has left the feed.
"""

CATEGORICAL = ["mode", "agency_name", "route_short_name"]
NUMERIC = [
    "first_delay_s",
    "hour_local",
    "dow",
    "n_stops",
    "last_stop_sequence",
    "direction_id",
    "temp_c",
    "precip_mm",
    "gust_kmh",
]
FEATURES = CATEGORICAL + NUMERIC
TARGET = "last_delay_s"


def training_sql(catalog: str, gold: str, silver: str) -> str:
    """Completed trips with features at the first observed stop and the final delay."""
    return f"""
    with first_stop as (
        select feed, trip_id, start_date, stop_id, event_ts
        from (
            select *, row_number() over (partition by feed, trip_id, start_date order by stop_sequence) as rn
            from {catalog}.{gold}.stg_stop_events
            where delay_s is not null and not is_skipped_stop
        ) where rn = 1
    )
    select
        t.feed, t.trip_id, t.start_date, t.service_date,
        t.mode, t.agency_name, t.route_short_name,
        t.first_delay_s,
        hour(from_utc_timestamp(f.event_ts, 'Europe/Berlin')) as hour_local,
        dayofweek(from_utc_timestamp(f.event_ts, 'Europe/Berlin')) as dow,
        t.n_stops, t.last_stop_sequence, coalesce(t.direction_id, -1) as direction_id,
        w.temp_c, w.precip_mm, w.gust_kmh,
        t.last_delay_s,
        f.event_ts as first_event_ts
    from {catalog}.{gold}.stg_trips t
    join first_stop f on t.feed = f.feed and t.trip_id = f.trip_id and t.start_date = f.start_date
    left join {catalog}.{gold}.dim_stop_weather_point p on f.stop_id = p.stop_id
    left join {catalog}.{silver}.silver_weather_hourly w
        on w.point_id = p.point_id and w.time = date_trunc('hour', f.event_ts)
    where t.is_completed and not t.is_cancelled
      and t.first_delay_s is not null and t.last_delay_s is not null and t.last_stop_sequence > 3
      and abs(t.first_delay_s) < 3600 and abs(t.last_delay_s) < 7200
    """


def scoring_sql(catalog: str, gold: str, silver: str, lookback_minutes: int = 60) -> str:
    """Trips still in the feed: features at their first observed stop plus the current delay."""
    return f"""
    with recent as (
        select * from {catalog}.{gold}.stg_stop_events
        where feed_ts >= (select max(feed_ts) from {catalog}.{gold}.stg_stop_events) - interval {lookback_minutes} minutes
          and delay_s is not null and not is_skipped_stop and not is_cancelled
    ),
    trips as (
        select feed, trip_id, start_date,
               min(mode) as mode, min(agency_name) as agency_name, min(route_short_name) as route_short_name,
               min(direction_id) as direction_id, count(*) as n_stops, max(stop_sequence) as last_stop_sequence,
               max(feed_ts) as last_feed_ts
        from recent group by feed, trip_id, start_date
    ),
    first_stop as (
        select feed, trip_id, start_date, stop_id, event_ts, delay_s as first_delay_s
        from (select *, row_number() over (partition by feed, trip_id, start_date order by stop_sequence) as rn from recent) where rn = 1
    ),
    current_stop as (
        select feed, trip_id, start_date, delay_s as current_delay_s, stop_sequence as current_stop_sequence
        from (select *, row_number() over (partition by feed, trip_id, start_date order by stop_sequence desc) as rn from recent) where rn = 1
    )
    select
        t.feed, t.trip_id, t.start_date, t.mode, t.agency_name, t.route_short_name,
        f.first_delay_s,
        hour(from_utc_timestamp(f.event_ts, 'Europe/Berlin')) as hour_local,
        dayofweek(from_utc_timestamp(f.event_ts, 'Europe/Berlin')) as dow,
        t.n_stops, t.last_stop_sequence, coalesce(t.direction_id, -1) as direction_id,
        w.temp_c, w.precip_mm, w.gust_kmh,
        c.current_delay_s, c.current_stop_sequence, t.last_feed_ts
    from trips t
    join first_stop f on t.feed = f.feed and t.trip_id = f.trip_id and t.start_date = f.start_date
    join current_stop c on t.feed = c.feed and t.trip_id = c.trip_id and t.start_date = c.start_date
    left join {catalog}.{silver}.silver_trips_gone g
        on t.feed = g.feed and t.trip_id = g.trip_id and t.start_date = g.start_date
    left join {catalog}.{gold}.dim_stop_weather_point p on f.stop_id = p.stop_id
    left join {catalog}.{silver}.silver_weather_hourly w
        on w.point_id = p.point_id and w.time = date_trunc('hour', f.event_ts)
    where g.trip_id is null
    """
