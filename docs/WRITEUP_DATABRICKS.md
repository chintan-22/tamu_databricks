# Databricks challenge submission: "Luck, Location, or a Leak?"

*Submission to the Databricks track. The same project is also our Dashboard Royale entry; this text explains what Databricks does in it.*

## What we built

A casino floor-analytics system for The Gilded Ace, the fictional 300-machine casino from the Dashboard Royale challenge. The manager wanted to replace the 10 slot machines that earned the least. Our system decides whether each machine is truly weak or just unlucky, badly placed, often broken, or paying out off spec. It then prices a $100,000 action plan. A public dashboard shows the result. It is fed entirely by a Databricks lakehouse.

## How Databricks is used, and why each piece matters

| Databricks feature | What it does here | Why it makes the answer better |
|---|---|---|
| **Unity Catalog volume + Auto Loader** | Downloads the 22 release files, checks each against the release's SHA-256 manifest, and loads them incrementally into bronze streaming tables with source-file lineage | The challenge data is a `0.9.0-draft` release whose values may change before 1.0.0. One job re-run picks up the new release, and every number stays traceable to a file |
| **Lakeflow Declarative Pipeline** (52 tables: 22 bronze, 10 silver, 20 gold) | Turns raw meters into decision tables: the machine scorecard, downtime valued by hour, natural experiments, comp-change test, priced actions | The whole analysis is declarative SQL with dependencies managed for us, so nothing is a hand-run notebook cell |
| **Lakeflow expectations** | Each pitfall in the challenge guide is a rule. 1,018 off-floor machine-days are dropped, not counted as zero sales. The update **fails** if meters don't balance, if our six-part earnings breakdown doesn't sum exactly, or if the plan breaks the $100K / 3-action limit | Analytical correctness is enforced by the platform on every run, not checked by hand. The event log records every pass/fail count, and the dashboard shows them |
| **MLflow** | Logs five forecast candidates as runs and records the April-only selection, holdout metrics and a holdout plot | The model choice is reproducible and auditable: anyone can see that it was picked before the holdout was scored |
| **Unity Catalog model registry** | Registers the frozen forecast as `floor_coin_in_forecast` with the `champion` alias | The July plan and future runs use a governed, versioned model |
| **Genie** | A plain-English Q&A space over the gold tables, with instructions that encode the challenge's rules (ratio of sums, carded-only player data, "inspect, never accuse") | The manager can ask follow-up questions ("why is M-1158 low?") without SQL, and the answers follow the rules |
| **Asset Bundle + Job** | `databricks bundle deploy` / `run` builds everything: ingest → pipeline → MLflow training → export | One command reproduces the submission in any workspace, Free Edition included |

## Creative parts

- **Exact luck test.** We use each game's published payout variance (Var = Σ bet² × Var(payout ÷ bet)) to compute how far each machine's result could drift by chance. That separates luck from a leak: M-1158's hit rate sits 124 standard deviations above spec.
- **An earnings breakdown that adds up exactly.** Every machine's gap splits into luck, location, downtime, game appeal, hold setting and time on floor. A pipeline expectation proves the six parts sum to the gap.
- **Natural experiments in SQL.** A walkway closure, a block of new installs and a game swap are each measured against the rest of the floor over the same days (difference-in-differences).
- **One codebase, two engines.** The Lakeflow SQL files also run unchanged on DuckDB through a small runner that enforces the same expectations. The dashboard recomputes the scorecard in the browser for any date range and matches the pipeline exactly (0 of 310 verdicts differ).

## Result

Replacing the manager's list would cost about $27K and return about $12K in July. Our plan spends $50K (inspect the leak, lease new titles for the 10 truly weak earners, run one tested promotion) and keeps $50K. Expected July benefit is $91K, with a range of $34K–$152K.
