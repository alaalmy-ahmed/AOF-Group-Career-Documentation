"""
Weekly, after the load: build the dbt models (the reporting views) and run
all their checks, with `dbt build` (step 7). The dbt project is in v2/dbt.

dbt is installed in its own Python environment, because its packages clash
with Airflow's, so this runs it as a separate program: DBT_EXECUTABLE in
settings.py. dbt exits with a non-zero code if a model or a check fails, and
so does this script.

Usage:
    python v2/build_models.py

Settings: DBT_EXECUTABLE (see settings.py), and PGHOST, PGPORT, PGUSER,
PGPASSWORD, PGDATABASE, which dbt/profiles.yml reads.
"""

import os
import subprocess
import sys

from settings import DBT_EXECUTABLE

DBT_PROJECT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dbt")


def main():
    result = subprocess.run([DBT_EXECUTABLE, "build", "--project-dir", DBT_PROJECT, "--profiles-dir", DBT_PROJECT])
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
