-- The weekly manager ranking for every Wednesday-Tuesday week, from the branch
-- ranking. Each branch counts for its manager on the week's last day.
--
--   done rate         = average of the manager's branches' done rates
--   issues per branch = average issues per branch
--   score             = 0.85 * done rate share + 0.15 * (1 - issues per branch share)
--                       (issues count a little more for managers, who fix them)

with managers as (
    select
        week_start,
        week_end,
        manager,
        count(*) as branches,
        round(avg(done_rate), 1) as done_rate,
        round(avg(number_of_issues), 1) as issues_per_branch,
        sum(number_of_issues) as number_of_issues
    from {{ ref('branch_weekly_ranking') }}
    group by week_start, week_end, manager
),

scored as (
    select
        *,
        0.85 * {{ share_of_max('done_rate', 'week_end') }}
            + 0.15 * (1 - {{ share_of_max('issues_per_branch', 'week_end') }}) as score
    from managers
)

select
    week_start,
    week_end,
    manager,
    branches,
    done_rate,
    issues_per_branch,
    number_of_issues,
    rank() over (partition by week_end order by score desc) as managers_rank,
    round(score, 4) as score    -- for reading; the rank and grade use the exact score
from scored
