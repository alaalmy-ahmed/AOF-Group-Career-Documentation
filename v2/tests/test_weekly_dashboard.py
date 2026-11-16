"""
Tests for weekly_dashboard.py that don't need Postgres: the wording, the
grade colours, and the page built from a tiny made-up week. test_database.py
builds the real dashboard from the sample and checks its numbers.
"""

import re
from datetime import date, timedelta

import pandas as pd
import pytest

from weekly_dashboard import (STYLE, badge, description_line, kpi_change, meal_line, plural, rank_change,
                              render, when)

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


@pytest.mark.parametrize("issues, missed, missed_when, expected", [
    (2, 1, ["Thu 15, 4-8 pm"], "Arabi Sop: 2 issues · 1 missed (Thu 15, 4-8 pm)"),
    (1, 0, [], "Arabi Sop: 1 issue"),
    (0, 2, ["Wed 14, 12-4 pm", "Sat 17, 4-8 pm"], "Arabi Sop: 2 missed (Wed 14, 12-4 pm; Sat 17, 4-8 pm)"),
])
def test_meal_line(issues, missed, missed_when, expected):
    assert meal_line("Arabi Sop", issues, missed, missed_when) == expected


def test_when_and_description_line():
    assert when(date(2026, 10, 15), "4-8 pm") == "Thu 15, 4-8 pm"
    assert description_line("Wrong sauce quantity", 2) == "Wrong sauce quantity ×2"
    assert description_line("Bread not heated", 1) == "Bread not heated"


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
    problems: on Arabi Sop, "Wrong sauce quantity" twice and a task missed on
    Thu Jan 8 at 4-8 pm; on French Fries, "Bread not heated" once and a task
    missed on Fri Jan 9 at 12-4 pm."""
    last = (lambda rank: rank) if with_last_week else (lambda rank: None)
    kpis = [(WEEK_END, 95.0, 3)] + ([(LAST_WEEK, 90.0, 5)] if with_last_week else [])
    return {
        "kpis": pd.DataFrame(kpis, columns=["week_end", "submission_rate", "quality_issues"]),
        "managers": pd.DataFrame([
            (1, "Manager B", "Excellent", 1, 100.0, 0, last(2)),
            (2, "Manager A", "Fair", 2, 77.5, 3, last(1)),
        ], columns=["rank", "manager", "grade", "branches", "done_rate", "issues", "last_rank"]),
        "branches": pd.DataFrame([
            (1, "B2", "Olaya & Co", "Manager B", "Excellent", 100.0, 0, last(2)),
            (2, "B3", "Malaz", "Manager A", "Good", 95.0, 0, last(3)),
            (3, "B1", "Al Nakheel - النخيل", "Manager A", "Terrible", 60.0, 3, last(1)),
        ], columns=["rank", "branch_code", "branch", "manager", "grade", "done_rate", "issues", "last_rank"]),
        "meals": pd.DataFrame([
            ("B1", "Arabi Sop", 1, 2),
            ("B1", "French Fries", 1, 1),
        ], columns=["branch_code", "meal", "missed", "issues"]),
        "descriptions": pd.DataFrame([
            ("B1", "Arabi Sop", "Wrong sauce quantity", 2),
            ("B1", "French Fries", "Bread not heated", 1),
        ], columns=["branch_code", "meal", "description", "issues"]),
        "missed": pd.DataFrame([
            ("B1", "Arabi Sop", date(2026, 1, 8), "4-8 pm"),
            ("B1", "French Fries", date(2026, 1, 9), "12-4 pm"),
        ], columns=["branch_code", "meal", "task_date", "due_time"]),
    }


def page_of(week):
    return render(WEEK_END, week, built_on=date(2026, 1, 14))


def blocks(page, kind):
    """The <details class="manager"> (or "branch") parts of the page, by the name in each one's summary."""
    parts = page.split(f'<details class="{kind}">')[1:]
    return {re.search(r"<strong><bdi>(.*?)</bdi></strong>", part).group(1): part for part in parts}


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
    assert "<table" not in page                                     # no ranking tables any more


def test_managers_and_branches_in_rank_order_with_grade_and_change():
    page = page_of(tiny_week())
    managers, branches = blocks(page, "manager"), blocks(page, "branch")

    assert list(managers) == ["Manager B", "Manager A"]
    assert "Olaya &amp; Co" in managers["Manager B"] and "Malaz" not in managers["Manager B"]
    assert managers["Manager A"].index("Malaz") < managers["Manager A"].index("Al Nakheel")
    assert "Olaya &amp; Co" in branches and "Olaya & Co" not in page        # names are escaped

    # The grade in its colour, then the places moved since last week
    assert '<span class="grade fair">Fair</span> <span class="bad">▼ 1</span>' in managers["Manager A"]
    assert ('<span class="grade terrible">Terrible</span> <span class="bad">▼ 2</span>'
            in branches["Al Nakheel - النخيل"])                     # 1st -> 3rd
    assert '<span class="grade good">Good</span> <span class="good">▲ 1</span>' in branches["Malaz"]


def test_arabic_names_keep_their_place():
    """Each name is in <bdi>, so what follows it (grade, ▲ 2) isn't pulled into the Arabic text."""
    page = page_of(tiny_week())
    assert "<strong><bdi>Al Nakheel - النخيل</bdi></strong>" in page


def test_each_branch_lists_its_meals_then_descriptions():
    branches = blocks(page_of(tiny_week()), "branch")

    assert ("<ul><li>Arabi Sop: 2 issues · 1 missed (Thu 8, 4-8 pm)<ul><li>Wrong sauce quantity ×2</li></ul></li>"
            "<li>French Fries: 1 issue · 1 missed (Fri 9, 12-4 pm)<ul><li>Bread not heated</li></ul></li></ul>"
            ) in branches["Al Nakheel - النخيل"]
    assert "No missed tasks or issues." in branches["Malaz"]
    assert "Arabi Sop" not in branches["Malaz"] and "Arabi Sop" not in branches["Olaya &amp; Co"]


def test_the_first_week_has_nothing_to_compare_with():
    page = page_of(tiny_week(with_last_week=False))

    assert page.count("no data for last week") == 2
    assert page.count('<span class="same">new</span>') == 5         # 3 branches, 2 managers
