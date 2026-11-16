-- How many times each quality issue description (from Fixed Choices) came up
-- for a branch's meal, week by week. One row per branch, meal, description and
-- Wednesday-Tuesday week. The weekly dashboard lists them under the meal (step 9).

select
    {{ week_end('t.task_date') }} as week_end,
    i.branch_code,
    meal.name as meal,
    i.description,
    count(*) as issues

from {{ source('ops', 'quality_issues') }} as i
join {{ source('ops', 'scheduled_tasks') }} as t using (task_id)
join {{ source('ops', 'meals') }} as meal on meal.meal_id = t.meal_id
group by week_end, i.branch_code, meal.name, i.description
