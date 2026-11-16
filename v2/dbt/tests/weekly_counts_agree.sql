-- The weekly dashboard shows a week's numbers at three levels: the headline
-- (weekly_kpis), each branch (branch_weekly_ranking) and each branch's meals
-- (branch_meal_weekly). They must add up to the same totals every week, or a
-- manager would see numbers that don't match.
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
)

select
    h.week_end,
    h.issues as headline_issues,
    b.issues as branch_issues,
    m.issues as meal_issues,
    h.missed as headline_missed,
    m.missed as meal_missed
from headline as h
left join branches as b using (week_end)
left join meals as m using (week_end)
where b.issues is distinct from h.issues
   or m.issues is distinct from h.issues
   or m.missed is distinct from h.missed
