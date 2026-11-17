"""
Tests for period_reports.py (step 10) and the fake history behind its sample,
without Postgres: the periods, the wording, and pages built from a tiny
made-up period. test_database.py builds the real reports from the fake
history and the sample, and checks their numbers.
"""

from datetime import date

import pandas as pd
import pytest
from plotly.offline import get_plotlyjs

from fake_history import make_history
from period_reports import (add_months, file_name, label, period_end, period_start, periods_due, previous_start,
                            ranking_figure, rate_floor, render, trend_figures)
from validate_workbook import find_problems, read_lists


# --------------------------------------------------------------------------------------------------------
# Periods

@pytest.mark.parametrize("day, months, expected", [
    (date(2026, 10, 26), 1, date(2026, 11, 1)),
    (date(2026, 11, 3), 2, date(2027, 1, 1)),          # into the next year
    (date(2026, 1, 15), -1, date(2025, 12, 1)),         # back into the year before
    (date(2026, 10, 1), -12, date(2025, 10, 1)),
])
def test_add_months(day, months, expected):
    assert add_months(day, months) == expected


@pytest.mark.parametrize("period, day, start, end, previous", [
    ("month", date(2026, 10, 26), date(2026, 10, 1), date(2026, 10, 31), date(2026, 9, 1)),
    ("month", date(2026, 2, 10), date(2026, 2, 1), date(2026, 2, 28), date(2026, 1, 1)),
    ("quarter", date(2026, 9, 30), date(2026, 7, 1), date(2026, 9, 30), date(2026, 4, 1)),
    ("quarter", date(2026, 1, 1), date(2026, 1, 1), date(2026, 3, 31), date(2025, 10, 1)),
    ("year", date(2026, 10, 26), date(2026, 1, 1), date(2026, 12, 31), date(2025, 1, 1)),
])
def test_period_start_end_and_previous(period, day, start, end, previous):
    assert period_start(period, day) == start
    assert period_end(period, start) == end
    assert previous_start(period, start) == previous


@pytest.mark.parametrize("day, due", [
    (date(2026, 10, 31), ["month"]),                     # the Nov 1 run
    (date(2026, 9, 30), ["month", "quarter"]),           # the Oct 1 run: September and Q3
    (date(2026, 12, 31), ["month", "quarter", "year"]),  # the Jan 1 run: all three
    (date(2026, 10, 26), ["month"]),                     # a run by hand mid-month: the month so far
])
def test_which_reports_are_due(day, due):
    assert periods_due(day) == due


def test_labels_and_file_names():
    assert label("month", date(2026, 10, 1)) == "October 2026"
    assert label("quarter", date(2026, 7, 1)) == "Q3 2026"
    assert label("year", date(2026, 1, 1)) == "2026"
    assert file_name("month", date(2026, 10, 1)) == "Monthly Report 2026-10.html"
    assert file_name("quarter", date(2026, 7, 1)) == "Quarterly Report 2026-Q3.html"
    assert file_name("year", date(2026, 1, 1)) == "Yearly Report 2026.html"


@pytest.mark.parametrize("rates, floor", [([95.2, 96.4], 90), ([92.4, 95.1], 90), ([97.9], 95), ([3.0], 0)])
def test_the_rate_scale_starts_just_below_the_lowest_point(rates, floor):
    assert rate_floor(rates) == floor


def test_both_trend_charts_are_lines():
    trend = pd.DataFrame({"point": [date(2026, 10, 6), date(2026, 10, 13)],
                          "submission_rate": [95.2, 96.4], "quality_issues": [44, 37]})
    rate, issues = trend_figures("month", trend)

    for fig in (rate, issues):
        assert fig.data[0].type == "scatter" and fig.data[0].mode == "lines+markers"
    assert rate.layout.yaxis.range == (90, 100)                            # 5 below the lowest, minus 2
    assert issues.layout.yaxis.rangemode == "tozero"                       # counts start at 0
    assert list(rate.data[0].x) == ["6 Oct", "13 Oct"]


def test_the_ranking_score_runs_from_0_to_100_percent():
    rows = pd.DataFrame({"rank": [1, 2], "manager": ["A", "B"], "grade": ["Good", "Fair"],
                         "done_rate": [95.0, 90.0], "issues": [2, 5], "score": [0.9325, 0.85]})
    fig = ranking_figure(rows, "manager")

    assert list(fig.data[0].x) == pytest.approx([93.25, 85.0])
    assert fig.layout.xaxis.range == (0, 100) and fig.layout.xaxis.ticksuffix == "%"
    assert [line.x0 for line in fig.layout.shapes] == [70, 80, 90, 95]     # where Bad, Fair, Good, Excellent start
    assert list(fig.data[0].marker.color) == ["#9CCC65", "#FFD54F"]        # light green, yellow


# --------------------------------------------------------------------------------------------------------
# Pages

def tiny_period(period, start, with_previous=True):
    """The tables read_period() returns, for a made-up period: Manager A runs
    Malaz and Olaya (Olaya: 2 issues and 1 missed task on Arabi Sop)."""
    previous = previous_start(period, start)
    kpis = [(start, 95.0, 2)] + ([(previous, 90.0, 5)] if with_previous else [])
    return {
        "kpis": pd.DataFrame(kpis, columns=["period_start", "submission_rate", "quality_issues"]),
        "trend": pd.DataFrame({"point": [start], "submission_rate": [95.0], "quality_issues": [2]}),
        "managers": pd.DataFrame([
            (1, "Manager A", "Good", 2, 3 if period != "month" else 2, 95.0, 2, 0.93, 2 if with_previous else None),
        ], columns=["rank", "manager", "grade", "branches", "branch_months", "done_rate", "issues", "score", "last_rank"]),
        "branches": pd.DataFrame([
            (1, "B1", "Malaz", "Manager A", "Excellent", 100.0, 0, 1.0, 1 if with_previous else None),
            (2, "B2", "Olaya", "Manager A", "Fair", 90.0, 2, 0.85, 1 if with_previous else None),
        ], columns=["rank", "branch_code", "branch", "manager", "grade", "done_rate", "issues", "score", "last_rank"]),
        "meals": pd.DataFrame([("B2", "Arabi Sop", 1, 2)], columns=["branch_code", "meal", "missed", "issues"]),
        "descriptions": pd.DataFrame([("B2", "Arabi Sop", "Wrong sauce quantity", 2)],
                                     columns=["branch_code", "meal", "description", "issues"]),
        "by_meal": pd.DataFrame([("Arabi Sop", 2, 1)], columns=["meal", "issues", "missed"]),
        "missed": pd.DataFrame(columns=["branch_code", "meal", "task_date", "due_time"]),
    }


def page(period, start, last_day=None, **kwargs):
    last_day = last_day or period_end(period, start)
    return render(period, start, tiny_period(period, start, **kwargs), last_day, built_on=date(2026, 11, 1))


def test_monthly_is_by_manager():
    html = page("month", date(2026, 10, 1))

    assert "<h1>Monthly report</h1>" in html
    assert "October 2026 · compared with September 2026" in html
    assert '<div class="change good">▲ 5 pts vs last month</div>' in html
    assert "<h2>By manager</h2>" in html and '<details class="manager">' in html
    assert "<h2>Manager ranking</h2>" in html and "<h2>Branch ranking</h2>" not in html
    assert "<h2>By meal</h2>" not in html                                  # yearly only


def test_quarterly_and_yearly_are_by_branch():
    quarter = page("quarter", date(2026, 7, 1))
    assert "Q3 2026 · compared with Q2 2026" in quarter
    assert "vs last quarter" in quarter
    assert '<details class="manager">' not in quarter                     # managers aren't tap-to-open
    assert "<h2>Managers</h2>" in quarter and "<h2>Branches</h2>" in quarter
    assert "ran 2 branches (3 branch-months)" in quarter
    assert "<h2>Branch ranking</h2>" in quarter and "<h2>By meal</h2>" not in quarter

    year = page("year", date(2026, 1, 1))
    assert "<h1>Yearly report</h1>" in year and "<h2>By meal</h2>" in year


def test_meals_show_missed_counts_and_descriptions_but_no_times():
    html = page("quarter", date(2026, 7, 1))
    assert "<li>Arabi Sop: 2 issues · 1 missed<ul><li>Wrong sauce quantity ×2</li></ul></li>" in html


def test_a_period_not_over_yet_says_so():
    assert "October 2026 · so far, to 26 Oct" in page("month", date(2026, 10, 1), last_day=date(2026, 10, 26))
    assert "so far" not in page("month", date(2026, 10, 1))


def test_the_first_period_has_nothing_to_compare_with():
    html = page("year", date(2026, 1, 1), with_previous=False)
    assert html.count("no data for last year") == 2
    assert html.count('<span class="same">new</span>') == 3               # 1 manager, 2 branches


def test_plotly_is_inside_the_file_once():
    """The charts work without the internet: Plotly's program is in the page, once."""
    html = page("year", date(2026, 1, 1))
    assert html.count(get_plotlyjs()) == 1
    assert "<script src=" not in html                                      # nothing loaded from elsewhere
    assert html.count('class="plotly-graph-div"') == 4                    # rate, issues, ranking, by meal


# --------------------------------------------------------------------------------------------------------
# The fake history (sample_data/fake_history.py)

@pytest.fixture(scope="module")
def history():
    lists = read_lists()
    tasks, issues, managers = make_history(lists)
    return lists, tasks, issues, managers


def test_the_fake_history_passes_every_workbook_check(history):
    lists, tasks, issues, managers = history
    sheets = {**lists, "Source Data": tasks, "Reviewing Reports": issues,
              "Managers": pd.concat([managers, lists["Managers"]], ignore_index=True)}
    assert find_problems(sheets) == []
    assert (tasks["Date"].min(), tasks["Date"].max()) == (date(2026, 7, 1), date(2026, 10, 12))


def test_the_fake_history_rotates_branches_every_month(history):
    lists, _, _, managers = history
    months = pd.concat([managers, lists["Managers"]])
    manager_of = {month: dict(zip(rows["Branch"], rows["Manager"])) for month, rows in months.groupby("Month")}
    order = sorted(manager_of)
    assert order == [date(2026, 7, 1), date(2026, 8, 1), date(2026, 9, 1), date(2026, 10, 1)]
    for month, next_month in zip(order, order[1:]):
        moved = [branch for branch in manager_of[month] if manager_of[month][branch] != manager_of[next_month][branch]]
        assert len(moved) == 10                                            # one branch per manager
    # Every manager keeps the same number of branches each month
    sizes = months.groupby(["Month", "Manager"]).size().unstack()
    assert (sizes.nunique() == 1).all()


def test_the_fake_history_gets_better_month_by_month(history):
    _, _, issues, _ = history
    per_month = issues.groupby(pd.to_datetime(issues["Date"]).dt.month).size()
    assert per_month[7] > per_month[8] > per_month[9]
