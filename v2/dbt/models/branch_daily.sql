-- One row per branch per day with tasks: the two KPIs at the smallest grain,
-- with the manager who ran the branch that month. Power BI's weekly, monthly,
-- quarterly and yearly reports can all add these rows up.
--
-- Every branch is due every scheduled task, so tasks_due is the same for all
-- branches on a day.

with tasks_per_day as (
    select task_date, count(*) as tasks_due
    from {{ source('ops', 'scheduled_tasks') }}
    group by task_date
),

misses as (
    select t.task_date, m.branch_code, count(*) as tasks_missed
    from {{ source('ops', 'task_misses') }} as m
    join {{ source('ops', 'scheduled_tasks') }} as t using (task_id)
    group by t.task_date, m.branch_code
),

issues as (
    select t.task_date, i.branch_code, count(*) as quality_issues
    from {{ source('ops', 'quality_issues') }} as i
    join {{ source('ops', 'scheduled_tasks') }} as t using (task_id)
    group by t.task_date, i.branch_code
)

select
    d.task_date,
    b.code as branch_code,
    b.name as branch,
    m.name as manager,
    d.tasks_due,
    coalesce(x.tasks_missed, 0) as tasks_missed,
    d.tasks_due - coalesce(x.tasks_missed, 0) as tasks_submitted,
    -- Same formula as the ranking's done rate. To get a week's or a month's
    -- rate, add up the counts first: an average of daily rates is wrong.
    100 - round(100.0 * coalesce(x.tasks_missed, 0) / d.tasks_due, 1) as submission_rate,
    coalesce(i.quality_issues, 0) as quality_issues

from tasks_per_day as d
-- Every branch with a manager that month (the workbook check makes sure
-- every branch has one in every month with data)
join {{ source('ops', 'branch_managers') }} as bm on bm.month = date_trunc('month', d.task_date)
join {{ source('ops', 'branches') }} as b on b.code = bm.branch_code
join {{ source('ops', 'managers') }} as m on m.manager_id = bm.manager_id
left join misses as x on x.task_date = d.task_date and x.branch_code = b.code
left join issues as i on i.task_date = d.task_date and i.branch_code = b.code
