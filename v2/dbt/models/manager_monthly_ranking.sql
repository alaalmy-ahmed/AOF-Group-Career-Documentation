-- The monthly manager ranking: the weekly manager method over a whole
-- month. Branches rotate every month, so each branch counts for the manager
-- who ran it that month (branch_managers). One row per manager per month.

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

managers as (
    select
        month,
        manager,
        count(*) as branches,
        round(avg(100 - round(100.0 * tasks_missed / tasks_due, 1)), 1) as done_rate,
        round(avg(number_of_issues), 1) as issues_per_branch,
        sum(number_of_issues) as number_of_issues
    from branch_months
    group by month, manager
),

scored as (
    select
        *,
        0.85 * {{ share_of_max('done_rate', 'month') }}
            + 0.15 * (1 - {{ share_of_max('issues_per_branch', 'month') }}) as score
    from managers
)

select
    month,
    manager,
    branches,
    done_rate,
    issues_per_branch,
    number_of_issues,
    rank() over (partition by month order by score desc) as managers_rank,
    round(score, 4) as score    -- for reading; the rank and grade use the exact score
from scored
