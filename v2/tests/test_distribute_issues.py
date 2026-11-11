"""
Tests for distribute_issues.py. The main test runs on the sample workbook,
because it's the only one with real in-cell photos; its last day,
2026-10-26, has 6 issues across 5 branches.
"""

import os
from datetime import date

import openpyxl
import pytest

import distribute_issues
import validate_workbook
from conftest import DAY, write_workbook
from distribute_issues import read_photos
from settings import WORKBOOK_PATH
from validate_workbook import excel_row, read_workbook

SAMPLE_DAY = date(2026, 10, 26)


def run_daily(monkeypatch, output_dir, day):
    """Run the daily script for `day`, writing into `output_dir`."""
    monkeypatch.setattr(distribute_issues, "OUTPUT_DIR", str(output_dir))
    monkeypatch.setattr(distribute_issues, "REPORT_DATE", day)
    distribute_issues.main()


def written_files(output_dir):
    """Every file written, as "<Manager>/<Branch>.xlsx"."""
    folder = os.path.join(output_dir, "managers")
    return sorted(f"{manager}/{file}" for manager in os.listdir(folder)
                  for file in os.listdir(os.path.join(folder, manager)))


def test_one_file_per_branch_in_its_managers_folder(tmp_path, monkeypatch):
    run_daily(monkeypatch, tmp_path, SAMPLE_DAY)
    assert written_files(tmp_path) == [
        "Al Ahsa Manager/Al Hofuf - الهفوف.xlsx",
        "Central Riyadh Manager/Al Malaz - الملز.xlsx",
        "East Riyadh Manager/Al Rimal - الرمال.xlsx",
        "North Riyadh Manager/Al Narjis - النرجس.xlsx",
        "Outskirts Manager/Al Diriyah - الدرعية.xlsx",
    ]


def test_each_file_has_its_issues_and_their_photos(tmp_path, monkeypatch):
    run_daily(monkeypatch, tmp_path, SAMPLE_DAY)
    issues = read_workbook()["Reviewing Reports"]
    photos = read_photos(WORKBOOK_PATH, "Reviewing Reports")

    for path in written_files(tmp_path):
        branch = path.split("/")[1].removesuffix(".xlsx")
        expected = issues[(issues["Date"] == SAMPLE_DAY) & (issues["Branch"] == branch)]
        sheet = openpyxl.load_workbook(os.path.join(tmp_path, "managers", path)).active

        # The rows: one per issue, in workbook order (row 1 is the header)
        assert sheet.max_row == len(expected) + 1
        descriptions = [sheet.cell(row=r, column=list(expected.columns).index("Description") + 1).value
                        for r in range(2, sheet.max_row + 1)]
        assert descriptions == list(expected["Description"])

        # The photos: one per issue, on its own row, and the same picture as in the workbook
        assert len(sheet._images) == len(expected)
        for image in sheet._images:
            position = image.anchor._from.row - 1                # anchors count from 0, minus the header
            workbook_row = excel_row(expected.index[position])
            assert image._data() == photos[workbook_row]


def test_a_mistake_in_that_days_issues_writes_nothing(sheets, tmp_path, monkeypatch):
    sheets["Reviewing Reports"].loc[0, "Code"] = "B3"
    workbook_path, meals_path = write_workbook(sheets, tmp_path)
    monkeypatch.setattr(validate_workbook, "WORKBOOK_PATH", workbook_path)
    monkeypatch.setattr(validate_workbook, "MEALS_PATH", meals_path)

    with pytest.raises(SystemExit):                              # the script stops with exit code 1
        run_daily(monkeypatch, tmp_path / "out", DAY)
    assert not (tmp_path / "out").exists()


def test_a_day_with_no_issues_writes_nothing(tmp_path, monkeypatch):
    run_daily(monkeypatch, tmp_path, date(2026, 11, 1))
    assert not (tmp_path / "managers").exists()


def test_a_workbook_without_photos(sheets, tmp_path):
    workbook_path, _ = write_workbook(sheets, tmp_path)
    assert read_photos(workbook_path, "Reviewing Reports") == {}
