-- The two KPIs for all branches together, for every month, quarter and year.
-- The headline numbers of the monthly, quarterly and yearly reports, and the
-- month-by-month trend in the quarterly and yearly ones (step 10).
--
--   period          = 'month', 'quarter' or 'year'
--   period_start    = its first day (date_trunc: 2026-10-26 -> 2026-10-01, 2026-10-01, 2026-01-01)
--   submission rate = 100 - missed / due * 100, rounded to 1 decimal, from the period's counts

select
    p.period,
    date_trunc(p.period, d.task_date)::date as period_start,
    sum(d.tasks_due) as tasks_due,
    sum(d.tasks_missed) as tasks_missed,
    sum(d.tasks_submitted) as tasks_submitted,
    100 - round(100.0 * sum(d.tasks_missed) / sum(d.tasks_due), 1) as submission_rate,
    sum(d.quality_issues) as quality_issues

from {{ ref('branch_daily') }} as d
-- Every day counts once in its month, once in its quarter and once in its year
cross join (values ('month'), ('quarter'), ('year')) as p (period)
group by p.period, date_trunc(p.period, d.task_date)
