"""
Tests for the ranking math in weekly_ranking.py, on a tiny week you can work
out on paper. No database: the tests give the functions the counts directly.

The week has 10 tasks and 4 branches:

    Branch  Manager  missed  issues   done rate
    A       X        0       0        100 - 0/10*100 = 100
    B       X        1       2        100 - 1/10*100 =  90
    C       Y        2       0        100 - 2/10*100 =  80
    D       Y        0       4        100

Branch score = 0.90 * done rate / 100 + 0.10 * (1 - issues / 4):

    A  0.90 * 1.0 + 0.10 * 1.0 = 1.00   rank 1, Excellent
    D  0.90 * 1.0 + 0.10 * 0.0 = 0.90   rank 2, Fair (0.90 itself is in 0.80-0.90)
    B  0.90 * 0.9 + 0.10 * 0.5 = 0.86   rank 3, Fair
    C  0.90 * 0.8 + 0.10 * 1.0 = 0.82   rank 4, Fair
"""

import pandas as pd

from weekly_ranking import rank_branches, rank_managers, share_of_max

TASKS = 10


def tiny_week():
    return pd.DataFrame({
        "Branch":           ["A", "B", "C", "D"],
        "Manager":          ["X", "X", "Y", "Y"],
        "missed":           [0,   1,   2,   0],
        "Number of Issues": [0,   2,   0,   4],
    })


def test_branch_done_rates_ranks_and_grades():
    summary = rank_branches(tiny_week(), TASKS).set_index("Branch")
    assert summary["Done Rate"].to_dict() == {"A": 100.0, "B": 90.0, "C": 80.0, "D": 100.0}
    assert summary["Branches Rank"].to_dict() == {"A": 1, "D": 2, "B": 3, "C": 4}
    assert summary["Completion Grade"].astype(str).to_dict() == {"A": "Excellent", "D": "Fair", "B": "Fair", "C": "Fair"}


def test_branches_are_sorted_best_first():
    assert list(rank_branches(tiny_week(), TASKS)["Branch"]) == ["A", "D", "B", "C"]


def test_manager_summary():
    # X: done rate (100 + 90) / 2 = 95.0, issues per branch (0 + 2) / 2 = 1.0, 2 issues in all
    # Y: done rate (80 + 100) / 2 = 90.0, issues per branch (0 + 4) / 2 = 2.0, 4 issues in all
    # X scores 0.85 * 1 + 0.15 * (1 - 0.5) = 0.925; Y scores 0.85 * 90/95 + 0.15 * 0 = 0.805
    summary = rank_managers(rank_branches(tiny_week(), TASKS)).set_index("Manager")
    assert summary.loc["X"].to_dict() == {"Done Rate": 95.0, "Issues per Branch": 1.0, "Number of Issues": 2, "Managers Rank": 1}
    assert summary.loc["Y"].to_dict() == {"Done Rate": 90.0, "Issues per Branch": 2.0, "Number of Issues": 4, "Managers Rank": 2}


def test_ties_share_a_rank():
    week = tiny_week()
    week.loc[1, ["missed", "Number of Issues"]] = [0, 0]   # B now matches A exactly
    ranks = rank_branches(week, TASKS).set_index("Branch")["Branches Rank"]
    assert ranks["A"] == ranks["B"] == 1
    assert ranks["D"] == 3                                 # the next rank skips 2


def test_a_week_with_no_issues_still_ranks():
    week = tiny_week()
    week["Number of Issues"] = 0
    summary = rank_branches(week, TASKS).set_index("Branch")
    assert summary["Branches Rank"].to_dict() == {"A": 1, "D": 1, "B": 3, "C": 4}


def test_share_of_max():
    assert list(share_of_max(pd.Series([0, 2, 4]))) == [0.0, 0.5, 1.0]
    assert list(share_of_max(pd.Series([0, 0]))) == [0, 0]     # no dividing by zero
