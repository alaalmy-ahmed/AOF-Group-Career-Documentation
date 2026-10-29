# Reports & deliverables

## Power BI (refreshed from PostgreSQL)

All reports use a custom **Shawarma Classic theme** (colours and fonts set in a theme JSON) and brand-specific SVG backgrounds.

| Report | Refresh | Audience | Contents |
|---|---|---|---|
| Weekly Report | Every week, after the database load | Area managers | Which branches did better or worse: the last 7 days compared with the previous 7. Done vs. missed tasks, issues by branch and meal, branch and manager rankings |
| Monthly Report | End of month | Management | Each manager's performance. Branches are reassigned between managers every month, so the month is the unit managers are judged on |
| Quarterly report (e.g. Q2 Analysis) | End of quarter | Management | Branch performance over the quarter |
| Yearly Report | End of year | CEO | What was achieved over the year, for Shawarma Classic and Lubda |

All of them track the same two KPIs: **quality issues** (down is better) and **submission rate** (up is better).

Supporting reports built along the way: *Daily Reports*, *Missed and Done Tasks*, *Shawarma and Lubda Progress*, and branch issue deep dives for Lubda.

## Excel outputs

| File | Produced by | Cadence | Use |
|---|---|---|---|
| `<Manager>/<Branch>.xlsx` | New Data Processing | Daily | Each area manager's action list for the previous day, photos included |
| Branches Weekly Performance Summary | loading data to the database | Weekly | Branch rank, grade, done rate, issue count |
| Managers Weekly Performance Summary | loading data to the database | Weekly | Manager rank, grade, branches, issues per branch |
| Shawarma / Lubda Weekly Missing Rates | weekly tasks distribution | Weekly | Branches that missed deliveries, by manager |
| Trainees with Trained Meals | trainings by employees | As needed | Which employee is certified on which SOP |

*Screenshots: add sanitised images to `docs/img/` and link them here.*
