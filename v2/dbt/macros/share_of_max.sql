{#
  Each value divided by the largest in its group (a week or a month), so two
  measures share a 0-1 scale. If every value is 0, they all become 0 instead
  of dividing by zero. Same as share_of_max() in v1's notebook.

  {{ share_of_max('done_rate', 'week_end') }} becomes:
      coalesce(done_rate / nullif(max(done_rate) over (partition by week_end), 0), 0)
#}
{% macro share_of_max(column, group_by) %}
    coalesce({{ column }} / nullif(max({{ column }}) over (partition by {{ group_by }}), 0), 0)
{% endmacro %}
