"""
Load the operations workbook into the v2 schema (v2/sql/001_schema.sql).

Safe to run more than once: rows already in the database are skipped, using
the unique rules from the schema. Everything runs in one transaction, so a
run that fails part-way changes nothing.

Usage:
    python v2/load_workbook.py

Settings (environment variables):
    WORKBOOK_PATH  default: v2/sample_data/sample_workbook.xlsx
    MEALS_PATH     default: v2/sample_data/meals.xlsx
    PGDATABASE     default: shawarma_classic
    PGHOST, PGPORT, PGUSER, PGPASSWORD   read by psycopg2 directly
"""

import os

import pandas as pd
import psycopg2

HERE = os.path.dirname(os.path.abspath(__file__))
WORKBOOK_PATH = os.getenv("WORKBOOK_PATH", os.path.join(HERE, "sample_data", "sample_workbook.xlsx"))
MEALS_PATH = os.getenv("MEALS_PATH", os.path.join(HERE, "sample_data", "meals.xlsx"))
DATABASE = os.getenv("PGDATABASE", "shawarma_classic")


# --------------------------------------------------------------------------------------------------------
# Read and reshape the workbook

def read_workbook():
    tasks = pd.read_excel(WORKBOOK_PATH, sheet_name="Source Data")
    issues = pd.read_excel(WORKBOOK_PATH, sheet_name="Reviewing Reports")
    branches = pd.read_excel(WORKBOOK_PATH, sheet_name="branches and codes")
    managers = pd.read_excel(WORKBOOK_PATH, sheet_name="Managers")
    meals = pd.read_excel(MEALS_PATH)

    tasks["Date"] = pd.to_datetime(tasks["Date"]).dt.date
    issues["Date"] = pd.to_datetime(issues["Date"]).dt.date
    return tasks, issues, branches, managers, meals


def reshape_tasks(tasks):
    """One row per (date, meal, due time). Teams are added together, and their
    missed-branch cells are joined so no branch is lost."""
    tasks = tasks.groupby(["Date", "Meal", "Due time"], as_index=False).agg(
        branches_submitted=("Done Tasks", "sum"),
        branches_missed=("Branches Missed Tasks", lambda cells: "\n".join(cells.dropna())),
    )
    return tasks.rename(columns={"Date": "date", "Meal": "meal", "Due time": "due_time"})


def split_misses(tasks):
    """One (date, meal, due time, branch name) row per branch that missed a task.
    This is v1's explode step."""
    rows = []
    for task in tasks.itertuples(index=False):
        for branch in task.branches_missed.split("\n"):
            if branch.strip():
                rows.append((task.date, task.meal, task.due_time, branch.strip()))
    return rows


def lookup(mapping, keys, what):
    """Translate each key through mapping, or stop with a clear message
    listing every key that isn't there."""
    unknown = sorted({key for key in keys if key not in mapping}, key=str)
    if unknown:
        raise ValueError(f"Unknown {what}: {unknown}")
    return [mapping[key] for key in keys]


def check_no_duplicate_issues(issues):
    """The database would quietly skip a repeated issue, so a typo that logs
    one twice in the workbook is caught here instead."""
    key = ["Date", "Code", "Meal", "Due time", "Description"]
    repeated = issues[issues.duplicated(key, keep=False)]
    if not repeated.empty:
        raise ValueError(f"Issues logged twice in the workbook:\n{repeated[key]}")


# --------------------------------------------------------------------------------------------------------
# Write to the database

def insert_rows(cur, sql, rows):
    """Run one INSERT per row and return how many rows were actually added.
    With ON CONFLICT DO NOTHING, a row that's already there adds 0."""
    added = 0
    for row in rows:
        cur.execute(sql, row)
        added += cur.rowcount
    return added


def load(cur, tasks, issues, branches, managers, meals):
    # 1. Reference lists: managers, meals, branches
    added = insert_rows(cur, "INSERT INTO ops.managers (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                        [(name,) for name in managers["Manager"].unique()])
    print(f"managers:        {added} new")
    cur.execute("SELECT name, manager_id FROM ops.managers")
    manager_id = dict(cur.fetchall())                    # {"North Riyadh Manager": 1, ...}

    added = insert_rows(cur, "INSERT INTO ops.meals (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                        [(name,) for name in meals["Meal"]])
    print(f"meals:           {added} new")
    cur.execute("SELECT name, meal_id FROM ops.meals")
    meal_id = dict(cur.fetchall())                       # {"Arabi Sop": 2, ...}

    # A branch's manager changes with the monthly rotation, so existing
    # branches are updated rather than skipped.
    manager_of = dict(zip(managers["Branch"], managers["Manager"]))
    branch_managers = lookup(manager_of, list(branches["Branch"]), "branches with no manager in the Managers sheet")
    added = insert_rows(cur, """
        INSERT INTO ops.branches (code, name, manager_id) VALUES (%s, %s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name, manager_id = EXCLUDED.manager_id
    """, zip(branches["Code"], branches["Branch"], lookup(manager_id, branch_managers, "managers")))
    print(f"branches:        {added} inserted or updated")

    # 2. Scheduled tasks
    task_meals = lookup(meal_id, list(tasks["meal"]), "meals in Source Data (not in the meal list)")
    added = insert_rows(cur, """
        INSERT INTO ops.scheduled_tasks (task_date, meal_id, due_time, branches_submitted)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (task_date, meal_id, due_time) DO NOTHING
    """, [(d, m, due, int(n)) for d, m, due, n
          in zip(tasks["date"], task_meals, tasks["due_time"], tasks["branches_submitted"])])
    print(f"scheduled_tasks: {added} new of {len(tasks)}")
    cur.execute("SELECT task_date, meal_id, due_time, task_id FROM ops.scheduled_tasks")
    task_id = {(d, m, due): t for d, m, due, t in cur.fetchall()}   # {(date, 2, "4-8 pm"): 17, ...}

    # 3. Task misses
    branch_code = dict(zip(branches["Branch"], branches["Code"]))
    misses = split_misses(tasks)
    miss_tasks = lookup(task_id, [(d, meal_id[m], due) for d, m, due, _ in misses], "tasks")
    miss_codes = lookup(branch_code, [b for *_, b in misses], "branches in Branches Missed Tasks")
    added = insert_rows(cur, """
        INSERT INTO ops.task_misses (task_id, branch_code) VALUES (%s, %s)
        ON CONFLICT (task_id, branch_code) DO NOTHING
    """, zip(miss_tasks, miss_codes))
    print(f"task_misses:     {added} new of {len(misses)}")

    # 4. Quality issues: each one must match a scheduled task (date, meal, due time)
    issue_meals = lookup(meal_id, list(issues["Meal"]), "meals in Reviewing Reports (not in the meal list)")
    issue_tasks = lookup(task_id, list(zip(issues["Date"], issue_meals, issues["Due time"])),
                         "tasks for these issues (date, meal_id, due time)")
    issue_managers = lookup(manager_id, list(issues["Manager"]), "managers in Reviewing Reports")
    added = insert_rows(cur, """
        INSERT INTO ops.quality_issues (task_id, branch_code, description, manager_id)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (task_id, branch_code, description) DO NOTHING
    """, zip(issue_tasks, issues["Code"], issues["Description"], issue_managers))
    print(f"quality_issues:  {added} new of {len(issues)}")


def main():
    tasks, issues, branches, managers, meals = read_workbook()
    tasks = reshape_tasks(tasks)
    check_no_duplicate_issues(issues)

    conn = psycopg2.connect(dbname=DATABASE)
    try:
        # Commits if everything succeeds, rolls back if anything fails
        with conn, conn.cursor() as cur:
            load(cur, tasks, issues, branches, managers, meals)
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
