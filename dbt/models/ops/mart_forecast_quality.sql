{{ config(materialized='table') }}

-- Honest, forward-looking score of the delay model: every trip's EARLIEST prediction (made while
-- the trip was still running) against the delay it ended with, per service date and mode,
-- next to the naive forecast made at the same moment (delay stays as it is now).

with first_prediction as (
    select *
    from (
        select *, row_number() over (partition by feed, trip_id, start_date order by predicted_at) as rn
        from {{ source('ops', 'forecast_log') }}
    )
    where rn = 1
),

scored as (
    select
        p.feed,
        p.trip_id,
        p.start_date,
        t.service_date,
        p.mode,
        p.model_version,
        p.predicted_at,
        p.current_stop_sequence,
        t.last_stop_sequence,
        t.last_delay_s as actual_last_delay_s,
        p.predicted_last_delay_s,
        p.naive_last_delay_s,
        abs(t.last_delay_s - p.predicted_last_delay_s) as abs_err_model,
        abs(t.last_delay_s - p.naive_last_delay_s) as abs_err_naive
    from first_prediction as p
    join {{ ref('stg_trips') }} as t
        on p.feed = t.feed and p.trip_id = t.trip_id and p.start_date = t.start_date
    where t.is_completed and not t.is_cancelled and t.last_delay_s is not null
      and t.last_stop_sequence > p.current_stop_sequence  -- the prediction was made before the end
)

select
    service_date,
    mode,
    model_version,
    count(*) as trips_scored,
    round(avg(abs_err_model) / 60.0, 2) as mae_model_min,
    round(avg(abs_err_naive) / 60.0, 2) as mae_naive_min,
    round(1 - avg(abs_err_model) / nullif(avg(abs_err_naive), 0), 4) as skill,
    round(percentile_approx(abs_err_model, 0.9) / 60.0, 2) as p90_err_model_min,
    round(percentile_approx(abs_err_naive, 0.9) / 60.0, 2) as p90_err_naive_min,
    round(avg(last_stop_sequence - current_stop_sequence), 1) as avg_stops_ahead
from scored
group by 1, 2, 3
