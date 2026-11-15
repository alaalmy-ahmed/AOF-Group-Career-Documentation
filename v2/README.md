# v2: the pipeline, rebuilt for reliability and scale

The original system (v1) is at the top of this repository, unchanged; git tag `v1` marks it. v2 rebuilds it step by step. Each step fixes a specific weakness in v1.

| Step | Status | What it changes |
|---|---|---|
| 1. Keys and constraints | Done | A normalised schema the database itself keeps clean: [sql/001_schema.sql](sql/001_schema.sql) |
| 2. Safe re-runnable loads | Done | [load_workbook.py](load_workbook.py) loads the workbook into the schema; a re-run adds nothing twice |
| 3. Validation before loading | Done | [validate_workbook.py](validate_workbook.py) checks the workbook and lists every problem; the load runs it first |
| 4. Notebooks → Python modules | Done | The daily distribution and the weekly ranking are scripts; all settings are in [settings.py](settings.py) |
| 5. Tests | Done | 56 pytest tests in [tests/](tests): checks, daily files, load, dbt build, schedule |
| 6. Scheduling and alerts | Done | Airflow runs the scripts on a schedule and emails the result of each step: [dags/pipeline_dags.py](dags/pipeline_dags.py) |
| 7. dbt models | Done | Reporting views built and tested by dbt: daily branch KPIs, weekly and monthly rankings, in [dbt/](dbt) |
| 8. Replacing the Excel intake | Planned | |

## Running v2

```bash
pip install -r v2/requirements.txt
psql -U postgres -d shawarma_classic -f v2/sql/001_schema.sql   # once
```

dbt goes in its own environment; see step 7.

| When | Command | What it does |
|---|---|---|
| Any time | `python v2/validate_workbook.py` | Checks the workbook; no database needed |
| Daily | `python v2/distribute_issues.py` | Yesterday's issues → one file per branch, in a folder per manager |
| Weekly | `python v2/load_workbook.py` | Checks the workbook, then loads it into the database |
| Weekly, after the load | `python v2/build_models.py` | dbt builds the reporting views and runs their checks |
| Weekly, after dbt | `python v2/weekly_ranking.py` | Branch and manager ranking for the last Wednesday–Tuesday week, to Excel |

On the sample data, add `REPORT_DATE=2026-10-26` (its last day) in front of the daily and ranking commands.

To run the tests: `pytest v2` (see step 5). To have Airflow run the scripts on a schedule, see step 6.

## Step 1: the schema

| Table | One row per | Key | Points to |
|---|---|---|---|
| `managers` | Area manager | `manager_id`; `name` is unique | |
| `branches` | Branch | `code` (e.g. `B25`) | |
| `branch_managers` | Branch in a month (added in step 7) | `(month, branch_code)` | `branches`, `managers` |
| `meals` | Meal | `meal_id`; `name` is unique | |
| `scheduled_tasks` | Meal due on a date at a due time | `task_id`; `(task_date, meal_id, due_time)` is unique | `meals` |
| `task_misses` | Branch that missed a task | `(task_id, branch_code)` | `scheduled_tasks`, `branches` |
| `quality_issues` | Quality issue | `issue_id`; `(task_id, branch_code, description)` is unique | `scheduled_tasks`, `branches` |

### What changed from v1, and why

| v1 | v2 | Why |
|---|---|---|
| `tasks` repeats the task's counts on every missed-branch row | `scheduled_tasks` (one row per task) + `task_misses` (one row per miss) | Each fact is stored once, so sums are correct without de-duplicating |
| `branch_missed = ''` when no branch missed | No row in `task_misses` | No placeholder values |
| `done_tasks`, `missed_tasks` | `branches_submitted`; misses are counted from `task_misses` | The names say what the numbers are, and nothing derivable is stored twice |
| Issues have no due time | Each issue points to its scheduled task (date, meal, due time) | A meal can be due twice a day; v1 couldn't tell those issues apart |
| Branch, meal and manager stored as free text | `branches` (keyed by code, e.g. `B25`), `meals` and `managers` tables, referenced by key | A typo or unknown value is rejected |
| No keys, no constraints | Primary keys, unique keys, foreign keys, checks | The database rejects duplicates, typos and impossible values by itself |

Who managed a branch is in `branch_managers`, one row per branch per month, because branches are reassigned every month. (Until step 7, the manager was stored on each issue and on each branch. Step 7 explains why that changed.)

The workbook stays as simple as it was for the data entry. The pipeline translates it into this model.

## Step 2: the load

```bash
python v2/load_workbook.py
```

It needs the schema from step 1 and the same `PG*` environment variables as v1. By default it reads the v2 sample data.

| v1 | v2 | Why |
|---|---|---|
| Tasks grouped by date and meal, keeping only the first due time | Grouped by date, meal **and due time** | A meal due twice a day (Arabi at 1-3 and 5-7 pm) was merged into one row in v1 |
| Only rows newer than `MAX(date)` are inserted | Every row is inserted; `ON CONFLICT DO NOTHING` skips the ones already there | Rows added late for an earlier date are no longer missed |
| No meal list | `meals.xlsx`, one column `Meal` | A misspelled meal is rejected instead of becoming a new meal |
| Issues have no due time | Reviewing Reports has a `Due time` column, filled by the data entry | Each issue is matched to its scheduled task |
| An unknown branch or meal fails with a database error, or not at all | The script stops with a message listing every unknown value | You know exactly what to fix in the workbook |

Everything runs in one transaction: if any step fails, nothing from that run is saved.

**Known limit:** a row that's already loaded and then edited in the workbook (for example a corrected description) isn't updated. The old version stays. If that turns out to matter, the next option is replacing a week's rows on each run.

### Workbook changes for the data entry

- **Reviewing Reports:** a new `Due time` column, next to `Meal`.
- **meals.xlsx:** a new file listing the meals, one per row.
- **Managers:** a `Month` column, one row per branch per month (added in step 7).

## Step 3: checking the workbook before loading

```bash
python v2/validate_workbook.py
```

It needs no database, so it can be run before handing the workbook over. `load_workbook.py` runs the same checks first: if there's any problem, it lists them all and loads nothing. Each problem names the sheet and the Excel row, for example:

```
Source Data row 5: missed branch 'Al Olayaa' isn't in 'branches and codes'
Reviewing Reports row 4: manager is 'Dammam Manager', but 'Managers' says 'Jeddah North Manager' for this branch
```

The checks run in three stages. A stage runs only if the previous one passed, because later checks rely on earlier ones (adding up Done Tasks needs every cell to be a number).

| Stage | Checks |
|---|---|
| 1. Columns | Every sheet has the columns the pipeline reads |
| 2. Basics | No blank required cells; dates are real dates and not in the future; Done Tasks and Missed Tasks are whole numbers ≥ 0 |
| 3. Rules | See below |

Rules checked in stage 3:

- **Every branch does every meal:** for each task (date, meal, due time), submitted + missed = the number of branches in *branches and codes*.
- **Missed Tasks matches the names:** the count equals the branch names listed in *Branches Missed Tasks*.
- **Names are known:** branches, meals, codes and descriptions are in their lists (*branches and codes*, `meals.xlsx`, *Fixed Choices*).
- **Code matches Branch** on each issue, so a wrong code can't blame the wrong branch.
- **Manager matches** the *Managers* row for that branch in the issue's month, so last month's issues keep last month's manager (step 7).
- **Every branch has a manager** in *Managers* for every month that has tasks or issues.
- **Each issue has its task** in *Source Data* (same date, meal and due time).
- **No issue is logged twice**, and each branch is listed once and has one manager.

Before checking, spaces at the start and end of text are removed (so `"Al Olaya "` matches `"Al Olaya"`), and fully empty rows are skipped.

When checks fail, the script exits with code 1, so a scheduler (step 6) can tell the run failed.

## Step 4: notebooks → Python modules

v1 ran as two notebooks. v2 is a set of small `.py` files, each with one job, which a scheduler (step 6) can run:

| File | Job | Replaces |
|---|---|---|
| [settings.py](settings.py) | Every setting (paths, database, report date) in one place | The configuration cells at the top of each notebook |
| [validate_workbook.py](validate_workbook.py) | Read the workbook and check it | (step 3) |
| [load_workbook.py](load_workbook.py) | Load it into the database | Notebook 02, Step 2 (step 2) |
| [distribute_issues.py](distribute_issues.py) | Daily per-manager, per-branch files with photos | Notebook 01 |
| [weekly_ranking.py](weekly_ranking.py) | Weekly branch and manager ranking | Notebook 02, Step 3 |

Each file imports what it needs from the others (for example, `from settings import REPORT_DATE`), so nothing is copied between them.

### What changed from v1, and why

| v1 | v2 | Why |
|---|---|---|
| The daily notebook reads managers from a separate `managers.xlsx` | It uses the workbook's *Managers* sheet, like everything else | One list, so the two can never disagree |
| An issue with a misspelled branch is silently left out of every folder | That day's issues are checked first (blanks, code matches branch, description, manager). If one fails, no files are written | Every issue reaches its manager, or you're told why not |
| The ranking reads the workbook | It reads the v2 database, after the weekly load | The ranking and Power BI use the same data |
| `REPORT_DATE` defaults to the sample's last day | Defaults to yesterday | Ready for a daily schedule |
| Code to centre each photo in its cell | Removed | It never ran: openpyxl's `add_image(image, "K2")` replaces the anchor set just before it, so v1's photos were already placed at the cell's top-left |

**Tested against v1:**
- **Daily files:** v1's notebook functions and `distribute_issues.py` were run on the same day. The files are identical (cell values, photo positions and sizes, row heights, column widths). The only difference: v1 also creates empty folders for managers with no issues that day.
- **Weekly ranking:** v1's ranking cell was run on the same tasks, with both due times kept. It matches row for row for two weeks, except one manager whose average is exactly 94.05: it rounds to 94.1 in v1 and 94.0 in v2, with the same rank. This is the same float tie noted in [metrics.md](../docs/metrics.md).

**Still the same as v1:** the score method ([metrics.md](../docs/metrics.md)), the two output files, and the format of the daily files. (Step 7 moved the ranking into dbt, and counts each branch for its manager on the week's last day instead of the current one.)

## Step 5: tests

```bash
pytest v2                                                     # no database needed
createdb shawarma_classic_test                                # once
TEST_PGDATABASE=shawarma_classic_test pytest v2               # all 56, including the database tests
```

A test runs a piece of the pipeline on input where the right answer is known, and fails if the answer changes. Run them after every change: if something breaks, a test names it before it reaches the reports.

| File | What it tests | Data |
|---|---|---|
| [test_validate_workbook.py](tests/test_validate_workbook.py) | Every check: a clean workbook passes, each mistake gives its exact message and Excel row, later stages wait for earlier ones, the daily check ignores tasks and other days | A tiny workbook (3 branches, 2 tasks, 1 issue), with one thing broken per test |
| [test_weekly_ranking.py](tests/test_weekly_ranking.py) | Which week the Excel ranking is for. (The ranking math was tested here until step 7 moved it into dbt; its tests are now dbt unit tests.) | Dates |
| [test_distribute_issues.py](tests/test_distribute_issues.py) | One file per branch in its manager's folder, the right rows, each photo on its own row and the same picture as in the workbook; a mistake writes nothing | The sample workbook (the only one with in-cell photos) |
| [test_database.py](tests/test_database.py) | A second load adds nothing, a failed load saves nothing, a corrected manager is updated, dbt builds with every check passing, the daily KPIs and the weekly Excel files add up to the workbook | The sample workbook, in a test database |

The tiny workbook is built in [conftest.py](tests/conftest.py), a file pytest loads by itself. Each test gets a fresh copy.

The database tests are skipped unless `TEST_PGDATABASE` is set. The name must contain `test`, because the tests drop and recreate the `ops` schema before each one. The ones that run dbt are also skipped when dbt can't be found (`DBT_EXECUTABLE`, step 7).

**Checked by planting bugs:** passing tests only matter if they fail when the code is wrong. Eight bugs were planted one at a time (v1's grouping without due time, no transaction, spaces not removed, Excel rows off by one, Missed Tasks not checked, a changed score weight, ties not skipping a rank, a photo one row too low). Each one made at least one test fail. (Step 7 repeated this for its own code.)

## Step 6: scheduling and alerts

[Airflow](https://airflow.apache.org/) runs the scripts on a schedule, and emails the result of every step.

| DAG | When (Riyadh time) | Steps, in order | Report date |
|---|---|---|---|
| `daily_issues` | Every day, 11:59 pm | `distribute_issues.py` | That day |
| `weekly_ranking` | Wednesdays, 9:00 am | `load_workbook.py`, `build_models.py` (dbt, step 7), then `weekly_ranking.py` | The day before, so the ranking covers last Wednesday to Tuesday |

A DAG is Airflow's word for a list of steps (tasks), the order they run in, and when.

| File | Job |
|---|---|
| [dags/pipeline_dags.py](dags/pipeline_dags.py) | The two DAGs |
| [alerts.py](alerts.py) | Sends the emails |
| [start_airflow.sh](start_airflow.sh) | Starts Airflow |
| [airflow.env.example](airflow.env.example) | Template for your paths, database password and email settings |

### Setting it up (once)

Airflow isn't in `requirements.txt`: it pins exact versions of hundreds of packages, so it's installed with its constraints file, the list of versions tested together. Use your Python version (`python3 --version`) in the link; this example is for 3.14:

```bash
pip install "apache-airflow==3.4.0" --constraint https://raw.githubusercontent.com/apache/airflow/constraints-3.4.0/constraints-3.14.txt
```

Copy `airflow.env.example` to `airflow.env` (same folder) and fill it in. `airflow.env` is in `.gitignore`. The email password is a Gmail **app password**, made at <https://myaccount.google.com/apppasswords> once 2-Step Verification is on, not the account's normal password. To check the email settings, send yourself a test email:

```bash
source v2/airflow.env && cd v2 && python -c "from alerts import send_email; send_email('Test', 'It works')"
```

### Running it

```bash
v2/start_airflow.sh
```

Leave that terminal open. Open <http://localhost:8080> and log in as `admin` with the password printed in the terminal. Both DAGs start paused: switch each one on with its toggle.

### How it works

- **Each task runs a script as you would in a terminal**, for example `REPORT_DATE=2026-11-12 python distribute_issues.py`. The script's exit code decides the result: 0 is success, 1 is failure (steps 3 and 4).
- **Each run knows which day it's for.** Airflow stamps every run with its scheduled time, and the task turns that into `REPORT_DATE`, in Riyadh time whatever the Mac's clock is set to. So re-running an old run redoes that day, not today. A run started by hand (the ▶ button) uses the time it's started.
- **Missed days are made up.** If Airflow wasn't running at a scheduled time (the Mac was off), it runs each missed day when it's back, oldest first, one at a time. It counts from `SCHEDULE_START_DATE` in `airflow.env`: set it to the day you switch the schedule on.
- **Each weekly step waits for the one before** (`load >> models >> ranking`). If one fails, the steps after it are skipped.
- **An email after every step:** `OK` with what the script printed, or `FAILED` with the error. That's one email a day, and three more on Wednesdays. If none arrives, Airflow isn't running.
- **No automatic retries:** a mistake in the workbook won't fix itself. Fix it, then click *Clear* on the failed run in Airflow to run it again for its own day.

A failure email looks like this:

```
Subject: FAILED: daily_issues / distribute_issues

distribute_issues.py stopped with exit code 1.

Report date: 2026-10-25

The workbook has 1 problem(s):
  - Reviewing Reports row 79: manager is 'Nobody', but 'Managers' says 'West Riyadh Manager' for this branch
No files were written.
```

### What changed from v1, and why

| v1 | v2 | Why |
|---|---|---|
| The notebooks are started by hand | Airflow starts them on schedule | Nothing depends on someone remembering |
| A failure is seen only by whoever ran the notebook | An email after every step, with the error | You hear about a problem even when you're away from the Mac |
| A day nobody ran is simply missing | Missed days are made up, each with its own date | Every day still gets its files, every week its load |
| The load and the ranking are cells in one notebook | Two tasks; the ranking runs only if the load succeeded | A ranking is never built on a load that failed |

### Tested

- **The real Airflow scheduler**, on the sample data, with a local test mail server in place of Gmail and `SCHEDULE_START_DATE=2026-10-24`. When switched on, it made up 19 daily runs (Oct 24 to Nov 11), each with its own report date. It also ran 3 weekly runs, at 9:00 am Riyadh time on Wednesdays, each covering Wednesday to Tuesday: the 2 weeks after the sample's last day failed with *No tasks in the database*. 25 emails, each with the right subject and content.
- **A workbook with one wrong manager** on Oct 25: re-running Oct 25 failed, and the email gave the row (above). The weekly load failed the same way, and the ranking was skipped with no email.
- **Tests:** [test_alerts.py](tests/test_alerts.py) checks the email without sending one. [test_dags.py](tests/test_dags.py) checks the schedules, the task order, the report date of each run (including a run just after midnight in Riyadh, when it's still the day before in UTC), and the emails. It also runs the real daily script once. `test_dags.py` is skipped when Airflow isn't installed. Nine bugs were planted in the new code (wrong week end, UTC day, ranking not waiting for the load, missed days not made up, a failed script not failing the task, and others), and each one made a test fail.

**Known limits:**
- Airflow runs only while its terminal is open and the Mac is awake. Missed runs are made up later, so files can arrive late. Starting it automatically at login is a possible next step.
- The weekly load checks the whole workbook at 9 am on Wednesday. If that Wednesday's rows are already half entered by then (for example an issue whose task isn't in *Source Data* yet), the check fails and nothing is loaded. Finish them, then *Clear* the run.
- `airflow standalone` keeps Airflow's own records in a single file (SQLite), which is fine for one machine. An always-on server would run Airflow as services with PostgreSQL for its records.

## Step 7: dbt models

[dbt](https://docs.getdbt.com/) builds reporting views in the database, as plain SQL files, and checks them every time it runs. Power BI and the weekly Excel ranking now read the same views, so every report uses one definition of each KPI.

| Model (view in schema `reporting`) | One row per | For |
|---|---|---|
| [branch_daily](dbt/models/branch_daily.sql) | Branch per day | Tasks due, missed and submitted, submission rate, quality issues, and that month's manager. The weekly, monthly, quarterly and yearly reports can add these rows up |
| [branch_weekly_ranking](dbt/models/branch_weekly_ranking.sql) | Branch per Wednesday–Tuesday week | Done rate, issues, score, rank and grade, for every week so far |
| [manager_weekly_ranking](dbt/models/manager_weekly_ranking.sql) | Manager per week | The weekly manager ranking. A branch counts for its manager on the week's last day |
| [manager_monthly_ranking](dbt/models/manager_monthly_ranking.sql) | Manager per month | The same method over a month, with the manager who ran each branch that month |

The method is the one in [metrics.md](../docs/metrics.md). `weekly_ranking.py` now only picks one week from the two weekly views and writes the Excel files; it no longer does any maths.

| File | What it is |
|---|---|
| [dbt/dbt_project.yml](dbt/dbt_project.yml) | The project's settings. Every model is a view: a saved query, always up to date, nothing to refresh |
| [dbt/profiles.yml](dbt/profiles.yml) | The connection. It reads the same `PG*` environment variables as the scripts, so no password is stored |
| [dbt/models/sources.yml](dbt/models/sources.yml) | The `ops` tables dbt reads from |
| [dbt/models/models.yml](dbt/models/models.yml) | What each model and column means, and the data checks |
| [dbt/models/unit_tests.yml](dbt/models/unit_tests.yml) | The unit tests |
| [dbt/macros/share_of_max.sql](dbt/macros/share_of_max.sql) | "Divide by the group's largest value", used by all three rankings |
| [dbt/tests/submissions_match_the_workbook.sql](dbt/tests/submissions_match_the_workbook.sql) | A check written as a query that returns the rows that break it |
| [build_models.py](build_models.py) | Runs `dbt build`; the weekly Airflow run calls it between the load and the ranking |

### Checks, every time dbt runs

`dbt build` builds each view and checks it before anything that depends on it. If a check fails, the views after it aren't built, the weekly run's email says which check failed, and the ranking step is skipped.

- **10 unit tests:** a few made-up rows in, the exact rows expected out, worked out on paper in each test's description. They cover the tiny week from step 5, ties, a week with no issues, a score of exactly 0.95, each week ranked on its own, the Wednesday–Tuesday weeks, a week that spans a rotation, the managers' 85/15 weights, and the monthly ranking following the rotation.
- **15 data checks on the real data:** one row per branch per day (and per week and month), no missing managers or ranks, only the five grades, every branch code known, and submissions that add up to the workbook's own *Done Tasks* on every day.

### Who managed a branch, month by month

dbt's monthly ranking needs to know who ran each branch in each month. Before this step, the workbook's *Managers* sheet was overwritten at every rotation, which caused two problems:

- **The weekly load would have stopped working.** The step 3 check compared every issue, including last month's, with the new names. After the first rotation, every older issue would fail, and nothing would be loaded.
- **Last month's managers were lost.** Nothing recorded them.

The fix:

| Before | Now |
|---|---|
| *Managers*: Branch, Manager, overwritten each month | *Managers*: **Month**, Branch, Manager. At a rotation, the data entry copies last month's rows and changes the Month and the names |
| Each issue checked against the current names | Each issue checked against its own month's row |
| The manager stored on each branch (current) and on each issue (when loaded) | One table, `ops.branch_managers`: one row per branch per month. The two old columns are removed, so the answer is stored once |

If a month's rows are missing, the checks say so in one line (`Managers: no rows for 2026-11`). The daily run only needs them on a day that has issues.

### Setting it up

dbt goes in its own Python environment: dbt and Airflow both pin the package `pathspec`, at versions that clash.

```bash
python3 -m venv ~/dbt-venv
~/dbt-venv/bin/pip install -r v2/dbt/requirements.txt
```

If the install fails with `CERTIFICATE_VERIFY_FAILED`, Python's certificate list isn't installed. This is usual for the python.org installer on a Mac. Run *Install Certificates.command* in the Python folder under Applications once, then install again.

Then set `DBT_EXECUTABLE` to the full path of `~/dbt-venv/bin/dbt` in `airflow.env` (or in your terminal). By hand:

```bash
python v2/build_models.py          # dbt build: every view and every check
cd v2/dbt && dbt build             # the same, with dbt itself (dbt finds profiles.yml in this folder)
```

### Tested

- **dbt against the step 4 ranking:** the old pandas ranking and the new dbt one were run on the sample's three weeks. Ranks and row order are identical. Eight values differ, all where pandas got the arithmetic slightly wrong: pandas stores numbers as binary fractions, and SQL keeps exact decimals.
  - **One grade:** a branch's score is exactly 0.95 (0.90 × 1 + 0.10 × 0.5), which the method grades Good. pandas computed 0.9500000000000001 and said Excellent.
  - **Seven manager averages**, each exactly on a half (94.05, 92.85, 92.25, 1.25): an average like 1.25 rounds to 1.3, as you'd round by hand. pandas rounds halves to the even digit and gets 1.2. This is also the 94.05 case from step 4: dbt gives 94.1, as v1 did.
- **In Airflow:** the weekly run on the sample made 3 catch-up runs, each one load, then dbt (29 passed), then ranking. A planted task row that disagrees with the workbook made dbt's `submissions_match_the_workbook` check fail. The email named the check, and the ranking was skipped.
- **Planted bugs:** 12 bugs, one at a time, in the new code. Examples: an issue checked against the latest month instead of its own, weeks ending on Monday, a week's manager taken from its first day, 0.95 graded Excellent, one manager weight changed, each week divided by the largest value of all weeks, a corrected manager not updated. Each one made a pytest test or a dbt test fail.

**Known limits:**
- The sample covers October only, so the rotation is tested with the tiny workbooks and the unit tests, not on the sample.
- dbt's own `.yml` files repeat a few rules the workbook check already enforces (for example, every branch has a manager each month). That's deliberate: the workbook check guards what goes in, and dbt checks what comes out.
