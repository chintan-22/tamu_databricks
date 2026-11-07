# Genie space: "Gilded Ace floor analyst"

Lets the general manager ask follow-up questions in plain English over the governed gold tables. Create it in the Databricks UI: **Genie → New → add tables**.

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
```

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
