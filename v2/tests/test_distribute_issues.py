"""
Tests for distribute_issues.py. The main tests run on the sample's daily
files, because they're the only ones with real in-cell photos; the last day,
2026-10-26, has 6 issues across 5 branches.
"""

import os
from datetime import date

import openpyxl
import pytest

import distribute_issues
from conftest import DAY, write_files
from distribute_issues import read_photos
from settings import INTAKE_DIR
from validate_workbook import excel_row, read_day_file

SAMPLE_DAY = date(2026, 10, 26)
SAMPLE_DAY_FILE = os.path.join(INTAKE_DIR, "2026-10-26.xlsx")


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
    issues = read_day_file(SAMPLE_DAY_FILE)["Reviewing Reports"]
    photos = read_photos(SAMPLE_DAY_FILE, "Reviewing Reports")

    for path in written_files(tmp_path):
        branch = path.split("/")[1].removesuffix(".xlsx")
        expected = issues[(issues["Date"] == SAMPLE_DAY) & (issues["Branch"] == branch)]
        sheet = openpyxl.load_workbook(os.path.join(tmp_path, "managers", path)).active

        # The rows: one per issue, in workbook order (row 1 is the header)
        assert sheet.max_row == len(expected) + 1
        descriptions = [sheet.cell(row=r, column=list(expected.columns).index("Description") + 1).value
                        for r in range(2, sheet.max_row + 1)]
        assert descriptions == list(expected["Description"])

        # The photos: one per issue, on its own row, and the same picture as in the daily file
        assert len(sheet._images) == len(expected)
        for image in sheet._images:
            position = image.anchor._from.row - 1                # anchors count from 0, minus the header
            file_row = excel_row(expected.index[position])
            assert image._data() == photos[file_row]


def test_a_mistake_in_that_days_issues_writes_nothing(sheets, tmp_path, monkeypatch, capsys):
    sheets["Reviewing Reports"].loc[0, "Code"] = "B3"
    write_files(sheets, tmp_path, monkeypatch)

    with pytest.raises(SystemExit):                              # the script stops with exit code 1
        run_daily(monkeypatch, tmp_path / "out", DAY)
    assert not (tmp_path / "out").exists()
    assert "day.xlsx: Reviewing Reports row 2: code 'B3' is 'Rawdah', not 'Malaz'" in capsys.readouterr().out


def test_a_day_without_a_file_stops(tmp_path, monkeypatch, capsys):
    """The sample has no file for Nov 1: the file hasn't been dropped in yet."""
    with pytest.raises(SystemExit):
        run_daily(monkeypatch, tmp_path, date(2026, 11, 1))
    assert not (tmp_path / "managers").exists()
    assert "No file for 2026-11-01 in the intake folder" in capsys.readouterr().out


def test_a_day_with_no_issues_writes_nothing(sheets, tmp_path, monkeypatch, capsys):
    """The day's file is there, with its tasks, but no issues."""
    sheets["Reviewing Reports"] = sheets["Reviewing Reports"].iloc[0:0]
    write_files(sheets, tmp_path, monkeypatch)
    run_daily(monkeypatch, tmp_path / "out", DAY)
    assert not (tmp_path / "out").exists()
    assert "No issues on 2026-01-01. Nothing to write." in capsys.readouterr().out


def test_a_file_without_photos(sheets, tmp_path):
    intake = write_files(sheets, tmp_path)
    assert read_photos(os.path.join(intake, "day.xlsx"), "Reviewing Reports") == {}
