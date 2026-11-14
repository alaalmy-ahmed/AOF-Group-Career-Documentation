"""
Every setting the v2 scripts use, in one place. Each one can be changed
with an environment variable of the same name; the defaults run on the
sample data.

The database connection (PGHOST, PGPORT, PGUSER, PGPASSWORD) isn't here:
psycopg2 reads those environment variables by itself.
"""

import os
from datetime import date, timedelta

HERE = os.path.dirname(os.path.abspath(__file__))

# The operations workbook and the meal list
WORKBOOK_PATH = os.getenv("WORKBOOK_PATH", os.path.join(HERE, "sample_data", "sample_workbook.xlsx"))
MEALS_PATH = os.getenv("MEALS_PATH", os.path.join(HERE, "sample_data", "meals.xlsx"))

# The database the load writes to and the ranking reads from
DATABASE = os.getenv("PGDATABASE", "shawarma_classic")

# Where the daily files and the weekly summaries are written
OUTPUT_DIR = os.getenv("OUTPUT_DIR", os.path.join(HERE, "output"))

# The day being reported: the daily files cover this day, and the weekly
# ranking covers the 7 days ending on it. Default: yesterday, because
# today's data is still coming in. Example: REPORT_DATE=2026-10-26
REPORT_DATE = date.fromisoformat(os.getenv("REPORT_DATE") or str(date.today() - timedelta(days=1)))

# The schedule (step 6) makes up every scheduled run from this day on. Set
# it to the day you switch the schedule on, so it doesn't redo days that
# were handled by hand.
SCHEDULE_START_DATE = date.fromisoformat(os.getenv("SCHEDULE_START_DATE", "2026-11-12"))

# Alert emails from the scheduled runs (step 6). The password is a Gmail
# app password, not the account's normal password. Several addresses in
# ALERT_EMAIL_TO are separated by commas.
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
ALERT_EMAIL_FROM = os.getenv("ALERT_EMAIL_FROM")
ALERT_EMAIL_PASSWORD = os.getenv("ALERT_EMAIL_PASSWORD")
ALERT_EMAIL_TO = os.getenv("ALERT_EMAIL_TO")
