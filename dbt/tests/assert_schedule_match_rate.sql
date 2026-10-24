-- Share of realtime trips found in the static schedule (dim_trips), per feed. Below 60 % the
-- static feed is probably stale or the ids changed; the marts keep working (route match is
-- separate), but the headsign/direction enrichment degrades. Warning, not error: a dip must not
-- block the gold build. Measured 2026-10-23 12:30 UTC (VBB): 1.00 for service date 2026-10-22,
-- 0.66 for 2026-10-23, 0.51 for 2026-10-24 (trips of the next schedule version reach the feed
-- before the static zip). Feeds with fewer than 1,000 trips are ignored (first hours of a feed).
{{ config(severity='warn') }}
with t as (
    select feed, count(*) as n, count(case when in_schedule then 1 end) as matched
    from {{ ref('stg_trips') }}
    group by feed
)
select * from t where n >= 1000 and matched / n < 0.60
