-- Tables loaded by notebooks/02_weekly_load_and_rankings.ipynb.
-- Same structure as production (see production/shawarma_classic.sql).
CREATE SCHEMA IF NOT EXISTS training;

CREATE TABLE IF NOT EXISTS training.branches (
    code character varying(30),
    name character varying(255)
);

CREATE TABLE IF NOT EXISTS training.issues (
    date date,
    branch character varying(255),
    meal character varying(50),
    description character varying(50),
    manager character varying(50)
);

-- One row per branch that missed a task; branch_missed is '' when none did.
CREATE TABLE IF NOT EXISTS training.tasks (
    date date,
    meal character varying(50),
    done_tasks integer,
    branch_missed character varying(255),
    due_time character varying(50),
    missed_tasks integer
);
