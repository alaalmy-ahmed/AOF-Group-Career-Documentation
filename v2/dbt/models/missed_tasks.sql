-- One row per missed task: which branch missed which meal, on which day and
-- due time, and the Wednesday-Tuesday week it falls in. The weekly dashboard
-- shows the day and due time of each miss under the branch's meal (step 9).

select
    m.task_id,
    m.branch_code,
    t.task_date,
    {{ week_end('t.task_date') }} as week_end,
    meal.name as meal,
    t.due_time

from {{ source('ops', 'task_misses') }} as m
join {{ source('ops', 'scheduled_tasks') }} as t using (task_id)
join {{ source('ops', 'meals') }} as meal on meal.meal_id = t.meal_id
