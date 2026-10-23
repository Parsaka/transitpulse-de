-- At least 70 % of realtime trips must match the static schedule (dim_trips). Lower means the
-- static feed is stale or the ids changed; the marts still work (route match is separate) but the
-- headsign/direction enrichment silently degrades.
with t as (
    select count(*) as n, count(case when in_schedule then 1 end) as matched
    from {{ ref('stg_trips') }}
)
select * from t where matched / n < 0.70
