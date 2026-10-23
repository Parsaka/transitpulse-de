{{ config(materialized='table') }}

-- One row per pipeline update from the published event log: start, end, final state, duration.
-- Source of the pipeline-success SLO.

with events as (
    select
        origin.update_id as update_id,
        origin.pipeline_name as pipeline_name,
        event_type,
        timestamp as event_ts,
        get_json_object(details, '$.update_progress.state') as state,
        get_json_object(details, '$.create_update.cause') as cause
    from {{ source('ops', 'lakeflow_event_log') }}
    where event_type in ('create_update', 'update_progress')
)

select
    update_id,
    min(pipeline_name) as pipeline_name,
    min(case when event_type = 'create_update' then event_ts end) as started_at,
    max(event_ts) as last_event_at,
    max(case when state in ('COMPLETED', 'FAILED', 'CANCELED') then state end) as final_state,
    (max(case when state = 'COMPLETED' then 1 else 0 end) = 1) as succeeded,
    round((unix_timestamp(max(event_ts)) - unix_timestamp(min(case when event_type = 'create_update' then event_ts end))) / 60.0, 2) as duration_min,
    to_date(min(case when event_type = 'create_update' then event_ts end)) as started_date
from events
group by update_id
having min(case when event_type = 'create_update' then event_ts end) is not null
