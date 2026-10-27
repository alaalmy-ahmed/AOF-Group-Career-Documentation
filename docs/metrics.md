# Metrics

All weekly metrics use a rolling window of the **7 days before today**. Today is left out because its data is still coming in.

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
