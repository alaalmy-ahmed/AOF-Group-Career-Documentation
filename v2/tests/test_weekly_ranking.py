"""
Tests for weekly_ranking.py's choice of week. The ranking math itself is now
in dbt, and its tests are dbt unit tests (dbt/models/unit_tests.yml), which
dbt runs on every build. test_database.py runs the whole chain on the sample.
"""

from datetime import date

import pytest

from weekly_ranking import week_end_for


@pytest.mark.parametrize("day, week_end", [
    (date(2026, 10, 20), date(2026, 10, 20)),   # a Tuesday is its own week's end
    (date(2026, 10, 21), date(2026, 10, 20)),   # Wednesday starts a new week, so it's last week
    (date(2026, 10, 26), date(2026, 10, 20)),   # Monday: the sample's last day
    (date(2026, 11, 3), date(2026, 11, 3)),
])
def test_week_ends_on_the_last_tuesday(day, week_end):
    assert week_end_for(day) == week_end
