# v2: the pipeline, rebuilt for reliability and scale

The original system (v1) is at the top of this repository, unchanged; git tag `v1` marks it. v2 rebuilds it step by step. Each step fixes a specific weakness in v1.

| Step | Status | What it changes |
|---|---|---|
| 1. Keys and constraints | Done | A normalised schema the database itself keeps clean: [sql/001_schema.sql](sql/001_schema.sql) |
| 2. Safe re-runnable loads | Done | [load_workbook.py](load_workbook.py) loads the workbook into the schema; a re-run adds nothing twice |
| 3. Validation before loading | Done | [validate_workbook.py](validate_workbook.py) checks the workbook and lists every problem; the load runs it first |
| 4. Notebooks → Python modules | Done | The daily distribution and the weekly ranking are scripts; all settings are in [settings.py](settings.py) |
| 5. Tests | Done | 127 pytest tests in [tests/](tests): checks, intake folder, daily files, load, dbt build, schedule, dashboards and reports |
| 6. Scheduling and alerts | Done | Airflow runs the scripts on a schedule and emails the result of each step: [dags/pipeline_dags.py](dags/pipeline_dags.py) |
| 7. dbt models | Done | Reporting views built and tested by dbt: daily branch KPIs, weekly and monthly rankings, in [dbt/](dbt) |
| 8. Replacing the Excel intake | Done | The entry person's daily files go into an intake folder and are read from there; only the last 10 days are kept |
| 9. Weekly dashboard | Done | A web page for the area managers instead of the Power BI weekly report: manager → branches → meals → issue descriptions, with grades in colour: [weekly_dashboard.py](weekly_dashboard.py) |
| 10. Monthly, quarterly and yearly reports | Done | The other three Power BI reports, for management on computers: Plotly charts, then the ranking down to meals and descriptions: [period_reports.py](period_reports.py) |

## Running v2

```bash
pip install -r v2/requirements.txt
psql -U postgres -d shawarma_classic -f v2/sql/001_schema.sql   # once
```

dbt goes in its own environment; see step 7.

Each day, drop the entry person's daily file into the intake folder (`INTAKE_DIR`, step 8). The lists (branches and codes, Managers, Fixed Choices) stay in the workbook (`WORKBOOK_PATH`).

| When | Command | What it does |
|---|---|---|
| Any time | `python v2/validate_workbook.py` | Checks every daily file with the lists; no database needed |
| Daily | `python v2/distribute_issues.py` | Yesterday's issues, from that day's file → one file per branch, in a folder per manager |
| Weekly | `python v2/load_workbook.py` | Checks every daily file, loads them into the database, then deletes files older than `KEEP_DAYS` days |
| Weekly, after the load | `python v2/build_models.py` | dbt builds the reporting views and runs their checks |
| Weekly, after dbt | `python v2/weekly_ranking.py` | Branch and manager ranking for the last Wednesday–Tuesday week, to Excel |
| Weekly, after dbt | `python v2/weekly_dashboard.py` | The weekly dashboard for the same week: one HTML file |
| Monthly, on the 1st, after a load and dbt | `python v2/period_reports.py` | Last month's report, plus the quarter's and the year's when they end |

On the sample data, add `REPORT_DATE=2026-10-26` (its last day) in front of the daily, ranking and dashboard commands. The monthly, quarterly and yearly reports need the sample's fake history; see step 10.

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
| [weekly_ranking.py](weekly_ranking.py) | Weekly branch and manager ranking, to Excel (the maths moved to dbt in step 7) | Notebook 02, Step 3 |

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
TEST_PGDATABASE=shawarma_classic_test pytest v2               # adds the database tests
TEST_PGDATABASE=shawarma_classic_test DBT_EXECUTABLE=~/dbt-venv/bin/dbt pytest v2   # all 127, dbt too (step 7)
```

A test runs a piece of the pipeline on input where the right answer is known, and fails if the answer changes. Run them after every change: if something breaks, a test names it before it reaches the reports.

| File | What it tests | Data |
|---|---|---|
| [test_validate_workbook.py](tests/test_validate_workbook.py) | Every check: a clean workbook passes, each mistake gives its exact message and Excel row, later stages wait for earlier ones, the daily check ignores tasks and other days | A tiny workbook (3 branches, 2 tasks, 1 issue), with one thing broken per test |
| [test_weekly_ranking.py](tests/test_weekly_ranking.py) | Which week the Excel ranking is for. (The ranking math was tested here until step 7 moved it into dbt; its tests are now dbt unit tests.) | Dates |
| [test_period_reports.py](tests/test_period_reports.py) | The monthly, quarterly and yearly reports (step 10): the periods, which reports are due, each report's layout and charts, Plotly inside the file; and the fake history: valid, rotating, improving | A tiny made-up period, and the fake history |
| [test_weekly_dashboard.py](tests/test_weekly_dashboard.py) | The weekly dashboard (step 9): the wording, no JavaScript on the page, the grade colours, names escaped, Arabic names kept in place, each manager's branches, each branch's meals with their descriptions and missed times, the first week | A tiny made-up week (2 managers, 3 branches) |
| [test_intake.py](tests/test_intake.py) | The intake folder (step 8): any file name, lock and hidden files skipped, problems named with their file, the same day in two files, deleting only files older than `KEEP_DAYS` days | The tiny workbook, saved as daily files |
| [test_distribute_issues.py](tests/test_distribute_issues.py) | One file per branch in its manager's folder, the right rows, each photo on its own row and the same picture as in the day's file; a mistake writes nothing; a missing day's file stops the run | The sample's daily files (the only ones with in-cell photos) |
| [test_database.py](tests/test_database.py) | A second load adds nothing, a failed load saves nothing, a corrected manager is updated, old files are deleted only after a successful load, dbt builds with every check passing, the daily KPIs, the weekly Excel files and the weekly dashboard add up to the daily files, and the monthly, quarterly and yearly reports to the fake history | A copy of the sample's daily files, in a test database |

The tiny workbook is built in [conftest.py](tests/conftest.py), a file pytest loads by itself. Each test gets a fresh copy.

The database tests are skipped unless `TEST_PGDATABASE` is set. The name must contain `test`, because the tests drop and recreate the `ops` schema before each one. The ones that run dbt are also skipped when dbt can't be found (`DBT_EXECUTABLE`, step 7).

**Checked by planting bugs:** passing tests only matter if they fail when the code is wrong. Eight bugs were planted one at a time (v1's grouping without due time, no transaction, spaces not removed, Excel rows off by one, Missed Tasks not checked, a changed score weight, ties not skipping a rank, a photo one row too low). Each one made at least one test fail. (Step 7 repeated this for its own code.)

## Step 6: scheduling and alerts

[Airflow](https://airflow.apache.org/) runs the scripts on a schedule, and emails the result of every step.

| DAG | When (Riyadh time) | Steps, in order | Report date |
|---|---|---|---|
| `daily_issues` | Every day, 11:59 pm | `distribute_issues.py` | That day |
| `weekly_ranking` | Wednesdays, 9:00 am | `load_workbook.py`, `build_models.py` (dbt, step 7), then `weekly_ranking.py` and `weekly_dashboard.py` (step 9) side by side | The day before, so the ranking covers last Wednesday to Tuesday |
| `period_reports` | The 1st of each month, 10:00 am | `load_workbook.py`, `build_models.py`, then `period_reports.py` (step 10) | The day before: the month's last day |

A DAG is Airflow's word for a list of steps (tasks), the order they run in, and when.

| File | Job |
|---|---|
| [dags/pipeline_dags.py](dags/pipeline_dags.py) | The three DAGs |
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
- **Each weekly step waits for the one before** (`load >> models >> [ranking, dashboard]`: the Excel ranking and the dashboard both start once dbt is done). If one fails, the steps after it are skipped.
- **An email after every step:** `OK` with what the script printed, or `FAILED` with the error. That's one email a day, four more on Wednesdays, and three on the 1st of each month. If none arrives, Airflow isn't running.
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
| [manager_weekly_ranking](dbt/models/manager_weekly_ranking.sql) | Manager per week | The weekly manager ranking. A branch counts for its manager on the week's last day. Since step 9, with a grade |
| [weekly_kpis](dbt/models/weekly_kpis.sql) | Week | The two KPIs for all branches together: the weekly dashboard's headline numbers (added in step 9) |
| [branch_meal_weekly](dbt/models/branch_meal_weekly.sql) | Branch, meal and week | Tasks due, missed, and quality issues: the meals under each branch on the weekly dashboard (added in step 9) |
| [issue_descriptions_weekly](dbt/models/issue_descriptions_weekly.sql) | Branch, meal, description and week | How many times each issue description came up (added in step 9) |
| [missed_tasks](dbt/models/missed_tasks.sql) | Missed task | Which branch missed which meal, with its day, due time and week (added in step 9) |
| [period_kpis](dbt/models/period_kpis.sql) | Month, quarter and year | The two KPIs for all branches together (added in step 10) |
| [branch_period_ranking](dbt/models/branch_period_ranking.sql) | Branch per month, quarter and year | The weekly branch method over a longer period (added in step 10) |
| [manager_period_ranking](dbt/models/manager_period_ranking.sql) | Manager per month, quarter and year | The manager ranking from branch-months: each branch counts for the manager who ran it that month. Its month rows were `manager_monthly_ranking` until step 10 |
| [branch_meal_period](dbt/models/branch_meal_period.sql) | Branch, meal, and month, quarter or year | Tasks due, missed, and quality issues (added in step 10) |
| [issue_descriptions_period](dbt/models/issue_descriptions_period.sql) | Branch, meal, description, and month, quarter or year | How many times each description came up (added in step 10) |

The method is the one in [metrics.md](../docs/metrics.md). `weekly_ranking.py` now only picks one week from the two weekly views and writes the Excel files; it no longer does any maths.

| File | What it is |
|---|---|
| [dbt/dbt_project.yml](dbt/dbt_project.yml) | The project's settings. Every model is a view: a saved query, always up to date, nothing to refresh |
| [dbt/profiles.yml](dbt/profiles.yml) | The connection. It reads the same `PG*` environment variables as the scripts, so no password is stored |
| [dbt/models/sources.yml](dbt/models/sources.yml) | The `ops` tables dbt reads from |
| [dbt/models/models.yml](dbt/models/models.yml) | What each model and column means, and the data checks |
| [dbt/models/unit_tests.yml](dbt/models/unit_tests.yml) | The unit tests |
| [dbt/macros/share_of_max.sql](dbt/macros/share_of_max.sql) | "Divide by the group's largest value", used by all three rankings |
| [dbt/macros/week_end.sql](dbt/macros/week_end.sql) | The Tuesday that ends a day's week, used by every weekly view (added in step 9) |
| [dbt/macros/grade.sql](dbt/macros/grade.sql) | The five grades from a score, used by the branch and manager rankings (added in step 9) |
| [dbt/tests/submissions_match_the_workbook.sql](dbt/tests/submissions_match_the_workbook.sql) | A check written as a query that returns the rows that break it |
| [dbt/tests/weekly_counts_agree.sql](dbt/tests/weekly_counts_agree.sql) | The same kind of check for the dashboard: its totals agree at every level, every week (added in step 9) |
| [dbt/tests/period_counts_agree.sql](dbt/tests/period_counts_agree.sql) | The same for the monthly, quarterly and yearly reports; and each quarter and year is the sum of its months (added in step 10) |
| [build_models.py](build_models.py) | Runs `dbt build`; the weekly and monthly Airflow runs call it after the load |

### Checks, every time dbt runs

`dbt build` builds each view and checks it before anything that depends on it. If a check fails, the views after it aren't built, the run's email says which check failed, and the steps after it (ranking, dashboard, reports) are skipped.

- **19 unit tests:** a few made-up rows in, the exact rows expected out, worked out on paper in each test's description. They cover the tiny week from step 5, ties, a week with no issues, a score of exactly 0.95, each week ranked on its own, the Wednesday–Tuesday weeks, a week that spans a rotation, the managers' 85/15 weights, and the monthly ranking following the rotation. Step 9 added four (the week's KPIs from counts, each branch's meals, the issue descriptions, the missed tasks) and checks the managers' grades. Step 10 moved the monthly ranking's test to `manager_period_ranking`, with quarter and year rows, and added five: months, quarters and years for the KPIs, the branch ranking (twice), the meals and the descriptions.
- **48 data checks on the real data:** one row per branch per day (and per week and month), no missing managers or ranks, only the five grades, every branch code known, and submissions that add up to the workbook's own *Done Tasks* on every day. Step 9 added twelve, for its four views, the managers' grades and the totals. Step 10's five views and their totals bring twenty-one more.

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

## Step 8: the intake folder

Before this step, the day's data passed through two manual hands: the entry person in Egypt filled a daily Excel file, then it was copied, row by row with its photos, into `07-2024.xlsx`, which the pipeline read. That workbook keeps every row and photo forever (Lubda's is already over 2 GB).

Now his daily file goes into an **intake folder** as it is, and the pipeline reads the daily files there. `07-2024.xlsx` keeps only the lists you maintain. After each weekly load, files older than 10 days are deleted.

| | Before | Now |
|---|---|---|
| Getting the day's data in | Copy his rows and photos into `07-2024.xlsx` | Save his file into the intake folder |
| Tasks and issues | One workbook that keeps growing | One file per day; the folder keeps the last 10 days |
| Photos for the managers' daily files | From `07-2024.xlsx` | From that day's file |
| History | `07-2024.xlsx` and the database | The database |
| `07-2024.xlsx` | Everything | The lists: branches and codes, Managers, Fixed Choices |

Why not have a script copy his rows into `07-2024.xlsx` instead: Python's Excel library (openpyxl) can't keep Excel's in-cell photos. Opening the step 7 sample workbook, adding one row and saving it took the photos from 90 to 0. Keeping that workbook would have meant driving Excel itself, or rewriting the photo parts inside the file by hand.

### How it works

- **Any file name.** The days are read from inside each file. Excel's lock files (`~$...`) and the hidden `._` files macOS leaves on some drives are skipped.
- **Each daily file is checked with the lists, like one workbook**, with every rule from step 3. A problem names its file: `2026-10-26.xlsx: Reviewing Reports row 4: description 'Bread cold' isn't in Fixed Choices`. A problem in the lists is listed once, without a file name.
- **Between files:** a day in two files is reported (for example a corrected resend next to the first one: remove the old one), and so is a file with no tasks.
- **The daily run** uses the file that has that day. If there's none, it stops with `No file for 2026-11-15 in the intake folder`, and Airflow emails FAILED: drop the file in and click *Clear* on the run. A file with tasks but no issues is a normal day with nothing to send.
- **The weekly load** reads every file in the folder, in one transaction. A problem in any file means nothing is loaded.
- **Keeping 10 days:** after the load is saved, a file is deleted when all its days are more than `KEEP_DAYS` days before the report date. The Wednesday run (report date: Tuesday Nov 10) keeps Nov 1–10. Files go for good, photos included: the database keeps the tasks and issues, but never had the photos. If the load fails, nothing is deleted. With `KEEP_DAYS` not set, nothing is ever deleted, which is how the sample files stay safe.

### Setting it up

1. Make an intake folder and set `INTAKE_DIR` and `KEEP_DAYS=10` in `airflow.env`.
2. Point `WORKBOOK_PATH` at the workbook with the lists. Only its three list sheets are read; a small copy holding just those lists opens faster than a 2 GB workbook.
3. Each day, drop the entry person's file into the folder before the daily run (11:59 pm Riyadh time).

### Tested

- **The sample, split into 14 daily files:** the same 84 tasks, 90 issues and 90 photos, in the same order, as the single workbook before.
- **Daily files:** for Oct 26, the five manager files are identical to the ones made from the single workbook (cells, photos, positions).
- **Load and delete**, on a copy of the sample with `KEEP_DAYS=10` and report date Oct 27: all 14 days loaded, the 5 files for Oct 13–17 deleted, Oct 18–26 kept. A second run added nothing.
- **Tests:** [test_intake.py](tests/test_intake.py) is new, and the other test files now read daily files. Two database tests check that old files are deleted after a successful load, and that nothing is deleted when the load fails.
- **Planted bugs:** 11 bugs, one at a time, in the new code. Examples: lock files not skipped, a day in two files not reported, 11 days kept instead of 10, a file deleted by its oldest day instead of its newest, files deleted before the load, a missing day's file treated as a day with no issues, photos read from the wrong file. Each one made a test fail.

**Known limits:**
- If the Mac is off for more than 10 days, the weekly catch-up run can delete files that the daily catch-up runs for those days still need. Those daily runs then fail with "No file", and their emails say so.
- His file must keep the sheets *Source Data* and *Reviewing Reports* with the same columns.
- Photos older than 10 days are deleted with their files, as decided. The database never kept photos.

## Step 9: the weekly dashboard

The Power BI weekly report is replaced by a web page built for the area managers. The weekly run makes it by itself: `Weekly Report 2026-10-14 to 2026-10-20.html` in the output folder, next to the Excel ranking. Send it the way the PDF went. It's one file of about 20 KB that opens in any browser, offline, with nothing to install and no login.

**See it:** [docs/sample-weekly-dashboard.html](../docs/sample-weekly-dashboard.html) is the dashboard built from the sample data, for the week of Oct 14–20. GitHub shows HTML files as code, so download it (*Download raw file*) and open it in a browser.

It isn't a copy of the Power BI report. It's built around who and what, the same way for both KPIs:

```
manager  →  their branches  →  the meals with a problem  →  the issue descriptions, and when each missed task was due
```

The page has two parts:

| Part | Shows | Read from (dbt view) |
|---|---|---|
| Two headline numbers | The week's submission rate and quality issues for all branches, with the change since the week before | `weekly_kpis` (new) |
| By manager | The managers in rank order, each with grade, % submitted, issues and places moved since last week. Tap a manager to see their branches, shown the same way. Tap a branch to see its problem meals ("Arabi Sop: 2 issues · 1 missed (Thu 15, 4-8 pm)") and, under each meal, its issue descriptions ("Wrong sauce quantity ×2") | `manager_weekly_ranking`, `branch_weekly_ranking`, and the new `branch_meal_weekly`, `issue_descriptions_weekly`, `missed_tasks` |

An opened branch looks like this:

```
▾ #11 Al Olaya - العليا  [Excellent]  ▼ 10
      97.6% submitted · 1 issue
      • Heating Shawarma: 1 issue
          ◦ Station not cleaned between orders
      • Arabi Sop: 1 missed (Fri 16, 12-4 pm)
```

### Colours that say good or bad

Each grade has its own colour, from best to worst. The word is always written too, so colour isn't the only signal:

| Grade | Colour |
|---|---|
| Excellent | Dark green |
| Good | Light green |
| Fair | Yellow |
| Bad | Orange |
| Terrible | Red |

**Managers now get a grade too**, from the score their ranking already computes, with the branches' thresholds ([metrics.md](../docs/metrics.md#rank-and-grade)). v1 only ranked them. Changes since last week are green when better and red when worse, with ▲ ▼ arrows. The other colours (navy, orange) come from the Power BI theme.

### Simple, and no JavaScript

- **Area managers read it on their phones, from an attachment.** On an iPhone, tapping an attachment in WhatsApp or Mail opens a preview that doesn't run JavaScript, and Safari won't open a file saved on the phone. So the page is plain HTML: no JavaScript and no pictures.
- **"Tap to open" is HTML's own `<details>` element.** It needs no JavaScript, but whether the iPhone preview lets you tap it is untested (see Known limits).
- **Everything that wasn't needed was taken out.** The first version had three charts (tasks by day, issues by meal, issues by branch) and two ranking tables. *By manager* shows the same rankings, grades and changes, so they were removed, and matplotlib with them.
- **Arabic names stay in one piece.** Each name is inside `<bdi>`. Without it, the browser pulled the grade and the ▲ number that follow a name into its Arabic half, and showed "Al Malaz - 21 ▲ Excellent الملز".

### Keeping the numbers right

- **The dashboard only reads the dbt views and picks rows. The formulas live in dbt, once.** So it shows the same numbers as the Excel ranking.
- **Four new views.**
  - `weekly_kpis`: the week's two KPIs for all branches. The counts are added up first, then divided.
  - `branch_meal_weekly`: one row per branch, meal and week, with tasks due, missed, and issues.
  - `issue_descriptions_weekly`: how many times each description came up, for each branch's meal and week.
  - `missed_tasks`: one row per missed task, with its day and due time.
- **Two new macros.** `week_end` holds the Wednesday–Tuesday rule, and `grade` holds the five grades. Each is written once, and used by every view that needs it.
- **A new dbt check, `weekly_counts_agree`:** every week, the issues must add up to the same total in the headline, the branches, the meals and the descriptions. The missed tasks must agree in the headline, the meals and the list of misses.

### Running it

```bash
python v2/weekly_dashboard.py
REPORT_DATE=2026-10-26 python v2/weekly_dashboard.py        # the sample's full week, Oct 14-20
```

In Airflow it's a fourth step in the Wednesday run. It starts once dbt has built the views, side by side with the Excel ranking, and sends its own email.

### Tested

- **In a browser at phone size (375 px wide) and computer size:** no sideways scrolling, no JavaScript on the page, and tapping opens a manager, then a branch. That's how the Arabic-name problem above was found.
- **In Airflow:** the weekly run on the sample did the load, then dbt, then the Excel ranking and the dashboard. (This was with the first version of the page. The task itself hasn't changed.)
- **Tests:**
  - [test_weekly_dashboard.py](tests/test_weekly_dashboard.py) is new: 22 tests, no database needed. They check the wording, the five grade colours, names escaped and Arabic names kept in place, each manager holding exactly their branches in rank order, and each branch listing only its own meals. Each meal must carry its own descriptions and missed times. The first week is checked too.
  - `test_database.py` builds the sample's dashboard and checks it against the daily files:
    - the submission rate, the issues and their change since last week;
    - every branch's missed tasks and issues, meal by meal;
    - every description and its count;
    - the day and due time of every missed task;
    - last week's rank for every branch and manager.
  - dbt: unit tests for the four new views and for the managers' grades, and new checks on the new views and the totals.
- **Planted bugs:** 22 bugs, one at a time. For example:
  - on the page: Excellent coloured red, a branch shown under the wrong manager, descriptions or missed times shown under the wrong meal, "×1" written on a single description, Arabic names not kept in one piece, more issues shown as good news;
  - in dbt: last week's rank taken from this week, each description counted once, missed tasks not put in their week, a miss counted on every meal, managers graded on their done rate instead of their score.

  Each one made a test fail. Two got past the first version of the tests:
  - **Managers graded on their done rate.** In that unit test, a 95% done rate and a 0.95 score both mean Good. A second unit test now checks a manager with a 100% done rate who scores 0.85, and is Fair.
  - **Missed times shown under every meal.** The made-up week had a missed task on only one meal. It now has one on two meals.

**Known limits:**
- **Not tested on a real iPhone.** That the preview doesn't run JavaScript is what people consistently report. There's no Xcode on this Mac, so there's no iPhone simulator to try it. Whether the preview lets you tap to open is also untested. If tapping doesn't work there, managers see only the manager lines. The fix is one word: `<details open>` shows everything open. Check it once: send yourself the sample dashboard on WhatsApp and open it on an iPhone and on an Android phone.
- **"vs last week" needs last week in the database.** Like the PDF, the page is a snapshot of one week, so the first week after going live says "no data for last week".
- **The sample's last week is partial.** The week before Oct 14–20 only has Oct 13, so issues seem to jump from 8 to 45. Real weeks are full.
- **The Excel managers summary has no grade column.** It keeps the columns it has always had.
- **No dark mode:** the page stays light, like the PDF.

## Step 10: monthly, quarterly and yearly reports

The other three Power BI reports are replaced by web pages for management, built on the 1st of each month: `Monthly Report 2026-10.html`, `Quarterly Report 2026-Q3.html` and `Yearly Report 2026.html`, in the output folder. Management reads them on computers, so the charts are interactive ([Plotly](https://plotly.com/python/)): hover over a point or a dot to see its numbers.

**See them:** built from the sample data and its fake history: [September 2026](../docs/sample-monthly-report.html), [Q3 2026](../docs/sample-quarterly-report.html) and [2026 so far](../docs/sample-yearly-report.html). GitHub shows HTML files as code, so download one (*Download raw file*, about 5 MB) and open it in a browser.

| | Monthly | Quarterly | Yearly |
|---|---|---|---|
| Headline numbers | Submission rate and quality issues, vs last month | vs last quarter | vs last year |
| Trend: two line charts, % submitted and quality issues | Week by week: the weeks that end in the month | Month by month | Month by month |
| Ranking chart | Managers | Branches | Branches |
| By meal chart | | | Issues and missed tasks for each meal, all branches together |
| Lists | Manager → branches → meals → descriptions, tap to open (like the weekly) | The managers, then branch → meals → descriptions | Same as quarterly |

The grade colours, the ▲ ▼ changes and the tap-to-open lists are the weekly dashboard's own pieces, reused.

### Why quarterly and yearly start with branches

Branches move between managers every month, so a quarter or a year has no single manager per branch.

- **Monthly is by manager**, like the weekly: in a month, each branch has one manager.
- **Quarterly and yearly list the branches**, and rank the managers separately, from **branch-months**. Each branch counts, month by month, for the manager who ran it that month. A manager who ran 4 branches for 3 months has 12 branch-months. Their done rate is the average over those 12, their issues are counted per branch-month, and the score keeps the managers' 85/15 weights.
- Step 7's monthly manager ranking is now the "month" rows of this one, `manager_period_ranking`. Its unit test moved with it.

### The charts

- **Plotly, from Python:** each chart is a few lines of `plotly.graph_objects`, and Plotly writes it into the page. Its chart program is inside every file, about 5 MB, so a report opens without the internet. Unlike the weekly page, these need JavaScript: open them in a browser on a computer.
- **The ranking is dots, not bars,** with the score as a percentage on a scale from 0% to 100%. Each dot sits at its score, in its grade's colour, and thin lines mark where each grade starts (70%, 80%, 90%, 95%). A first version had bars; scores sit close together, between 80% and 100%, so the bars all looked about the same length.
- **Both trends are line charts.** The quality issues scale starts at 0, since it counts. The submission rate scale starts just below its lowest point (90%, not 0): left to itself, Plotly zoomed in to 95%–96.5%, and a one-point change looked like a cliff.
- **Missed tasks are counts only.** Over a month, the day and due time of every miss would make very long lines. The weekly keeps them.

### When they're built

- **A third Airflow schedule, `period_reports`,** runs on the 1st of each month at 10:00 am Riyadh time: `load_workbook.py`, `build_models.py`, then `period_reports.py`. The report date is the day before, the month's last day. The load comes first because the weekly load only runs on Wednesdays.
- **On Oct 1 it writes September's report and Q3's.** On Jan 1 it writes December's, Q4's and the year's. On other months it writes just the month's.
- **By hand:** `python v2/period_reports.py` writes the reports due for `REPORT_DATE`. `python v2/period_reports.py quarter year` writes those two whatever the date, up to the report date, marked "so far, to 26 Oct".

### Keeping the numbers right

- **Five new dbt views, each for every month, quarter and year at once:** `period_kpis`, `branch_period_ranking`, `manager_period_ranking`, `branch_meal_period` and `issue_descriptions_period`. The trick is `date_trunc(period, day)`, which turns a day into the first day of its month, quarter or year. Crossed with the three words, one query gives all three.
- **A new dbt check, `period_counts_agree`.** Every period, the headline, the branches, the meals and the descriptions must add up to the same totals. And every quarter and year must equal the sum of its months.

### The sample's fake history

The sample's 14 daily files cover only Oct 13–26, so a quarterly or yearly report would show one month, and no branch would ever change manager. [sample_data/fake_history.py](sample_data/fake_history.py) adds July 1 – October 12:

- **Branches move every month:** in each month before October, every manager hands their first branch to the next. That's 10 branches a month with a new manager, recorded in *Managers* rows for July, August and September.
- **Things get better month by month,** so the trends have a direction: 342 issues in July, 275 in August, 232 in September.
- **It's loaded with `load_workbook.py`'s own `load()`**, as if from daily files, and it passes every check in `validate_workbook.py`. There are no files and no photos, so the repo stays small, and the 14 sample daily files are unchanged.
- **It only goes into a database whose name contains "sample" or "test"**, so fake data can't reach a real one.

```bash
createdb shawarma_classic_sample
psql -d shawarma_classic_sample -f v2/sql/001_schema.sql
export PGDATABASE=shawarma_classic_sample
python v2/sample_data/fake_history.py                       # Jul 1 - Oct 12
python v2/load_workbook.py                                  # the sample's daily files, Oct 13-26
python v2/build_models.py
REPORT_DATE=2026-09-30 python v2/period_reports.py          # September and Q3
REPORT_DATE=2026-10-26 python v2/period_reports.py year     # 2026, so far
```

### Tested

- **In a browser at computer size:** every chart draws, hovering shows the numbers, and the managers, branches and meals open.
- **In Airflow:** the monthly run for 10:00 am on Oct 1 got the report date Sep 30. It did the load, then dbt (79 passed), then wrote the September and Q3 reports.
- **Tests:**
  - [test_period_reports.py](tests/test_period_reports.py) is new: 29 tests, no database needed. They cover:
    - the periods, and which reports are due on which day;
    - monthly by manager, quarterly and yearly by branch, and the meal chart only in the yearly;
    - missed counts without times, "so far", and the first period;
    - Plotly inside the file, once; both trends drawn as lines; the ranking from 0% to 100%, with the grade lines at 70, 80, 90 and 95;
    - the fake history passing every workbook check, rotating every month and improving month by month.
  - `test_database.py` has three new tests on the fake history plus the sample:
    - the Oct 1 run writes September and Q3;
    - Q3's issues, meals and descriptions match the raw rows, and its 36 branches give 108 branch-months;
    - each September branch is under the manager who ran it in September;
    - the year so far is the history plus the sample;
    - a month with no data stops.
  - dbt: five new unit tests, the monthly one moved, and checks on every new view.
- **Planted bugs:** 22 bugs, one at a time. For example:
  - quarters starting in the wrong month, a quarter compared with the month before, the quarter's report written every month, "vs last week" in a monthly report;
  - a quarterly report organised by manager, the meal chart in every report, Plotly loaded from the internet, the rate scale starting at 0;
  - branch-months counted as branches, a miss counted on every meal, a monthly run on every day, a fake history that never rotates;
  - the issues drawn as dots without a line, the score left as 0 to 1, the scale cut to 60–100%, a grade line at 0.70 instead of 70%.

  Each one made a test fail. One got past the first version of the tests: **branches ranked against all months at once** instead of their own month. That doesn't change the order within a month, only the grades, and the unit test's numbers happened to give the same grades. A new unit test has a July branch that is Excellent against July's best and only Good against August's.

**Known limits:**
- **No comparison with last year** until the v1 history is migrated: the yearly report says "no data for last year" and marks every branch and manager "new".
- **About 5 MB per file,** because Plotly is inside. Fine for email. Loading Plotly from the internet instead would make them small, but then they'd need the internet to open.
- **The charts need JavaScript:** open the reports in a browser on a computer, not in a phone's attachment preview.
- **The monthly trend uses the Wednesday–Tuesday weeks that end in the month,** with the weekly reports' own numbers. So a month's first days can belong to a week shown in the month before, and the weeks don't add up exactly to the month's headline.
- **The fake history is only for the sample.** The real history comes with the v1 migration.
