-- The weekly branch ranking (docs/metrics.md) for every week. A week runs
-- Wednesday to Tuesday, like the weekly Airflow run. One row per branch per week.
--
--   done rate = 100 - missed / tasks due * 100, rounded to 1 decimal
--   score     = 0.90 * done rate share + 0.10 * (1 - issues share)
--               (a share is the value divided by the week's largest)
--   rank      = 1 is the best score; ties share a rank and the next one is skipped

with days as (
    select
        *,
        {{ week_end('task_date') }} as week_end     -- the Tuesday that ends this day's week (macros/week_end.sql)
    from {{ ref('branch_daily') }}
),

weeks as (
    select
        week_end,
        branch_code,
        branch,
        -- The manager on the week's last day: if the week spans a rotation,
        -- the whole week counts for the new manager
        (array_agg(manager order by task_date desc))[1] as manager,
        sum(tasks_due) as tasks_due,
        sum(tasks_missed) as tasks_missed,
        sum(quality_issues) as number_of_issues
    from days
    group by week_end, branch_code, branch
),

scored as (
    select
        *,
        0.90 * {{ share_of_max('done_rate', 'week_end') }}
            + 0.10 * (1 - {{ share_of_max('number_of_issues', 'week_end') }}) as score
    from (
        select *, 100 - round(100.0 * tasks_missed / tasks_due, 1) as done_rate
        from weeks
    ) as with_rates
)

select
    week_end - 6 as week_start,
    week_end,
    manager,
    branch_code,
    branch,
    done_rate,
    number_of_issues,
    rank() over (partition by week_end order by score desc) as branches_rank,
    {{ grade('score') }} as completion_grade,      -- macros/grade.sql
    round(score, 4) as score    -- for reading; the rank and grade use the exact score
from scored
