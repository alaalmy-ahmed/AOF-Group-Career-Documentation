-- How many times each quality issue description came up for a branch's meal,
-- for every month, quarter and year. The reports list them under the meal (step 10).

select
    p.period,
    date_trunc(p.period, t.task_date)::date as period_start,
    i.branch_code,
    meal.name as meal,
    i.description,
    count(*) as issues

from {{ source('ops', 'quality_issues') }} as i
join {{ source('ops', 'scheduled_tasks') }} as t using (task_id)
join {{ source('ops', 'meals') }} as meal on meal.meal_id = t.meal_id
cross join (values ('month'), ('quarter'), ('year')) as p (period)
group by p.period, date_trunc(p.period, t.task_date), i.branch_code, meal.name, i.description
