-- Weekly branch and manager rankings, computed in the database.
--
-- Same method as the pandas version in notebooks/02_weekly_load_and_rankings.ipynb
-- (see docs/metrics.md). Window: the 7 days ending on the report date.
--
--   SELECT * FROM training.branch_weekly_ranking(DATE '2026-10-26');
--   SELECT * FROM training.manager_weekly_ranking(DATE '2026-10-26');
--
-- The two views always show the week ending yesterday, for Power BI.

-- Branch -> area manager. Lives in the workbook's "Managers" sheet; the weekly
-- notebook refreshes it together with training.branches.
CREATE TABLE IF NOT EXISTS training.branch_managers (
    branch character varying(255) PRIMARY KEY,
    manager character varying(50) NOT NULL
);


CREATE OR REPLACE FUNCTION training.branch_weekly_ranking(p_report_date date)
RETURNS TABLE (
    manager          character varying,
    branch           character varying,
    done_rate        numeric,
    number_of_issues bigint,
    branches_rank    bigint,
    completion_grade text
)
LANGUAGE sql STABLE AS $$
    WITH tasks_in_window AS (
        SELECT *
        FROM training.tasks t
        WHERE t.date BETWEEN p_report_date - 6 AND p_report_date
    ),
    -- Every scheduled task (meal x slot x day) in the window
    task_count AS (
        SELECT COUNT(*) AS n
        FROM (SELECT DISTINCT date, meal, due_time FROM tasks_in_window) s
    ),
    missed AS (
        SELECT branch_missed AS branch, COUNT(*) AS missed
        FROM tasks_in_window
        WHERE branch_missed <> ''
        GROUP BY branch_missed
    ),
    issues_in_window AS (
        SELECT i.branch, COUNT(i.meal) AS issues
        FROM training.issues i
        WHERE i.date BETWEEN p_report_date - 6 AND p_report_date
        GROUP BY i.branch
    ),
    per_branch AS (
        SELECT bm.manager,
               b.name AS branch,
               -- Branches that never missed a task get 100
               100 - ROUND(COALESCE(m.missed, 0)::numeric / NULLIF(tc.n, 0) * 100, 1) AS done_rate,
               COALESCE(iw.issues, 0) AS number_of_issues
        FROM training.branches b
        JOIN training.branch_managers bm ON bm.branch = b.name
        LEFT JOIN missed m ON m.branch = b.name
        LEFT JOIN issues_in_window iw ON iw.branch = b.name
        CROSS JOIN task_count tc
    ),
    scored AS (
        -- Normalise each metric to the group maximum, then weight 90 / 10
        SELECT *,
               0.90 * done_rate / NULLIF(MAX(done_rate) OVER (), 0)
             + 0.10 * (1 - number_of_issues::numeric / NULLIF(MAX(number_of_issues) OVER (), 0)) AS score
        FROM per_branch
    )
    SELECT manager,
           branch,
           done_rate,
           number_of_issues,
           RANK() OVER (ORDER BY score DESC) AS branches_rank,
           CASE
               WHEN score > 0.95 THEN 'Excellent'
               WHEN score > 0.90 THEN 'Good'
               WHEN score > 0.80 THEN 'Fair'
               WHEN score > 0.70 THEN 'Bad'
               WHEN score > 0    THEN 'Terrible'
           END AS completion_grade
    FROM scored
    ORDER BY branches_rank, branch;
$$;


CREATE OR REPLACE FUNCTION training.manager_weekly_ranking(p_report_date date)
RETURNS TABLE (
    manager           character varying,
    done_rate         numeric,
    issues_per_branch numeric,
    number_of_issues  numeric,
    managers_rank     bigint
)
LANGUAGE sql STABLE AS $$
    WITH per_manager AS (
        SELECT r.manager,
               ROUND(AVG(r.done_rate), 1)        AS done_rate,
               ROUND(AVG(r.number_of_issues), 1) AS issues_per_branch,
               SUM(r.number_of_issues)           AS number_of_issues
        FROM training.branch_weekly_ranking(p_report_date) r
        GROUP BY r.manager
    ),
    scored AS (
        -- Issues weigh more for managers (85 / 15): they're the ones who fix them
        SELECT *,
               0.85 * done_rate / NULLIF(MAX(done_rate) OVER (), 0)
             + 0.15 * (1 - issues_per_branch / NULLIF(MAX(issues_per_branch) OVER (), 0)) AS score
        FROM per_manager
    )
    SELECT manager,
           done_rate,
           issues_per_branch,
           number_of_issues,
           RANK() OVER (ORDER BY score DESC) AS managers_rank
    FROM scored
    ORDER BY managers_rank, manager;
$$;


CREATE OR REPLACE VIEW training.v_branch_weekly_ranking AS
SELECT * FROM training.branch_weekly_ranking(CURRENT_DATE - 1);

CREATE OR REPLACE VIEW training.v_manager_weekly_ranking AS
SELECT * FROM training.manager_weekly_ranking(CURRENT_DATE - 1);
