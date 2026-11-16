-- The two KPIs for all branches together, one row per Wednesday-Tuesday week.
-- The weekly dashboard's headline numbers (weekly_dashboard.py, step 9).
--
--   tasks_due       = every branch's tasks added up (each branch is due every task)
--   submission rate = 100 - missed / due * 100, rounded to 1 decimal,
--                     from the week's counts (not an average of daily rates)

with days as (
    select
        *,
        {{ week_end('task_date') }} as week_end
    from {{ ref('branch_daily') }}
)

select
    week_end - 6 as week_start,
    week_end,
    sum(tasks_due) as tasks_due,
    sum(tasks_missed) as tasks_missed,
    sum(tasks_submitted) as tasks_submitted,
    100 - round(100.0 * sum(tasks_missed) / sum(tasks_due), 1) as submission_rate,
    sum(quality_issues) as quality_issues
from days
group by week_end
