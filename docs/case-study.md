# Case study: building an operations data system from screenshots to Power BI

**Company:** AOF Group (Shawarma Classic & Lubda), Saudi Arabia
**Role:** Data Analytics Engineer · **Period:** February 2024 – present
**Stack:** Excel (data validation, lookups), Python (pandas, openpyxl, psycopg2), PostgreSQL, Power BI

---

## The starting point

AOF Group runs two restaurant brands. **Shawarma Classic** has ~37 branches across Riyadh, Jeddah and the Eastern Province, run by 10 area managers. **Lubda** launched about a year and a half after I joined: 2 branches with 2 supervisors, overseen by one of the Shawarma Classic area managers.

At Shawarma Classic, branch checks and scheduled tasks are recorded in Zenput (now Crunchtime OPS Execution).

When I joined, Shawarma Classic had no data system:

- A data-entry employee took **screenshots** of the Zenput results and pasted them into a Word file.
- From that, they built **one Word file per area manager** by hand.
- Managers acted on those files branch by branch.

Nothing was stored as data. There was no history, no way to count issues by type or branch, and nothing to compare one week, manager or branch with another.

## What I built, step by step

**1. A structured workbook in place of screenshots.**
I designed an Excel workbook (`07-2024.xlsx`) that holds tasks and quality issues as proper tables: one row per issue, one row per scheduled task. To keep the data clean at the point of entry:

- **Data validation on every column**, so the data-entry employee can only pick allowed values.
- **Lookups** for branch codes and managers, so they're filled in, not typed.
- **A fixed list of issue descriptions**, so issues can be grouped by type and the most frequent problems found.

**2. Automated daily distribution.**
I replaced the hand-made Word files with a notebook that runs every morning. It takes yesterday's issues and creates a folder per area manager (10 in total), with one formatted Excel file per branch. Excel stores in-cell photos as rich values that standard libraries drop, so I parsed the workbook's internal XML to map each photo back to its row and re-embedded it in the right file.

**3. A PostgreSQL database when Excel wasn't enough.**
As the data grew, a workbook could no longer hold the history. I designed the tables in PostgreSQL and wrote the weekly load notebook. It reshapes the task log (one row per branch that missed a task) and inserts only rows newer than what the database already holds. Each brand has its own database.

**4. Defining the KPIs.**
Nobody had set targets for the operation. From the data, I identified the two numbers that matter:

- **Quality issues**: should go down.
- **Submission rate** (share of scheduled tasks submitted): should go up.

**5. Power BI reports, each for a specific audience.**
All reports refresh from PostgreSQL:

| Report | Question it answers | For |
|---|---|---|
| Weekly | Which branches did better or worse, this 7 days compared with the previous 7? | Area managers |
| Monthly | How did each manager perform? Upper management reassigns branches between managers every month, so this is the period their performance is judged on. | Management |
| Quarterly | How is each branch performing over the quarter? | Management |
| Yearly | What did we achieve this year? | CEO |

**6. A weekly branch and manager scorecard.**
A done rate and a weighted performance score (task completion plus issue count), with ranks and grades from *Excellent* to *Terrible*. [Method →](metrics.md)

**7. Training traceability.**
I merged ~70 SOP inspection exports into a single record of which employee is trained on which meal.

**8. Lubda, built in from day one.**
I was there when Lubda launched, so it never went through screenshots and Word files. I set up its workbook (`Lubda.xlsx`), its own PostgreSQL database and its reports from the start, adapted to its own columns (in Arabic) and process.

## Outcome (Shawarma Classic)

| | |
|---|---|
| **−85%** | quality issues across all branches |
| **+15.8%** | submission rate |
| **8 → 4 hours a day** | of reporting work |
| **12 stakeholders** | 10 area managers, the Development Manager and the Operations Manager use the outputs |

## What I'd do next

- Schedule the daily and weekly notebooks, with logging and failure alerts.
- Add keys and constraints to the database, and make the load safe to re-run after a failure.
- Move transformations into dbt models, with tests.
- Replace the Excel intake as volume grows: the Lubda workbook is already over 2 GB.

## Skills shown

Data modeling · data validation at entry · ETL in Python · PostgreSQL · Excel/OOXML internals · KPI design · Power BI dashboarding · stakeholder reporting
