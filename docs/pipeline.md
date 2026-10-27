# Pipeline components

Paths are relative to `Shawerma Classic/`, which is not committed.

## Current pipeline

| Cadence | File | Input | Output |
|---|---|---|---|
| Daily | `Company/Programming/New Data Processing.ipynb` | `07-2024/07-2024.xlsx` → *Reviewing Reports* (yesterday's rows, with photos); `Company/managers.xlsx` | `Company/Programming/<Manager>/<Branch>.xlsx`: one formatted file per branch, photos embedded |
| Weekly | `Company/Programming/loading data to the database.ipynb` | `07-2024.xlsx` (*Source Data*, *Reviewing Reports*, *branches and codes*, *Managers*); `Lubda.xlsx` (*Tasks*, *Issues*) | New rows in `shawarma_classic.training.{tasks,issues}` and `lubda.operation.{tasks,issues}`; `Branches Weekly Performance Summary.xlsx`, `Managers Weekly Performance Summary.xlsx` |
| Weekly | Power BI: `07-2024/Weekly Report.pbix` | PostgreSQL | Weekly Report |
| Quarterly | Power BI | PostgreSQL | Quarterly report (e.g. `Q2 Analysis`) |
| Yearly | Power BI | PostgreSQL | `Yearly Report` (per brand) |

### `New Data Processing.ipynb`, key functions

| Function | Purpose |
|---|---|
| `get_image_order_from_rich_data(xlsx_path, sheet_name)` | Opens the workbook zip, finds the sheet XML and returns `{excel_row: image_bytes}` by following each cell's `vm` index through the rich-value relationships to the image file |
| `create_formatted_excel(file_path, data_df, row_image_mapping)` | Writes one branch file: header styling, borders, wrapped text, and images sized and centred in their cells |
| `gather_and_save_data(managers_df, data_df, …)` | Loops over managers → branches, filters the day's issues and calls the writer |

### `loading data to the database.ipynb`, sections

1. **Pushing the newest data**: reshapes Shawarma Classic tasks and issues and inserts rows newer than the latest date in the database.
2. **Branches and managers weekly rankings**: done rates, performance scores, ranks and grades ([metrics.md](metrics.md)).
3. **Lubda data loading**: the same incremental load for the Lubda workbook.

## Supporting tools

| File | Purpose |
|---|---|
| `Programming/weekly tasks distribution.py` | Lists the branches that missed deliveries in the last 7 days, per manager, for both brands |
| `Programming/Database Recreation 2.0.ipynb` | Development copy of the ranking logic, plus the *Missing Tools* summary (Manager → Branch → Meal → Item) |
| `Programming/Data Exploration in psycopg.ipynb` | Ad-hoc SQL against the database |
| `Data/trainings by employees.ipynb` | Merges ~70 Zenput SOP exports into one record of trainee × meal (`Trainees_with_Trained_Meals.xlsx`) |

## Earlier iterations (kept for reference)

| File | What it was |
|---|---|
| `seperating.ipynb`, `Data Processing.ipynb`, `managers manipulation.ipynb` | First versions of the per-manager split, without photos; branch-name cleaning |
| `Daily Reports.py`, `Data Manipulation from sheet to db.py`, `distributing_branches.py` | Google Sheets–based ingestion with a mirrored backup database |
| `web server database.py` | Flask `POST /update-database` endpoint for single-row inserts |
| `database creation.ipynb` | Initial database bootstrap from CSV |

## Running it

```bash
pip install pandas openpyxl psycopg2-binary
```

1. **Daily**: open `New Data Processing.ipynb` and run all cells. Manager folders are created or updated under `Programming/`.
2. **Weekly**: run `loading data to the database.ipynb`, then refresh `Weekly Report.pbix` in Power BI.
3. **End of quarter / year**: refresh the quarterly and yearly reports.
