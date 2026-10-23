{{ config(materialized='table') }}

-- Expectation results per day, flow and expectation, summed over every update of the day.

with progress as (
    select
        to_date(timestamp) as event_date,
        origin.flow_name as flow_name,
        from_json(
            get_json_object(details, '$.flow_progress.data_quality.expectations'),
            'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>'
        ) as expectations
    from {{ source('ops', 'lakeflow_event_log') }}
    where event_type = 'flow_progress'
      and details like '%expectations%'
)

select
    event_date,
    element_at(split(flow_name, '[.]'), -1) as flow,
    e.name as expectation,
    sum(e.passed_records) as passed_records,
    sum(e.failed_records) as failed_records,
    round(sum(e.failed_records) / nullif(sum(e.passed_records) + sum(e.failed_records), 0), 6) as fail_rate
from progress
lateral view explode(expectations) as e
group by 1, 2, 3
