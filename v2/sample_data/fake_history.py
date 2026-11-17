"""
A fake history for the monthly, quarterly and yearly reports (step 10):
July 1 to October 12, 2026, the months before the sample's 14 daily files
(Oct 13-26). Without it, the sample reports would show one month, and no
branch would ever change manager.

It's made like the sample (generate_sample_data.py), with three differences:
  - Branches move between managers every month: in each month before
    October, every manager hands their first branch to the next manager.
    The Managers rows for July, August and September record it.
  - Things get better month by month, so the trends have a direction.
  - No photos and no files: the tasks and issues are loaded straight into the
    database with load_workbook.py's own load(), as if they'd been read from
    daily files. The 14 sample daily files stay exactly as they are.

Everything here is made up. The tables pass every check in
validate_workbook.py (tested in test_period_reports.py).

Usage, into a database you can fill with fake data (its name must contain
"sample" or "test"), before loading the sample's daily files:
    PGDATABASE=shawarma_classic_sample python v2/sample_data/fake_history.py
    PGDATABASE=shawarma_classic_sample python v2/load_workbook.py
"""

import os
import random
import sys
from datetime import date, timedelta

import pandas as pd
import psycopg2

# The v2 folder, for its modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from generate_sample_data import ISSUES, MEALS  # noqa: E402  (next to this file)
from load_workbook import load, reshape_tasks  # noqa: E402
from validate_workbook import read_lists  # noqa: E402

SEED = 11
FIRST_DAY = date(2026, 7, 1)
LAST_DAY = date(2026, 10, 12)               # the day before the sample's first daily file
MONTHS = [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1)]   # October's rows are the sample's

# How bad each month is, compared with October (1.0): misses and issues fall month by month
BADNESS = {7: 1.8, 8: 1.5, 9: 1.2, 10: 1.0}


def rotated_managers(october):
    """The Managers rows for July, August and September. `october` is the
    sample's Managers sheet. Going back one month, every manager hands their
    first branch to the next manager in the list (the last one to the first),
    so each month 10 branches have a different manager than the month after."""
    branches_of = {manager: list(rows["Branch"]) for manager, rows in october.groupby("Manager", sort=False)}
    managers = list(branches_of)
    rows = []
    for month in sorted(MONTHS, reverse=True):          # September, then August, then July
        firsts = [branches_of[manager][0] for manager in managers]
        branches_of = {manager: branches_of[manager][1:] + [firsts[i - 1]]
                       for i, manager in enumerate(managers)}
        rows += [{"Month": month, "Branch": branch, "Manager": manager}
                 for manager, branches in branches_of.items() for branch in branches]
    return pd.DataFrame(rows)


def make_history(lists):
    """Source Data and Reviewing Reports for July 1 - October 12, shaped like
    the daily files' sheets, and the Managers rows for July-September."""
    rng = random.Random(SEED)
    branches = lists["branches and codes"]
    all_branches = list(branches["Branch"])
    code_of = dict(zip(branches["Branch"], branches["Code"]))
    managers = rotated_managers(lists["Managers"])
    manager_of = {(row.Month, row.Branch): row.Manager for row in
                  pd.concat([managers, lists["Managers"]]).itertuples()}

    weak = set(rng.sample(all_branches, 6))             # a few branches struggle more
    weights = [5 if branch in weak else 1 for branch in all_branches]

    tasks, issues = [], []
    day = FIRST_DAY
    while day <= LAST_DAY:
        badness = BADNESS[day.month]
        for meal, due in MEALS:
            n_missed = round(rng.choice([0, 0, 1, 1, 2, 3, 4]) * badness)
            missed = sorted(set(rng.choices(all_branches, weights=weights, k=n_missed)))
            done = len(all_branches) - len(missed)
            tasks.append({
                "Date": day, "Meal": meal, "Team": "S.C Branches",
                "Done Tasks": done, "Missed Tasks": len(missed),
                "Branches Missed Tasks": "\n".join(missed) if missed else None,
                "Due time": due, "Team Done Rate": round(done / len(all_branches), 3),
            })
        for _ in range(round(rng.randint(4, 9) * badness)):
            branch = rng.choices(all_branches, weights=weights, k=1)[0]
            meal, due = rng.choice(MEALS)
            # Two issues with the same description on the same task count once, like the load does
            issues.append({
                "Date": day, "Code": code_of[branch], "Branch": branch, "Meal": meal, "Due time": due,
                "Description": rng.choice(ISSUES), "Manager": manager_of[(day.replace(day=1), branch)],
            })
        day += timedelta(days=1)

    issues = pd.DataFrame(issues).drop_duplicates(["Date", "Code", "Meal", "Due time", "Description"])
    return pd.DataFrame(tasks), issues.reset_index(drop=True), managers


def load_history(database):
    """Load the fake history into `database`, with load_workbook.py's load()."""
    lists = read_lists()
    tasks, issues, managers = make_history(lists)
    all_managers = pd.concat([managers, lists["Managers"]], ignore_index=True)
    conn = psycopg2.connect(dbname=database)
    try:
        with conn, conn.cursor() as cur:
            load(cur, reshape_tasks(tasks), issues, lists["branches and codes"], all_managers, lists["meals.xlsx"])
    finally:
        conn.close()
    return tasks, issues


def main():
    database = os.getenv("PGDATABASE", "")
    if "sample" not in database and "test" not in database:
        print(f"PGDATABASE={database!r}: the name must contain 'sample' or 'test', "
              f"so fake data never goes into a real database.")
        sys.exit(1)
    tasks, issues = load_history(database)
    print(f"Fake history loaded into {database}: {FIRST_DAY} to {LAST_DAY}, "
          f"{len(tasks)} tasks, {len(issues)} issues")


if __name__ == "__main__":
    main()
