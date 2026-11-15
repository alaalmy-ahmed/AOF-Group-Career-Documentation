"""
Tests that need Postgres: the load (load_workbook.py), the dbt models
(build_models.py) and the weekly Excel ranking (weekly_ranking.py). They run
on the sample workbook in a test database, and are skipped unless
TEST_PGDATABASE is set (see the `database` fixture in conftest.py). The dbt
tests are also skipped when dbt isn't installed (DBT_EXECUTABLE).
"""

import shutil
from datetime import date

import pandas as pd
import psycopg2
import pytest

import build_models
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
    issues.loc[issues.index[-1], "Due time"] = "9-11 pm"    # no such task: fails at the very last step, the issues

    monkeypatch.setattr(load_workbook, "DATABASE", database)
    monkeypatch.setattr(load_workbook, "read_workbook", lambda: sheets)       # the broken workbook
    # Switch the checks off, so the mistake gets past them and fails inside the transaction
    monkeypatch.setattr(load_workbook, "find_problems", lambda sheets: [])
    with pytest.raises(ValueError, match="Unknown tasks for these issues"):
        load_workbook.main()

    # Managers, branches, their months, meals and tasks were inserted before it failed, and were all rolled back
    assert all_counts(database) == {"scheduled_tasks": 0, "task_misses": 0, "quality_issues": 0}
    assert count_rows(database, "managers") == 0
    assert count_rows(database, "branch_managers") == 0


def test_a_corrected_manager_is_updated(database, monkeypatch, capsys):
    monkeypatch.setattr(load_workbook, "DATABASE", database)
    load_workbook.main()

    # The data entry fixes one branch's manager for October, then the load runs again
    sheets = read_workbook()
    managers = sheets["Managers"]
    first = managers.index[0]
    branch, old_manager = managers.at[first, "Branch"], managers.at[first, "Manager"]
    new_manager = next(name for name in managers["Manager"] if name != old_manager)
    managers.at[first, "Manager"] = new_manager
    monkeypatch.setattr(load_workbook, "read_workbook", lambda: sheets)
    monkeypatch.setattr(load_workbook, "find_problems", lambda sheets: [])   # issues still name the old manager
    load_workbook.main()

    assert "branch_managers: 1 new or changed" in capsys.readouterr().out
    assert query(database, f"""
        SELECT m.name FROM ops.branch_managers bm
          JOIN ops.branches b ON b.code = bm.branch_code
          JOIN ops.managers m USING (manager_id)
         WHERE b.name = '{branch}' AND bm.month = '2026-10-01'""") == (new_manager,)


@pytest.fixture
def built(database, monkeypatch):
    """The sample loaded, then the dbt models built with every dbt check and
    unit test (build_models.py). Skipped when dbt isn't installed."""
    if shutil.which(build_models.DBT_EXECUTABLE) is None:
        pytest.skip(f"dbt not found (DBT_EXECUTABLE={build_models.DBT_EXECUTABLE!r})")
    monkeypatch.setattr(load_workbook, "DATABASE", database)
    monkeypatch.setattr(weekly_ranking, "DATABASE", database)
    monkeypatch.setenv("PGDATABASE", database)              # dbt reads it from profiles.yml
    load_workbook.main()
    with pytest.raises(SystemExit) as exit_code:
        build_models.main()
    assert exit_code.value.code == 0                        # every model built, every check passed
    return database


def query(database, sql):
    conn = psycopg2.connect(dbname=database)
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()
    finally:
        conn.close()


def test_daily_kpis_add_up_to_the_workbook(built):
    sheets = read_workbook()
    tasks, issues = sheets["Source Data"], sheets["Reviewing Reports"]
    days, branches = tasks["Date"].nunique(), len(sheets["branches and codes"])

    rows, missed, issue_count = query(built, """
        SELECT count(*), sum(tasks_missed)::int, sum(quality_issues)::int FROM reporting.branch_daily""")
    assert rows == days * branches                          # every branch, every day
    assert missed == tasks["Branches Missed Tasks"].map(lambda cell: len(split_names(cell))).sum()
    assert issue_count == len(issues)


def test_weekly_ranking_writes_the_week(built, tmp_path, monkeypatch):
    monkeypatch.setattr(weekly_ranking, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_ranking, "REPORT_DATE", date(2026, 10, 26))     # a Monday: the week Oct 14-20
    weekly_ranking.main()

    branches = pd.read_excel(tmp_path / "Branches Weekly Performance Summary.xlsx")
    managers = pd.read_excel(tmp_path / "Managers Weekly Performance Summary.xlsx")
    assert list(branches.columns) == ["Manager", "Branch", "Done Rate", "Number of Issues",
                                      "Branches Rank", "Completion Grade"]
    assert list(managers.columns) == ["Manager", "Done Rate", "Issues per Branch", "Number of Issues", "Managers Rank"]
    assert len(branches) == 36 and len(managers) == 10
    assert branches["Branches Rank"].iloc[0] == 1 and managers["Managers Rank"].iloc[0] == 1

    # The week's issues, counted straight from the workbook
    issues = read_workbook()["Reviewing Reports"]
    week = issues[(issues["Date"] >= date(2026, 10, 14)) & (issues["Date"] <= date(2026, 10, 20))]
    assert branches["Number of Issues"].sum() == managers["Number of Issues"].sum() == len(week)


def test_a_week_with_no_data_stops(built, tmp_path, monkeypatch):
    monkeypatch.setattr(weekly_ranking, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_ranking, "REPORT_DATE", date(2026, 11, 10))
    with pytest.raises(SystemExit):
        weekly_ranking.main()
    assert list(tmp_path.iterdir()) == []
