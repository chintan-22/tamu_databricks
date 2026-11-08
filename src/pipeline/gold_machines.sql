-- =====================================================================================
-- GOLD · MACHINES — "luck, location, or a leak?"
--
-- For every machine we split the gap between its house win and a typical machine's
-- house win over the same 181 days into parts that add up exactly:
--
--   house_win_m - 181 * H_floor =
--       luck         sum(house_win - theo)                      (chance, or a payout leak)
--     + location     sum(zone theo/machine - floor theo/machine) (where it sits)
--     + downtime     extra downtime vs. zone peers, valued at the machine's own play rate
--     + appeal       coin-in vs. zone peers at peer hold, net of downtime (the game itself)
--     + hold_setting theo - coin-in * zone hold                  (game configured to hold less)
--     + exposure     days not on the floor (installed / retired mid-window) + floor-wide luck
--
-- All per-day comparisons use same-day peers, so a walkway closure or a busy weekend
-- moves the benchmark instead of being blamed on the machine.
-- =====================================================================================

CREATE OR REFRESH MATERIALIZED VIEW gold_zone_day
COMMENT 'Zone totals per gaming day: the same-day peer benchmark.'
AS SELECT
  zone_id,
  ANY_VALUE(zone_name) AS zone_name,
  gaming_date,
  COUNT(*) AS machines,
  SUM(coin_in_cents) AS coin_in_cents,
  SUM(theo_cents) AS theo_cents,
  SUM(house_win_cents) AS house_win_cents,
  SUM(available_seconds) AS available_seconds,
  SUM(scheduled_seconds) AS scheduled_seconds,
  SUM(downtime_seconds) AS downtime_seconds,
  SUM(occupied_seconds) AS occupied_seconds
FROM silver_machine_day
GROUP BY zone_id, gaming_date;

CREATE OR REFRESH MATERIALIZED VIEW gold_machine_day_components
COMMENT 'Per machine-day contribution of each explanation (cents); sums to the machine scorecard.'
AS WITH floor_day AS (
  SELECT gaming_date, COUNT(*) AS machines, SUM(theo_cents) AS theo_cents
  FROM silver_machine_day GROUP BY gaming_date
), machine_rate AS (
  SELECT machine_id, SUM(coin_in_cents) / NULLIF(SUM(available_seconds), 0) AS coin_in_per_available_second
  FROM silver_machine_day GROUP BY machine_id
)
SELECT
  d.machine_id,
  d.gaming_date,
  d.zone_id,
  d.bank_id,
  d.house_win_cents,
  d.theo_cents,
  d.house_win_cents - d.theo_cents AS luck_cents,
  z.theo_cents / z.machines - f.theo_cents / f.machines AS location_cents,
  d.theo_cents - d.coin_in_cents * (z.theo_cents / NULLIF(z.coin_in_cents, 0)) AS hold_setting_cents,
  -(d.downtime_seconds - d.scheduled_seconds * z.downtime_seconds / z.scheduled_seconds)
    * COALESCE(r.coin_in_per_available_second, 0) * (z.theo_cents / NULLIF(z.coin_in_cents, 0)) AS downtime_cents,
  (d.coin_in_cents - z.coin_in_cents / z.machines) * (z.theo_cents / NULLIF(z.coin_in_cents, 0))
    + (d.downtime_seconds - d.scheduled_seconds * z.downtime_seconds / z.scheduled_seconds)
      * COALESCE(r.coin_in_per_available_second, 0) * (z.theo_cents / NULLIF(z.coin_in_cents, 0)) AS appeal_cents,
  f.theo_cents / f.machines AS floor_theo_per_machine_cents,
  d.coin_in_cents,
  -- What a same-zone machine with the same uptime earned (theo) / took in (coin-in) that day.
  d.available_seconds * z.theo_cents / NULLIF(z.available_seconds, 0) AS zone_expected_theo_cents,
  d.available_seconds * z.coin_in_cents / NULLIF(z.available_seconds, 0) AS zone_expected_coin_in_cents
FROM silver_machine_day d
JOIN gold_zone_day z ON z.zone_id = d.zone_id AND z.gaming_date = d.gaming_date
JOIN floor_day f ON f.gaming_date = d.gaming_date
LEFT JOIN machine_rate r ON r.machine_id = d.machine_id;

CREATE OR REFRESH MATERIALIZED VIEW gold_machine_scorecard (
  CONSTRAINT decomposition_adds_up EXPECT (abs(gap_usd - (luck_usd + location_usd + downtime_usd + appeal_usd + hold_setting_usd + exposure_usd)) < 1.0) ON VIOLATION FAIL UPDATE
)
COMMENT 'One row per machine: manager rank vs. fair (luck- and location-adjusted) rank, statistical tests and the verdict.'
AS WITH window_days AS (
  SELECT COUNT(*) AS n_days FROM silver_calendar
), floor AS (
  SELECT SUM(house_win_cents) / COUNT(*) AS house_win_per_machine_day_cents FROM silver_machine_day
), m AS (
  SELECT
    d.machine_id,
    MAX_BY(d.zone_name, d.gaming_date) AS zone_name,
    MAX_BY(d.zone_id, d.gaming_date) AS zone_id,
    MAX_BY(d.bank_id, d.gaming_date) AS bank_id,
    MAX_BY(d.location_id, d.gaming_date) AS location_id,
    MAX_BY(d.config_id, d.gaming_date) AS config_id,
    MAX_BY(d.theme, d.gaming_date) AS theme,
    MAX_BY(d.volatility_class, d.gaming_date) AS volatility_class,
    MAX(d.manufacturer) AS manufacturer,
    MAX(d.lease_class) AS lease_class,
    MAX(d.retire_date) AS retire_date,
    MAX(d.install_date) AS install_date,
    COUNT(*) AS days_on_floor,
    COUNT(DISTINCT d.zone_id) AS zones_occupied,
    SUM(d.coin_in_cents) / 100.0 AS coin_in_usd,
    SUM(d.house_win_cents) / 100.0 AS house_win_usd,
    SUM(d.theo_cents) / 100.0 AS theo_usd,
    SUM(d.house_win_cents) / NULLIF(SUM(d.coin_in_cents), 0) AS observed_hold,
    SUM(d.theo_cents) / NULLIF(SUM(d.coin_in_cents), 0) AS theo_hold,
    SQRT(SUM(d.win_variance_cents2)) / 100.0 AS luck_sd_usd,
    SUM(d.paid_spins) AS paid_spins,
    SUM(d.payout_positive_spins) AS hit_spins,
    MAX(d.spec_hit_probability) AS spec_hit_probability,
    SUM(d.available_seconds) / SUM(d.scheduled_seconds) AS availability,
    SUM(d.occupied_seconds) / NULLIF(SUM(d.available_seconds), 0) AS occupancy,
    SUM(d.downtime_seconds) / 3600.0 AS downtime_hours,
    SUM(d.faults_opened) AS faults,
    SUM(d.house_win_cents) / 100.0 - SUM(d.supplied_cost_usd) AS contribution_usd
  FROM silver_machine_day d
  GROUP BY d.machine_id
), c0 AS (
  SELECT
    *,
    SUM(theo_cents) OVER (PARTITION BY machine_id)
      / NULLIF(SUM(zone_expected_theo_cents) OVER (PARTITION BY machine_id), 0) AS idx
  FROM gold_machine_day_components
), c AS (
  SELECT
    machine_id,
    SUM(luck_cents) / 100.0 AS luck_usd,
    SUM(location_cents) / 100.0 AS location_usd,
    SUM(downtime_cents) / 100.0 AS downtime_usd,
    SUM(appeal_cents) / 100.0 AS appeal_usd,
    SUM(hold_setting_cents) / 100.0 AS hold_setting_usd,
    SUM(floor_theo_per_machine_cents) / 100.0 AS floor_theo_on_days_usd,
    -- Fair index: theo (luck-free) vs. what same-zone, same-day peers earned with equal uptime.
    -- 1.0 = par for its spot. Accounts for luck, location, availability and time on floor.
    SUM(theo_cents) / NULLIF(SUM(zone_expected_theo_cents), 0) AS fair_index,
    -- Demand index: same comparison on coin-in (how much the game is played, ignoring hold).
    SUM(coin_in_cents) / NULLIF(SUM(zone_expected_coin_in_cents), 0) AS demand_index,
    -- ratio-estimator standard error of the fair index across days
    STDDEV_SAMP(theo_cents - zone_expected_theo_cents * idx) AS resid_sd_cents,
    AVG(zone_expected_theo_cents) AS mean_expected_cents,
    COUNT(*) AS n
  FROM c0
  GROUP BY machine_id
), scored AS (
  SELECT
    m.*,
    c.luck_usd,
    c.location_usd,
    c.downtime_usd,
    c.appeal_usd,
    c.hold_setting_usd,
    c.floor_theo_on_days_usd - w.n_days * f.house_win_per_machine_day_cents / 100.0 AS exposure_usd,
    m.house_win_usd - w.n_days * f.house_win_per_machine_day_cents / 100.0 AS gap_usd,
    w.n_days * f.house_win_per_machine_day_cents / 100.0 AS typical_machine_house_win_usd,
    c.fair_index,
    c.demand_index,
    c.resid_sd_cents / NULLIF(c.mean_expected_cents * SQRT(c.n), 0) AS fair_index_se,
    (m.house_win_usd - m.theo_usd) / NULLIF(m.luck_sd_usd, 0) AS luck_z,
    (m.hit_spins - m.paid_spins * m.spec_hit_probability)
      / NULLIF(SQRT(m.paid_spins * m.spec_hit_probability * (1 - m.spec_hit_probability)), 0) AS hit_rate_z,
    m.hit_spins / NULLIF(m.paid_spins, 0) AS observed_hit_rate
  FROM m
  JOIN c ON c.machine_id = m.machine_id
  CROSS JOIN window_days w
  CROSS JOIN floor f
)
SELECT
  s.*,
  RANK() OVER (ORDER BY s.house_win_usd ASC) AS manager_rank,
  RANK() OVER (ORDER BY s.fair_index ASC) AS fair_rank,
  s.fair_index - 1.96 * s.fair_index_se AS fair_index_lo,
  s.fair_index + 1.96 * s.fair_index_se AS fair_index_hi,
  CASE
    WHEN LEAST(s.luck_usd, s.location_usd, s.downtime_usd, s.appeal_usd, s.hold_setting_usd, s.exposure_usd) = s.luck_usd THEN 'luck'
    WHEN LEAST(s.luck_usd, s.location_usd, s.downtime_usd, s.appeal_usd, s.hold_setting_usd, s.exposure_usd) = s.location_usd THEN 'location'
    WHEN LEAST(s.luck_usd, s.location_usd, s.downtime_usd, s.appeal_usd, s.hold_setting_usd, s.exposure_usd) = s.downtime_usd THEN 'downtime'
    WHEN LEAST(s.luck_usd, s.location_usd, s.downtime_usd, s.appeal_usd, s.hold_setting_usd, s.exposure_usd) = s.appeal_usd THEN 'appeal'
    WHEN LEAST(s.luck_usd, s.location_usd, s.downtime_usd, s.appeal_usd, s.hold_setting_usd, s.exposure_usd) = s.hold_setting_usd THEN 'hold_setting'
    ELSE 'exposure'
  END AS largest_drag,
  CASE
    -- A paytable that pays far off its published spec is a leak to inspect, never a verdict.
    -- The hit-rate test is binomial and holds on any window. The luck test is a normal approximation
    -- of a jackpot-skewed sum, so it only counts on 150+ days: on 1-30 day windows it flagged
    -- 0.6-3 honest machines per window (local/check_dashboard.js checks this stays at 0).
    WHEN ABS(s.hit_rate_z) > 6 OR (s.luck_z < -3.6 AND s.days_on_floor >= 150) THEN 'Leak? Inspect payout'
    WHEN s.retire_date IS NOT NULL THEN 'Already retired'
    WHEN s.days_on_floor < 150 THEN 'New install (short exposure)'
    -- Weak earner: even after luck, location, uptime and tenure, it earns clearly (95% CI) under 85% of par.
    WHEN s.fair_index + 1.96 * s.fair_index_se < 0.85 AND s.hold_setting_usd < s.appeal_usd THEN 'Weak earner: low-hold game'
    WHEN s.fair_index + 1.96 * s.fair_index_se < 0.85 THEN 'Weak earner: low play'
    WHEN s.luck_usd < 0 AND s.luck_usd <= LEAST(s.location_usd, s.downtime_usd, s.appeal_usd, s.hold_setting_usd) THEN 'Unlucky'
    WHEN s.location_usd < 0 AND s.location_usd <= LEAST(s.downtime_usd, s.appeal_usd, s.hold_setting_usd) THEN 'Quiet location'
    WHEN s.downtime_usd < 0 AND s.downtime_usd <= LEAST(s.appeal_usd, s.hold_setting_usd) THEN 'Downtime'
    ELSE 'At or near par'
  END AS verdict
FROM scored s;

CREATE OR REFRESH MATERIALIZED VIEW gold_bank_summary
COMMENT 'Bank-level drill-down: performance per machine-day, uptime and the bank fair index.'
AS SELECT
  d.bank_id,
  ANY_VALUE(d.zone_name) AS zone_name,
  COUNT(DISTINCT d.machine_id) AS machines,
  COUNT(*) AS machine_days,
  SUM(d.coin_in_cents) / 100.0 / COUNT(*) AS coin_in_per_machine_day_usd,
  SUM(d.house_win_cents) / 100.0 / COUNT(*) AS house_win_per_machine_day_usd,
  SUM(d.theo_cents) / 100.0 / COUNT(*) AS theo_per_machine_day_usd,
  SUM(d.available_seconds) / SUM(d.scheduled_seconds) AS availability,
  SUM(d.occupied_seconds) / NULLIF(SUM(d.available_seconds), 0) AS occupancy,
  SUM(d.house_win_cents - d.theo_cents) / 100.0 AS luck_usd,
  SUM(d.faults_opened) AS faults
FROM silver_machine_day d
GROUP BY d.bank_id;
