-- branch_daily counts submissions branch by branch (tasks due - misses). The
-- workbook also gives a total per task (Done Tasks, stored as
-- branches_submitted). Both must agree on every day. If a branch had no
-- manager row that month, it would drop out of branch_daily and this would catch it.
--
-- Returns the days where they don't agree; the check passes when there are none.

with from_branches as (
    select task_date, sum(tasks_submitted) as submitted
    from {{ ref('branch_daily') }}
    group by task_date
),

from_workbook as (
    select task_date, sum(branches_submitted) as submitted
    from {{ source('ops', 'scheduled_tasks') }}
    group by task_date
)

select w.task_date, w.submitted as workbook_says, b.submitted as branches_add_up_to
from from_workbook as w
left join from_branches as b using (task_date)
where b.submitted is distinct from w.submitted
