# Metrics

All weekly metrics use a rolling window of the **7 days ending on the report date**, which is yesterday in production. Today is left out because its data is still coming in.

## Done rate (per branch)

```
tasks_in_window = distinct (Date, Meal, Due time) combinations in the window
missed(branch)  = times the branch appears in "Branches Missed Tasks"
done_rate       = 100 − missed / tasks_in_window × 100
```

Branches that never missed a task are filled in as **100%**, so every branch shows up in the ranking, not only the ones with problems.

**Manager done rate** = mean done rate of that manager's branches.

## Performance score

Each component is normalised to its maximum across the group, so the two are on the same scale.

| Level | Formula |
|---|---|
| Branch | `0.90 × done_rate_norm + 0.10 × (1 − issues_norm)` |
| Manager | `0.85 × done_rate_norm + 0.15 × (1 − issues_per_branch_norm)` |

Task completion carries most of the weight. Issues count for a little more at manager level, because managers are responsible for fixing them.

## Rank and grade

- **Rank**: 1 = best; ties share a rank (`method='min'`).
- **Grade** by score:

| Score | Grade |
|---|---|
| > 0.95 | Excellent |
| 0.90 – 0.95 | Good |
| 0.80 – 0.90 | Fair |
| 0.70 – 0.80 | Bad |
| ≤ 0.70 | Terrible |

## Two implementations

The ranking exists twice, with the same method:

| | Where | Used for |
|---|---|---|
| pandas | [notebook 02](../notebooks/02_weekly_load_and_rankings.ipynb), Step 3 | The weekly Excel summaries |
| SQL | [`sql/ranking.sql`](../sql/ranking.sql) | `training.branch_weekly_ranking(date)` and `training.manager_weekly_ranking(date)`, plus the views `v_branch_weekly_ranking` / `v_manager_weekly_ranking` (week ending yesterday) for Power BI |

```sql
SELECT * FROM training.manager_weekly_ranking(DATE '2026-10-26');
```

The SQL version is built from CTEs (window, task count, misses, issues, per-branch rates) and window functions: `MAX() OVER ()` for normalising and `RANK() OVER (ORDER BY score DESC)` for ranking.

**Tested against pandas** on the sample data for 8 report dates (Oct 19–26). Branch rankings match row for row. Manager rankings differ only where an average lands exactly on a half:

| Manager average | pandas | SQL |
|---|---|---|
| 97.85 | 97.8 | 97.9 |
| 0.25 | 0.2 | 0.3 |

pandas rounds binary floats (97.85 is stored as 97.8499…) and rounds exact halves to the nearest even digit. Postgres `numeric` rounds exactly, half away from zero, which is what a reader expects. When the SQL was switched to float rounding as a check, every row matched on all 8 dates, so rounding is the only difference. It can occasionally swap two managers whose scores are almost tied.
