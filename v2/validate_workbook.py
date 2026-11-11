"""
Read the operations workbook and check it before loading.

Every problem is listed with its sheet and Excel row, so the workbook can be
fixed in one go. load_workbook.py runs these checks first and loads nothing
if any fail.

The checks run in three stages. A stage runs only if the one before it found
nothing, because the later checks rely on the earlier ones (for example,
adding up Done Tasks needs every cell to be a number):

    1. Columns:  every sheet has the columns the pipeline reads
    2. Basics:   no blank required cells, real dates not in the future,
                 counts are whole numbers >= 0
    3. Rules:    names match the lists, and the numbers add up

Usage (no database needed):
    python v2/validate_workbook.py

Settings (environment variables):
    WORKBOOK_PATH  default: v2/sample_data/sample_workbook.xlsx
    MEALS_PATH     default: v2/sample_data/meals.xlsx
"""

import os
import sys
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
WORKBOOK_PATH = os.getenv("WORKBOOK_PATH", os.path.join(HERE, "sample_data", "sample_workbook.xlsx"))
MEALS_PATH = os.getenv("MEALS_PATH", os.path.join(HERE, "sample_data", "meals.xlsx"))

# Columns the pipeline reads. Other columns (Team, Prepared By, Images, ...) are ignored.
REQUIRED_COLUMNS = {
    "Source Data": ["Date", "Meal", "Due time", "Done Tasks", "Missed Tasks", "Branches Missed Tasks"],
    "Reviewing Reports": ["Date", "Code", "Branch", "Meal", "Due time", "Description", "Manager"],
    "branches and codes": ["Code", "Branch"],
    "Managers": ["Branch", "Manager"],
    "Fixed Choices": ["Issues"],
    "meals.xlsx": ["Meal"],
}

# Columns no row may leave blank. "Branches Missed Tasks" isn't here: blank
# means no branch missed. The two lists (Fixed Choices, meals) aren't here
# either: their blank cells are just skipped.
MUST_BE_FILLED = {
    "Source Data": ["Date", "Meal", "Due time", "Done Tasks", "Missed Tasks"],
    "Reviewing Reports": ["Date", "Code", "Branch", "Meal", "Due time", "Description", "Manager"],
    "branches and codes": ["Code", "Branch"],
    "Managers": ["Branch", "Manager"],
}


# --------------------------------------------------------------------------------------------------------
# Read the workbook

def read_workbook():
    """Return every sheet the pipeline uses, as {sheet name: table}."""
    sheets = {}
    for name in ["Source Data", "Reviewing Reports", "branches and codes", "Managers", "Fixed Choices"]:
        sheets[name] = pd.read_excel(WORKBOOK_PATH, sheet_name=name)
    sheets["meals.xlsx"] = pd.read_excel(MEALS_PATH)

    for name, sheet in sheets.items():
        # Drop rows that are completely empty. Row numbers (the index) are
        # kept, so messages still point at the right Excel row.
        sheet = sheet.dropna(how="all")
        # Remove spaces at the start and end of text, so "Al Olaya " matches "Al Olaya".
        sheets[name] = sheet.map(lambda value: value.strip() if isinstance(value, str) else value)

    # Anything that isn't a date becomes blank, and the blank check reports it.
    for name in ["Source Data", "Reviewing Reports"]:
        sheets[name]["Date"] = pd.to_datetime(sheets[name]["Date"], format="mixed", errors="coerce").dt.date
    return sheets


def excel_row(index):
    """Row 1 in Excel is the header, so table row 0 is Excel row 2."""
    return index + 2


def split_names(cell):
    """The branch names in one "Branches Missed Tasks" cell, one per line."""
    if pd.isna(cell):
        return []
    return [name.strip() for name in cell.split("\n") if name.strip()]


# --------------------------------------------------------------------------------------------------------
# Stage 1: columns

def check_columns(sheets):
    problems = []
    for name, columns in REQUIRED_COLUMNS.items():
        missing = [column for column in columns if column not in sheets[name].columns]
        if missing:
            problems.append(f"{name}: missing column(s) {missing}")
    return problems


# --------------------------------------------------------------------------------------------------------
# Stage 2: basics

def check_blanks(sheets):
    problems = []
    for name, columns in MUST_BE_FILLED.items():
        sheet = sheets[name]
        for column in columns:
            for index in sheet.index[sheet[column].isna()]:
                what = "blank or not a date" if column == "Date" else "blank"
                problems.append(f"{name} row {excel_row(index)}: {column} is {what}")
    return problems


def check_dates(sheets):
    problems = []
    today = date.today()
    for name in ["Source Data", "Reviewing Reports"]:
        for index, day in sheets[name]["Date"].dropna().items():
            if day > today:
                problems.append(f"{name} row {excel_row(index)}: Date {day} is in the future")
    return problems


def check_counts(tasks):
    problems = []
    for column in ["Done Tasks", "Missed Tasks"]:
        for index, value in tasks[column].dropna().items():
            if not (pd.api.types.is_number(value) and value >= 0 and value == int(value)):
                problems.append(f"Source Data row {excel_row(index)}: {column} must be a whole number >= 0, not {value!r}")
    return problems


# --------------------------------------------------------------------------------------------------------
# Stage 3: rules

def check_branch_lists(branches, managers):
    """Each branch appears once in 'branches and codes' and has exactly one manager."""
    problems = []
    for column in ["Code", "Branch"]:
        for index in branches.index[branches.duplicated(column)]:
            problems.append(f"branches and codes row {excel_row(index)}: {column} {branches.at[index, column]!r} is listed twice")

    for index in managers.index[managers.duplicated("Branch")]:
        problems.append(f"Managers row {excel_row(index)}: {managers.at[index, 'Branch']!r} has more than one manager")
    for index, branch in managers["Branch"].items():
        if branch not in set(branches["Branch"]):
            problems.append(f"Managers row {excel_row(index)}: {branch!r} isn't in 'branches and codes'")
    for index, branch in branches["Branch"].items():
        if branch not in set(managers["Branch"]):
            problems.append(f"branches and codes row {excel_row(index)}: {branch!r} has no manager in 'Managers'")
    return problems


def check_tasks(tasks, branches, meals):
    problems = []
    meal_names = set(meals["Meal"].dropna())
    branch_names = set(branches["Branch"])

    for index, task in tasks.iterrows():
        where = f"Source Data row {excel_row(index)}"
        if task["Meal"] not in meal_names:
            problems.append(f"{where}: meal {task['Meal']!r} isn't in meals.xlsx")

        names = split_names(task["Branches Missed Tasks"])
        for name in names:
            if name not in branch_names:
                problems.append(f"{where}: missed branch {name!r} isn't in 'branches and codes'")
        for name in sorted({name for name in names if names.count(name) > 1}):
            problems.append(f"{where}: missed branch {name!r} is listed more than once")
        if len(names) != task["Missed Tasks"]:
            problems.append(f"{where}: Missed Tasks says {task['Missed Tasks']:g}, "
                            f"but {len(names)} branch(es) are listed in Branches Missed Tasks")

    # Every branch does every meal, so for each task (date, meal, due time),
    # branches that submitted + branches that missed = all branches.
    counts = tasks.assign(missed=tasks["Branches Missed Tasks"].map(lambda cell: len(split_names(cell))))
    totals = counts.groupby(["Date", "Meal", "Due time"])[["Done Tasks", "missed"]].sum()
    for (day, meal, due_time), total in totals.iterrows():
        if total["Done Tasks"] + total["missed"] != len(branches):
            problems.append(f"Source Data, {day} {meal} {due_time}: {total['Done Tasks']:g} submitted + "
                            f"{total['missed']:g} missed = {total['Done Tasks'] + total['missed']:g}, "
                            f"but there are {len(branches)} branches")
    return problems


def check_issues(issues, tasks, branches, managers, fixed_choices, meals):
    problems = []
    meal_names = set(meals["Meal"].dropna())
    descriptions = set(fixed_choices["Issues"].dropna())
    branch_of_code = dict(zip(branches["Code"], branches["Branch"]))
    manager_of = dict(zip(managers["Branch"], managers["Manager"]))
    scheduled = set(zip(tasks["Date"], tasks["Meal"], tasks["Due time"]))

    for index, issue in issues.iterrows():
        where = f"Reviewing Reports row {excel_row(index)}"

        if issue["Code"] not in branch_of_code:
            problems.append(f"{where}: code {issue['Code']!r} isn't in 'branches and codes'")
        elif branch_of_code[issue["Code"]] != issue["Branch"]:
            problems.append(f"{where}: code {issue['Code']!r} is {branch_of_code[issue['Code']]!r}, not {issue['Branch']!r}")

        if issue["Meal"] not in meal_names:
            problems.append(f"{where}: meal {issue['Meal']!r} isn't in meals.xlsx")
        elif (issue["Date"], issue["Meal"], issue["Due time"]) not in scheduled:
            problems.append(f"{where}: no task in Source Data for {issue['Date']} {issue['Meal']} {issue['Due time']}")

        if issue["Description"] not in descriptions:
            problems.append(f"{where}: description {issue['Description']!r} isn't in Fixed Choices")

        expected = manager_of.get(issue["Branch"])
        if expected is not None and issue["Manager"] != expected:
            problems.append(f"{where}: manager is {issue['Manager']!r}, but 'Managers' says {expected!r} for this branch")

    # The database would quietly skip a repeated issue, so it's caught here instead.
    key = ["Date", "Code", "Meal", "Due time", "Description"]
    for index in issues.index[issues.duplicated(key, keep=False)]:
        problems.append(f"Reviewing Reports row {excel_row(index)}: the same issue is logged more than once "
                        f"(same date, code, meal, due time and description)")
    return problems


# --------------------------------------------------------------------------------------------------------

def find_problems(sheets):
    """Run the three stages and return every problem found, as a list of messages."""
    problems = check_columns(sheets)
    if problems:
        return problems

    tasks = sheets["Source Data"]
    problems = check_blanks(sheets) + check_dates(sheets) + check_counts(tasks)
    if problems:
        return problems

    issues = sheets["Reviewing Reports"]
    branches = sheets["branches and codes"]
    managers = sheets["Managers"]
    return (check_branch_lists(branches, managers)
            + check_tasks(tasks, branches, sheets["meals.xlsx"])
            + check_issues(issues, tasks, branches, managers, sheets["Fixed Choices"], sheets["meals.xlsx"]))


def print_problems(problems):
    print(f"The workbook has {len(problems)} problem(s):")
    for problem in problems:
        print(f"  - {problem}")


def main():
    problems = find_problems(read_workbook())
    if problems:
        print_problems(problems)
        sys.exit(1)     # A non-zero exit tells a scheduler (e.g. Airflow) that the run failed
    print("No problems found.")


if __name__ == "__main__":
    main()
