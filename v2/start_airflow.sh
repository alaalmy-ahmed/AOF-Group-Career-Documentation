#!/bin/bash
# Starts Airflow for the v2 schedule (step 6).
#
# Leave this terminal open: closing it, logging out or restarting the Mac
# stops the schedule until you run this again. Missed days are made up then.
#
# Run it with the v2 virtual environment active:
#     v2/start_airflow.sh
# Then open http://localhost:8080 (the login is printed in this terminal).

set -e
V2="$(cd "$(dirname "$0")" && pwd)"

# Your paths, database password and email settings (not in git)
source "$V2/airflow.env"

export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"  # Airflow's own files: its database, logs, settings
export AIRFLOW__CORE__DAGS_FOLDER="$V2/dags"          # where it finds the DAGs
export AIRFLOW__CORE__LOAD_EXAMPLES=False             # don't show Airflow's example DAGs

airflow standalone
