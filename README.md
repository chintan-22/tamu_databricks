# Luck, Location, or a Leak?

**TAMU Datathon 2026**: *Dashboard Royale* (The Gilded Ace) built on **Databricks**.

The general manager of The Gilded Ace, a fictional 300-machine casino, wants to replace the 10 slot machines that earned the least in January–June 2025. This project tests every machine against luck, location, downtime and payout leaks before calling it weak. It then prices a $100,000 plan.

**Headline:** none of the manager's 10 machines makes our replacement list.
- 2 are already retired, and 1 has been on the floor for only 49 days.
- 1 (M-1158) pays out far beyond its paytable and needs inspecting, not replacing.
- 6 are weak for their spot, but sit in Back Forty, a zone whose play fell 29% when a single walkway closed. A new title there adds less than half the theo it would in a busy zone.

Our replacement targets are the weak earners where a new title gains most: Royal Draw cabinets set to a 95% payout, in busy zones.

> **New to the project? Start with [HANDOFF.md](HANDOFF.md)**: setup, checks, open tasks and how we work.

| | |
|---|---|
| Dashboard (public) | `dashboard/index.html`. Publish the `dashboard/` folder with GitHub Pages, or run `python -m http.server` inside it |
| **Start here (team)** | [docs/TEAM_GUIDE.md](docs/TEAM_GUIDE.md): plain-language overview, findings, open tasks |
| Write-up: Dashboard Royale (≤ 400 words) | [docs/WRITEUP_DASHBOARD_ROYALE.md](docs/WRITEUP_DASHBOARD_ROYALE.md) |
| Write-up: Databricks track | [docs/WRITEUP_DATABRICKS.md](docs/WRITEUP_DATABRICKS.md) |
| Claims & Evidence appendix | [docs/CLAIMS_EVIDENCE.md](docs/CLAIMS_EVIDENCE.md) |
| AI-use disclosure | [docs/AI_DISCLOSURE.md](docs/AI_DISCLOSURE.md) |
| Video script | [docs/VIDEO_SCRIPT.md](docs/VIDEO_SCRIPT.md) |

## How Databricks is used

```
GitHub release ──► 01_ingest_raw (notebook) ──► UC Volume /raw  (SHA-256 verified against manifest)
                                                     │ Auto Loader
                    Lakeflow Declarative Pipeline    ▼
   bronze_* (22 streaming tables, source-file lineage)
   silver_* (conformed; expectations encode every pitfall in the challenge guide)
   gold_*   (machine scorecard, downtime valuation, natural experiments, comps, players, priced actions)
                                                     │
   02_train_forecast ── MLflow runs ── UC model registry: floor_coin_in_forecast@champion ── gold_forecast
                                                     │
   03_export_dashboard ── event-log expectations → expectation_log ── gilded_ace.json → public dashboard
   Genie space over the gold tables for the manager's follow-up questions (genie/GENIE_SPACE.md)
```

- **Lakeflow expectations do the analytical hygiene.** Off-floor machine-days are dropped, not counted as zero sales. The update fails if meters don't balance or go negative, if an RTP is not a real payback, if a machine-day is duplicated or missing, or if the six-part decomposition doesn't sum to the gap. The plan fails if it goes over budget or uses more than three action types. `local/stress_test.py` feeds broken data through the pipeline to prove each of these fires.
- **Unity Catalog** governs the raw volume, every table, and the registered forecast model.
- **MLflow** tracks every forecast candidate, the April selection, the frozen champion and its holdout plot.
- **One SQL codebase.** The same `src/pipeline/*.sql` files run on Databricks and, through `local/lakeflow_duckdb.py`, on DuckDB for verification. Expectations are enforced in both.

## Deploy on Databricks

```sh
databricks bundle deploy -t dev                 # catalog/schema default to workspace.gilded_ace (+ gilded_ace_ml for forecast tables)
databricks bundle run gilded_ace_job -t dev     # ingest → pipeline → forecast → export
```

Then copy `/Volumes/workspace/gilded_ace/exports/gilded_ace.json` to `dashboard/data/` and create the Genie agent with `python genie/genie_space.py create` (config in `genie/gilded_ace_floor_analyst.json`; see `genie/GENIE_SPACE.md`).

## Run locally (no Databricks needed)

```sh
git clone --depth 1 https://github.com/tamu-datathon-org/dashboard-royale.git ../dashboard-royale
python -m venv .venv && .venv/Scripts/pip install -r requirements.txt     # Python 3.11+
python local/run_local.py          # bronze → silver → gold → forecast → dashboard/data/gilded_ace.json
python local/build_pages.py        # dashboard/app.html → dashboard/index.html
node local/check_dashboard.js      # dashboard maths must match the pipeline (0 mismatches)
python local/stress_test.py        # independent re-checks, robustness tests, broken-data guards
cd dashboard && python -m http.server
```

## Checks (CI)

`python local/ci.py` runs every check in one go: the pipeline, a comparison of the committed export with a fresh run, dashboard parity, the stress test and `local/judge_check.py` (hackathon guardrails: the submission package, the six questions, the judges' four tasks, the $100K plan rules, the forecast protocol, every quoted number against the gold tables, wording rules, and Spark/DuckDB SQL rules). GitHub Actions runs it on every push and pull request (`.github/workflows/ci.yml`). Run `git config core.hooksPath .githooks` once to run it on every local commit and push too.

## Method in one paragraph

Each machine's gap to a typical machine splits exactly into six parts:
- **Luck:** house win minus theo.
- **Location:** its zone's theo per machine against the floor's, on the same days.
- **Downtime:** extra downtime against zone peers, valued at the machine's own play rate.
- **Game appeal:** coin-in against zone peers.
- **Hold setting:** theo lost to a more generous paytable than its neighbours.
- **Time on floor:** days not installed.

Luck is tested exactly. The per-spin payout variance comes from `game_math`, so Var(house win) = Σ bet² × Var(payout/bet), and the leak cut-off is |z| > 3.6, which accounts for running 310 tests at once. That luck test only counts over 150+ days, because one jackpot can push an honest machine past it in a short window; the hit-rate test (|z| > 6) applies on any window. The **fair index** compares theo with what same-zone machines earned on the same days per available second, with a 95% interval across days. The forecast is chosen on April, frozen on April 30, and scored once on May–June against a constant-mean baseline.

## Repository

```
databricks.yml, resources/      Asset Bundle: pipeline + job
src/pipeline/                   Lakeflow SQL (silver, gold_*) + bronze.py (Auto Loader)
src/notebooks/                  01 ingest · 02 forecast (MLflow/UC) · 03 export
src/gilded_ace/                 shared Python: table list, forecast, export, Lakeflow SQL parser
local/                          DuckDB runner for the same pipeline, Pages builder, checks (ci.py, judge_check.py)
.github/workflows/, .githooks/  CI on every push/PR, local commit/push hooks
dashboard/                      app.html (source) · index.html (built) · data/gilded_ace.json
genie/, docs/                   Genie space setup, submission documents
```

*The Gilded Ace is fictional and its data synthetic. Only the LVCVA, NOAA and Missouri Gaming Commission files are real public data. Unusual payouts are leads to inspect, not accusations.*
