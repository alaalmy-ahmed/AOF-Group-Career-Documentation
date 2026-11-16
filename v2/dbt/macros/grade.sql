{#
  The grade for a ranking score (docs/metrics.md). Used by the branch and the
  manager rankings, so both grade the same way.

  {{ grade('score') }} becomes:
      case when score > 0.95 then 'Excellent' ... end
#}
{% macro grade(score) %}
    case
        when {{ score }} > 0.95 then 'Excellent'
        when {{ score }} > 0.90 then 'Good'
        when {{ score }} > 0.80 then 'Fair'
        when {{ score }} > 0.70 then 'Bad'
        when {{ score }} > 0 then 'Terrible'
    end
{% endmacro %}
