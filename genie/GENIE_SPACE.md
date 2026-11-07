# Genie space: "Gilded Ace floor analyst"

Lets the general manager ask follow-up questions in plain English over the governed gold tables.

## The agent is in git

The live agent's full configuration (tables, column settings, instructions; sample questions and example SQL once added) is exported to [`gilded_ace_floor_analyst.json`](gilded_ace_floor_analyst.json). You don't need the manual steps below:

```sh
python genie/genie_space.py create            # build the agent in your workspace from the JSON
python genie/genie_space.py export            # after editing the agent in the UI: save it back to the JSON, then commit
python genie/genie_space.py update SPACE_ID   # push the JSON over an existing agent
```

It uses the Databricks CLI (run `databricks auth login` first) and needs the pipeline tables to exist. Workspace-specific IDs are stripped, and the first SQL warehouse is used.

## Manual setup (what the JSON contains)

In the Databricks UI: **Genie Agents → New → Select tables manually → add the tables → Configure**.

## Tables to add (catalog `workspace`)

- Schema `gilded_ace`: `gold_machine_scorecard`, `gold_bank_summary`, `gold_zone_week`, `gold_floor_day`, `gold_downtime_lost`, `gold_repair_response`, `gold_manufacturer_reliability`, `gold_player_segment_month`, `gold_comp_month`, `gold_action_options`
- Schema `gilded_ace_ml`: `gold_forecast` (the notebooks write here because Free Edition caps a schema at 100 tables)

## General instructions (paste into the space)

```
You answer questions about The Gilded Ace, a FICTIONAL casino with synthetic data (Jan 1 - Jun 30, 2025).
- "Underperforming" means gold_machine_scorecard.fair_index well below 1.0 (theo vs same-zone peers with equal uptime), never raw house_win_usd.
- Luck: luck_z beyond -3.6 or |hit_rate_z| > 6 is "off spec - inspect", never "cheating".
- Ratios are ratio of sums: SUM(house_win)/SUM(coin_in), never AVG of daily ratios.
- Player tables are carded (tracked) play only; label player results "tracked".
- Comp cost is already inside POS cogs; never subtract it twice.
- Money columns ending _usd are dollars; _cents are cents.
- Never suggest marketing aimed at players by how much they lose.
- manager_rank ranks machines by raw house win (1 = lowest earner, the manager's list). fair_rank ranks by fair_index (1 = weakest for its spot). A machine can be low on manager_rank but normal on fair_rank; say which ranking you mean.
- fair_index near 1.0 means the machine earns normally for its zone. Location effects (location_usd) come from the zone the machine is in, not its position inside the zone.
- Explain a machine's gap with the six parts in gold_machine_scorecard: luck_usd, location_usd, downtime_usd, appeal_usd, hold_setting_usd and time on floor. Quote the largest ones in dollars.
- hit_rate_z and luck_z in gold_machine_scorecard already account for chance. If hit_rate_z > 6 or luck_z < -3.6, chance cannot explain the result: say so, quote observed_hit_rate vs spec_hit_probability and paid_spins, and recommend inspecting the payout. Never say it will regress to the mean or that variance could explain it.
```

These four lines were added after testing: without them Genie confused manager_rank with fair_rank, and called M-1158's off-spec payout "bad luck that should regress to the mean".

## Sample questions (add as examples)

1. Which 10 machines have the lowest fair index, and what is their main drag?
2. Why does M-1158 rank so low?
3. How much theo did Ridgeline downtime cost by month?
4. Compare Back Forty and Center Pit coin-in per machine-day by week.
5. What did comps cost per month, and what was the reinvestment rate?
6. Which actions in the plan have a positive expected net, and what do they cost?

## Trusted SQL (example)

```sql
-- "Is machine X truly weak?"
SELECT machine_id, zone_name, theme, manager_rank, fair_rank, fair_index, fair_index_lo, fair_index_hi,
       luck_z, hit_rate_z, largest_drag, verdict
FROM gold_machine_scorecard
WHERE machine_id = :machine_id
```
