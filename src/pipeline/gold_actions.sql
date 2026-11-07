-- =====================================================================================
-- GOLD · ACTIONS — pricing every option for the $100,000 / 30-day budget (July 1-30, 2025).
--
-- cost   = quantity x (unit_cost + recurring_per_day x max(0, 30 - lead_days))   (catalogue rule)
-- benefit= expected extra theo (or avoided cost) on the days left after the lead time,
--          valued at the most recent 8 weeks' run rate (May 6 - Jun 30), with a low / base /
--          high range whose assumptions are stated row by row.
-- Every evidence column points at the gold table the number comes from.
-- =====================================================================================

CREATE OR REFRESH MATERIALIZED VIEW gold_action_options
COMMENT 'Every candidate action, priced with the catalogue rule, with low/base/high benefit, break-even and evidence.'
AS WITH cat AS (
  SELECT action_type_id, name, unit_cost_cents / 100.0 AS unit_cost, recurring_cost_cents_per_day / 100.0 AS per_day,
    lead_days, GREATEST(0, 30 - lead_days) AS effective_days, quantity_limit
  FROM bronze_action_catalog
), recent AS (
  SELECT * FROM silver_machine_day WHERE gaming_date >= DATE'2025-05-06'
), recent_days AS (
  SELECT COUNT(DISTINCT gaming_date) AS n FROM recent
),
-- 1 · Inspect: only machines whose results are off spec beyond chance across 310 tests.
-- (The next most extreme machines sit at |z| ~ 2.8, which 310 honest machines produce by chance.)
inspect_targets AS (
  SELECT machine_id, luck_usd, days_on_floor, verdict
  FROM gold_machine_scorecard
  WHERE retire_date IS NULL AND verdict LIKE 'Leak%'
), inspect AS (
  SELECT 'A-INSPECT' AS action_type_id, COUNT(*) AS quantity,
    ARRAY_JOIN(COLLECT_LIST(machine_id), ', ') AS targets,
    0.0 AS benefit_low,
    SUM(CASE WHEN verdict LIKE 'Leak%' THEN GREATEST(0, -luck_usd) / days_on_floor ELSE 0 END) AS benefit_per_day_base,
    SUM(GREATEST(0, -luck_usd) / days_on_floor) * 1.25 AS benefit_per_day_high,
    'gold_machine_scorecard: M-1158 hits 38.6% of spins vs the 31.5% its published paytable allows, over 674k spins (z = +124), and held 3.0% vs 10% theo (luck z = -4.6, beyond the 3.6 cut-off for 310 machines). No other machine is off spec beyond chance.' AS evidence,
    'Base: the paytable is off spec and is corrected the day after inspection, recovering the machine''s average daily shortfall vs theo for 29 days. Low: nothing is found (it was extreme luck). High: the shortfall was growing (Mar-May hold ran near 0%), +25%.' AS assumption,
    'Paytable/RTP verification report per machine; then weekly hit rate vs spec (control chart, z within +/-3) and hold vs theo.' AS measurement
  FROM inspect_targets
),
-- 2 · Lease-replace the weakest earners (fair index, not raw house win) ----------------
aurora AS (
  SELECT AVG(fair_index) AS new_title_index FROM gold_machine_scorecard WHERE theme = 'Aurora Link'
), replace_targets AS (
  SELECT machine_id, zone_name, theme, fair_index, a.new_title_index,
    theo_usd / days_on_floor AS theo_per_day,
    theo_usd / days_on_floor * (1 / fair_index - 1) AS gain_per_day_at_par
  FROM gold_machine_scorecard CROSS JOIN aurora a
  WHERE verdict LIKE 'Weak earner%' AND retire_date IS NULL AND days_on_floor >= 150
  ORDER BY theo_usd / days_on_floor * (1 / fair_index - 1) DESC
  LIMIT 10
), replace_fair AS (
  SELECT 'A-REPLACE-LEASE' AS action_type_id, COUNT(*) AS quantity,
    ARRAY_JOIN(COLLECT_LIST(machine_id), ', ') AS targets,
    SUM(theo_per_day * (0.75 / fair_index - 1)) AS benefit_per_day_low,
    SUM(gain_per_day_at_par) AS benefit_per_day_base,
    SUM(theo_per_day * (new_title_index / fair_index - 1)) AS benefit_per_day_high,
    'gold_machine_scorecard: these earn about half the theo of same-zone peers with equal uptime (fair index ~0.5, 95% CI width < 0.02); Royal Draw''s 95% RTP does not buy extra play (demand index ~1.0). New leased Aurora Link titles run at 1.37x par with no cannibalisation of neighbours (gold_natural_experiments: +1.6%).' AS evidence,
    'Base: the new title earns par for its zone (index 1.0). Low: it reaches only 0.75 of par. High: it matches the Aurora Link installs (~1.37). 16 operating days after the 14-day lead; 6 h install downtime ignored (<0.1%).' AS assumption,
    'Weekly fair index of each replaced position vs. its zone (target >= 0.9 by week 3), against the remaining weak earners as a holdout group.' AS measurement
  FROM replace_targets
),
-- 2b · The manager's original plan, for comparison -----------------------------------
manager_targets AS (
  -- the two already-retired machines on the manager's list cannot be replaced
  SELECT s.machine_id, s.fair_index, s.theo_usd / s.days_on_floor AS theo_per_day, a.new_title_index
  FROM gold_machine_scorecard s CROSS JOIN aurora a
  WHERE s.manager_rank <= 10 AND s.retire_date IS NULL
), replace_manager AS (
  SELECT 'A-REPLACE-LEASE (manager bottom 10)' AS action_type_id,
    COUNT(*) AS quantity,
    ARRAY_JOIN(COLLECT_LIST(machine_id), ', ') AS targets,
    SUM(theo_per_day * (0.75 / fair_index - 1)) AS benefit_per_day_low,
    SUM(theo_per_day * (1 / fair_index - 1)) AS benefit_per_day_base,
    SUM(theo_per_day * (new_title_index / fair_index - 1)) AS benefit_per_day_high,
    'gold_machine_scorecard: of the 10 lowest raw earners, 2 are already retired, 1 is a 49-day-old install, 1 is a payout leak, and every Back Forty machine carries a -$26.7k location drag that a new cabinet in the same slot would inherit.' AS evidence,
    'Same scenario rules as the fair plan; retired machines cannot be replaced.' AS assumption,
    'Not recommended.' AS measurement
  FROM manager_targets
),
-- 3 · Wayfinding for Back Forty ------------------------------------------------------
b40 AS (
  SELECT SUM(theo_cents) / 100.0 / MAX(rd.n) AS theo_per_day FROM recent CROSS JOIN recent_days rd WHERE zone_id = 'Z-B40'
), closure AS (
  SELECT did_effect FROM gold_natural_experiments WHERE experiment = 'Back Forty walkway closure'
), wayfinding AS (
  SELECT 'A-WAYFINDING' AS action_type_id, 1 AS quantity, 'Back Forty (Z-B40)' AS targets,
    0.0 AS benefit_per_day_low,
    0.05 * b40.theo_per_day AS benefit_per_day_base,
    0.10 * b40.theo_per_day AS benefit_per_day_high,
    CONCAT('gold_natural_experiments: when walkway W-ENT-B40 closed (Mar 3 - Apr 6) Back Forty coin-in fell ',
      CAST(ROUND(-100 * closure.did_effect, 0) AS STRING), '% vs. the rest of the floor and its door counter fell by the same share; play there tracks foot traffic. Back Forty is the largest location drag in the scorecard.') AS evidence,
    'Base: signage recovers a 5% lift in Back Forty play (about a sixth of the access effect measured during the closure). Low: no effect. High: 10%. 20 days after the 10-day lead.' AS assumption,
    'Difference-in-differences: Back Forty coin-in per machine-day and door-counter entries vs. other zones, 4 weeks before vs. after install.' AS measurement
  FROM b40 CROSS JOIN closure
),
-- 4 · Promotion weekend --------------------------------------------------------------
weekend AS (
  SELECT AVG(theo_usd) * 3 AS theo_per_weekend
  FROM silver_property_day WHERE gaming_date >= DATE'2025-05-06' AND local_weekday IN ('Fri', 'Sat', 'Sun') AND events_active IS NULL
), promo_lift AS (
  SELECT MIN(lift) AS lo, AVG(lift) AS mid, MAX(lift) AS hi FROM gold_event_lift WHERE local_scope = 'property'
), promo AS (
  SELECT 'A-PROMO' AS action_type_id, 1 AS quantity, 'One slot-tournament weekend, Jul 18-20 (first weekend after the 14-day lead)' AS targets,
    p.lo * w.theo_per_weekend AS benefit_low,
    p.mid * w.theo_per_weekend AS benefit_base,
    p.hi * w.theo_per_weekend AS benefit_high,
    'gold_event_lift: the Winter Slot Tournament lifted coin-in 18% over same-weekday medians; Locals Appreciation Week only 4%. No sign the lift was borrowed: the 7 days before/after the tournament ran +0.9% / -0.1% vs. their medians. Two observations only.' AS evidence,
    'Low/base/high = the lowest, mean and highest lift seen at the two property promotions, applied to a recent non-event Fri-Sun. Prizes and marketing are inside the catalogue price. Run one weekend first; the second unit is only bought if the first clears break-even.' AS assumption,
    'Coin-in vs. the validated weekday forecast (gold_forecast) for the promo weekend and the two weekends either side.' AS measurement
  FROM weekend w CROSS JOIN promo_lift p
),
-- 5 · Another grave-shift technician --------------------------------------------------
grave AS (
  SELECT
    SUM(CASE WHEN tech_shift = 'grave' THEN fault_tickets END) / 181.0 AS tickets_per_day,
    SUM(CASE WHEN tech_shift = 'grave' THEN total_wait_hours END) / SUM(CASE WHEN tech_shift = 'grave' THEN fault_tickets END) AS grave_wait,
    SUM(CASE WHEN tech_shift = 'grave' THEN lost_theo_usd END) / SUM(CASE WHEN tech_shift = 'grave' THEN downtime_hours END) AS theo_per_down_hour
  FROM gold_repair_response
), two_tech AS (
  SELECT AVG(avg_wait_hours) AS wait FROM gold_wait_vs_staffing WHERE techs_on_shift = 2
), tech AS (
  SELECT 'A-TECH-SHIFT' AS action_type_id, 1 AS quantity, 'Grave shift (22:00-06:00), the only shift with one technician' AS targets,
    0.0 AS benefit_per_day_low,
    g.tickets_per_day * (g.grave_wait - t.wait) * g.theo_per_down_hour AS benefit_per_day_base,
    g.tickets_per_day * g.grave_wait * g.theo_per_down_hour AS benefit_per_day_high,
    'gold_repair_response / gold_wait_vs_staffing: grave-shift faults wait ~2.0 h for a tech vs ~0.1 h when two techs are on; but a grave downtime hour costs only ~$16 of theo.' AS evidence,
    'Base: grave wait falls to the two-tech level. High: grave wait disappears. 23 days after the 7-day lead.' AS assumption,
    'Ticket wait time (opened -> work started) by shift.' AS measurement
  FROM grave g CROSS JOIN two_tech t
),
-- 6 · Preventive maintenance for Ridgeline ------------------------------------------
ridge AS (
  SELECT r.lost_theo_usd / 181.0 + r.repair_cost_usd / 181.0 AS cost_per_day,
    1 - n.faults_per_100_machine_days / r.faults_per_100_machine_days AS gap_to_northwind
  FROM gold_manufacturer_reliability r CROSS JOIN gold_manufacturer_reliability n
  WHERE r.manufacturer = 'Ridgeline' AND n.manufacturer = 'Northwind'
), preventive AS (
  SELECT 'A-PREVENTIVE' AS action_type_id, 1 AS quantity, 'Ridgeline (94 machines)' AS targets,
    0.0 AS benefit_per_day_low,
    0.25 * cost_per_day AS benefit_per_day_base,
    gap_to_northwind * cost_per_day AS benefit_per_day_high,
    'gold_manufacturer_reliability: Ridgeline fails 4.0 times per 100 machine-days vs 1.1-1.7 for the others; 55% of lost theo and $118k of repair cost in six months.' AS evidence,
    'Base: the sweep cuts Ridgeline faults 25% for the rest of July (no maintenance outcome history exists to calibrate this). High: down to Northwind''s fault rate. Value = lost theo + direct repair cost avoided. 23 days after the 7-day lead.' AS assumption,
    'Ridgeline faults per 100 machine-days vs. Northwind and Halcyon, 4 weeks before vs. after.' AS measurement
  FROM ridge
),
-- 7/8 · Comp policy -----------------------------------------------------------------
comp AS (
  SELECT
    MAX(CASE WHEN period = 'after' THEN comp_cost_per_day END) - MAX(CASE WHEN period = 'before' THEN comp_cost_per_day END) AS extra_cost_per_day,
    MAX(CASE WHEN period = 'after' THEN carded_share END) - MAX(CASE WHEN period = 'before' THEN carded_share END) AS carded_share_change
  FROM gold_comp_change_test
), comp_pilot AS (
  SELECT 'A-COMP-PILOT' AS action_type_id, 1 AS quantity, 'Random half of card holders back at ~12.5 points per comp dollar; other half stays at 5.8' AS targets,
    0.0 AS benefit_per_day_low, 0.5 * c.extra_cost_per_day AS benefit_per_day_base, 0.5 * c.extra_cost_per_day AS benefit_per_day_high,
    'gold_comp_change_test: the May 1 cut (12.3 -> 5.7 points per comp dollar) raised comp cost ~$78/day and reinvestment 1.19% -> 1.31%; carded share of play moved +0.5 pt, inside normal month-to-month noise.' AS evidence,
    'Financial value in July is small; the value is a causal answer on whether cheaper comps buy play.' AS assumption,
    'Randomised: visits, carded theo and comp cost per player, treatment vs control, 4 weeks.' AS measurement
  FROM comp c
),
priced AS (
  SELECT o.action_type_id, cat.name, o.quantity, o.targets,
    o.quantity * (cat.unit_cost + cat.per_day * cat.effective_days) AS cost_usd,
    cat.lead_days, cat.effective_days,
    o.benefit_per_day_low * cat.effective_days AS benefit_low_usd,
    o.benefit_per_day_base * cat.effective_days AS benefit_base_usd,
    o.benefit_per_day_high * cat.effective_days AS benefit_high_usd,
    o.evidence, o.assumption, o.measurement
  FROM (
    SELECT action_type_id, quantity, targets, benefit_low AS benefit_per_day_low, benefit_per_day_base, benefit_per_day_high, evidence, assumption, measurement FROM inspect
    UNION ALL SELECT action_type_id, quantity, targets, benefit_per_day_low, benefit_per_day_base, benefit_per_day_high, evidence, assumption, measurement FROM replace_fair
    UNION ALL SELECT action_type_id, quantity, targets, benefit_per_day_low, benefit_per_day_base, benefit_per_day_high, evidence, assumption, measurement FROM replace_manager
    UNION ALL SELECT action_type_id, quantity, targets, benefit_per_day_low, benefit_per_day_base, benefit_per_day_high, evidence, assumption, measurement FROM wayfinding
    UNION ALL SELECT action_type_id, quantity, targets, benefit_per_day_low, benefit_per_day_base, benefit_per_day_high, evidence, assumption, measurement FROM tech
    UNION ALL SELECT action_type_id, quantity, targets, benefit_per_day_low, benefit_per_day_base, benefit_per_day_high, evidence, assumption, measurement FROM preventive
    UNION ALL SELECT action_type_id, quantity, targets, benefit_per_day_low, benefit_per_day_base, benefit_per_day_high, evidence, assumption, measurement FROM comp_pilot
  ) o
  JOIN cat ON cat.action_type_id = CASE WHEN o.action_type_id LIKE 'A-REPLACE-LEASE%' THEN 'A-REPLACE-LEASE' ELSE o.action_type_id END
  UNION ALL
  -- the promotion's benefit is a whole-weekend amount, not a daily rate
  SELECT p.action_type_id, cat.name, p.quantity, p.targets, cat.unit_cost, cat.lead_days, cat.effective_days,
    p.benefit_low, p.benefit_base, p.benefit_high, p.evidence, p.assumption, p.measurement
  FROM promo p JOIN cat ON cat.action_type_id = 'A-PROMO'
)
SELECT *,
  benefit_base_usd - cost_usd AS net_base_usd,
  cost_usd / NULLIF(benefit_base_usd, 0) AS cost_to_benefit,
  -- Chosen: one action per real cause found (leak -> inspect, weak game -> replace) plus the
  -- best-evidenced demand lever. Wayfinding is the runner-up (assumed, not observed, uplift).
  action_type_id IN ('A-INSPECT', 'A-REPLACE-LEASE', 'A-PROMO') AS recommended
FROM priced;

CREATE OR REFRESH MATERIALIZED VIEW gold_action_plan (
  CONSTRAINT within_budget EXPECT (total_cost_usd <= 100000) ON VIOLATION FAIL UPDATE,
  CONSTRAINT at_most_three_types EXPECT (action_types <= 3) ON VIOLATION FAIL UPDATE
)
COMMENT 'The recommended plan: up to three action types within $100,000, with the unspent remainder kept.'
AS SELECT
  COUNT(*) AS action_types,
  SUM(cost_usd) AS total_cost_usd,
  100000 - SUM(cost_usd) AS budget_kept_usd,
  SUM(benefit_low_usd) AS benefit_low_usd,
  SUM(benefit_base_usd) AS benefit_base_usd,
  SUM(benefit_high_usd) AS benefit_high_usd
FROM gold_action_options
WHERE recommended;
