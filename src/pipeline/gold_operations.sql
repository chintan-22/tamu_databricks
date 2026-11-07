-- =====================================================================================
-- GOLD · OPERATIONS — how much play was lost to downtime, when, and why?
--
-- Downtime is valued at the hour it happened: each lost machine-second is priced at the
-- coin-in an available machine in the same zone, at the same local hour and day type
-- (weekday/weekend), actually took in. Lost theo = lost coin-in x the machine's
-- configured hold. A 3 a.m. outage in Back Forty therefore costs far less than a
-- Saturday-night outage at the Main Entrance.
-- =====================================================================================

CREATE OR REFRESH MATERIALIZED VIEW gold_play_rate_zone_hour
COMMENT 'Coin-in per available machine-second by zone, local hour and day type (the price of an idle second).'
AS SELECT
  zone_id,
  local_hour,
  is_weekend,
  SUM(coin_in_cents) / NULLIF(SUM(available_seconds), 0) AS coin_in_cents_per_available_second,
  SUM(occupied_seconds) / NULLIF(SUM(available_seconds), 0) AS occupancy
FROM silver_machine_hour
GROUP BY zone_id, local_hour, is_weekend;

CREATE OR REFRESH MATERIALIZED VIEW gold_downtime_lost (
  CONSTRAINT nonnegative_loss EXPECT (lost_theo_usd >= 0)
)
COMMENT 'Lost play from downtime by gaming day, zone, manufacturer and technician shift.'
AS SELECT
  h.gaming_date,
  d.month,
  h.zone_id,
  d.zone_name,
  d.manufacturer,
  CASE
    WHEN h.local_hour >= 6 AND h.local_hour < 14 THEN 'day'
    WHEN h.local_hour >= 14 AND h.local_hour < 22 THEN 'swing'
    ELSE 'grave'
  END AS tech_shift,
  SUM(3600 - h.available_seconds) / 3600.0 AS downtime_hours,
  SUM((3600 - h.available_seconds) * r.coin_in_cents_per_available_second) / 100.0 AS lost_coin_in_usd,
  SUM((3600 - h.available_seconds) * r.coin_in_cents_per_available_second * (1 - d.configured_rtp)) / 100.0 AS lost_theo_usd
FROM silver_machine_hour h
JOIN silver_machine_day d ON d.machine_id = h.machine_id AND d.gaming_date = h.gaming_date
JOIN gold_play_rate_zone_hour r
  ON r.zone_id = h.zone_id AND r.local_hour = h.local_hour AND r.is_weekend = h.is_weekend
WHERE h.available_seconds < 3600
GROUP BY h.gaming_date, d.month, h.zone_id, d.zone_name, d.manufacturer,
  CASE
    WHEN h.local_hour >= 6 AND h.local_hour < 14 THEN 'day'
    WHEN h.local_hour >= 14 AND h.local_hour < 22 THEN 'swing'
    ELSE 'grave'
  END;

CREATE OR REFRESH MATERIALIZED VIEW gold_repair_response
COMMENT 'Fault tickets by month and technician shift: wait for a tech vs. time to fix, against slot-tech headcount.'
AS WITH tickets AS (
  SELECT
    month,
    tech_shift,
    COUNT(*) AS fault_tickets,
    AVG(wait_hours) AS avg_wait_hours,
    PERCENTILE_APPROX(wait_hours, 0.9) AS p90_wait_hours,
    AVG(fix_hours) AS avg_fix_hours,
    SUM(wait_hours) AS total_wait_hours,
    SUM(down_hours) AS total_down_hours,
    SUM(direct_cost_usd) AS repair_cost_usd
  FROM silver_operations
  WHERE event_type = 'fault_repair'
  GROUP BY month, tech_shift
), roster AS (
  SELECT c.month, r.tech_shift,
    AVG(r.planned_headcount) AS planned_techs,
    AVG(r.actual_headcount) AS actual_techs,
    SUM(CASE WHEN r.actual_headcount < r.planned_headcount THEN 1 ELSE 0 END) AS short_staffed_shifts
  FROM silver_tech_roster r
  JOIN silver_calendar c ON c.gaming_date = r.gaming_date
  GROUP BY c.month, r.tech_shift
), lost AS (
  SELECT month, tech_shift, SUM(lost_theo_usd) AS lost_theo_usd, SUM(downtime_hours) AS downtime_hours
  FROM gold_downtime_lost
  GROUP BY month, tech_shift
)
SELECT t.*, r.planned_techs, r.actual_techs, r.short_staffed_shifts, l.lost_theo_usd, l.downtime_hours
FROM tickets t
LEFT JOIN roster r ON r.month = t.month AND r.tech_shift = t.tech_shift
LEFT JOIN lost l ON l.month = t.month AND l.tech_shift = t.tech_shift;

CREATE OR REFRESH MATERIALIZED VIEW gold_wait_vs_staffing
COMMENT 'Each fault ticket matched to the techs actually on shift when it opened: does short staffing slow response?'
AS SELECT
  o.tech_shift,
  r.actual_headcount AS techs_on_shift,
  r.actual_headcount < r.planned_headcount AS short_staffed,
  COUNT(*) AS fault_tickets,
  AVG(o.wait_hours) AS avg_wait_hours,
  AVG(o.fix_hours) AS avg_fix_hours
FROM silver_operations o
JOIN silver_tech_roster r ON r.gaming_date = o.gaming_date AND r.tech_shift = o.tech_shift
WHERE o.event_type = 'fault_repair'
GROUP BY o.tech_shift, r.actual_headcount, r.actual_headcount < r.planned_headcount;

CREATE OR REFRESH MATERIALIZED VIEW gold_manufacturer_reliability
COMMENT 'Reliability by manufacturer: faults per 100 machine-days, availability, lost theo and repair cost.'
AS WITH md AS (
  SELECT manufacturer, COUNT(DISTINCT machine_id) AS machines, COUNT(*) AS machine_days,
    SUM(faults_opened) AS faults, SUM(available_seconds) / SUM(scheduled_seconds) AS availability,
    SUM(downtime_seconds) / 3600.0 AS downtime_hours
  FROM silver_machine_day GROUP BY manufacturer
), lost AS (
  SELECT manufacturer, SUM(lost_theo_usd) AS lost_theo_usd FROM gold_downtime_lost GROUP BY manufacturer
), cost AS (
  SELECT manufacturer, SUM(direct_cost_usd) AS repair_cost_usd FROM silver_operations
  WHERE event_type = 'fault_repair' GROUP BY manufacturer
)
SELECT md.*, 100.0 * md.faults / md.machine_days AS faults_per_100_machine_days,
  lost.lost_theo_usd, cost.repair_cost_usd
FROM md LEFT JOIN lost USING (manufacturer) LEFT JOIN cost USING (manufacturer);
