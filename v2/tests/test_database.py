"""
Tests that need Postgres: the load (load_workbook.py) and the ranking's
counts (weekly_ranking.read_counts). They run on the sample workbook in a
test database, and are skipped unless TEST_PGDATABASE is set (see the
`database` fixture in conftest.py).
"""

from datetime import date

import pytest

import load_workbook
import weekly_ranking
from conftest import count_rows
from validate_workbook import read_workbook, split_names

# The sample workbook has 84 tasks (date, meal, due time), 141 missed
# branches and 90 quality issues.
SAMPLE_COUNTS = {"scheduled_tasks": 84, "task_misses": 141, "quality_issues": 90}


def all_counts(database):
    return {table: count_rows(database, table) for table in SAMPLE_COUNTS}


def test_load_adds_everything_once(database, monkeypatch, capsys):
    monkeypatch.setattr(load_workbook, "DATABASE", database)

    load_workbook.main()
    assert all_counts(database) == SAMPLE_COUNTS

    load_workbook.main()                                    # a second run adds nothing
    assert all_counts(database) == SAMPLE_COUNTS
    assert "quality_issues:  0 new of 90" in capsys.readouterr().out    # capsys holds what was printed


def test_a_failed_load_saves_nothing(database, monkeypatch):
    sheets = read_workbook()
    issues = sheets["Reviewing Reports"]
    issues.loc[issues.index[-1], "Manager"] = "Nobody"      # fails at the very last step, the issues

    monkeypatch.setattr(load_workbook, "DATABASE", database)
    monkeypatch.setattr(load_workbook, "read_workbook", lambda: sheets)       # the broken workbook
    # Switch the checks off, so the mistake gets past them and fails inside the transaction
    monkeypatch.setattr(load_workbook, "find_problems", lambda sheets: [])
    with pytest.raises(ValueError, match="Unknown managers in Reviewing Reports"):
        load_workbook.main()

    # Managers, meals, branches and tasks were inserted before it failed, and were all rolled back
    assert all_counts(database) == {"scheduled_tasks": 0, "task_misses": 0, "quality_issues": 0}
    assert count_rows(database, "managers") == 0


def test_ranking_counts_match_the_workbook(database, monkeypatch):
    monkeypatch.setattr(load_workbook, "DATABASE", database)
    monkeypatch.setattr(weekly_ranking, "DATABASE", database)
    load_workbook.main()

    first_day, last_day = date(2026, 10, 20), date(2026, 10, 26)
    task_count, branches = weekly_ranking.read_counts(first_day, last_day)

    # The same numbers, counted straight from the workbook
    sheets = read_workbook()
    tasks = sheets["Source Data"]
    week_tasks = tasks[(tasks["Date"] >= first_day) & (tasks["Date"] <= last_day)]
    issues = sheets["Reviewing Reports"]
    week_issues = issues[(issues["Date"] >= first_day) & (issues["Date"] <= last_day)]

    assert task_count == len(week_tasks.drop_duplicates(["Date", "Meal", "Due time"]))
    assert branches["missed"].sum() == week_tasks["Branches Missed Tasks"].map(lambda cell: len(split_names(cell))).sum()
    assert branches["Number of Issues"].sum() == len(week_issues)
    assert len(branches) == len(sheets["branches and codes"])     # every branch, even with nothing
