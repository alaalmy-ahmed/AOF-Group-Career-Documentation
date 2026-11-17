-- Each branch's meals for every month, quarter and year: how many of the
-- meal's tasks it was due, how many it missed, and its quality issues on that
-- meal. The reports list, under each branch, the meals with a missed task or
-- an issue; the yearly one adds them up by meal for all branches (step 10).

with tasks as (
    select
        t.task_id,
        t.meal_id,
        p.period,
        date_trunc(p.period, t.task_date)::date as period_start
    from {{ source('ops', 'scheduled_tasks') }} as t
    cross join (values ('month'), ('quarter'), ('year')) as p (period)
),

due as (
    select period, period_start, meal_id, count(*) as tasks_due
    from tasks
    group by period, period_start, meal_id
),

-- The branches in each period (branch_daily has every branch, every day)
branches as (
    select distinct p.period, date_trunc(p.period, d.task_date)::date as period_start, d.branch_code, d.branch
    from {{ ref('branch_daily') }} as d
    cross join (values ('month'), ('quarter'), ('year')) as p (period)
),

misses as (
    select t.period, t.period_start, t.meal_id, m.branch_code, count(*) as tasks_missed
    from {{ source('ops', 'task_misses') }} as m
    join tasks as t using (task_id)
    group by t.period, t.period_start, t.meal_id, m.branch_code
),

issues as (
    select t.period, t.period_start, t.meal_id, i.branch_code, count(*) as quality_issues
    from {{ source('ops', 'quality_issues') }} as i
    join tasks as t using (task_id)
    group by t.period, t.period_start, t.meal_id, i.branch_code
)

select
    d.period,
    d.period_start,
    b.branch_code,
    b.branch,
    meal.name as meal,
    d.tasks_due,
    coalesce(x.tasks_missed, 0) as tasks_missed,
    coalesce(i.quality_issues, 0) as quality_issues

from due as d
join branches as b on b.period = d.period and b.period_start = d.period_start
join {{ source('ops', 'meals') }} as meal on meal.meal_id = d.meal_id
left join misses as x
    on x.period = d.period and x.period_start = d.period_start
   and x.meal_id = d.meal_id and x.branch_code = b.branch_code
left join issues as i
    on i.period = d.period and i.period_start = d.period_start
   and i.meal_id = d.meal_id and i.branch_code = b.branch_code
