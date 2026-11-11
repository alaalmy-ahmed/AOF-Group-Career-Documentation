"""
Weekly: rank every branch and area manager on the 7 days ending on
REPORT_DATE, reading the v2 database. This is v1's notebook 02 (Step 3) as
a script, with the same method (docs/metrics.md). Run it after the weekly
load (load_workbook.py).

Writes:
    output/Branches Weekly Performance Summary.xlsx
    output/Managers Weekly Performance Summary.xlsx

Usage:
    python v2/weekly_ranking.py
    REPORT_DATE=2026-10-26 python v2/weekly_ranking.py     # the sample data's last day

Settings: PGDATABASE, OUTPUT_DIR, REPORT_DATE (see settings.py), and
PGHOST, PGPORT, PGUSER, PGPASSWORD, which psycopg2 reads by itself.
"""

import os
import sys
from datetime import timedelta

import pandas as pd
import psycopg2

from settings import DATABASE, OUTPUT_DIR, REPORT_DATE

# How many tasks (date, meal, due time) were scheduled in the window
TASK_COUNT_SQL = """
    SELECT count(*)
      FROM ops.scheduled_tasks
     WHERE task_date BETWEEN %(first_day)s AND %(last_day)s
"""

# One row per branch: its current manager, how many tasks it missed and how
# many quality issues it got in the window. A branch with none gets 0.
BRANCH_COUNTS_SQL = """
    SELECT b.name AS branch,
           m.name AS manager,
           (SELECT count(*)
              FROM ops.task_misses tm
              JOIN ops.scheduled_tasks t USING (task_id)
             WHERE tm.branch_code = b.code
               AND t.task_date BETWEEN %(first_day)s AND %(last_day)s) AS missed,
           (SELECT count(*)
              FROM ops.quality_issues qi
              JOIN ops.scheduled_tasks t USING (task_id)
             WHERE qi.branch_code = b.code
               AND t.task_date BETWEEN %(first_day)s AND %(last_day)s) AS issues
      FROM ops.branches b
      JOIN ops.managers m USING (manager_id)
"""


def read_counts(first_day, last_day):
    window = {"first_day": first_day, "last_day": last_day}
    conn = psycopg2.connect(dbname=DATABASE)
    try:
        with conn, conn.cursor() as cur:
            cur.execute(TASK_COUNT_SQL, window)
            task_count = cur.fetchone()[0]
            cur.execute(BRANCH_COUNTS_SQL, window)
            branches = pd.DataFrame(cur.fetchall(), columns=["Branch", "Manager", "missed", "Number of Issues"])
    finally:
        conn.close()
    return task_count, branches


def share_of_max(values):
    """Each value divided by the largest, so two measures share a 0-1 scale.
    If every value is 0 they all stay 0 (instead of dividing by zero)."""
    largest = values.max()
    return values / largest if largest > 0 else values * 0


def rank_branches(branches, task_count):
    summary = branches.copy()
    summary["Done Rate"] = 100 - (summary["missed"] / task_count * 100).round(1)

    # Done rate counts most; fewer issues adds a little
    score = 0.90 * share_of_max(summary["Done Rate"]) + 0.10 * (1 - share_of_max(summary["Number of Issues"]))
    summary["Branches Rank"] = score.rank(ascending=False, method="min").astype(int)      # 1 = best, ties share
    summary["Completion Grade"] = pd.cut(score, bins=[0, 0.7, 0.8, 0.9, 0.95, 1.0],
                                         labels=["Terrible", "Bad", "Fair", "Good", "Excellent"])

    columns = ["Manager", "Branch", "Done Rate", "Number of Issues", "Branches Rank", "Completion Grade"]
    return summary[columns].sort_values(["Branches Rank", "Branch"])


def rank_managers(branch_summary):
    summary = branch_summary.groupby("Manager", as_index=False).agg(
        **{"Done Rate": ("Done Rate", "mean"),
           "Issues per Branch": ("Number of Issues", "mean"),
           "Number of Issues": ("Number of Issues", "sum")})
    summary["Done Rate"] = summary["Done Rate"].round(1)
    summary["Issues per Branch"] = summary["Issues per Branch"].round(1)

    # Issues count a little more for managers, who are responsible for fixing them
    score = 0.85 * share_of_max(summary["Done Rate"]) + 0.15 * (1 - share_of_max(summary["Issues per Branch"]))
    summary["Managers Rank"] = score.rank(ascending=False, method="min").astype(int)
    return summary.sort_values(["Managers Rank", "Manager"])


def main():
    last_day = REPORT_DATE
    first_day = last_day - timedelta(days=6)              # 7 days, both ends included
    task_count, branches = read_counts(first_day, last_day)
    if task_count == 0:
        print(f"No tasks in the database from {first_day} to {last_day}. Has the weekly load run?")
        sys.exit(1)

    branch_summary = rank_branches(branches, task_count)
    manager_summary = rank_managers(branch_summary)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    branch_summary.to_excel(os.path.join(OUTPUT_DIR, "Branches Weekly Performance Summary.xlsx"), index=False)
    manager_summary.to_excel(os.path.join(OUTPUT_DIR, "Managers Weekly Performance Summary.xlsx"), index=False)

    print(f"Week {first_day} to {last_day}: {task_count} tasks, {len(branches)} branches\n")
    print(manager_summary.to_string(index=False))
    print(f"\nWritten to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
