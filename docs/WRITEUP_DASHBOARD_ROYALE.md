# Luck, Location, or a Leak?

[Live dashboard](https://chintan-22.github.io/tamu_databricks/)

**The question.** The Gilded Ace, a fictional casino, wants to replace the 10 slot machines that earned least in January–June 2025. We first tested every machine for luck, location and leaks.

**Method.** A Databricks Lakeflow pipeline enforces the guide's pitfalls as data-quality rules: off-floor days are dropped, meters must balance, and gaming days follow daylight saving. Each machine's gap to a typical machine splits exactly into luck, location, downtime, game appeal, hold setting and time on floor. Luck compares actual win with theo, the win the game math expects, using each game's published payout variance. Location: each machine is compared only with same-zone machines on the same days, per available hour.

**Findings.**
- Of the manager's 10, two are retired and one is a 49-day-old install. **M-1158** hits 38.6% of spins against a 31.5% spec (z = +124), every week: inspect, don't replace.
- The other six are weak for their spot, but in **Back Forty** any machine earns $26.7K less (closing one walkway cut play there 29%), so a new title adds $103/day of theo there vs $226 in busy zones.
- Our replacement targets are **Royal Draw** machines (95% RTP) in busy zones, earning half of what their spot should.
- Downtime cost $102K of theo (0.4%), 55% of it from Ridgeline.
- The top 5% of players generate 52% of tracked theo; 16% of players finished ahead.
- On May 1 comps got 53% cheaper overnight (Apr 30 → May 1; 56% on Jan–Apr vs. May–Jun averages); reinvestment rose 1.19% → 1.31% with no detectable play lift.

**Model.** A weekday forecast of daily coin-in was chosen on April, frozen on April 30, and scored once on May–June: MAE $68.7K against $218K for the constant baseline. It changes one decision: a single weekend can only reveal a lift of 11%+, so we buy one promotion weekend, not two.

**Plan: $50,000 spent, $50,000 kept.** Each action: cost, expected July theo (range), measurement.
- Inspect M-1158: $1,200, expected $5.8K ($0–$7.2K); verify the paytable, then chart weekly hit rate.
- Lease new titles for the 10 Royal Draws that gain most: $33,800, expected $36.2K ($16K–$66K); track each spot against its zone.
- One slot-tournament weekend, Jul 18–20: $15,000, expected $48.7K ($18K–$80K); compare coin-in with the frozen forecast.

The manager's own list would cost $27K and return about $12K.
