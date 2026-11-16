-- Each branch's meals, week by week: how many of the meal's tasks it was due,
-- how many it missed, and its quality issues on that meal. One row per branch
-- per meal per Wednesday-Tuesday week (step 9). The weekly dashboard lists,
-- under each branch, the meals with a missed task or an issue.
--
-- Every branch is due every scheduled task, so tasks_due is the same for all
-- branches in a week.

with tasks as (
    select task_id, meal_id, {{ week_end('task_date') }} as week_end
    from {{ source('ops', 'scheduled_tasks') }}
),

due as (
    select week_end, meal_id, count(*) as tasks_due
    from tasks
    group by week_end, meal_id
),

-- The branches in each week (branch_daily has every branch, every day)
branches as (
    select distinct {{ week_end('task_date') }} as week_end, branch_code, branch
    from {{ ref('branch_daily') }}
),

misses as (
    select t.week_end, t.meal_id, m.branch_code, count(*) as tasks_missed
    from {{ source('ops', 'task_misses') }} as m
    join tasks as t using (task_id)
    group by t.week_end, t.meal_id, m.branch_code
),

issues as (
    select t.week_end, t.meal_id, i.branch_code, count(*) as quality_issues
    from {{ source('ops', 'quality_issues') }} as i
    join tasks as t using (task_id)
    group by t.week_end, t.meal_id, i.branch_code
)

select
    d.week_end,
    b.branch_code,
    b.branch,
    meal.name as meal,
    d.tasks_due,
    coalesce(x.tasks_missed, 0) as tasks_missed,
    coalesce(i.quality_issues, 0) as quality_issues

from due as d
join branches as b on b.week_end = d.week_end
join {{ source('ops', 'meals') }} as meal on meal.meal_id = d.meal_id
left join misses as x
    on x.week_end = d.week_end and x.meal_id = d.meal_id and x.branch_code = b.branch_code
left join issues as i
    on i.week_end = d.week_end and i.meal_id = d.meal_id and i.branch_code = b.branch_code
