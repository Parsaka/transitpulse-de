-- Share of realtime trips found in the static schedule (dim_trips). Below 60 % the static feed
-- is probably stale or the ids changed; the marts keep working (route match is separate), but the
-- headsign/direction enrichment degrades. Warning, not error: a dip must not block the gold build.
-- Measured 2026-10-23: 0.72 on 2026-10-22, lower on the current day because trips of the next
-- schedule version and short-notice extra services are in the feed before they are in the zip.
{{ config(severity='warn') }}
with t as (
    select count(*) as n, count(case when in_schedule then 1 end) as matched
    from {{ ref('stg_trips') }}
)
select * from t where matched / n < 0.60
