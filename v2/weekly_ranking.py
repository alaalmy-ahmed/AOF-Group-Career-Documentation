"""
Weekly: write the branch and manager ranking for one week to Excel. Weeks run
Wednesday to Tuesday, and this writes the one ending on the last Tuesday on or
before REPORT_DATE.

The ranking itself is computed in the database by the dbt models
(dbt/models/branch_weekly_ranking.sql and manager_weekly_ranking.sql, method
in docs/metrics.md). So the order is: load_workbook.py, build_models.py, then
this script.

Writes:
    output/Branches Weekly Performance Summary.xlsx
    output/Managers Weekly Performance Summary.xlsx

Usage:
    python v2/weekly_ranking.py
    REPORT_DATE=2026-10-20 python v2/weekly_ranking.py     # a full week of the sample data

Settings: PGDATABASE, OUTPUT_DIR, REPORT_DATE (see settings.py), and
PGHOST, PGPORT, PGUSER, PGPASSWORD, which psycopg2 reads by itself.
"""

import os
import sys
from datetime import timedelta

import pandas as pd
import psycopg2

from settings import DATABASE, OUTPUT_DIR, REPORT_DATE

# The dbt models are in the "reporting" schema (dbt/profiles.yml). The column
# names are the ones the Excel files have always had.
BRANCHES_SQL = """
    SELECT manager AS "Manager",
           branch AS "Branch",
           done_rate::float AS "Done Rate",
           number_of_issues::int AS "Number of Issues",
           branches_rank::int AS "Branches Rank",
           completion_grade AS "Completion Grade"
      FROM reporting.branch_weekly_ranking
     WHERE week_end = %(week_end)s
     ORDER BY branches_rank, branch
"""

MANAGERS_SQL = """
    SELECT manager AS "Manager",
           done_rate::float AS "Done Rate",
           issues_per_branch::float AS "Issues per Branch",
           number_of_issues::int AS "Number of Issues",
           managers_rank::int AS "Managers Rank"
      FROM reporting.manager_weekly_ranking
     WHERE week_end = %(week_end)s
     ORDER BY managers_rank, manager
"""


def week_end_for(day):
    """The last Tuesday on or before `day` (weeks run Wednesday to Tuesday).
    weekday() counts Monday as 0, so Tuesday is 1."""
    return day - timedelta(days=(day.weekday() - 1) % 7)


def read_week(week_end):
    """The branch and manager ranking of the week ending on `week_end`."""
    conn = psycopg2.connect(dbname=DATABASE)
    try:
        with conn, conn.cursor() as cur:
            tables = []
            for sql in (BRANCHES_SQL, MANAGERS_SQL):
                cur.execute(sql, {"week_end": week_end})
                columns = [column.name for column in cur.description]
                tables.append(pd.DataFrame(cur.fetchall(), columns=columns))
    finally:
        conn.close()
    return tables


def main():
    week_end = week_end_for(REPORT_DATE)
    week_start = week_end - timedelta(days=6)
    branches, managers = read_week(week_end)
    if branches.empty:
        print(f"No ranking for the week {week_start} to {week_end}. "
              f"Have load_workbook.py and build_models.py run?")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    branches.to_excel(os.path.join(OUTPUT_DIR, "Branches Weekly Performance Summary.xlsx"), index=False)
    managers.to_excel(os.path.join(OUTPUT_DIR, "Managers Weekly Performance Summary.xlsx"), index=False)

    print(f"Week {week_start} to {week_end}: {len(branches)} branches\n")
    print(managers.to_string(index=False))
    print(f"\nWritten to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
