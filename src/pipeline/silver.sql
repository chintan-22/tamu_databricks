-- =====================================================================================
-- SILVER: conformed, typed, analysis-safe tables.
-- Every "common mistake" from the challenge guide is encoded here once, as a join rule
-- or as a Lakeflow expectation, so no downstream query can repeat it:
--   * off-floor machine-days are dropped, not treated as zero sales
--   * money stays in integer cents until the gold layer
--   * event timestamps are mapped to the 06:00-06:00 gaming day through calendar_day
--     (handles the 23-hour DST day) instead of assuming 24 h
--   * meters must balance (house win = coin-in - payout) or the update fails
-- =====================================================================================

CREATE OR REFRESH MATERIALIZED VIEW silver_calendar
COMMENT 'Gaming days (06:00-06:00 local) with UTC bounds and scheduled seconds.'
AS SELECT
  gaming_date,
  gaming_day_start_utc,
  gaming_day_end_utc,
  scheduled_seconds,
  local_weekday,
  month,
  is_weekend,
  federal_holiday,
  gaming_date >= DATE'2025-05-01' AS is_holdout
FROM bronze_calendar_day;

CREATE OR REFRESH MATERIALIZED VIEW silver_locations
COMMENT 'Slot positions with their bank, zone and coordinates.'
AS SELECT
  s.location_id,
  s.bank_id,
  s.zone_id,
  z.name AS zone_name,
  s.x_m,
  s.y_m,
  b.x_m AS bank_x_m,
  b.y_m AS bank_y_m
FROM bronze_floor_locations s
JOIN bronze_floor_locations z ON z.location_id = s.zone_id
LEFT JOIN bronze_floor_locations b ON b.location_id = s.bank_id
WHERE s.node_type = 'slot';

CREATE OR REFRESH MATERIALIZED VIEW silver_machine_day (
  CONSTRAINT machine_on_floor EXPECT (active AND location_id IS NOT NULL) ON VIOLATION DROP ROW,
  CONSTRAINT meters_balance EXPECT (house_win_cents = coin_in_cents - payout_cents) ON VIOLATION FAIL UPDATE,
  CONSTRAINT availability_within_schedule EXPECT (available_seconds BETWEEN 0 AND scheduled_seconds),
  CONSTRAINT occupancy_within_availability EXPECT (occupied_seconds <= available_seconds),
  CONSTRAINT hits_within_spins EXPECT (payout_positive_spins <= paid_spins),
  CONSTRAINT known_location EXPECT (zone_id IS NOT NULL)
)
COMMENT 'One row per machine per gaming day while on the floor, with location, game math and luck variance.'
AS SELECT
  md.machine_id,
  md.gaming_date,
  c.month,
  c.local_weekday,
  c.is_weekend,
  c.federal_holiday,
  c.is_holdout,
  md.active,
  md.location_id,
  l.bank_id,
  l.zone_id,
  l.zone_name,
  md.config_id,
  gm.theme,
  gm.volatility_class,
  CAST(gm.configured_rtp AS DOUBLE) AS configured_rtp,
  CAST(gm.hit_probability AS DOUBLE) AS spec_hit_probability,
  m.manufacturer,
  m.lease_class,
  m.install_date,
  m.retire_date,
  c.scheduled_seconds AS day_seconds,
  md.scheduled_seconds,
  md.available_seconds,
  md.occupied_seconds,
  md.scheduled_seconds - md.available_seconds AS downtime_seconds,
  md.paid_spins,
  md.payout_positive_spins,
  md.coin_in_cents,
  md.payout_cents,
  md.house_win_cents,
  CAST(md.theo_cents AS DOUBLE) AS theo_cents,
  -- Var(house win) for one spin = bet^2 * Var(payout/bet); spins are independent.
  md.sum_bet_squared * CAST(gm.payout_multiplier_variance AS DOUBLE) AS win_variance_cents2,
  md.carded_coin_in_cents,
  md.carded_payout_cents,
  CAST(md.carded_theo_cents AS DOUBLE) AS carded_theo_cents,
  COALESCE(p.faults_opened, 0) AS faults_opened,
  CAST(p.lease_cost_usd AS DOUBLE) + CAST(p.service_cost_usd AS DOUBLE)
    + CAST(p.power_cost_usd AS DOUBLE) + CAST(p.repair_cost_usd AS DOUBLE) AS supplied_cost_usd
FROM bronze_machine_day md
JOIN silver_calendar c ON c.gaming_date = md.gaming_date
JOIN bronze_game_math gm ON gm.config_id = md.config_id
JOIN bronze_machines m ON m.machine_id = md.machine_id
LEFT JOIN silver_locations l ON l.location_id = md.location_id
LEFT JOIN bronze_prepared_daily_view p
  ON p.machine_id = md.machine_id AND p.gaming_date = md.gaming_date;

CREATE OR REFRESH MATERIALIZED VIEW silver_machine_hour (
  CONSTRAINT active_hour EXPECT (active) ON VIOLATION DROP ROW,
  CONSTRAINT availability_in_hour EXPECT (available_seconds BETWEEN 0 AND 3600)
)
COMMENT 'Hourly meters while installed, with the zone and local hour (for valuing downtime at the time it happened).'
AS SELECT
  h.machine_id,
  h.gaming_date,
  h.hour_start_utc,
  h.local_hour,
  c.is_weekend,
  h.active,
  h.location_id,
  l.zone_id,
  h.available_seconds,
  h.occupied_seconds,
  h.coin_in_cents,
  h.paid_spins
FROM bronze_machine_hour h
JOIN silver_calendar c ON c.gaming_date = h.gaming_date
LEFT JOIN silver_locations l ON l.location_id = h.location_id;

CREATE OR REFRESH MATERIALIZED VIEW silver_operations (
  CONSTRAINT ordered_timestamps EXPECT (down_hours >= 0 AND wait_hours >= 0) ON VIOLATION DROP ROW
)
COMMENT 'Repair/maintenance tickets on their gaming day, with the technician shift and wait vs. fix time.'
AS SELECT
  o.operation_id,
  o.machine_id,
  o.event_type,
  c.gaming_date,
  c.month,
  c.is_weekend,
  o.opened_at_utc,
  o.opened_at_local,
  hour(o.opened_at_local) AS local_hour,
  CASE
    WHEN hour(o.opened_at_local) >= 6 AND hour(o.opened_at_local) < 14 THEN 'day'
    WHEN hour(o.opened_at_local) >= 14 AND hour(o.opened_at_local) < 22 THEN 'swing'
    ELSE 'grave'
  END AS tech_shift,
  (unix_timestamp(o.work_started_at_utc) - unix_timestamp(o.opened_at_utc)) / 3600.0 AS wait_hours,
  (unix_timestamp(o.available_at_utc) - unix_timestamp(o.work_started_at_utc)) / 3600.0 AS fix_hours,
  (unix_timestamp(o.available_at_utc) - unix_timestamp(o.opened_at_utc)) / 3600.0 AS down_hours,
  o.direct_cost_cents / 100.0 AS direct_cost_usd,
  m.manufacturer,
  l.zone_id,
  l.zone_name
FROM bronze_operations o
JOIN silver_calendar c
  ON o.opened_at_utc >= c.gaming_day_start_utc AND o.opened_at_utc < c.gaming_day_end_utc
JOIN bronze_machines m ON m.machine_id = o.machine_id
LEFT JOIN silver_locations l ON l.location_id = o.location_id;

CREATE OR REFRESH MATERIALIZED VIEW silver_tech_roster
COMMENT 'Slot-technician headcount per gaming day and shift.'
AS SELECT
  gaming_date,
  shift AS tech_shift,
  planned_headcount,
  actual_headcount
FROM bronze_shift_roster
WHERE role = 'slot_tech';

CREATE OR REFRESH MATERIALIZED VIEW silver_redemptions (
  CONSTRAINT positive_cost EXPECT (economic_cost_cents > 0),
  CONSTRAINT points_spent EXPECT (points_spent > 0)
)
COMMENT 'Comp redemptions on their gaming day: points spent, house cost, menu value.'
AS SELECT
  r.loyalty_event_id,
  r.player_id,
  c.gaming_date,
  c.month,
  r.benefit_id,
  r.tier_before,
  -r.points_delta AS points_spent,
  r.economic_cost_cents,
  r.face_value_cents
FROM bronze_loyalty_ledger r
JOIN silver_calendar c
  ON r.event_at_utc >= c.gaming_day_start_utc AND r.event_at_utc < c.gaming_day_end_utc
WHERE r.event_type = 'redeem';

CREATE OR REFRESH MATERIALIZED VIEW silver_player_period (
  CONSTRAINT net_is_payout_minus_coin_in EXPECT (abs(tracked_net_usd - (tracked_payout_usd - tracked_coin_in_usd)) < 0.01)
)
COMMENT 'Tracked (carded) results per player per month. Carded play only.'
AS SELECT
  player_id,
  period_month AS month,
  home_region,
  COALESCE(age_band, 'unknown') AS age_band,
  opening_tier,
  tier_end,
  observed_visits,
  sessions,
  carded_play_hours,
  CAST(tracked_coin_in_usd AS DOUBLE) AS tracked_coin_in_usd,
  CAST(tracked_payout_usd AS DOUBLE) AS tracked_payout_usd,
  CAST(tracked_net_usd AS DOUBLE) AS tracked_net_usd,
  CAST(theo_usd AS DOUBLE) AS theo_usd,
  CAST(luck_residual_usd AS DOUBLE) AS luck_residual_usd,
  CAST(linked_pos_cash_usd AS DOUBLE) AS linked_pos_cash_usd,
  CAST(linked_pos_cogs_usd AS DOUBLE) AS linked_pos_cogs_usd,
  comps_redeemed,
  CAST(comp_face_value_usd AS DOUBLE) AS comp_face_value_usd,
  CAST(comp_cost_usd AS DOUBLE) AS comp_cost_usd,
  points_earned,
  points_redeemed,
  CAST(tracked_contribution_usd AS DOUBLE) AS tracked_contribution_usd
FROM bronze_player_period;

CREATE OR REFRESH MATERIALIZED VIEW silver_property_day
COMMENT 'Floor totals per gaming day with calendar, events and (real) NOAA weather.'
AS SELECT
  p.gaming_date,
  c.month,
  c.local_weekday,
  c.is_weekend,
  c.federal_holiday,
  c.is_holdout,
  c.scheduled_seconds,
  p.events_active,
  p.active_machines,
  CAST(p.coin_in_usd AS DOUBLE) AS coin_in_usd,
  CAST(p.house_win_usd AS DOUBLE) AS house_win_usd,
  CAST(p.theo_usd AS DOUBLE) AS theo_usd,
  p.available_machine_hours,
  p.occupied_machine_hours,
  p.carded_coin_in_share,
  CAST(p.pos_cash_usd AS DOUBLE) AS pos_cash_usd,
  CAST(p.pos_cogs_usd AS DOUBLE) AS pos_cogs_usd,
  CAST(p.comp_cost_usd AS DOUBLE) AS comp_cost_usd,
  CAST(p.comp_face_value_usd AS DOUBLE) AS comp_face_value_usd,
  p.faults_opened,
  p.total_zone_entries_observed,
  p.counter_coverage_share,
  CAST(p.contribution_after_supplied_costs_usd AS DOUBLE) AS contribution_usd,
  CAST(w.tmax_c AS DOUBLE) AS tmax_c,
  CAST(w.prcp_mm AS DOUBLE) AS prcp_mm
FROM bronze_property_day p
JOIN silver_calendar c ON c.gaming_date = p.gaming_date
LEFT JOIN bronze_weather_daily w ON w.source_date = p.gaming_date;

CREATE OR REFRESH MATERIALIZED VIEW silver_zone_traffic_day
COMMENT 'Door/zone counter entries per zone and gaming day. Missing hours are offline, not zero.'
AS SELECT
  t.zone_id,
  c.gaming_date,
  SUM(CASE WHEN t.counter_status <> 'offline' THEN t.entries_count END) AS entries_observed,
  SUM(t.coverage_minutes) / 60.0 AS coverage_hours,
  c.scheduled_seconds / 3600.0 AS day_hours
FROM bronze_zone_traffic_hourly t
JOIN silver_calendar c
  ON t.hour_start_utc >= c.gaming_day_start_utc AND t.hour_start_utc < c.gaming_day_end_utc
GROUP BY t.zone_id, c.gaming_date, c.scheduled_seconds;
