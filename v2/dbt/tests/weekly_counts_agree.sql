-- The weekly dashboard shows a week's numbers at four levels: the headline
-- (weekly_kpis), each branch (branch_weekly_ranking), each branch's meals
-- (branch_meal_weekly), and under each meal the issue descriptions
-- (issue_descriptions_weekly) and the missed tasks (missed_tasks). They must
-- add up to the same totals every week, or a manager would see numbers that
-- don't match.
--
-- Returns the weeks where they don't agree; the check passes when there are none.

with headline as (
    select week_end, quality_issues as issues, tasks_missed as missed
    from {{ ref('weekly_kpis') }}
),

branches as (
    select week_end, sum(number_of_issues) as issues
    from {{ ref('branch_weekly_ranking') }}
    group by week_end
),

meals as (
    select week_end, sum(quality_issues) as issues, sum(tasks_missed) as missed
    from {{ ref('branch_meal_weekly') }}
    group by week_end
),

descriptions as (
    select week_end, sum(issues) as issues
    from {{ ref('issue_descriptions_weekly') }}
    group by week_end
),

misses as (
    select week_end, count(*) as missed
    from {{ ref('missed_tasks') }}
    group by week_end
)

select
    h.week_end,
    h.issues as headline_issues,
    b.issues as branch_issues,
    m.issues as meal_issues,
    coalesce(d.issues, 0) as description_issues,
    h.missed as headline_missed,
    m.missed as meal_missed,
    coalesce(x.missed, 0) as missed_task_rows
from headline as h
left join branches as b using (week_end)
left join meals as m using (week_end)
left join descriptions as d using (week_end)
left join misses as x using (week_end)
where b.issues is distinct from h.issues
   or m.issues is distinct from h.issues
   or coalesce(d.issues, 0) <> h.issues
   or m.missed is distinct from h.missed
   or coalesce(x.missed, 0) <> h.missed
