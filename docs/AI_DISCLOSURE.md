# AI-use disclosure

- **Tool:** Claude (Anthropic), used through Claude Code.
- **What it did:** wrote the project code with us: the Databricks Asset Bundle, the Lakeflow SQL pipeline, the forecast module and MLflow notebook, the DuckDB local runner, the export, and the HTML dashboard. It also ran the exploratory queries and drafted this write-up, the claims appendix and the video script.
- **What we checked:** every number in the write-up comes from a gold table produced by the pipeline (re-run with `python local/run_local.py`). The dashboard's in-browser recomputation is checked against the pipeline (0 of 310 verdicts differ). The decomposition is checked by a pipeline expectation that fails if its parts don't sum to the gap.
- **Decisions made by the team:** the choice of actions, the thresholds (|z| 3.6 for 310 tests; fair index CI below 0.85), and the decision to keep the April-selected forecast after seeing better post-hoc variants.
- **Who did what (people; every step used Claude Code as above):**
  - Ujjawal Patel: analysis design, the pipeline, forecast, plan and dashboard; the review fixes (Back Forty story, leak rule, data guards).
  - Chintan Shah: the Databricks Free Edition deployment and run, the Genie agent, publishing the dashboard on GitHub Pages.
  - Khushi Shah: CI and the judge guardrails (`local/ci.py`, `local/judge_check.py`, GitHub Actions, git hooks).
- **Not used:** AI-generated data. All data comes from the challenge release and its cited public sources.
