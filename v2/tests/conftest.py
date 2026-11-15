"""
Shared test helpers. pytest loads this file by itself, and any test can ask
for a fixture below by naming it as an argument, e.g. def test_x(sheets).
"""

import os
import shutil
from datetime import date

import pandas as pd
import psycopg2
import pytest

import validate_workbook
from validate_workbook import DAY_SHEETS, LIST_SHEETS

DAY = date(2026, 1, 1)
JANUARY = date(2026, 1, 1)      # the Managers sheet's Month: the first day of the month


@pytest.fixture
def sheets():
    """A tiny workbook with no mistakes: 3 branches, 2 managers, and on one day
    Arabi Sop due twice (2 tasks) with 1 quality issue.

    Every test gets a fresh copy, so a test can break one thing without
    affecting the others. Row 0 in a table is Excel row 2.
    """
    return {
        "Source Data": pd.DataFrame({
            "Date":                  [DAY,         DAY],
            "Meal":                  ["Arabi Sop", "Arabi Sop"],
            "Due time":              ["12-4 pm",   "4-8 pm"],
            "Done Tasks":            [3,           2],
            "Missed Tasks":          [0,           1],
            "Branches Missed Tasks": [None,        "Olaya"],
        }),
        "Reviewing Reports": pd.DataFrame({
            "Date":        [DAY],
            "Code":        ["B1"],
            "Branch":      ["Malaz"],
            "Meal":        ["Arabi Sop"],
            "Due time":    ["4-8 pm"],
            "Description": ["Wrong sauce quantity"],
            "Manager":     ["Manager A"],
        }),
        "branches and codes": pd.DataFrame({
            "Code":   ["B1",    "B2",    "B3"],
            "Branch": ["Malaz", "Olaya", "Rawdah"],
        }),
        "Managers": pd.DataFrame({
            "Month":   [JANUARY,     JANUARY,     JANUARY],
            "Branch":  ["Malaz",     "Olaya",     "Rawdah"],
            "Manager": ["Manager A", "Manager A", "Manager B"],
        }),
        "Fixed Choices": pd.DataFrame({"Issues": ["Wrong sauce quantity", "Bread not heated"]}),
        "meals.xlsx": pd.DataFrame({"Meal": ["Arabi Sop", "French Fries"]}),
    }


def write_files(sheets, folder, monkeypatch=None):
    """Save the tiny workbook the way the files look since step 8: the lists
    workbook (branches and codes, Managers, Fixed Choices), meals.xlsx, and one
    daily file, day.xlsx, in an intake folder. Returns the intake folder.

    With monkeypatch, the scripts read these files for the rest of the test."""
    workbook_path = os.path.join(folder, "workbook.xlsx")
    meals_path = os.path.join(folder, "meals.xlsx")
    intake_dir = os.path.join(folder, "intake")
    os.makedirs(intake_dir, exist_ok=True)
    with pd.ExcelWriter(workbook_path) as writer:
        for name in LIST_SHEETS:
            sheets[name].to_excel(writer, sheet_name=name, index=False)
    write_day_file(sheets, os.path.join(intake_dir, "day.xlsx"))
    sheets["meals.xlsx"].to_excel(meals_path, index=False)

    if monkeypatch:
        monkeypatch.setattr(validate_workbook, "WORKBOOK_PATH", workbook_path)
        monkeypatch.setattr(validate_workbook, "MEALS_PATH", meals_path)
        monkeypatch.setattr(validate_workbook, "INTAKE_DIR", intake_dir)
    return intake_dir


def write_day_file(sheets, path):
    """A daily file like the entry person's: Source Data and Reviewing Reports."""
    with pd.ExcelWriter(path) as writer:
        for name in DAY_SHEETS:
            sheets[name].to_excel(writer, sheet_name=name, index=False)


@pytest.fixture
def sample_intake(tmp_path, monkeypatch):
    """A copy of the sample's intake folder, so a test can load (and delete)
    files without touching the real sample. The scripts read the copy."""
    copy = tmp_path / "intake"
    shutil.copytree(validate_workbook.INTAKE_DIR, copy, ignore=shutil.ignore_patterns("._*"))
    monkeypatch.setattr(validate_workbook, "INTAKE_DIR", str(copy))
    return copy


@pytest.fixture
def database():
    """An empty v2 schema in a test database, for the tests that need Postgres.

    Set TEST_PGDATABASE to the name of a database you can wipe, e.g.
        createdb shawarma_classic_test
        TEST_PGDATABASE=shawarma_classic_test pytest v2
    Without it, these tests are skipped. The name must contain "test",
    because the schema is dropped and created again before every test.
    """
    name = os.getenv("TEST_PGDATABASE")
    if not name:
        pytest.skip("TEST_PGDATABASE isn't set")
    if "test" not in name:
        pytest.fail(f"TEST_PGDATABASE={name!r}: the name must contain 'test', because the tests wipe it")

    schema_sql = open(os.path.join(os.path.dirname(__file__), "..", "sql", "001_schema.sql")).read()
    conn = psycopg2.connect(dbname=name)
    conn.autocommit = True          # the schema file has its own BEGIN and COMMIT
    with conn.cursor() as cur:
        cur.execute("DROP SCHEMA IF EXISTS ops CASCADE")
        cur.execute(schema_sql)
    conn.close()
    return name


def count_rows(database, table):
    conn = psycopg2.connect(dbname=database)
    try:
        with conn.cursor() as cur:
            cur.execute(f"SELECT count(*) FROM ops.{table}")
            return cur.fetchone()[0]
    finally:
        conn.close()
