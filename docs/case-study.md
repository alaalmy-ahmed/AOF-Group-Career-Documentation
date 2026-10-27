# Case study: automating operations reporting for a multi-brand restaurant group

**Company:** AOF Group (Shawarma Classic & Lubda), Saudi Arabia
**Role:** Data Analytics Engineer · **Period:** February 2024 – present
**Stack:** Python (pandas, openpyxl, psycopg2), PostgreSQL, Power BI

---

## The problem

AOF Group runs ~37 branches across Riyadh, Jeddah and the Eastern Province under two brands. Every day, trainers and branch staff log task completions and quality issues for ~25 menu items, each with its own standard operating procedure (SOP).

Before this project:

- Daily logs lived in one large operations workbook. Someone had to filter and split them by hand, photos included, before area managers saw anything.
- Branch names were entered inconsistently ("Al Rawdha" vs. "Rawdha Branch"), so totals didn't add up.
- There was no single history. Each month was a separate workbook.
- Nobody could compare branches or managers week to week.

## What I built

**1. A pipeline that works around the team's existing tools.**
The quality team keeps working in the same Excel workbook. Behind it, Python handles distribution and loading, PostgreSQL holds the full history, and Power BI produces the reports. Nobody had to change how they enter data.

**2. Daily distribution to area managers, photos included.**
Every morning a notebook takes yesterday's quality issues and writes a folder per area manager (10 in total), with one formatted Excel file per branch. Excel stores in-cell photos as rich values that standard libraries drop. So I parsed the workbook's internal XML to map each photo back to its row and re-embedded it in the right file.

**3. Weekly incremental load into PostgreSQL.**
Once a week a notebook reshapes the task log (one row per branch that missed a task) and inserts only rows newer than what the database already holds, so a repeat run does no harm. It does this for both brands, each in its own database.

**4. A weekly branch and manager scorecard.**
I defined a done-rate metric and a weighted performance score (task completion plus issue count), with ranks and grades from *Excellent* to *Terrible*. This gave leadership one comparable number per branch and per manager each week. [Method →](metrics.md)

**5. Training traceability.**
I merged ~70 SOP inspection exports into a single record of which employee is trained on which meal.

**6. One database behind every report.**
The weekly, quarterly and yearly Power BI reports all refresh from the same PostgreSQL tables, in a custom brand theme. The numbers agree across reports, and each period's report is just a refresh.

## Outcome

| | |
|---|---|
| **−85%** | quality issues across the company |
| **+15.8%** | task submission rate |
| **8 → 4 hours a day** | of reporting work, cutting the daily effort in half |
| **12 stakeholders** | 10 area managers, the Development Manager and the Operations Manager use the outputs |

- Area managers get the previous day's issues for their own branches, with photo evidence, every morning. Problems are fixed faster, and fewer of them come back.
- The weekly ranking made completion visible and comparable, which pushed task submissions up.
- Management has one consistent set of numbers across weekly, quarterly and yearly reports for both brands.

## What I'd do next

- Schedule the daily and weekly notebooks (cron or Airflow) and move credentials into environment variables.
- Move notebook transformations into dbt models, with tests.
- Host PostgreSQL in the cloud so Power BI refreshes without a local machine.

## Skills shown

Data pipeline design · ETL in Python · PostgreSQL · Excel/OOXML internals · data cleaning and standardisation · KPI design · Power BI dashboarding · stakeholder reporting
