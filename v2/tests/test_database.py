"""
Tests that need Postgres: the load (load_workbook.py), the dbt models
(build_models.py), the weekly Excel ranking (weekly_ranking.py) and the weekly
dashboard (weekly_dashboard.py). They run
on a copy of the sample's daily files in a test database, and are skipped
unless TEST_PGDATABASE is set (see the `database` fixture in conftest.py).
The dbt tests are also skipped when dbt isn't installed (DBT_EXECUTABLE).
"""

import os
import shutil
from collections import Counter
from datetime import date

import pandas as pd
import psycopg2
import pytest

import build_models
import load_workbook
import weekly_dashboard
import weekly_ranking
from conftest import count_rows
from validate_workbook import read_intake, split_names

# The sample's 14 daily files have 84 tasks (date, meal, due time), 141
# missed branches and 90 quality issues.
SAMPLE_COUNTS = {"scheduled_tasks": 84, "task_misses": 141, "quality_issues": 90}


def all_counts(database):
    return {table: count_rows(database, table) for table in SAMPLE_COUNTS}


def sample_tables():
    """The sample's tasks and issues from every daily file, and its branches."""
    files = read_intake()
    tasks = pd.concat([sheets["Source Data"] for _, _, sheets in files])
    issues = pd.concat([sheets["Reviewing Reports"] for _, _, sheets in files])
    return tasks, issues, files[0][2]["branches and codes"]


@pytest.fixture(autouse=True)
def copy_of_the_sample(sample_intake):
    """Every test here reads a copy of the sample's intake folder (conftest.py)."""
    return sample_intake


def test_load_adds_everything_once(database, monkeypatch, capsys):
    monkeypatch.setattr(load_workbook, "DATABASE", database)

    load_workbook.main()
    assert all_counts(database) == SAMPLE_COUNTS

    load_workbook.main()                                    # a second run adds nothing
    assert all_counts(database) == SAMPLE_COUNTS
    assert "quality_issues:  0 new of 90" in capsys.readouterr().out    # capsys holds what was printed


def test_a_failed_load_saves_nothing(database, monkeypatch):
    files = read_intake()
    issues = files[-1][2]["Reviewing Reports"]
    issues.loc[issues.index[-1], "Due time"] = "9-11 pm"    # no such task: fails at the very last step, the issues

    monkeypatch.setattr(load_workbook, "DATABASE", database)
    monkeypatch.setattr(load_workbook, "read_intake", lambda: files)          # the broken files
    # Switch the checks off, so the mistake gets past them and fails inside the transaction
    monkeypatch.setattr(load_workbook, "find_intake_problems", lambda files: [])
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
    files = read_intake()
    managers = files[0][2]["Managers"]                      # the lists, shared by every file
    first = managers.index[0]
    branch, old_manager = managers.at[first, "Branch"], managers.at[first, "Manager"]
    new_manager = next(name for name in managers["Manager"] if name != old_manager)
    managers.at[first, "Manager"] = new_manager
    monkeypatch.setattr(load_workbook, "read_intake", lambda: files)
    monkeypatch.setattr(load_workbook, "find_intake_problems", lambda files: [])   # issues still name the old manager
    load_workbook.main()

    assert "branch_managers: 1 new or changed" in capsys.readouterr().out
    assert query(database, f"""
        SELECT m.name FROM ops.branch_managers bm
          JOIN ops.branches b ON b.code = bm.branch_code
          JOIN ops.managers m USING (manager_id)
         WHERE b.name = '{branch}' AND bm.month = '2026-10-01'""") == (new_manager,)


# --------------------------------------------------------------------------------------------------------
# Keeping the last 10 days: files are deleted only once they're loaded

def test_old_files_are_deleted_after_the_load(database, sample_intake, monkeypatch, capsys):
    monkeypatch.setattr(load_workbook, "DATABASE", database)
    monkeypatch.setattr(load_workbook, "KEEP_DAYS", 10)
    monkeypatch.setattr(load_workbook, "REPORT_DATE", date(2026, 10, 27))   # keeps Oct 18-27
    load_workbook.main()

    assert all_counts(database) == SAMPLE_COUNTS            # all 14 days are in the database...
    assert sorted(os.listdir(sample_intake)) == [f"2026-10-{day}.xlsx" for day in range(18, 27)]  # ...9 files stay
    assert "Deleted 5 daily file(s) with only days up to 2026-10-17" in capsys.readouterr().out


def test_nothing_is_deleted_when_the_load_fails(database, sample_intake, monkeypatch):
    shutil.copy(sample_intake / "2026-10-13.xlsx", sample_intake / "2026-10-13 resent.xlsx")  # a day in two files
    monkeypatch.setattr(load_workbook, "DATABASE", database)
    monkeypatch.setattr(load_workbook, "KEEP_DAYS", 10)
    monkeypatch.setattr(load_workbook, "REPORT_DATE", date(2026, 10, 27))
    with pytest.raises(SystemExit):
        load_workbook.main()

    assert all_counts(database) == {"scheduled_tasks": 0, "task_misses": 0, "quality_issues": 0}
    assert len(os.listdir(sample_intake)) == 15             # every file still there


@pytest.fixture
def built(database, monkeypatch):
    """The sample loaded, then the dbt models built with every dbt check and
    unit test (build_models.py). Skipped when dbt isn't installed."""
    if shutil.which(build_models.DBT_EXECUTABLE) is None:
        pytest.skip(f"dbt not found (DBT_EXECUTABLE={build_models.DBT_EXECUTABLE!r})")
    monkeypatch.setattr(load_workbook, "DATABASE", database)
    monkeypatch.setattr(weekly_ranking, "DATABASE", database)
    monkeypatch.setattr(weekly_dashboard, "DATABASE", database)
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


def test_daily_kpis_add_up_to_the_daily_files(built):
    tasks, issues, branch_list = sample_tables()
    days, branches = tasks["Date"].nunique(), len(branch_list)

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

    # The week's issues, counted straight from the daily files
    _, issues, _ = sample_tables()
    week = issues[(issues["Date"] >= date(2026, 10, 14)) & (issues["Date"] <= date(2026, 10, 20))]
    assert branches["Number of Issues"].sum() == managers["Number of Issues"].sum() == len(week)


def test_a_week_with_no_data_stops(built, tmp_path, monkeypatch):
    monkeypatch.setattr(weekly_ranking, "OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(weekly_ranking, "REPORT_DATE", date(2026, 11, 10))
    with pytest.raises(SystemExit):
        weekly_ranking.main()
    assert not (tmp_path / "out").exists()


# --------------------------------------------------------------------------------------------------------
# The weekly dashboard (step 9)

def in_week(table, start, end):
    return table[(table["Date"] >= start) & (table["Date"] <= end)]


def test_weekly_dashboard_matches_the_daily_files(built, tmp_path, monkeypatch):
    monkeypatch.setattr(weekly_dashboard, "OUTPUT_DIR", str(tmp_path))
    monkeypatch.setattr(weekly_dashboard, "REPORT_DATE", date(2026, 10, 26))     # a Monday: the week Oct 14-20
    weekly_dashboard.main()
    page = (tmp_path / "Weekly Report 2026-10-14 to 2026-10-20.html").read_text(encoding="utf-8")

    # The week's KPIs, counted straight from the daily files
    tasks, issues, branch_list = sample_tables()
    week_tasks = in_week(tasks, date(2026, 10, 14), date(2026, 10, 20))
    week_issues = in_week(issues, date(2026, 10, 14), date(2026, 10, 20))
    due = len(week_tasks.drop_duplicates(["Date", "Meal", "Due time"])) * len(branch_list)   # every branch, every task
    missed = week_tasks["Branches Missed Tasks"].map(lambda cell: len(split_names(cell))).sum()
    rate = 100 - round(100 * missed / due, 1)

    assert f'<div class="value">{rate:g}%</div>' in page
    assert f'<div class="value">{len(week_issues)}</div>' in page
    # The week before (the sample only has its last day, Oct 13)
    last_week_issues = in_week(issues, date(2026, 10, 7), date(2026, 10, 13))
    assert f"▲ {len(week_issues) - len(last_week_issues)} vs last week" in page

    # Under each branch, its meals with a missed task or an issue
    code_of = dict(zip(branch_list["Branch"], branch_list["Code"]))
    missed_by = Counter((code_of[name], meal)                       # {(branch code, meal): times missed}
                        for meal, cell in zip(week_tasks["Meal"], week_tasks["Branches Missed Tasks"])
                        for name in split_names(cell))
    issues_by = Counter(zip(week_issues["Code"], week_issues["Meal"]))
    expected = {key: (missed_by[key], issues_by[key]) for key in missed_by | issues_by}
    week = weekly_dashboard.read_week(date(2026, 10, 20))
    shown = {(m.branch_code, m.meal): (m.missed, m.issues) for m in week["meals"].itertuples()}
    assert shown == expected

    # Under each meal: the issue descriptions with their counts, and the day and due time of each miss
    shown = {(d.branch_code, d.meal, d.description): d.issues for d in week["descriptions"].itertuples()}
    assert shown == Counter(zip(week_issues["Code"], week_issues["Meal"], week_issues["Description"]))
    expected = sorted((code_of[name], meal, day, due)
                      for day, meal, due, cell in zip(week_tasks["Date"], week_tasks["Meal"],
                                                      week_tasks["Due time"], week_tasks["Branches Missed Tasks"])
                      for name in split_names(cell))
    assert sorted(week["missed"].itertuples(index=False, name=None)) == expected
    assert len(week["branches"]) == len(branch_list) and len(week["managers"]) == 10

    # "vs last week" uses each branch's and manager's real rank from the week before
    last_week = weekly_dashboard.read_week(date(2026, 10, 13))
    for table, name in (("branches", "branch"), ("managers", "manager")):
        shown = dict(zip(week[table][name], week[table]["last_rank"]))
        actual = dict(zip(last_week[table][name], last_week[table]["rank"]))
        assert shown == actual


def test_a_dashboard_week_with_no_data_stops(built, tmp_path, monkeypatch):
    monkeypatch.setattr(weekly_dashboard, "OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(weekly_dashboard, "REPORT_DATE", date(2026, 11, 10))
    with pytest.raises(SystemExit):
        weekly_dashboard.main()
    assert not (tmp_path / "out").exists()
