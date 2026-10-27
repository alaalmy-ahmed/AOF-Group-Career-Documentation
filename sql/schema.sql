-- Tables loaded by notebooks/02_weekly_load_and_rankings.ipynb
CREATE SCHEMA IF NOT EXISTS training;

CREATE TABLE IF NOT EXISTS training.issues (
    "date"        DATE NOT NULL,
    "branch"      TEXT NOT NULL,
    "meal"        TEXT,
    "description" TEXT,
    "manager"     TEXT
);

-- One row per branch that missed a task; branch_missed is '' when none did.
CREATE TABLE IF NOT EXISTS training.tasks (
    "date"          DATE NOT NULL,
    "meal"          TEXT NOT NULL,
    "done_tasks"    INTEGER,
    "missed_tasks"  INTEGER,
    "branch_missed" TEXT,
    "due_time"      TEXT
);
