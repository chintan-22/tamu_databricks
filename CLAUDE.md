# CLAUDE.md: context for coding agents on this repo

TAMU Datathon 2026 project, entered in **two** challenges: **Dashboard Royale** (fictional Gilded Ace casino: are the 10 lowest-earning slot machines truly weak, or luck/location/leak? + $100K plan) and the **Databricks** track (Databricks is the engine). Start with `docs/TEAM_GUIDE.md` (plain-language overview, findings, open tasks). Per-submission text is in `docs/WRITEUP_DASHBOARD_ROYALE.md` (hard limit 400 words, currently 390) and `docs/WRITEUP_DATABRICKS.md`.

## Layout
- `src/pipeline/*.sql`: **single source of truth** for all analysis. Lakeflow Declarative Pipeline SQL (`CREATE OR REFRESH MATERIALIZED VIEW name (CONSTRAINT ... EXPECT ...) COMMENT '...' AS SELECT ...;`). `bronze.py` = Auto Loader bronze tables (Databricks only).
- `src/gilded_ace/`: shared Python, used both on Databricks and locally: `tables.py` (raw file list), `forecast.py` (model + validation protocol), `export.py` (gold → `dashboard/data/gilded_ace.json`), `lakeflow_sql.py` (parser for the SQL subset above).
- `src/notebooks/`: Databricks job tasks: 01 ingest → (pipeline) → 02 forecast/MLflow/UC → 03 expectation log + export.
- `databricks.yml`, `resources/*.yml`: Asset Bundle (pipeline + job). Vars: `catalog` (default `workspace`), `schema` (`gilded_ace`).
- `local/run_local.py`: runs the **same SQL** on DuckDB (`lakeflow_duckdb.py` adds Spark shims and enforces expectations), then forecast, then export. `local/build_pages.py`: `dashboard/app.html` (fragment, the source) → `dashboard/index.html` (standalone, generated). `local/check_dashboard.js`: parity test.
- `dashboard/app.html`: the whole dashboard (vanilla JS + SVG, no libraries). It recomputes the machine scorecard in the browser (`computeScorecard`) for any period.
- Challenge data is NOT in this repo: clone `tamu-datathon-org/dashboard-royale` next to it (`../dashboard-royale/data`).

## Workflow (run after any change)
```sh
.venv/Scripts/python local/run_local.py      # must finish with no expectation failure
.venv/Scripts/python local/build_pages.py    # after editing dashboard/app.html
node local/check_dashboard.js                # must print "verdict mismatches 0" and exit 0
```
On Windows set `PYTHONUTF8=1` (or pass `encoding="utf-8"`) when a script reads/writes repo files; the SQL contains non-ASCII characters.

## Invariants: don't break these
- **SQL must run on both Spark and DuckDB.** Use only functions that both have, or that `SPARK_SHIMS` in `local/lakeflow_duckdb.py` maps (`unix_timestamp`, `percentile_approx`, `collect_list`, `array_join`). No 0- vs 1-based array indexing, no aggregate nested in an aggregate, no `::` casts. Expectations may reference **output columns only**.
- **The scorecard maths lives in two places**: `src/pipeline/gold_machines.sql` and `computeScorecard`/`verdictOf` in `dashboard/app.html`. Change both together; `check_dashboard.js` must stay at 0 mismatches.
- **Money/analysis rules from the challenge guide**: ratio of sums (never average daily ratios); exclude off-floor rows (`silver_machine_day` drops them); gaming day 06:00–06:00 via `silver_calendar` UTC bounds (DST day = 23 h); comp cost is already inside POS cogs; player tables = carded play only; theo = coin-in × (1 − RTP).
- **Forecast protocol** (`forecast.py`): select on April (fit Jan–Mar), freeze 2025-04-30, score once on May–Jun; events are inputs only if `announced_date <= freeze`. Don't re-select the model using holdout scores.
- **Action plan**: ≤ 3 action types, ≤ $100,000, catalogue cost formula `qty × (unit + per_day × max(0, 30 − lead_days))`. These are enforced as FAIL expectations in `gold_action_plan`. `recommended` set = A-INSPECT, A-REPLACE-LEASE, A-PROMO.
- **Wording**: the casino is fictional; unusual payouts are "leads to inspect", never accusations; no ideas that push heavy losers to gamble more.
- Any number quoted in `docs/` or the dashboard copy must come from a gold table. If the pipeline changes, re-check `docs/WRITEUP_*.md`, `docs/CLAIMS_EVIDENCE.md`, `docs/TEAM_GUIDE.md` and hard-coded text in `dashboard/app.html` (hero/finding sentences).

## Status
- Verified locally: full pipeline, forecast, plan, dashboard parity (0/310 mismatches).
- **Not yet run on Databricks.** Expected fix spots: the `sys.path` import in `src/pipeline/bronze.py`, the `event_log(...)` query in `03_export_dashboard.py`, `mlflow.pyfunc.log_model` in `02_train_forecast.py`.
- Open tasks are tracked in `docs/TEAM_GUIDE.md` §7.
- Git: commit/push only when a human asks; work on a branch, not `main`.
