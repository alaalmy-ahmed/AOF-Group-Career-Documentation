"""
The schedule for the v2 pipeline (step 6), as two Airflow DAGs.

A DAG is a list of steps (tasks), the order they run in, and when to run.

    daily_issues     every day at 11:59 pm      distribute_issues.py
    weekly_ranking   Wednesdays at 9:00 am      load_workbook.py, then weekly_ranking.py

Each task runs a script exactly as you would in a terminal, with
REPORT_DATE set to the day the run is for. After each task, an email says
OK (with what the script printed) or FAILED (with the error).

Times are Riyadh time. If Airflow wasn't running at a scheduled time (the
Mac was off), it runs every missed day when it's back, oldest first.
"""

import os
import subprocess
import sys
from datetime import timedelta

import pendulum
from airflow.providers.standard.operators.python import PythonOperator
from airflow.sdk import DAG

# The v2 folder (one level up from this file). Adding it to Python's search
# path lets this file import alerts.py, and tells the tasks where the scripts are.
V2 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, V2)

from alerts import send_email  # noqa: E402
from settings import SCHEDULE_START_DATE  # noqa: E402

RIYADH = pendulum.timezone("Asia/Riyadh")

# Airflow makes up every scheduled run from this day on (see settings.py)
START_DATE = pendulum.datetime(
    SCHEDULE_START_DATE.year, SCHEDULE_START_DATE.month, SCHEDULE_START_DATE.day, tz=RIYADH
)


def run_script(script, days_back, logical_date=None, dag_run=None):
    """
    Run one v2 script for the day this run is for. Airflow fills in
    logical_date (the scheduled time) and dag_run. A run started by hand
    has no logical_date, so the time it was started is used.

    days_back: 0 = the run's own day; 1 = the day before.
    """
    run_time = logical_date or dag_run.run_after
    report_date = run_time.astimezone(RIYADH).date() - timedelta(days=days_back)

    result = subprocess.run(
        [sys.executable, script],
        cwd=V2,
        env={**os.environ, "REPORT_DATE": str(report_date)},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    output = f"Report date: {report_date}\n\n{result.stdout}{result.stderr}"
    print(output)  # shown in the task's log in Airflow

    if result.returncode != 0:
        raise RuntimeError(f"{script} stopped with exit code {result.returncode}.\n\n{output}")
    return output  # Airflow keeps it, and email_ok reads it back


def email_ok(context):
    task = context["ti"]
    output = task.xcom_pull(task_ids=task.task_id)
    send_email(f"OK: {task.dag_id} / {task.task_id}", output)


def email_failed(context):
    task = context["ti"]
    error = context.get("exception")
    send_email(f"FAILED: {task.dag_id} / {task.task_id}", str(error))


# Settings every task in both DAGs gets
TASK_SETTINGS = {
    "on_success_callback": email_ok,
    "on_failure_callback": email_failed,
    "retries": 0,  # a mistake in the workbook won't fix itself by trying again
}


with DAG(
    dag_id="daily_issues",
    schedule="59 23 * * *",  # minute 59, hour 23, every day
    start_date=START_DATE,
    catchup=True,  # make up missed days
    max_active_runs=1,  # one day at a time, oldest first
    default_args=TASK_SETTINGS,
):
    PythonOperator(
        task_id="distribute_issues",
        python_callable=run_script,
        op_kwargs={"script": "distribute_issues.py", "days_back": 0},
    )


with DAG(
    dag_id="weekly_ranking",
    schedule="0 9 * * 3",  # minute 0, hour 9, Wednesdays (0 = Sunday)
    start_date=START_DATE,
    catchup=True,
    max_active_runs=1,
    default_args=TASK_SETTINGS,
):
    # days_back=1: the week ends on Tuesday, so it covers Wednesday to Tuesday
    load = PythonOperator(
        task_id="load_workbook",
        python_callable=run_script,
        op_kwargs={"script": "load_workbook.py", "days_back": 1},
    )
    ranking = PythonOperator(
        task_id="weekly_ranking",
        python_callable=run_script,
        op_kwargs={"script": "weekly_ranking.py", "days_back": 1},
    )
    load >> ranking  # the ranking runs only after the load succeeded
