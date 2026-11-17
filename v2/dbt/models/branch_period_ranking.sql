-- The branch ranking for every month, quarter and year: the weekly method
-- (branch_weekly_ranking, docs/metrics.md) over a longer period (step 10).
--
--   done rate = 100 - missed / tasks due * 100, rounded to 1 decimal
--   score     = 0.90 * done rate share + 0.10 * (1 - issues share)
--               (a share is the value divided by the period's largest)
--   rank      = 1 is the best score; ties share a rank and the next one is skipped

with periods as (
    select
        p.period,
        date_trunc(p.period, d.task_date)::date as period_start,
        d.*
    from {{ ref('branch_daily') }} as d
    cross join (values ('month'), ('quarter'), ('year')) as p (period)
),

branches as (
    select
        period,
        period_start,
        branch_code,
        branch,
        -- The manager on the period's last day. For a month that's the month's
        -- manager; a quarter or a year can have had several.
        (array_agg(manager order by task_date desc))[1] as manager,
        sum(tasks_due) as tasks_due,
        sum(tasks_missed) as tasks_missed,
        sum(quality_issues) as number_of_issues
    from periods
    group by period, period_start, branch_code, branch
),

scored as (
    select
        *,
        0.90 * {{ share_of_max('done_rate', 'period, period_start') }}
            + 0.10 * (1 - {{ share_of_max('number_of_issues', 'period, period_start') }}) as score
    from (
        select *, 100 - round(100.0 * tasks_missed / tasks_due, 1) as done_rate
        from branches
    ) as with_rates
)

select
    period,
    period_start,
    manager,
    branch_code,
    branch,
    done_rate,
    number_of_issues,
    rank() over (partition by period, period_start order by score desc) as branches_rank,
    {{ grade('score') }} as completion_grade,      -- macros/grade.sql
    round(score, 4) as score    -- for reading; the rank and grade use the exact score
from scored
