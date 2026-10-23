-- Observed stop events must lie in the past relative to the newest feed timestamp (sanity check
-- on the settle logic in stg_stop_events).
select count(*) as violations
from {{ ref('stg_stop_events') }}
where is_observed and event_ts >= (select max(feed_ts) from {{ ref('stg_stop_events') }})
having count(*) > 0
