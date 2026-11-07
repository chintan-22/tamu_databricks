# Luck, Location, or a Leak? — write-up

**The question.** The manager wants to replace the 10 lowest-earning machines from January–June 2025. We tested every machine against luck, location and leaks first.

**Method.** A Databricks Lakeflow pipeline (bronze → silver → gold) enforces the guide's pitfalls as data-quality rules: off-floor days are dropped, meters must balance, and gaming days follow the calendar through daylight saving. Each machine's gap to a typical machine splits exactly into luck, location, downtime, game appeal, hold setting and time on floor. Luck is tested from the published game math: Var(win) = Σbet² × Var(payout/bet). Location is handled by comparing each machine only with same-zone machines on the same day, per available hour.

**Findings.**
- Of the manager's 10: two are already retired and one is a 49-day-old install. **M-1158** hits 38.6% of spins against a 31.5% spec (z = +124): inspect it, don't replace it. Six sit in **Back Forty**, where any machine earns $26.7K less.
- Closing one walkway cut Back Forty play by **29%** against the rest of the floor. That's a traffic problem.
- The truly weak earners are **Royal Draw** machines (95% RTP) in busy zones, at 0.5× par. None is on the manager's list.
- Downtime cost $102K of theo (0.4%), 55% of it from Ridgeline.
- The top 5% of players generate 52% of tracked theo; 16% of players finished ahead.
- On May 1, comps got 55% cheaper in points. Reinvestment rose from 1.19% to 1.31% with no detectable lift in play.

**Model.** A weekday-profile forecast of daily coin-in was chosen on April, frozen on April 30, and scored once on May–June: MAE $68.7K against $218K for the constant baseline. It changes one decision. A single weekend can only reveal a lift of 11% or more, so we buy one promotion weekend and a second only if the first clears that bar.

**Plan: $50,000 spent, $50,000 kept.**
- Inspect M-1158: $1,200, expected benefit $5.8K
- Lease new titles for the 10 weakest Royal Draws: $33,800, expected $36.2K ($16K–$66K)
- One slot-tournament weekend, Jul 18–20: $15,000, expected $48.7K ($18K–$80K)

Each action comes with its own measurement plan. The manager's own list would cost $27K and return about $12K.

**Why Databricks.** Expectations make re-runs safe when release 1.0.0 lands. MLflow and Unity Catalog govern the forecast. Genie answers the manager's follow-up questions. One export feeds the public dashboard.
