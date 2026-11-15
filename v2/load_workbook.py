"""
Load every daily file in the intake folder, with the lists, into the v2
schema (v2/sql/001_schema.sql).

Everything is checked first (validate_workbook.py). If any file has a
problem, they're all listed and nothing is loaded.

Safe to run more than once: rows already in the database are skipped, using
the unique rules from the schema. Everything runs in one transaction, so a
run that fails part-way changes nothing.

After a successful load, daily files older than KEEP_DAYS days are deleted
(step 8): they're in the database by then.

Usage:
    python v2/load_workbook.py

Settings: INTAKE_DIR, WORKBOOK_PATH, MEALS_PATH, PGDATABASE, KEEP_DAYS,
REPORT_DATE (see settings.py), and PGHOST, PGPORT, PGUSER, PGPASSWORD, which
psycopg2 reads by itself.
"""

import os
import sys
from datetime import timedelta

import pandas as pd
import psycopg2

from settings import DATABASE, KEEP_DAYS, REPORT_DATE
from validate_workbook import days_in, find_intake_problems, print_problems, read_intake


# --------------------------------------------------------------------------------------------------------
# Reshape the workbook

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
    listing every key that isn't there. validate_workbook.py should have
    caught any unknown value already; this is a last safety net."""
    unknown = sorted({key for key in keys if key not in mapping}, key=str)
    if unknown:
        raise ValueError(f"Unknown {what}: {unknown}")
    return [mapping[key] for key in keys]


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
    # 1. Reference lists: managers, meals, branches, and who managed each branch when
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

    # A renamed branch is updated. The WHERE skips rows that haven't changed,
    # so the count shows only real changes.
    added = insert_rows(cur, """
        INSERT INTO ops.branches (code, name) VALUES (%s, %s)
        ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
        WHERE ops.branches.name <> EXCLUDED.name
    """, zip(branches["Code"], branches["Branch"]))
    print(f"branches:        {added} new or changed")

    # Who managed each branch in each month. A corrected name for a month is updated.
    branch_code = dict(zip(branches["Branch"], branches["Code"]))
    added = insert_rows(cur, """
        INSERT INTO ops.branch_managers (month, branch_code, manager_id) VALUES (%s, %s, %s)
        ON CONFLICT (month, branch_code) DO UPDATE SET manager_id = EXCLUDED.manager_id
        WHERE ops.branch_managers.manager_id <> EXCLUDED.manager_id
    """, zip(managers["Month"],
             lookup(branch_code, list(managers["Branch"]), "branches in the Managers sheet"),
             lookup(manager_id, list(managers["Manager"]), "managers")))
    print(f"branch_managers: {added} new or changed")

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
    # The issue's Manager column isn't stored: the checks made sure it matches
    # branch_managers for the issue's month.
    added = insert_rows(cur, """
        INSERT INTO ops.quality_issues (task_id, branch_code, description)
        VALUES (%s, %s, %s)
        ON CONFLICT (task_id, branch_code, description) DO NOTHING
    """, zip(issue_tasks, issues["Code"], issues["Description"]))
    print(f"quality_issues:  {added} new of {len(issues)}")


# --------------------------------------------------------------------------------------------------------
# Keep only the last days in the intake folder

def delete_old_files(files):
    """Delete the daily files whose days are all more than KEEP_DAYS days before
    REPORT_DATE. main() calls this only after the load has been saved, so every
    file deleted is already in the database. With KEEP_DAYS not set, nothing is
    deleted."""
    if KEEP_DAYS is None:
        return
    last_day_to_delete = REPORT_DATE - timedelta(days=KEEP_DAYS)
    old = [(name, path) for name, path, sheets in files if max(days_in(sheets)) <= last_day_to_delete]
    for _, path in old:
        os.remove(path)
    names = ", ".join(name for name, _ in old) or "none"
    print(f"Deleted {len(old)} daily file(s) with only days up to {last_day_to_delete} "
          f"(older than {KEEP_DAYS} days, already loaded): {names}")


def main():
    files = read_intake()
    problems = find_intake_problems(files)
    if problems:
        print_problems(problems)
        print("Nothing was loaded.")
        sys.exit(1)

    # All the daily files together, as if they were one workbook
    tasks = reshape_tasks(pd.concat([sheets["Source Data"] for _, _, sheets in files], ignore_index=True))
    issues = pd.concat([sheets["Reviewing Reports"] for _, _, sheets in files], ignore_index=True)
    lists = files[0][2]                 # the same lists come with every file
    all_days = set().union(*(days_in(sheets) for _, _, sheets in files))
    print(f"{len(files)} daily file(s), {min(all_days)} to {max(all_days)}")

    conn = psycopg2.connect(dbname=DATABASE)
    try:
        # Commits if everything succeeds, rolls back if anything fails
        with conn, conn.cursor() as cur:
            load(cur, tasks, issues, lists["branches and codes"], lists["Managers"], lists["meals.xlsx"])
        print("Done.")
    finally:
        conn.close()

    delete_old_files(files)


if __name__ == "__main__":
    main()
