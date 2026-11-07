# Handoff: how to pick this up

Welcome. The analysis, pipeline, dashboard and write-ups are done and verified locally. What's left is running it on Databricks, publishing, and submitting. This page gets you from a fresh clone to working on a task in about 15 minutes.

**Read in this order:** this file → [docs/TEAM_GUIDE.md](docs/TEAM_GUIDE.md) (what we built and found, in plain words) → [CLAUDE.md](CLAUDE.md) (rules your coding agent follows; it loads them automatically).

---

## 1. Set up (once, ~10 minutes)

You need Git, Python 3.11+ and Node.js 18+.

```sh
# 1. Put the repo and the challenge data side by side in the same folder
git clone https://github.com/chintan-22/tamu_databricks.git
git clone --depth 1 https://github.com/tamu-datathon-org/dashboard-royale.git
cd tamu_databricks

# 2. Python environment
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt          # Windows
# .venv/bin/pip install -r requirements.txt            # macOS / Linux
```

The data repo must sit **next to** this one (`../dashboard-royale/data`). If you put it elsewhere, pass `--data <path>` to `run_local.py`.

## 2. Check that everything works (~1 minute)

```sh
.venv\Scripts\python local\run_local.py        # macOS/Linux: .venv/bin/python local/run_local.py
node local/check_dashboard.js
```

You should see:
- `pipeline done in ~3s`, with no expectation failure
- `forecast: selected weekday_mean on April validation`
- `exported dashboard data -> .../dashboard/data`
- `machines 310 | ... | verdict mismatches 0` and `dashboard rendered: ok`

To view the dashboard: `cd dashboard`, then `python -m http.server 8000`, then open http://localhost:8000. Opening the file directly won't work, because it loads its data over HTTP.

If any of this fails, stop and fix it before starting a task (or ask in the team chat). Common causes: the data repo is in the wrong place; Python older than 3.11; on Windows, a `UnicodeDecodeError` (set `PYTHONUTF8=1`).

## 3. How we work

1. **Claim a task** in the table below. Put your name in it in a small PR, or say so in the team chat.
2. **Branch from `main`:** `git checkout main && git pull && git checkout -b <task-branch>` (branch names are in the table).
3. **Before you push, run the three checks:** `run_local.py`, `build_pages.py` (only if you changed `dashboard/app.html`), and `check_dashboard.js` (must say 0 mismatches).
4. **Open a pull request into `main`.** Another teammate glances at it, then merge. Don't push straight to `main`.
5. **If you change any number** (pipeline SQL, forecast, plan), update the documents that quote it. [CLAUDE.md](CLAUDE.md) lists which ones.

Never edit `dashboard/index.html` by hand. It is generated from `dashboard/app.html` by `local/build_pages.py`.

## 4. Tasks left

| # | Task | Branch | Owner | Depends on | Done when |
|---|---|---|---|---|---|
| 1 | **Run the project on Databricks** | `databricks-run` | | none | Job `gilded-ace-end-to-end` succeeds; tables exist in `workspace.gilded_ace`; model `floor_coin_in_forecast@champion` registered |
| 2 | Create the Genie space | `genie` | | 1 | Space answers the six sample questions in `genie/GENIE_SPACE.md` |
| 3 | Screenshots for the Databricks submission | `screenshots` | | 1, 2 | PNGs in `docs/screenshots/`: pipeline graph, expectations, MLflow runs, registered model, Genie |
| 4 | Publish the dashboard (GitHub Pages) | `pages-deploy` | | none | Public link opens in a private window; link added to both write-ups and the README |
| 5 | Record the video(s), ≤ 2 min | none | | 4 | Uploaded; links in the write-ups |
| 6 | Finalise the AI disclosure | `docs-final` | | none | `docs/AI_DISCLOSURE.md` says who did what |
| 7 | Final number check + submit both Devposts | `docs-final` | | all | Both submissions in (see §6 checklist) |
| 8 | *(Optional)* AI/BI dashboard inside Databricks | `aibi-dashboard` | | 1 | A Lakeview dashboard on the gold tables, screenshot added |

### Task notes

**1 · Run on Databricks.** Free Edition works; it ships with a `workspace` catalog.
```sh
# install the Databricks CLI (https://docs.databricks.com/dev-tools/cli/install.html), then:
databricks auth login --host https://<your-workspace>.cloud.databricks.com
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run gilded_ace_job -t dev
```
This has **never been run on a real workspace**, so expect a few small fixes. The likely spots:
- `src/pipeline/bronze.py`: the `sys.path` import of `gilded_ace.tables`. If it fails, inline the `RAW_TABLES` dict.
- `src/notebooks/02_train_forecast.py`: `mlflow.pyfunc.log_model` arguments (the name differs between MLflow versions).
- `src/notebooks/03_export_dashboard.py`: the `event_log(TABLE(...))` query. If it fails, read the pipeline's event log by pipeline ID.

After a successful run, download `/Volumes/workspace/gilded_ace/exports/gilded_ace.json`. Run `node local/check_dashboard.js` against it (copy it over `dashboard/data/gilded_ace.json` on your branch). The Databricks numbers should match the local ones; if any differ, investigate before merging.

**4 · GitHub Pages.** Pages can't serve the `dashboard/` folder directly, so add `.github/workflows/pages.yml` that uploads `dashboard/` with `actions/upload-pages-artifact` and deploys with `actions/deploy-pages`. Then, in the repo, go to **Settings → Pages → Source: GitHub Actions**. The repo must be public, or the account must have Pages for private repos. The data file is 4.5 MB, which is fine.

**7 · Submission checklist**
- Dashboard Royale Devpost: public dashboard link · video ≤ 2 min · `docs/WRITEUP_DASHBOARD_ROYALE.md` (≤ 400 words; check with a word counter) · `docs/CLAIMS_EVIDENCE.md` · `docs/AI_DISCLOSURE.md` · repo link · the 3 priced actions (already in the write-up)
- Databricks Devpost: `docs/WRITEUP_DATABRICKS.md` · screenshots from task 3 · repo link · dashboard link · video
- Test every link in a private browser window.

## 5. Using Claude Code (or another agent) on a task

Open the repo folder in Claude Code. It reads `CLAUDE.md` automatically. Start with a prompt like these:

- **Task 1:** "Read HANDOFF.md and CLAUDE.md. I'm on task 1. I've run `databricks auth login`. Deploy and run the bundle on the dev target, fix any errors you hit (start with the known fix spots), and keep the SQL runnable on DuckDB. When the job succeeds, compare the exported gilded_ace.json with the local one using check_dashboard.js."
- **Task 4:** "Read HANDOFF.md. Do task 4: add a GitHub Actions workflow that deploys the dashboard/ folder to GitHub Pages, and tell me the repo settings I need to change."
- **Task 7:** "Read HANDOFF.md and CLAUDE.md. Re-run the pipeline, then check every number quoted in docs/ and in the copy inside dashboard/app.html against the gold tables, and list any that don't match."

Ask the agent to work on your task branch and to open a PR, not to push to `main`.

## 6. Where things are

| You want to… | Look at |
|---|---|
| Understand the findings | `docs/TEAM_GUIDE.md` §3–5 |
| Change the analysis | `src/pipeline/*.sql` (then the dashboard copy if the logic changes; see CLAUDE.md) |
| Change the forecast | `src/gilded_ace/forecast.py` |
| Change the plan / prices | `src/pipeline/gold_actions.sql` |
| Change the dashboard | `dashboard/app.html` → `local/build_pages.py` |
| Databricks deployment | `databricks.yml`, `resources/`, `src/notebooks/` |

Questions about why something was done a certain way are usually answered in the SQL comments at the top of each `src/pipeline/gold_*.sql` file, or in `docs/CLAIMS_EVIDENCE.md`.
