"""
Tests for the intake folder (step 8): reading the daily files, the checks
between files, and deleting files older than KEEP_DAYS. No database needed.
"""

import os
import shutil
from datetime import date

import pandas as pd

import load_workbook
from conftest import DAY, write_day_file, write_files
from validate_workbook import find_intake_problems, read_intake


def test_any_file_name_works(sheets, tmp_path, monkeypatch):
    intake = write_files(sheets, tmp_path, monkeypatch)
    os.rename(os.path.join(intake, "day.xlsx"), os.path.join(intake, "تقرير يوم 1 يناير.xlsx"))
    [(name, _, _)] = read_intake()
    assert name == "تقرير يوم 1 يناير.xlsx"
    assert find_intake_problems(read_intake()) == []


def test_excel_lock_files_and_hidden_files_are_skipped(sheets, tmp_path, monkeypatch):
    intake = write_files(sheets, tmp_path, monkeypatch)
    for junk in ["~$day.xlsx", "._day.xlsx", "notes.txt"]:      # not Excel files the pipeline should open
        open(os.path.join(intake, junk), "w").write("not a workbook")
    assert [name for name, _, _ in read_intake()] == ["day.xlsx"]


def test_an_empty_folder_is_a_problem(sheets, tmp_path, monkeypatch):
    intake = write_files(sheets, tmp_path, monkeypatch)
    os.remove(os.path.join(intake, "day.xlsx"))
    assert find_intake_problems(read_intake()) == [f"No daily files in the intake folder ({intake})"]


def test_problems_are_named_with_their_file(sheets, tmp_path, monkeypatch):
    sheets["Reviewing Reports"].loc[0, "Description"] = "Bread cold"
    write_files(sheets, tmp_path, monkeypatch)
    assert find_intake_problems(read_intake()) == [
        "day.xlsx: Reviewing Reports row 2: description 'Bread cold' isn't in Fixed Choices"]


def test_a_missing_sheet_is_named(sheets, tmp_path, monkeypatch):
    intake = write_files(sheets, tmp_path, monkeypatch)
    with pd.ExcelWriter(os.path.join(intake, "day.xlsx")) as writer:       # only Source Data
        sheets["Source Data"].to_excel(writer, sheet_name="Source Data", index=False)
    assert find_intake_problems(read_intake()) == ["day.xlsx: no sheet named 'Reviewing Reports'"]


def test_a_file_without_tasks_is_a_problem(sheets, tmp_path, monkeypatch):
    sheets["Source Data"] = sheets["Source Data"].iloc[0:0]                 # the columns, no rows
    sheets["Reviewing Reports"] = sheets["Reviewing Reports"].iloc[0:0]
    write_files(sheets, tmp_path, monkeypatch)
    assert find_intake_problems(read_intake()) == ["day.xlsx: no tasks in Source Data"]


def test_the_same_day_in_two_files(sheets, tmp_path, monkeypatch):
    intake = write_files(sheets, tmp_path, monkeypatch)
    shutil.copy(os.path.join(intake, "day.xlsx"), os.path.join(intake, "day (resent).xlsx"))
    assert find_intake_problems(read_intake()) == ["2026-01-01 is in more than one file: day (resent).xlsx, day.xlsx"]


def test_a_problem_in_the_lists_is_listed_once(sheets, tmp_path, monkeypatch):
    sheets["Managers"] = sheets["Managers"].drop(index=2)                  # Rawdah has no manager
    intake = write_files(sheets, tmp_path, monkeypatch)
    next_day = {name: sheet.assign(Date=date(2026, 1, 2)) for name, sheet in sheets.items()
                if name in ("Source Data", "Reviewing Reports")}
    write_day_file(next_day, os.path.join(intake, "day 2.xlsx"))           # two daily files, same lists
    assert find_intake_problems(read_intake()) == ["branches and codes row 4: 'Rawdah' has no manager for 2026-01 in 'Managers'"]


# --------------------------------------------------------------------------------------------------------
# Keeping the last KEEP_DAYS days

def ten_daily_files(sheets, tmp_path, monkeypatch):
    """Files for Jan 1 to Jan 12 (one day each). Returns read_intake()."""
    intake = write_files(sheets, tmp_path, monkeypatch)
    os.remove(os.path.join(intake, "day.xlsx"))
    for day in range(1, 13):
        one_day = {name: sheets[name].assign(Date=date(2026, 1, day)) for name in ("Source Data", "Reviewing Reports")}
        write_day_file(one_day, os.path.join(intake, f"jan {day:02d}.xlsx"))
    return read_intake()


def test_old_files_are_deleted(sheets, tmp_path, monkeypatch):
    files = ten_daily_files(sheets, tmp_path, monkeypatch)
    monkeypatch.setattr(load_workbook, "KEEP_DAYS", 10)
    monkeypatch.setattr(load_workbook, "REPORT_DATE", date(2026, 1, 12))
    load_workbook.delete_old_files(files)
    # The 10 days Jan 3 to Jan 12 stay; Jan 1 and 2 are more than 10 days before Jan 12
    assert sorted(os.listdir(tmp_path / "intake")) == [f"jan {day:02d}.xlsx" for day in range(3, 13)]


def test_nothing_is_deleted_without_keep_days(sheets, tmp_path, monkeypatch):
    files = ten_daily_files(sheets, tmp_path, monkeypatch)
    monkeypatch.setattr(load_workbook, "KEEP_DAYS", None)
    monkeypatch.setattr(load_workbook, "REPORT_DATE", date(2027, 1, 1))
    load_workbook.delete_old_files(files)
    assert len(os.listdir(tmp_path / "intake")) == 12


def test_a_file_is_kept_while_any_of_its_days_is_recent(sheets, tmp_path, monkeypatch):
    intake = write_files(sheets, tmp_path, monkeypatch)
    late_issue = sheets["Reviewing Reports"].assign(Date=date(2026, 1, 10))     # a Jan 1 file with a Jan 10 issue
    write_day_file({"Source Data": sheets["Source Data"], "Reviewing Reports": late_issue},
                   os.path.join(intake, "day.xlsx"))
    monkeypatch.setattr(load_workbook, "KEEP_DAYS", 10)
    monkeypatch.setattr(load_workbook, "REPORT_DATE", date(2026, 1, 15))
    load_workbook.delete_old_files(read_intake())
    assert os.listdir(intake) == ["day.xlsx"]
    assert DAY == date(2026, 1, 1)
