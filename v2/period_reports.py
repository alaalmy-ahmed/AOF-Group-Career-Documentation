"""
Monthly, quarterly and yearly: the reports for management, one HTML file each
(step 10). They read the dbt views, like the weekly dashboard, and reuse its
pieces: the grade colours, the ▲ ▼ changes and the tap-to-open lists.

Each page, top to bottom:
    the two KPIs for all branches, with the change since the period before
    the KPI trend: week by week (monthly), month by month (quarterly, yearly)
    the ranking as dots, coloured by grade, the score from 0 to 100%: managers (monthly),
        branches (quarterly, yearly)
    yearly only: issues and missed tasks for each meal, all branches together
    monthly: manager -> their branches -> meals -> issue descriptions
    quarterly, yearly: the managers, then branch -> meals -> issue descriptions
        (branches move between managers every month, so a quarter or a
        year has no single manager per branch)

Management reads these on computers, so the charts use Plotly: hover over
them for the exact numbers. Plotly's chart program is inside each file
(about 5 MB), so a file opens without the internet.

Writes, for the period that REPORT_DATE is in:
    output/Monthly Report 2026-10.html        always
    output/Quarterly Report 2026-Q3.html      when REPORT_DATE is a quarter's last day
    output/Yearly Report 2026.html            when REPORT_DATE is Dec 31
The monthly Airflow run (on the 1st, REPORT_DATE = the day before) gets the
quarter's on Jan 1, Apr 1, Jul 1 and Oct 1, and the year's on Jan 1.

Usage:
    python v2/period_reports.py                       # the reports due for REPORT_DATE
    python v2/period_reports.py quarter year          # these ones, so far, whatever the date
    REPORT_DATE=2026-09-30 python v2/period_reports.py    # the sample: September and Q3

Settings: PGDATABASE, OUTPUT_DIR, REPORT_DATE (see settings.py), and
PGHOST, PGPORT, PGUSER, PGPASSWORD, which psycopg2 reads by itself.
"""

import math
import os
import sys
from datetime import date, timedelta
from html import escape

import pandas as pd
import plotly.graph_objects as go
import psycopg2
from plotly.offline import get_plotlyjs

from settings import DATABASE, OUTPUT_DIR, REPORT_DATE
from weekly_dashboard import (GRADE_COLOURS, INK, MUTED, NAVY, ORANGE, STYLE, badge, by_manager, coloured, footer,
                              kpi_change, meals_of, plural, rank_change, section, tile)

PERIODS = ("month", "quarter", "year")
MONTHS_IN = {"month": 1, "quarter": 3, "year": 12}
NAME = {"month": "Monthly", "quarter": "Quarterly", "year": "Yearly"}


# --------------------------------------------------------------------------------------------------------
# Periods

def add_months(day, months):
    """The first day of the month `months` after `day`'s month (negative: before)."""
    count = day.year * 12 + day.month - 1 + months
    return date(count // 12, count % 12 + 1, 1)


def period_start(period, day):
    """The first day of the month, quarter or year `day` is in."""
    if period == "month":
        return day.replace(day=1)
    if period == "quarter":
        return date(day.year, 3 * ((day.month - 1) // 3) + 1, 1)
    return date(day.year, 1, 1)


def period_end(period, start):
    return add_months(start, MONTHS_IN[period]) - timedelta(days=1)


def previous_start(period, start):
    return add_months(start, -MONTHS_IN[period])


def periods_due(day):
    """The reports a run for `day` writes: the month always, the quarter on a
    quarter's last day, the year on Dec 31."""
    return [period for period in PERIODS
            if period == "month" or day == period_end(period, period_start(period, day))]


def label(period, start):
    """'October 2026', 'Q3 2026', '2026'."""
    if period == "month":
        return f"{start:%B %Y}"
    if period == "quarter":
        return f"Q{(start.month - 1) // 3 + 1} {start.year}"
    return f"{start.year}"


def file_name(period, start):
    """'Monthly Report 2026-10.html', 'Quarterly Report 2026-Q3.html', 'Yearly Report 2026.html'."""
    if period == "month":
        when = f"{start:%Y-%m}"
    elif period == "quarter":
        when = f"{start.year}-Q{(start.month - 1) // 3 + 1}"
    else:
        when = f"{start.year}"
    return f"{NAME[period]} Report {when}.html"


# --------------------------------------------------------------------------------------------------------
# Read a period from the dbt views (schema "reporting")

KPIS_SQL = """
    SELECT period_start, submission_rate::float, quality_issues::int
      FROM reporting.period_kpis
     WHERE period = %(period)s AND period_start IN (%(start)s, %(previous)s)
"""

# The monthly trend is the weeks that end in the month, with the weekly
# reports' own numbers; the quarterly and yearly trends are their months.
WEEKS_SQL = """
    SELECT week_end AS point, submission_rate::float, quality_issues::int
      FROM reporting.weekly_kpis
     WHERE week_end BETWEEN %(start)s AND %(end)s
     ORDER BY week_end
"""

MONTHS_SQL = """
    SELECT period_start AS point, submission_rate::float, quality_issues::int
      FROM reporting.period_kpis
     WHERE period = 'month' AND period_start BETWEEN %(start)s AND %(end)s
     ORDER BY period_start
"""

# Each row also gets its rank in the period before, to show who moved
MANAGERS_SQL = """
    SELECT m.managers_rank::int AS rank, m.manager, m.completion_grade AS grade, m.branches::int,
           m.branch_months::int, m.done_rate::float, m.number_of_issues::int AS issues, m.score::float,
           last.managers_rank::int AS last_rank
      FROM reporting.manager_period_ranking AS m
      LEFT JOIN reporting.manager_period_ranking AS last
        ON last.manager = m.manager AND last.period = m.period AND last.period_start = %(previous)s
     WHERE m.period = %(period)s AND m.period_start = %(start)s
     ORDER BY m.managers_rank, m.manager
"""

BRANCHES_SQL = """
    SELECT b.branches_rank::int AS rank, b.branch_code, b.branch, b.manager, b.completion_grade AS grade,
           b.done_rate::float, b.number_of_issues::int AS issues, b.score::float,
           last.branches_rank::int AS last_rank
      FROM reporting.branch_period_ranking AS b
      LEFT JOIN reporting.branch_period_ranking AS last
        ON last.branch_code = b.branch_code AND last.period = b.period AND last.period_start = %(previous)s
     WHERE b.period = %(period)s AND b.period_start = %(start)s
     ORDER BY b.branches_rank, b.branch
"""

# Only the meals with a problem: a missed task or a quality issue
MEALS_SQL = """
    SELECT branch_code, meal, tasks_missed::int AS missed, quality_issues::int AS issues
      FROM reporting.branch_meal_period
     WHERE period = %(period)s AND period_start = %(start)s AND (tasks_missed > 0 OR quality_issues > 0)
     ORDER BY branch_code, quality_issues DESC, tasks_missed DESC, meal
"""

DESCRIPTIONS_SQL = """
    SELECT branch_code, meal, description, issues::int
      FROM reporting.issue_descriptions_period
     WHERE period = %(period)s AND period_start = %(start)s
     ORDER BY branch_code, meal, issues DESC, description
"""

# All branches together, meal by meal (the yearly report's chart)
BY_MEAL_SQL = """
    SELECT meal, sum(quality_issues)::int AS issues, sum(tasks_missed)::int AS missed
      FROM reporting.branch_meal_period
     WHERE period = %(period)s AND period_start = %(start)s
     GROUP BY meal
     ORDER BY issues DESC, missed DESC, meal
"""


def read_period(period, start):
    """Everything a report shows for the period starting on `start`, as
    tables: kpis, trend, managers, branches, meals, descriptions, by_meal."""
    dates = {"period": period, "start": start, "end": period_end(period, start),
             "previous": previous_start(period, start)}
    queries = {"kpis": KPIS_SQL, "trend": WEEKS_SQL if period == "month" else MONTHS_SQL,
               "managers": MANAGERS_SQL, "branches": BRANCHES_SQL, "meals": MEALS_SQL,
               "descriptions": DESCRIPTIONS_SQL, "by_meal": BY_MEAL_SQL}
    conn = psycopg2.connect(dbname=DATABASE)
    try:
        with conn, conn.cursor() as cur:
            data = {}
            for name, sql in queries.items():
                cur.execute(sql, dates)
                columns = [column.name for column in cur.description]
                data[name] = pd.DataFrame(cur.fetchall(), columns=columns)
    finally:
        conn.close()
    # These reports show missed tasks as counts only: no day and due time (see meal_line)
    data["missed"] = pd.DataFrame(columns=["branch_code", "meal", "task_date", "due_time"])
    return data


# --------------------------------------------------------------------------------------------------------
# Charts: Plotly draws them in the browser, so hovering shows the numbers

def chart(fig, height):
    """The chart as HTML for the page. Plotly's program is added once, in the page's <head>."""
    fig.update_layout(height=height, margin=dict(l=10, r=10, t=24, b=10), plot_bgcolor="#FFFFFF",
                      paper_bgcolor="#FFFFFF", font=dict(family="-apple-system, Segoe UI, Roboto, Arial", color=INK),
                      hoverlabel=dict(bgcolor="#FFFFFF"), showlegend=False,
                      bargap=0.45, bargroupgap=0.1)          # thin bars, with air between them
    fig.update_xaxes(gridcolor="#EEEEEE", zeroline=False)
    fig.update_yaxes(gridcolor="#EEEEEE", zeroline=False)
    return fig.to_html(full_html=False, include_plotlyjs=False, config={"displayModeBar": False, "responsive": True})


def rate_floor(rates):
    """Where the % submitted scale starts: the 5 below the lowest point minus 2
    (95.2 -> 90), so a change of one point doesn't look like a cliff."""
    return max(0, 5 * math.floor((min(rates) - 2) / 5))


def trend_figures(period, trend):
    """The two trend charts: % submitted and quality issues, each a line with a
    dot per week (monthly) or month (quarterly, yearly)."""
    if period == "month":
        points = [f"{day.day} {day:%b}" for day in trend["point"]]        # the Tuesday each week ends on
        axis, hover = "Week ending (Tuesday)", "Week ending %{x}"
    else:
        points = [f"{day:%b %Y}" for day in trend["point"]]
        axis, hover = None, "%{x}"
    rate = go.Figure(go.Scatter(x=points, y=trend["submission_rate"], mode="lines+markers",
                                line=dict(color=NAVY, width=2), marker=dict(size=8),
                                hovertemplate=hover + "<br>%{y}% submitted<extra></extra>"))
    rate.update_yaxes(ticksuffix="%", range=[rate_floor(trend["submission_rate"]), 100])
    issues = go.Figure(go.Scatter(x=points, y=trend["quality_issues"], mode="lines+markers",
                                  line=dict(color=ORANGE, width=2), marker=dict(size=8),
                                  hovertemplate=hover + "<br>%{y} quality issues<extra></extra>"))
    issues.update_yaxes(rangemode="tozero")                          # counts: the scale starts at 0
    for fig in (rate, issues):
        fig.update_xaxes(title_text=axis, type="category")
    return rate, issues


def trend_charts(period, trend):
    """The two trend charts, side by side."""
    rate, issues = trend_figures(period, trend)
    return (f'<div class="charts"><div><h3>Submission rate</h3>{chart(rate, 260)}</div>'
            f'<div><h3>Quality issues</h3>{chart(issues, 260)}</div></div>')


# Where each grade starts, in % of the score (docs/metrics.md: Good above 0.90 = 90%, and so on)
GRADE_FROM = {"Terrible": 0, "Bad": 70, "Fair": 80, "Good": 90, "Excellent": 95}


def ranking_figure(rows, name):
    """One dot per manager or branch, best at the top: the dot is the score the
    rank comes from, as a % from 0 to 100, and its colour is the grade. Thin
    lines mark where each grade starts. Dots, not bars: scores sit close
    together (80-100%), and bars would all look about the same length."""
    colours = [GRADE_COLOURS[grade][0] if grade in GRADE_COLOURS else MUTED for grade in rows["grade"]]
    fig = go.Figure(go.Scatter(
        x=[score * 100 for score in rows["score"]], y=rows[name], mode="markers",
        marker=dict(size=12, color=colours),
        customdata=list(zip(rows["rank"], rows["grade"].fillna(""), rows["done_rate"], rows["issues"])),
        hovertemplate=("#%{customdata[0]} %{y}<br>%{customdata[1]} · score %{x:.1f}%<br>"
                       "%{customdata[2]}% submitted · %{customdata[3]} issues<extra></extra>")))
    edges = sorted(GRADE_FROM.items(), key=lambda item: item[1])
    for (grade, start), (_, stop) in zip(edges, edges[1:] + [("", 100)]):
        if start > 0:
            fig.add_vline(x=start, line_width=1, line_color="#CCCCCC")
        fig.add_annotation(x=(start + stop) / 2, y=1, yref="paper", yanchor="bottom",
                           text=grade, showarrow=False, font=dict(size=10, color=MUTED))
    fig.update_yaxes(autorange="reversed", automargin=True, showgrid=True)     # rank 1 at the top
    fig.update_xaxes(range=[0, 100], ticksuffix="%", title_text="Score (100% is the best)", showgrid=False)
    return fig


def ranking_chart(rows, name):
    return chart(ranking_figure(rows, name), 24 * len(rows) + 90)


def by_meal_chart(by_meal):
    """Issues and missed tasks for each meal, all branches together."""
    fig = go.Figure([
        go.Bar(name="Quality issues", y=by_meal["meal"], x=by_meal["issues"], orientation="h", marker_color=ORANGE,
               hovertemplate="%{y}<br>%{x} quality issues<extra></extra>"),
        go.Bar(name="Missed tasks", y=by_meal["meal"], x=by_meal["missed"], orientation="h", marker_color=NAVY,
               hovertemplate="%{y}<br>%{x} missed tasks<extra></extra>"),
    ])
    fig.update_yaxes(autorange="reversed", automargin=True)
    html = chart(fig, 50 * len(by_meal) + 60)
    return f'<p class="note"><span class="key issues"></span> Quality issues <span class="key missed"></span> Missed tasks</p>{html}'


# --------------------------------------------------------------------------------------------------------
# The lists under the charts

def manager_list(managers):
    """The quarterly and yearly managers, in rank order. Not tap-to-open: a
    manager's branches changed during the period."""
    rows = ""
    for m in managers.itertuples():
        rows += (f'<div class="row">{m.rank} <strong><bdi>{escape(m.manager)}</bdi></strong> {badge(m.grade)} '
                 f'{coloured(rank_change(m.rank, m.last_rank))}'
                 f'<span class="sub">ran {plural(m.branches, "branch", "branches")} '
                 f'({plural(m.branch_months, "branch-month", "branch-months")}) · {m.done_rate:g}% submitted · '
                 f'{plural(m.issues, "issue", "issues")}</span></div>\n')
    return rows


def branch_list(data):
    """The quarterly and yearly branches, in rank order: tap a branch to see its
    meals, then a meal to see its issues."""
    html = ""
    for b in data["branches"].itertuples():
        html += (f'<details class="branch top"><summary>#{b.rank} <strong><bdi>{escape(b.branch)}</bdi></strong> '
                 f'{badge(b.grade)} {coloured(rank_change(b.rank, b.last_rank))}'
                 f'<span class="sub">{b.done_rate:g}% submitted · {plural(b.issues, "issue", "issues")}</span>'
                 f"</summary>{meals_of(b.branch_code, data)}</details>\n")
    return html


PAGE_STYLE = STYLE + f"""
  main {{ max-width: 1000px; }}
  header div {{ max-width: 968px; }}
  h3 {{ margin: 0 0 4px; font-size: 14px; color: {MUTED}; font-weight: 600; }}
  .charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
  @media (max-width: 700px) {{ .charts {{ grid-template-columns: 1fr; }} }}
  .row {{ padding: 10px 0; border-bottom: 1px solid #E3E3E3; }}
  details.branch.top {{ margin-left: 0; border-bottom: 1px solid #E3E3E3; }}
  .key {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-left: 8px; }}
  .key.issues {{ background: {ORANGE}; }}
  .key.missed {{ background: {NAVY}; }}
"""


def render(period, start, data, last_day, built_on):
    """The whole report as one HTML page. `last_day` is the last day with data
    it covers: the period's end, or REPORT_DATE for a period not over yet."""
    end = period_end(period, start)
    previous = previous_start(period, start)
    than = f"last {period}"
    so_far = f" · so far, to {last_day.day} {last_day:%b}" if last_day < end else ""

    # 1. The two KPIs, with the change since the period before
    kpis = data["kpis"].set_index("period_start")
    this = kpis.loc[start]
    last = kpis.loc[previous] if previous in kpis.index else None
    tiles = (
        tile("Submission rate", f"{this['submission_rate']:g}%",
             kpi_change(this["submission_rate"], None if last is None else last["submission_rate"],
                        unit=" pts", than=than))
        + tile("Quality issues", f"{int(this['quality_issues'])}",
               kpi_change(this["quality_issues"], None if last is None else last["quality_issues"],
                          lower_is_better=True, than=than))
    )

    # 2. The charts
    trend_note = ("The weeks that end in this month, with the weekly reports' numbers." if period == "month"
                  else "Month by month.")
    grades = " ".join(badge(grade) for grade in GRADE_COLOURS)
    if period == "month":
        bars = section("Manager ranking", f"Each dot is the score the rank comes from; its colour is the grade: {grades}",
                       ranking_chart(data["managers"], "manager"))
    else:
        bars = section("Branch ranking", f"Each dot is the score the rank comes from; its colour is the grade: {grades}",
                       ranking_chart(data["branches"], "branch"))
    charts = section("Trend", trend_note, trend_charts(period, data["trend"])) + bars
    if period == "year":
        charts += section("By meal", "All branches together: the meals with the most problems first.",
                          by_meal_chart(data["by_meal"]))

    # 3. The lists
    changes = f"▲ ▼: places moved since {than}."
    if period == "month":
        lists = section("By manager",
                        f"1 is the best. Tap a manager, then a branch, then a meal, to open it. {changes} "
                        "#: the branch's rank among all branches.", by_manager(data))
    else:
        lists = (section("Managers", "Each branch counts, month by month, for the manager who ran it that month. "
                         f"1 is the best. {changes}", manager_list(data["managers"]))
                 + section("Branches", f"1 is the best. Tap a branch to see its meals, then a meal to see its issues. {changes}", branch_list(data)))

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{NAME[period]} Report {label(period, start)}</title>
<style>{PAGE_STYLE}</style>
<script>{get_plotlyjs()}</script>
</head>
<body>
<header><div>
  <h1>{NAME[period]} report</h1>
  <p>{label(period, start)}{so_far} · compared with {label(period, previous)}</p>
</div></header>
<main>
<section class="tiles">{tiles}
</section>
{charts}
{lists}
{footer(built_on)}
</main>
</body>
</html>
"""


def main():
    periods = sys.argv[1:] or periods_due(REPORT_DATE)
    unknown = [period for period in periods if period not in PERIODS]
    if unknown:
        print(f"Unknown period(s): {', '.join(unknown)}. Use month, quarter or year.")
        sys.exit(1)

    for period in periods:
        start = period_start(period, REPORT_DATE)
        data = read_period(period, start)
        if data["branches"].empty:
            print(f"No data for {label(period, start)}. Have load_workbook.py and build_models.py run?")
            sys.exit(1)
        last_day = min(REPORT_DATE, period_end(period, start))
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        path = os.path.join(OUTPUT_DIR, file_name(period, start))
        with open(path, "w", encoding="utf-8") as file:
            file.write(render(period, start, data, last_day, built_on=date.today()))
        kpis = data["kpis"].set_index("period_start").loc[start]
        print(f"{NAME[period]} report, {label(period, start)}: submission rate {kpis['submission_rate']:g}%, "
              f"{int(kpis['quality_issues'])} quality issues. Written to {path}")


if __name__ == "__main__":
    main()
