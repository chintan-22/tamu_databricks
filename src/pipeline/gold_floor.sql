-- =====================================================================================
-- GOLD · FLOOR — what changed in demand over the six months, and why?
-- Natural experiments in the data are measured as difference-in-differences against the
-- rest of the floor, so floor-wide swings (seasonality, citywide tourism) cancel out.
-- =====================================================================================

CREATE OR REFRESH MATERIALIZED VIEW gold_floor_day
COMMENT 'Daily floor totals with traffic, weather and the citywide (real, LVCVA) monthly context.'
AS SELECT
  p.*,
  p.house_win_usd - p.theo_usd AS luck_usd,
  p.coin_in_usd / p.active_machines AS coin_in_per_machine_usd,
  v.visitor_volume AS city_visitors_month,
  v.visitor_yoy_ratio AS city_visitor_yoy,
  v.convention_attendance AS city_convention_attendance_month,
  CAST(v.hotel_occupancy_ratio AS DOUBLE) AS city_hotel_occupancy
FROM silver_property_day p
LEFT JOIN bronze_city_visitation_monthly v ON v.month = p.month;

CREATE OR REFRESH MATERIALIZED VIEW gold_zone_week
COMMENT 'Zone demand per ISO week: coin-in and theo per machine-day, occupancy and counter entries.'
AS WITH play AS (
  SELECT zone_id, ANY_VALUE(zone_name) AS zone_name,
    CAST(date_trunc('week', gaming_date) AS DATE) AS week_start,
    COUNT(*) AS machine_days,
    SUM(coin_in_cents) / 100.0 / COUNT(*) AS coin_in_per_machine_day_usd,
    SUM(theo_cents) / 100.0 / COUNT(*) AS theo_per_machine_day_usd,
    SUM(occupied_seconds) / NULLIF(SUM(available_seconds), 0) AS occupancy
  FROM silver_machine_day
  GROUP BY zone_id, CAST(date_trunc('week', gaming_date) AS DATE)
), traffic AS (
  SELECT zone_id, CAST(date_trunc('week', gaming_date) AS DATE) AS week_start,
    SUM(entries_observed) / NULLIF(SUM(coverage_hours), 0) * 24 AS entries_per_covered_day
  FROM silver_zone_traffic_day
  GROUP BY zone_id, CAST(date_trunc('week', gaming_date) AS DATE)
)
SELECT play.*, traffic.entries_per_covered_day
FROM play LEFT JOIN traffic USING (zone_id, week_start);

CREATE OR REFRESH MATERIALIZED VIEW gold_natural_experiments
COMMENT 'Difference-in-differences for three floor changes: the Back Forty walkway closure, the Aurora Link installs and the High-Limit game swap.'
AS WITH md AS (
  SELECT d.*, d.coin_in_cents / 100.0 AS coin_in_usd, d.theo_cents / 100.0 AS theo_usd FROM silver_machine_day d
), traffic AS (
  SELECT zone_id, gaming_date, entries_observed / NULLIF(coverage_hours, 0) * day_hours AS entries
  FROM silver_zone_traffic_day
), closure AS (
  -- Walkway W-ENT-B40 (Main Entrance <-> Back Forty) closed for renovation, gaming days 2025-03-03 .. 2025-04-06.
  SELECT
    'Back Forty walkway closure' AS experiment,
    'Back Forty' AS treated_group,
    'All other zones' AS control_group,
    'Gaming days 2025-03-03 to 2025-04-06 (walkway W-ENT-B40 closed) vs. the rest of Jan-Jun' AS window_note,
    AVG(CASE WHEN zone_id = 'Z-B40' AND gaming_date BETWEEN DATE'2025-03-03' AND DATE'2025-04-06' THEN coin_in_usd END) AS treated_during,
    AVG(CASE WHEN zone_id = 'Z-B40' AND NOT gaming_date BETWEEN DATE'2025-03-03' AND DATE'2025-04-06' THEN coin_in_usd END) AS treated_outside,
    AVG(CASE WHEN zone_id <> 'Z-B40' AND gaming_date BETWEEN DATE'2025-03-03' AND DATE'2025-04-06' THEN coin_in_usd END) AS control_during,
    AVG(CASE WHEN zone_id <> 'Z-B40' AND NOT gaming_date BETWEEN DATE'2025-03-03' AND DATE'2025-04-06' THEN coin_in_usd END) AS control_outside
  FROM md
), closure_traffic AS (
  SELECT
    'Back Forty walkway closure (door counters)' AS experiment,
    'Back Forty counter' AS treated_group,
    'All other counters' AS control_group,
    'Entries per covered day, same windows' AS window_note,
    AVG(CASE WHEN zone_id = 'Z-B40' AND gaming_date BETWEEN DATE'2025-03-03' AND DATE'2025-04-06' THEN entries END),
    AVG(CASE WHEN zone_id = 'Z-B40' AND NOT gaming_date BETWEEN DATE'2025-03-03' AND DATE'2025-04-06' THEN entries END),
    AVG(CASE WHEN zone_id <> 'Z-B40' AND gaming_date BETWEEN DATE'2025-03-03' AND DATE'2025-04-06' THEN entries END),
    AVG(CASE WHEN zone_id <> 'Z-B40' AND NOT gaming_date BETWEEN DATE'2025-03-03' AND DATE'2025-04-06' THEN entries END)
  FROM traffic
), aurora AS (
  -- Eight leased Aurora Link machines joined the Center Pit on 2025-03-24: did they pull play from neighbours?
  SELECT
    'Aurora Link installs: neighbour cannibalisation' AS experiment,
    'Other Center Pit machines' AS treated_group,
    'Machines in all other zones' AS control_group,
    'After 2025-03-24 vs. before, coin-in per machine-day' AS window_note,
    AVG(CASE WHEN zone_id = 'Z-PIT' AND theme <> 'Aurora Link' AND gaming_date >= DATE'2025-03-24' THEN coin_in_usd END),
    AVG(CASE WHEN zone_id = 'Z-PIT' AND theme <> 'Aurora Link' AND gaming_date < DATE'2025-03-24' THEN coin_in_usd END),
    AVG(CASE WHEN zone_id <> 'Z-PIT' AND gaming_date >= DATE'2025-03-24' THEN coin_in_usd END),
    AVG(CASE WHEN zone_id <> 'Z-PIT' AND gaming_date < DATE'2025-03-24' THEN coin_in_usd END)
  FROM md
), high_limit AS (
  -- M-1118 (Platinum Reels, $5-$25 bets) retired 2025-02-25; M-1532 (Classic Sevens, $1-$3) took over.
  SELECT
    'High-Limit game swap (Platinum Reels -> Classic Sevens)' AS experiment,
    'High-Limit Room' AS treated_group,
    'All other zones' AS control_group,
    'From 2025-02-25 vs. before, coin-in per machine-day' AS window_note,
    AVG(CASE WHEN zone_id = 'Z-HL' AND gaming_date >= DATE'2025-02-25' THEN coin_in_usd END),
    AVG(CASE WHEN zone_id = 'Z-HL' AND gaming_date < DATE'2025-02-25' THEN coin_in_usd END),
    AVG(CASE WHEN zone_id <> 'Z-HL' AND gaming_date >= DATE'2025-02-25' THEN coin_in_usd END),
    AVG(CASE WHEN zone_id <> 'Z-HL' AND gaming_date < DATE'2025-02-25' THEN coin_in_usd END)
  FROM md
), unioned AS (
  SELECT * FROM closure
  UNION ALL SELECT * FROM closure_traffic
  UNION ALL SELECT * FROM aurora
  UNION ALL SELECT * FROM high_limit
)
SELECT
  *,
  treated_during / treated_outside - 1 AS treated_change,
  control_during / control_outside - 1 AS control_change,
  (treated_during / treated_outside) / (control_during / control_outside) - 1 AS did_effect
FROM unioned;

CREATE OR REFRESH MATERIALIZED VIEW gold_event_lift
COMMENT 'Coin-in on each event day vs. the median of same-weekday, non-event days in the same month window.'
AS WITH base AS (
  SELECT local_weekday, PERCENTILE_APPROX(coin_in_usd, 0.5) AS median_coin_in
  FROM silver_property_day
  WHERE events_active IS NULL AND federal_holiday IS NULL
  GROUP BY local_weekday
), ev AS (
  SELECT e.event_id, e.name, e.event_type, e.local_scope, e.start_date, e.end_date, p.gaming_date, p.local_weekday, p.coin_in_usd
  FROM bronze_events e
  JOIN silver_property_day p ON p.gaming_date BETWEEN e.start_date AND e.end_date
)
SELECT
  ev.event_id, ev.name, ev.event_type, ev.local_scope, ev.start_date, ev.end_date,
  COUNT(*) AS days,
  SUM(ev.coin_in_usd) AS coin_in_usd,
  SUM(b.median_coin_in) AS baseline_coin_in_usd,
  SUM(ev.coin_in_usd) / SUM(b.median_coin_in) - 1 AS lift
FROM ev JOIN base b ON b.local_weekday = ev.local_weekday
GROUP BY ev.event_id, ev.name, ev.event_type, ev.local_scope, ev.start_date, ev.end_date;
