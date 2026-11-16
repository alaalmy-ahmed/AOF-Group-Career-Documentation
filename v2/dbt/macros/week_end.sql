{#
  The Tuesday that ends a day's Wednesday-Tuesday week. isodow numbers the
  days Monday = 1 ... Sunday = 7, so Tuesday (2) adds 0 days, Wednesday (3)
  adds 6, and Monday (1) adds 1.

  {{ week_end('task_date') }} becomes:
      (task_date + ((9 - extract(isodow from task_date)::int) % 7))
#}
{% macro week_end(day) %}
    ({{ day }} + ((9 - extract(isodow from {{ day }})::int) % 7))
{% endmacro %}
