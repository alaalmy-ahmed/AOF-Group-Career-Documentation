-- The manager ranking for every month, quarter and year (step 10; it replaces
-- step 7's manager_monthly_ranking, which is now the 'month' rows).
--
-- Branches move between managers every month, so the unit is a branch-month:
-- each branch counts, month by month, for the manager who ran it that month.
-- In a month that's simply the manager's branches; in a quarter or a year, a
-- manager who ran 4 branches for 3 months has 12 branch-months.
--
--   done rate              = average of the manager's branch-month done rates
--   issues per branch-month = average issues per branch-month
--   score                  = 0.85 * done rate share + 0.15 * (1 - issues per branch-month share)
--   grade                  = from the score, with the branches' thresholds

with branch_months as (
    select
        date_trunc('month', task_date)::date as month,
        branch_code,
        manager,
        sum(tasks_due) as tasks_due,
        sum(tasks_missed) as tasks_missed,
        sum(quality_issues) as number_of_issues
    from {{ ref('branch_daily') }}
    group by 1, branch_code, manager
),

periods as (
    select
        p.period,
        date_trunc(p.period, b.month)::date as period_start,
        b.*
    from branch_months as b
    cross join (values ('month'), ('quarter'), ('year')) as p (period)
),

managers as (
    select
        period,
        period_start,
        manager,
        count(distinct branch_code) as branches,
        count(*) as branch_months,
        round(avg(100 - round(100.0 * tasks_missed / tasks_due, 1)), 1) as done_rate,
        round(avg(number_of_issues), 1) as issues_per_branch_month,
        sum(number_of_issues) as number_of_issues
    from periods
    group by period, period_start, manager
),

scored as (
    select
        *,
        0.85 * {{ share_of_max('done_rate', 'period, period_start') }}
            + 0.15 * (1 - {{ share_of_max('issues_per_branch_month', 'period, period_start') }}) as score
    from managers
)

select
    period,
    period_start,
    manager,
    branches,
    branch_months,
    done_rate,
    issues_per_branch_month,
    number_of_issues,
    rank() over (partition by period, period_start order by score desc) as managers_rank,
    {{ grade('score') }} as completion_grade,      -- macros/grade.sql
    round(score, 4) as score    -- for reading; the rank and grade use the exact score
from scored
