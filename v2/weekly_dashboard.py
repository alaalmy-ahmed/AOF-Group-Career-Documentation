"""
Weekly: the weekly dashboard for the area managers, one HTML file (step 9).
It covers the same Wednesday-Tuesday week as weekly_ranking.py and reads the
same dbt views, so its numbers match the Excel ranking.

The page, top to bottom:
    the two KPIs for all branches, with the change since last week
    By manager, in rank order, each level inside the one above (tap to open):
        manager -> their branches -> the meals where a branch missed a task
        or had a quality issue -> the issue descriptions, and when each
        missed task was due
    Every manager and branch shows its grade in colour and the places it
    moved since last week.

It's plain HTML: no JavaScript, no pictures. So it opens anywhere, offline,
including the iPhone's attachment preview, which doesn't run JavaScript.
"Tap to open" is HTML's own <details> element, which needs no JavaScript.

Writes:
    output/Weekly Report 2026-10-14 to 2026-10-20.html

Usage:
    python v2/weekly_dashboard.py
    REPORT_DATE=2026-10-26 python v2/weekly_dashboard.py     # the sample's full week, Oct 14-20

Settings: PGDATABASE, OUTPUT_DIR, REPORT_DATE (see settings.py), and
PGHOST, PGPORT, PGUSER, PGPASSWORD, which psycopg2 reads by itself.
"""

import os
import sys
from datetime import date, timedelta
from html import escape

import pandas as pd
import psycopg2

from settings import DATABASE, OUTPUT_DIR, REPORT_DATE
from weekly_ranking import week_end_for

# Colours from the Power BI theme (Shawarma Classic Theme.json)
NAVY = "#0F1934"        # headings
ORANGE = "#E59925"      # accents
GREEN = "#536F18"       # better than last week
RED = "#F0512F"         # worse than last week
INK = "#070F25"         # text
MUTED = "#666666"       # secondary text
LINE = "#E3E3E3"        # lines between rows

# Each grade's colour, from best to worst, and the text colour that reads on it
GRADE_COLOURS = {
    "Excellent": ("#2E7D32", "#FFFFFF"),    # dark green
    "Good":      ("#9CCC65", INK),          # light green
    "Fair":      ("#FFD54F", INK),          # yellow
    "Bad":       ("#FB8C00", INK),          # orange
    "Terrible":  ("#C62828", "#FFFFFF"),    # red
}


# --------------------------------------------------------------------------------------------------------
# Read the week from the dbt views (schema "reporting")

KPIS_SQL = """
    SELECT week_end, submission_rate::float, quality_issues::int
      FROM reporting.weekly_kpis
     WHERE week_end IN (%(week_end)s, %(last_week)s)
"""

# Each row also gets last week's rank, to show who moved up or down
MANAGERS_SQL = """
    SELECT m.managers_rank::int AS rank, m.manager, m.completion_grade AS grade, m.branches::int,
           m.done_rate::float, m.number_of_issues::int AS issues,
           last.managers_rank::int AS last_rank
      FROM reporting.manager_weekly_ranking AS m
      LEFT JOIN reporting.manager_weekly_ranking AS last
        ON last.manager = m.manager AND last.week_end = %(last_week)s
     WHERE m.week_end = %(week_end)s
     ORDER BY m.managers_rank, m.manager
"""

BRANCHES_SQL = """
    SELECT b.branches_rank::int AS rank, b.branch_code, b.branch, b.manager, b.completion_grade AS grade,
           b.done_rate::float, b.number_of_issues::int AS issues,
           last.branches_rank::int AS last_rank
      FROM reporting.branch_weekly_ranking AS b
      LEFT JOIN reporting.branch_weekly_ranking AS last
        ON last.branch_code = b.branch_code AND last.week_end = %(last_week)s
     WHERE b.week_end = %(week_end)s
     ORDER BY b.branches_rank, b.branch
"""

# Only the meals with a problem: a missed task or a quality issue
MEALS_SQL = """
    SELECT branch_code, meal, tasks_missed::int AS missed, quality_issues::int AS issues
      FROM reporting.branch_meal_weekly
     WHERE week_end = %(week_end)s AND (tasks_missed > 0 OR quality_issues > 0)
     ORDER BY branch_code, quality_issues DESC, tasks_missed DESC, meal
"""

DESCRIPTIONS_SQL = """
    SELECT branch_code, meal, description, issues::int
      FROM reporting.issue_descriptions_weekly
     WHERE week_end = %(week_end)s
     ORDER BY branch_code, meal, issues DESC, description
"""

MISSED_SQL = """
    SELECT branch_code, meal, task_date, due_time
      FROM reporting.missed_tasks
     WHERE week_end = %(week_end)s
     ORDER BY branch_code, meal, task_date, due_time
"""


def read_week(week_end):
    """Everything the dashboard shows for the week ending on `week_end`, as
    tables: kpis, managers, branches, meals, descriptions, missed."""
    dates = {"week_end": week_end, "last_week": week_end - timedelta(days=7)}
    queries = {"kpis": KPIS_SQL, "managers": MANAGERS_SQL, "branches": BRANCHES_SQL, "meals": MEALS_SQL,
               "descriptions": DESCRIPTIONS_SQL, "missed": MISSED_SQL}
    conn = psycopg2.connect(dbname=DATABASE)
    try:
        with conn, conn.cursor() as cur:
            week = {}
            for name, sql in queries.items():
                cur.execute(sql, dates)
                columns = [column.name for column in cur.description]
                week[name] = pd.DataFrame(cur.fetchall(), columns=columns)
    finally:
        conn.close()
    return week


# --------------------------------------------------------------------------------------------------------
# Wording

def kpi_change(this, last, unit="", lower_is_better=False):
    """The line under a headline number, and whether it's good or bad news:
    ("▼ 1.2 pts vs last week", "bad")."""
    if last is None:
        return "no data for last week", "same"
    difference = round(this - last, 1)
    if difference == 0:
        return "same as last week", "same"
    arrow = "▲" if difference > 0 else "▼"
    better = difference < 0 if lower_is_better else difference > 0
    return f"{arrow} {abs(difference):g}{unit} vs last week", "good" if better else "bad"


def rank_change(rank, last_rank):
    """How many places a branch or manager moved since last week. Rank 1 is
    the best, so going from 5th to 2nd is up 3: ("▲ 3", "good")."""
    if pd.isna(last_rank):
        return "new", "same"            # not in last week's ranking
    moved = int(last_rank) - int(rank)
    if moved > 0:
        return f"▲ {moved}", "good"
    if moved < 0:
        return f"▼ {-moved}", "bad"
    return "–", "same"


def plural(number, one, many):
    """plural(1, "issue", "issues") -> "1 issue"; plural(3, ...) -> "3 issues"."""
    return f"{number:g} {one if number == 1 else many}"


def when(day, due_time):
    """'Thu 15, 4-8 pm': the day and due time of a missed task."""
    return f"{day:%a} {day.day}, {due_time}"


def meal_line(meal, issues, missed, missed_when):
    """'Arabi Sop: 2 issues · 1 missed (Thu 15, 4-8 pm)': only the parts
    that aren't zero, with when each missed task was due."""
    parts = []
    if issues:
        parts.append(plural(issues, "issue", "issues"))
    if missed:
        parts.append(f"{missed} missed ({'; '.join(missed_when)})")
    return f"{meal}: {' · '.join(parts)}"


def description_line(description, count):
    """'Wrong sauce quantity ×2', or just the description when it came up once."""
    return f"{description} ×{count}" if count > 1 else description


# --------------------------------------------------------------------------------------------------------
# The page's pieces. Names go through escape(), so a name with & or < shows as written.

def coloured(change):
    """("▲ 3", "good") -> the text in green (see STYLE)."""
    text, mood = change
    return f'<span class="{mood}">{text}</span>'


def badge(grade):
    """The grade as a coloured label: green for Excellent ... red for Terrible."""
    if not grade or pd.isna(grade):
        return ""                       # a score of 0 has no grade
    return f'<span class="grade {grade.lower()}">{grade}</span>'


def tile(label, value, change):
    return f"""
    <div class="tile">
      <div class="label">{label}</div>
      <div class="value">{value}</div>
      <div class="change {change[1]}">{change[0]}</div>
    </div>"""


def meals_of(branch_code, week):
    """The list under an opened branch: each meal with a problem, and under
    it the issue descriptions."""
    meals = week["meals"][week["meals"]["branch_code"] == branch_code]
    if meals.empty:
        return '<p class="sub">No missed tasks or issues.</p>'
    descriptions, missed = week["descriptions"], week["missed"]
    html = "<ul>"
    for meal in meals.itertuples():
        times = missed[(missed["branch_code"] == branch_code) & (missed["meal"] == meal.meal)]
        found = descriptions[(descriptions["branch_code"] == branch_code) & (descriptions["meal"] == meal.meal)]
        line = meal_line(meal.meal, meal.issues, meal.missed,
                         [when(t.task_date, t.due_time) for t in times.itertuples()])
        html += f"<li>{escape(line)}"
        if not found.empty:
            html += "<ul>" + "".join(f"<li>{escape(description_line(d.description, d.issues))}</li>"
                                     for d in found.itertuples()) + "</ul>"
        html += "</li>"
    return html + "</ul>"


def by_manager(week):
    """Manager -> their branches -> meals -> descriptions, each level inside
    the one above it (<details>: tap to open). Managers and branches are in
    rank order.

    Each name is inside <bdi>, so the Arabic half of a branch name stays in
    its place. Without it, the browser pulls the grade and the ▲ number that
    follow into the right-to-left text: "Al Malaz - 21 ▲ Excellent الملز"."""
    branches = week["branches"]
    html = ""
    for m in week["managers"].itertuples():
        branch_html = ""
        for b in branches[branches["manager"] == m.manager].itertuples():
            branch_html += (
                f'<details class="branch"><summary>#{b.rank} <strong><bdi>{escape(b.branch)}</bdi></strong> '
                f'{badge(b.grade)} {coloured(rank_change(b.rank, b.last_rank))}'
                f'<span class="sub">{b.done_rate:g}% submitted · {plural(b.issues, "issue", "issues")}</span>'
                f"</summary>{meals_of(b.branch_code, week)}</details>\n")
        html += (
            f'<details class="manager"><summary>{m.rank} <strong><bdi>{escape(m.manager)}</bdi></strong> '
            f'{badge(m.grade)} {coloured(rank_change(m.rank, m.last_rank))}'
            f'<span class="sub">{plural(m.branches, "branch", "branches")} · {m.done_rate:g}% submitted · '
            f'{plural(m.issues, "issue", "issues")}</span></summary>\n{branch_html}</details>\n')
    return html


def section(title, note, content):
    note = f'<p class="note">{note}</p>' if note else ""
    return f"<section><h2>{title}</h2>{note}{content}</section>"


GRADE_STYLE = "\n".join(f"  .grade.{grade.lower()} {{ background: {back}; color: {text}; }}"
                        for grade, (back, text) in GRADE_COLOURS.items())

STYLE = f"""
  :root {{ color-scheme: light; }}
  * {{ box-sizing: border-box; }}
  body {{ margin: 0; background: #F4F4F2; color: {INK};
         font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }}
  main {{ max-width: 760px; margin: 0 auto; padding: 0 16px 32px; }}
  header {{ background: {NAVY}; color: #FFFFFF; padding: 20px 16px; }}
  header div {{ max-width: 728px; margin: 0 auto; }}
  h1 {{ margin: 0; font-size: 22px; }}
  header p {{ margin: 4px 0 0; color: #D7DAE2; }}
  h2 {{ margin: 0 0 4px; font-size: 17px; color: {NAVY}; }}
  section {{ background: #FFFFFF; border-radius: 8px; padding: 16px; margin-top: 16px; }}
  .note {{ margin: 0 0 8px; color: {MUTED}; font-size: 13px; }}
  .tiles {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; background: none; padding: 0; }}
  .tile {{ background: #FFFFFF; border-radius: 8px; padding: 14px 16px; border-top: 4px solid {ORANGE}; }}
  .tile .label {{ color: {MUTED}; font-size: 13px; }}
  .tile .value {{ font-size: 32px; font-weight: 600; line-height: 1.2; }}
  .tile .change {{ font-size: 13px; }}
  .good {{ color: {GREEN}; }}
  .bad {{ color: {RED}; }}
  .same {{ color: {MUTED}; }}
  .grade {{ display: inline-block; padding: 0 8px; border-radius: 10px; font-size: 12px; font-weight: 600;
            line-height: 20px; white-space: nowrap; }}
{GRADE_STYLE}
  .sub {{ display: block; color: {MUTED}; font-size: 12px; margin-top: 2px; }}
  details {{ border-bottom: 1px solid {LINE}; }}
  summary {{ padding: 10px 0; cursor: pointer; }}
  details.branch {{ margin-left: 20px; }}
  details.branch:last-child {{ border-bottom: none; }}
  details ul {{ margin: 0 0 10px 20px; padding-left: 20px; }}
  details ul ul {{ margin: 2px 0 6px; padding-left: 18px; color: {MUTED}; font-size: 14px; }}
  details.branch > p.sub {{ margin: 0 0 10px 20px; }}
  footer {{ color: {MUTED}; font-size: 12px; margin-top: 16px; }}
"""


def render(week_end, week, built_on):
    """The whole dashboard as one HTML page."""
    week_start = week_end - timedelta(days=6)
    period = f"{week_start:%a} {week_start.day} {week_start:%b} – {week_end:%a} {week_end.day} {week_end:%b %Y}"

    # 1. The two KPIs, with the change since last week
    kpis = week["kpis"].set_index("week_end")
    this_week = kpis.loc[week_end]
    last_week = kpis.loc[week_end - timedelta(days=7)] if week_end - timedelta(days=7) in kpis.index else None
    tiles = (
        tile("Submission rate", f"{this_week['submission_rate']:g}%",
             kpi_change(this_week["submission_rate"],
                        None if last_week is None else last_week["submission_rate"], unit=" pts"))
        + tile("Quality issues", f"{int(this_week['quality_issues'])}",
               kpi_change(this_week["quality_issues"],
                          None if last_week is None else last_week["quality_issues"], lower_is_better=True))
    )

    # 2. Manager -> branches -> meals -> descriptions
    grades = " ".join(badge(grade) for grade in GRADE_COLOURS)
    hierarchy = section(
        "By manager",
        "1 is the best. Tap a manager, then a branch, to open it. ▲ ▼: places moved since last week. "
        f"#: the branch's rank among all branches.<br>Grades, best to worst: {grades}",
        by_manager(week))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weekly Report {week_start} to {week_end}</title>
<style>{STYLE}</style>
</head>
<body>
<header><div>
  <h1>Weekly report</h1>
  <p>{period} · compared with the week before</p>
</div></header>
<main>
<section class="tiles">{tiles}
</section>
{hierarchy}
<footer>AOF Group · built {built_on} by Ahmed Khaled, Data Analytics Engineer</footer>
</main>
</body>
</html>
"""


def main():
    week_end = week_end_for(REPORT_DATE)
    week_start = week_end - timedelta(days=6)
    week = read_week(week_end)
    if week["branches"].empty:
        print(f"No ranking for the week {week_start} to {week_end}. "
              f"Have load_workbook.py and build_models.py run?")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    path = os.path.join(OUTPUT_DIR, f"Weekly Report {week_start} to {week_end}.html")
    with open(path, "w", encoding="utf-8") as file:
        file.write(render(week_end, week, built_on=date.today()))

    kpis = week["kpis"].set_index("week_end").loc[week_end]
    print(f"Week {week_start} to {week_end}: submission rate {kpis['submission_rate']:g}%, "
          f"{int(kpis['quality_issues'])} quality issues, {len(week['branches'])} branches")
    print(f"Written to {path}")


if __name__ == "__main__":
    main()
