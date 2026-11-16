"""
Tests for weekly_dashboard.py that don't need Postgres: the wording, the
grade colours, and the page built from a tiny made-up week. test_database.py
builds the real dashboard from the sample and checks its numbers.
"""

import re
from datetime import date, timedelta

import pandas as pd
import pytest

from weekly_dashboard import STYLE, badge, kpi_change, meal_line, plural, rank_change, render

WEEK_END = date(2026, 1, 13)            # a Tuesday
LAST_WEEK = WEEK_END - timedelta(days=7)


@pytest.mark.parametrize("this, last, unit, lower_is_better, expected", [
    (95.1, 96.3, " pts", False, ("▼ 1.2 pts vs last week", "bad")),     # submission rate down: bad
    (96.3, 95.1, " pts", False, ("▲ 1.2 pts vs last week", "good")),
    (45, 8, "", True, ("▲ 37 vs last week", "bad")),                    # more issues: bad
    (5, 8, "", True, ("▼ 3 vs last week", "good")),
    (8, 8, "", True, ("same as last week", "same")),
    (95.1, None, " pts", False, ("no data for last week", "same")),     # the first week
])
def test_kpi_change(this, last, unit, lower_is_better, expected):
    assert kpi_change(this, last, unit, lower_is_better) == expected


@pytest.mark.parametrize("rank, last_rank, expected", [
    (2, 5, ("▲ 3", "good")),        # 5th last week, 2nd now: up 3 places
    (5, 2, ("▼ 3", "bad")),
    (4, 4, ("–", "same")),
    (4, None, ("new", "same")),     # wasn't ranked last week
])
def test_rank_change(rank, last_rank, expected):
    assert rank_change(rank, last_rank) == expected


def test_plural():
    assert plural(1, "issue", "issues") == "1 issue"
    assert plural(3, "issue", "issues") == "3 issues"
    assert plural(1.0, "issue", "issues") == "1 issue"          # an average that lands on 1
    assert plural(2.5, "issue", "issues") == "2.5 issues"


@pytest.mark.parametrize("missed, issues, expected", [
    (1, 2, "Arabi Sop: 2 issues · 1 missed"),
    (0, 1, "Arabi Sop: 1 issue"),
    (3, 0, "Arabi Sop: 3 missed"),
])
def test_meal_line(missed, issues, expected):
    assert meal_line("Arabi Sop", missed, issues) == expected


def test_grade_colours_go_from_green_to_red():
    assert badge("Excellent") == '<span class="grade excellent">Excellent</span>'
    assert badge(None) == ""                                        # a score of 0 has no grade
    assert ".grade.excellent { background: #2E7D32;" in STYLE       # dark green
    assert ".grade.good { background: #9CCC65;" in STYLE            # light green
    assert ".grade.fair { background: #FFD54F;" in STYLE            # yellow
    assert ".grade.bad { background: #FB8C00;" in STYLE             # orange
    assert ".grade.terrible { background: #C62828;" in STYLE        # red


def tiny_week(with_last_week=True):
    """The tables read_week() returns, for a made-up week: Manager B runs
    "Olaya & Co"; Manager A runs Malaz and Al Nakheel. Only Al Nakheel had
    problems: on Arabi Sop (2 issues, 1 missed) and French Fries (1 issue)."""
    last = (lambda rank: rank) if with_last_week else (lambda rank: None)
    kpis = [(WEEK_END, 95.0, 3)] + ([(LAST_WEEK, 90.0, 5)] if with_last_week else [])
    return {
        "kpis": pd.DataFrame(kpis, columns=["week_end", "submission_rate", "quality_issues"]),
        "managers": pd.DataFrame([
            (1, "Manager B", "Excellent", 1, 100.0, 0.0, 0, last(2)),
            (2, "Manager A", "Fair", 2, 77.5, 1.5, 3, last(1)),
        ], columns=["rank", "manager", "grade", "branches", "done_rate", "issues_per_branch", "issues", "last_rank"]),
        "branches": pd.DataFrame([
            (1, "B2", "Olaya & Co", "Manager B", "Excellent", 100.0, 0, last(2)),
            (2, "B3", "Malaz", "Manager A", "Good", 95.0, 0, last(3)),
            (3, "B1", "Al Nakheel - النخيل", "Manager A", "Terrible", 60.0, 3, last(1)),
        ], columns=["rank", "branch_code", "branch", "manager", "grade", "done_rate", "issues", "last_rank"]),
        "meals": pd.DataFrame([
            ("B1", "Arabi Sop", 1, 2),
            ("B1", "French Fries", 0, 1),
        ], columns=["branch_code", "meal", "missed", "issues"]),
    }


def page_of(week):
    return render(WEEK_END, week, built_on=date(2026, 1, 14))


def blocks(page, kind):
    """The <details class="manager"> (or "branch") parts of the page, by the name in each one's summary."""
    parts = page.split(f'<details class="{kind}">')[1:]
    return {re.search(r"<strong>(.*?)</strong>", part).group(1): part for part in parts}


def test_the_page_has_no_javascript():
    """The iPhone's attachment preview doesn't run JavaScript, so the page must not need any."""
    page = page_of(tiny_week())
    assert "<script" not in page.lower()
    assert not re.search(r"\son[a-z]+=", page)                      # no onclick= and the like either


def test_headline_numbers_and_changes():
    page = page_of(tiny_week())

    assert "Wed 7 Jan – Tue 13 Jan 2026" in page
    assert '<div class="value">95%</div>' in page
    assert '<div class="change good">▲ 5 pts vs last week</div>' in page        # 90 -> 95
    assert '<div class="value">3</div>' in page
    assert '<div class="change good">▼ 2 vs last week</div>' in page           # 5 -> 3 issues


def test_rankings_show_each_grade_in_its_colour():
    page = page_of(tiny_week())

    assert "Olaya &amp; Co" in page and "Olaya & Co" not in page     # names are escaped
    assert ('<span class="grade terrible">Terrible</span> Manager A · 60% submitted · 3 issues'
            in page)
    assert ('<span class="grade fair">Fair</span> 2 branches · 77.5% submitted · 3 issues (1.5 per branch)'
            in page)
    # Up one place: Malaz 3rd -> 2nd, Olaya and Manager B 2nd -> 1st
    assert page.count('<span class="good">▲ 1</span>') == 3
    assert '<span class="bad">▼ 2</span>' in page                   # Al Nakheel: 1st -> 3rd
    assert '<span class="bad">▼ 1</span>' in page                   # Manager A: 1st -> 2nd


def test_by_manager_holds_each_managers_branches_and_their_meals():
    page = page_of(tiny_week())
    managers, branches = blocks(page, "manager"), blocks(page, "branch")

    assert list(managers) == ["Manager B", "Manager A"]             # in rank order
    assert "Olaya &amp; Co" in managers["Manager B"] and "Malaz" not in managers["Manager B"]
    # Manager A's branches, in rank order
    assert managers["Manager A"].index("Malaz") < managers["Manager A"].index("Al Nakheel")

    nakheel = branches["Al Nakheel - النخيل"]
    assert "<li>Arabi Sop: 2 issues · 1 missed</li><li>French Fries: 1 issue</li>" in nakheel
    assert "No missed tasks or issues." in branches["Malaz"]
    assert "Arabi Sop" not in branches["Malaz"] and "Arabi Sop" not in branches["Olaya &amp; Co"]


def test_the_first_week_has_nothing_to_compare_with():
    page = page_of(tiny_week(with_last_week=False))

    assert page.count("no data for last week") == 2
    assert page.count('<span class="same">new</span>') == 5         # 3 branches, 2 managers
