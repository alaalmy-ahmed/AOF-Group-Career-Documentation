"""
Tests for validate_workbook.py. Each test takes the tiny workbook from
conftest.py (no mistakes), breaks one thing, and checks the exact message.
"""

from datetime import date

import pandas as pd
import pytest

import validate_workbook
from conftest import DAY, write_workbook
from validate_workbook import find_day_problems, find_problems, read_workbook


# --------------------------------------------------------------------------------------------------------
# Clean workbooks pass

def test_tiny_workbook_has_no_problems(sheets):
    assert find_problems(sheets) == []


def test_sample_workbook_has_no_problems():
    assert find_problems(read_workbook()) == []


# --------------------------------------------------------------------------------------------------------
# Stage 1: columns

def test_missing_column(sheets):
    sheets["Reviewing Reports"] = sheets["Reviewing Reports"].drop(columns=["Due time"])
    assert find_problems(sheets) == ["Reviewing Reports: missing column(s) ['Due time']"]


# --------------------------------------------------------------------------------------------------------
# Stage 2: basics

def test_blank_cell(sheets):
    sheets["Reviewing Reports"].loc[0, "Description"] = None
    assert find_problems(sheets) == ["Reviewing Reports row 2: Description is blank"]


def test_date_in_the_future(sheets):
    sheets["Reviewing Reports"].loc[0, "Date"] = date(2999, 1, 1)
    assert find_problems(sheets) == ["Reviewing Reports row 2: Date 2999-01-01 is in the future"]


# parametrize runs this test once for each value
@pytest.mark.parametrize("value", [2.5, -1, "abc"])
def test_count_must_be_a_whole_number(sheets, value):
    sheets["Source Data"]["Done Tasks"] = sheets["Source Data"]["Done Tasks"].astype(object)
    sheets["Source Data"].loc[1, "Done Tasks"] = value
    assert find_problems(sheets) == [f"Source Data row 3: Done Tasks must be a whole number >= 0, not {value!r}"]


def test_rules_wait_until_the_basics_pass(sheets):
    sheets["Reviewing Reports"].loc[0, "Description"] = None           # stage 2 problem
    sheets["Source Data"].loc[1, "Branches Missed Tasks"] = "Olayaa"   # stage 3 problem
    assert find_problems(sheets) == ["Reviewing Reports row 2: Description is blank"]


# --------------------------------------------------------------------------------------------------------
# Stage 3: rules

def test_unknown_missed_branch(sheets):
    sheets["Source Data"].loc[1, "Branches Missed Tasks"] = "Olayaa"
    assert find_problems(sheets) == ["Source Data row 3: missed branch 'Olayaa' isn't in 'branches and codes'"]


def test_missed_count_must_match_the_names(sheets):
    sheets["Source Data"].loc[1, "Missed Tasks"] = 2
    assert find_problems(sheets) == [
        "Source Data row 3: Missed Tasks says 2, but 1 branch(es) are listed in Branches Missed Tasks"]


def test_submitted_plus_missed_must_equal_all_branches(sheets):
    sheets["Source Data"].loc[0, "Done Tasks"] = 2
    assert find_problems(sheets) == [
        "Source Data, 2026-01-01 Arabi Sop 12-4 pm: 2 submitted + 0 missed = 2, but there are 3 branches"]


def test_unknown_meal(sheets):
    sheets["Source Data"].loc[0, "Meal"] = "Arabi Soup"
    problems = find_problems(sheets)
    assert "Source Data row 2: meal 'Arabi Soup' isn't in meals.xlsx" in problems


def test_code_must_match_the_branch(sheets):
    sheets["Reviewing Reports"].loc[0, "Code"] = "B3"
    assert find_problems(sheets) == ["Reviewing Reports row 2: code 'B3' is 'Rawdah', not 'Malaz'"]


def test_description_must_be_in_fixed_choices(sheets):
    sheets["Reviewing Reports"].loc[0, "Description"] = "Bread cold"
    assert find_problems(sheets) == ["Reviewing Reports row 2: description 'Bread cold' isn't in Fixed Choices"]


def test_manager_must_match_the_managers_sheet(sheets):
    sheets["Reviewing Reports"].loc[0, "Manager"] = "Manager B"
    assert find_problems(sheets) == [
        "Reviewing Reports row 2: manager is 'Manager B', but 'Managers' says 'Manager A' for this branch"]


def test_issue_needs_its_task(sheets):
    sheets["Reviewing Reports"].loc[0, "Due time"] = "9-11 pm"
    assert find_problems(sheets) == ["Reviewing Reports row 2: no task in Source Data for 2026-01-01 Arabi Sop 9-11 pm"]


def test_issue_logged_twice(sheets):
    issues = sheets["Reviewing Reports"]
    sheets["Reviewing Reports"] = pd.concat([issues, issues], ignore_index=True)
    message = "the same issue is logged more than once (same date, code, meal, due time and description)"
    assert find_problems(sheets) == [f"Reviewing Reports row 2: {message}", f"Reviewing Reports row 3: {message}"]


def test_branch_without_a_manager(sheets):
    sheets["Managers"] = sheets["Managers"].drop(index=2)              # Rawdah
    assert find_problems(sheets) == ["branches and codes row 4: 'Rawdah' has no manager in 'Managers'"]


def test_every_problem_is_listed_at_once(sheets):
    sheets["Reviewing Reports"].loc[0, "Code"] = "B3"
    sheets["Reviewing Reports"].loc[0, "Description"] = "Bread cold"
    assert len(find_problems(sheets)) == 2


# --------------------------------------------------------------------------------------------------------
# The daily check: only that day's issues

def test_day_check_catches_that_days_issue(sheets):
    sheets["Reviewing Reports"].loc[0, "Code"] = "B3"
    assert find_day_problems(sheets, DAY) == ["Reviewing Reports row 2: code 'B3' is 'Rawdah', not 'Malaz'"]


def test_day_check_ignores_tasks_and_other_days(sheets):
    sheets["Source Data"].loc[0, "Done Tasks"] = None                  # a task not filled in yet
    sheets["Reviewing Reports"].loc[0, "Code"] = "B3"                  # a mistake, but on DAY
    assert find_day_problems(sheets, date(2026, 1, 2)) == []


# --------------------------------------------------------------------------------------------------------
# Reading the workbook file

def test_read_workbook_cleans_up(sheets, tmp_path, monkeypatch):
    sheets["Source Data"].loc[1, "Branches Missed Tasks"] = "Olaya  "  # spaces at the end
    sheets["Reviewing Reports"].loc[0, "Branch"] = " Malaz"            # a space at the start
    workbook_path, meals_path = write_workbook(sheets, tmp_path)
    # monkeypatch changes a setting for this test only (tmp_path is a new empty folder)
    monkeypatch.setattr(validate_workbook, "WORKBOOK_PATH", workbook_path)
    monkeypatch.setattr(validate_workbook, "MEALS_PATH", meals_path)

    read = read_workbook()
    assert read["Reviewing Reports"].loc[0, "Branch"] == "Malaz"
    assert read["Source Data"].loc[0, "Date"] == DAY                   # a plain date, not a timestamp
    assert find_problems(read) == []


def test_read_workbook_reports_a_bad_date(sheets, tmp_path, monkeypatch):
    sheets["Source Data"]["Date"] = sheets["Source Data"]["Date"].astype(object)
    sheets["Source Data"].loc[1, "Date"] = "13/13/2026"
    workbook_path, meals_path = write_workbook(sheets, tmp_path)
    monkeypatch.setattr(validate_workbook, "WORKBOOK_PATH", workbook_path)
    monkeypatch.setattr(validate_workbook, "MEALS_PATH", meals_path)

    assert find_problems(read_workbook()) == ["Source Data row 3: Date is blank or not a date"]
