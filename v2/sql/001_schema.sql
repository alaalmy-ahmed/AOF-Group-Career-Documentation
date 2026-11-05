-- v2 schema for Shawarma Classic: tasks, misses and quality issues with keys
-- and constraints, so the database rejects bad data on its own.
--
-- Lives in its own schema, `ops`, so it can sit next to v1's `training`
-- schema in the same database. Run once:
--
--   psql -U postgres -d shawarma_classic -f v2/sql/001_schema.sql
--
-- Design notes: v2/README.md

BEGIN;

CREATE SCHEMA ops;


-- ── Reference tables ────────────────────────────────────────────────────

-- Names are kept distinct in the workbook (e.g. "Mohamed Emad"), and the load
-- looks managers up by name, so a repeated name is rejected here.
CREATE TABLE ops.managers (
    manager_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name        varchar(50) NOT NULL UNIQUE
);

-- The branch code (e.g. B25) is short and unique, so it is the key.
-- manager_id is the branch's current manager.
CREATE TABLE ops.branches (
    code        varchar(30)  PRIMARY KEY,
    name        varchar(255) NOT NULL UNIQUE,
    manager_id  integer      NOT NULL REFERENCES ops.managers (manager_id)
);

CREATE TABLE ops.meals (
    meal_id  integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name     varchar(50) NOT NULL UNIQUE
);


-- ── Facts ───────────────────────────────────────────────────────────────

-- One row per scheduled task: a meal every branch must submit by a due time.
-- The same meal can be due twice a day (e.g. 1-3 pm and 5-7 pm).
CREATE TABLE ops.scheduled_tasks (
    task_id             integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_date           date        NOT NULL,
    meal_id             integer     NOT NULL REFERENCES ops.meals (meal_id),
    due_time            varchar(50) NOT NULL,
    branches_submitted  integer     NOT NULL CHECK (branches_submitted >= 0),
    UNIQUE (task_date, meal_id, due_time)
);

-- One row per branch that missed a task. No row means the branch submitted,
-- so the number missed is COUNT(*) here rather than a stored column.
CREATE TABLE ops.task_misses (
    task_id      integer     NOT NULL REFERENCES ops.scheduled_tasks (task_id),
    branch_code  varchar(30) NOT NULL REFERENCES ops.branches (code),
    PRIMARY KEY (task_id, branch_code)
);

-- One row per quality issue, tied to the task (date, meal, due time) it was
-- found on. manager_id is the branch's manager on the day it was loaded, so
-- history survives the monthly rotation.
CREATE TABLE ops.quality_issues (
    issue_id     integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    task_id      integer     NOT NULL REFERENCES ops.scheduled_tasks (task_id),
    branch_code  varchar(30) NOT NULL REFERENCES ops.branches (code),
    description  varchar(50) NOT NULL,
    manager_id   integer     NOT NULL REFERENCES ops.managers (manager_id),
    -- A branch can't get the same description twice on one task (same date,
    -- meal and due time). This also lets a re-run of the load skip rows
    -- that are already in.
    UNIQUE (task_id, branch_code, description)
);

COMMIT;
