"""
Tests for the Airflow schedule in dags/pipeline_dags.py: the DAGs load,
they run at the right times in the right order, each run gets the right
REPORT_DATE, and the right emails go out.

Skipped when Airflow isn't installed (it isn't in requirements.txt).
"""

import os
import subprocess
import tempfile
from types import SimpleNamespace

import pytest

# Airflow writes its own files to AIRFLOW_HOME (default ~/airflow) as soon as
# it's imported. Point it at a temporary folder so the tests leave nothing behind.
os.environ.setdefault("AIRFLOW_HOME", tempfile.mkdtemp())
pytest.importorskip("airflow")

import pendulum  # noqa: E402  (installed with Airflow)
from airflow.dag_processing.dagbag import DagBag  # noqa: E402

import pipeline_dags  # noqa: E402

DAGS_FOLDER = os.path.dirname(pipeline_dags.__file__)


def riyadh(*args):
    return pendulum.datetime(*args, tz="Asia/Riyadh")


@pytest.fixture
def dags():
    bag = DagBag(dag_folder=DAGS_FOLDER)
    assert bag.import_errors == {}
    return bag.dags


@pytest.fixture
def fake_run(monkeypatch):
    """Replace subprocess.run: remember each call and pretend the script printed 'Done.'"""
    calls = []

    def run(args, **kwargs):
        calls.append({"args": args, **kwargs})
        return subprocess.CompletedProcess(args, 0, stdout="Done.\n", stderr="")

    monkeypatch.setattr(pipeline_dags.subprocess, "run", run)
    return calls


@pytest.fixture
def sent(monkeypatch):
    """Replace send_email: remember each (subject, body)."""
    emails = []
    monkeypatch.setattr(pipeline_dags, "send_email", lambda subject, body: emails.append((subject, body)))
    return emails


def test_schedules(dags):
    assert set(dags) == {"daily_issues", "weekly_ranking"}

    daily, weekly = dags["daily_issues"], dags["weekly_ranking"]
    assert daily.timetable.expression == "59 23 * * *"  # every day, 11:59 pm
    assert weekly.timetable.expression == "0 9 * * 3"  # Wednesdays, 9:00 am
    for dag in (daily, weekly):
        assert dag.timetable.timezone.name == "Asia/Riyadh"
        assert dag.catchup is True
        assert dag.max_active_runs == 1


def test_tasks_and_order(dags):
    daily = dags["daily_issues"].task_dict
    assert list(daily) == ["distribute_issues"]
    assert daily["distribute_issues"].op_kwargs == {"script": "distribute_issues.py", "days_back": 0}

    weekly = dags["weekly_ranking"].task_dict
    assert weekly["weekly_ranking"].upstream_task_ids == {"load_workbook"}
    assert weekly["load_workbook"].op_kwargs == {"script": "load_workbook.py", "days_back": 1}
    assert weekly["weekly_ranking"].op_kwargs == {"script": "weekly_ranking.py", "days_back": 1}

    for dag in dags.values():
        for task in dag.tasks:
            assert task.retries == 0
            # By name: the DagBag loads its own copy of the file, so the functions aren't the same objects
            assert [f.__name__ for f in task.on_success_callback] == ["email_ok"]
            assert [f.__name__ for f in task.on_failure_callback] == ["email_failed"]


@pytest.mark.parametrize(
    "logical_date, days_back, expected",
    [
        (riyadh(2026, 11, 12, 23, 59), 0, "2026-11-12"),  # daily: the run's own day
        (riyadh(2026, 11, 11, 9, 0), 1, "2026-11-10"),  # weekly on Wednesday: the week ends Tuesday
        # 00:30 on Nov 13 in Riyadh is still Nov 12 in UTC: the Riyadh day must win
        (pendulum.datetime(2026, 11, 12, 21, 30, tz="UTC"), 0, "2026-11-13"),
    ],
)
def test_report_date(fake_run, logical_date, days_back, expected):
    output = pipeline_dags.run_script("distribute_issues.py", days_back, logical_date=logical_date)

    [call] = fake_run
    assert call["env"]["REPORT_DATE"] == expected
    assert output.startswith(f"Report date: {expected}")


def test_run_started_by_hand_uses_its_start_time(fake_run):
    started = SimpleNamespace(run_after=riyadh(2026, 11, 12, 10, 0))

    pipeline_dags.run_script("distribute_issues.py", 0, logical_date=None, dag_run=started)

    assert fake_run[0]["env"]["REPORT_DATE"] == "2026-11-12"


def test_failed_script_fails_the_task_with_its_output(monkeypatch):
    problem = "Reviewing Reports row 4: manager is 'Nobody', but 'Managers' says 'Manager A' for this branch"

    def run(args, **kwargs):
        return subprocess.CompletedProcess(args, 1, stdout=f"{problem}\nNo files were written.\n", stderr="")

    monkeypatch.setattr(pipeline_dags.subprocess, "run", run)

    with pytest.raises(RuntimeError) as error:
        pipeline_dags.run_script("distribute_issues.py", 0, logical_date=riyadh(2026, 10, 26, 23, 59))
    assert "distribute_issues.py stopped with exit code 1" in str(error.value)
    assert problem in str(error.value)


def test_runs_the_real_script(monkeypatch, tmp_path):
    """No fakes: the sample workbook's last day, written to a temporary folder."""
    monkeypatch.setenv("OUTPUT_DIR", str(tmp_path))

    output = pipeline_dags.run_script("distribute_issues.py", 0, logical_date=riyadh(2026, 10, 26, 23, 59))

    assert "Done: 6 issues from 2026-10-26." in output
    assert len(list(tmp_path.glob("managers/*/*.xlsx"))) == 5


def test_emails(sent):
    task = SimpleNamespace(
        dag_id="daily_issues",
        task_id="distribute_issues",
        xcom_pull=lambda task_ids: "Report date: 2026-10-26\n\nDone.",
    )

    pipeline_dags.email_ok({"ti": task})
    pipeline_dags.email_failed({"ti": task, "exception": RuntimeError("distribute_issues.py stopped")})

    assert sent == [
        ("OK: daily_issues / distribute_issues", "Report date: 2026-10-26\n\nDone."),
        ("FAILED: daily_issues / distribute_issues", "distribute_issues.py stopped"),
    ]
