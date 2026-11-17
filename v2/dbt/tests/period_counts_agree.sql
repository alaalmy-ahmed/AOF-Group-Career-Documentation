-- The monthly, quarterly and yearly reports show each period's numbers at four
-- levels: the headline (period_kpis), each branch (branch_period_ranking), each
-- branch's meals (branch_meal_period) and their issue descriptions
-- (issue_descriptions_period). Every period, they must add up to the same
-- totals. And a quarter or a year must be the sum of its months.
--
-- Returns the periods where something doesn't agree; the check passes when there are none.

with headline as (
    select period, period_start, quality_issues as issues, tasks_missed as missed
    from {{ ref('period_kpis') }}
),

branches as (
    select period, period_start, sum(number_of_issues) as issues
    from {{ ref('branch_period_ranking') }}
    group by period, period_start
),

meals as (
    select period, period_start, sum(quality_issues) as issues, sum(tasks_missed) as missed
    from {{ ref('branch_meal_period') }}
    group by period, period_start
),

descriptions as (
    select period, period_start, sum(issues) as issues
    from {{ ref('issue_descriptions_period') }}
    group by period, period_start
),

-- Each quarter and year, added up from its months
from_months as (
    select p.period, date_trunc(p.period, k.period_start)::date as period_start,
           sum(k.quality_issues) as issues, sum(k.tasks_missed) as missed
    from {{ ref('period_kpis') }} as k
    cross join (values ('quarter'), ('year')) as p (period)
    where k.period = 'month'
    group by p.period, date_trunc(p.period, k.period_start)
)

select h.period, h.period_start, h.issues, h.missed,
       b.issues as branch_issues, m.issues as meal_issues, m.missed as meal_missed,
       coalesce(d.issues, 0) as description_issues, f.issues as issues_from_months, f.missed as missed_from_months
from headline as h
left join branches as b using (period, period_start)
left join meals as m using (period, period_start)
left join descriptions as d using (period, period_start)
left join from_months as f using (period, period_start)
where b.issues is distinct from h.issues
   or m.issues is distinct from h.issues
   or coalesce(d.issues, 0) <> h.issues
   or m.missed is distinct from h.missed
   or (h.period <> 'month' and (f.issues is distinct from h.issues or f.missed is distinct from h.missed))
