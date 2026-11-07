-- =====================================================================================
-- GOLD · GUESTS & COMPS — tracked (loyalty-card) play only.
-- Uncarded play never appears at the person level; every player metric here is labelled
-- "tracked". Comp cost is already inside POS cogs, so it is never subtracted twice.
-- =====================================================================================

CREATE OR REFRESH MATERIALIZED VIEW gold_player_segment_month
COMMENT 'Tracked results per month by tier, age band and home region (drill-down grain for the dashboard).'
AS SELECT
  month,
  opening_tier,
  age_band,
  home_region,
  COUNT(*) AS player_months,
  SUM(CASE WHEN tracked_coin_in_usd > 0 THEN 1 ELSE 0 END) AS playing_player_months,
  SUM(CASE WHEN tracked_net_usd > 0 THEN 1 ELSE 0 END) AS ahead_player_months,
  SUM(observed_visits) AS visits,
  SUM(tracked_coin_in_usd) AS coin_in_usd,
  SUM(tracked_payout_usd) AS payout_usd,
  SUM(tracked_net_usd) AS player_net_usd,
  SUM(theo_usd) AS theo_usd,
  SUM(luck_residual_usd) AS luck_usd,
  SUM(comps_redeemed) AS comps_redeemed,
  SUM(comp_cost_usd) AS comp_cost_usd,
  SUM(comp_face_value_usd) AS comp_face_value_usd,
  SUM(points_earned) AS points_earned,
  SUM(points_redeemed) AS points_redeemed,
  SUM(tracked_contribution_usd) AS contribution_usd
FROM silver_player_period
GROUP BY month, opening_tier, age_band, home_region;

CREATE OR REFRESH MATERIALIZED VIEW gold_player_concentration
COMMENT 'How concentrated tracked results are: players ranked by six-month theo, grouped into percentile bands.'
AS WITH p AS (
  SELECT player_id,
    SUM(tracked_coin_in_usd) AS coin_in_usd,
    SUM(tracked_net_usd) AS net_usd,
    SUM(theo_usd) AS theo_usd,
    SUM(comp_cost_usd) AS comp_cost_usd
  FROM silver_player_period
  GROUP BY player_id
  HAVING SUM(tracked_coin_in_usd) > 0
), ranked AS (
  SELECT *, PERCENT_RANK() OVER (ORDER BY theo_usd DESC) AS pr FROM p
), banded AS (
  SELECT *,
    CASE WHEN pr < 0.01 THEN '1. Top 1%'
         WHEN pr < 0.05 THEN '2. Next 4% (1-5%)'
         WHEN pr < 0.20 THEN '3. Next 15% (5-20%)'
         WHEN pr < 0.50 THEN '4. Next 30% (20-50%)'
         ELSE '5. Bottom 50%' END AS band
  FROM ranked
)
SELECT
  band,
  COUNT(*) AS players,
  SUM(coin_in_usd) AS coin_in_usd,
  SUM(theo_usd) AS theo_usd,
  SUM(net_usd) AS player_net_usd,
  SUM(comp_cost_usd) AS comp_cost_usd,
  SUM(CASE WHEN net_usd > 0 THEN 1 ELSE 0 END) / COUNT(*) AS share_ahead,
  SUM(theo_usd) / SUM(SUM(theo_usd)) OVER () AS share_of_theo,
  SUM(net_usd) / SUM(SUM(net_usd)) OVER () AS share_of_player_losses,
  SUM(comp_cost_usd) / NULLIF(SUM(theo_usd), 0) AS comp_reinvestment
FROM banded
GROUP BY band;

CREATE OR REFRESH MATERIALIZED VIEW gold_comp_price_day
COMMENT 'What a comp cost in points each gaming day: points per menu dollar and per dollar of house cost.'
AS SELECT
  gaming_date,
  month,
  COUNT(*) AS redemptions,
  SUM(points_spent) AS points_spent,
  SUM(economic_cost_cents) / 100.0 AS comp_cost_usd,
  SUM(face_value_cents) / 100.0 AS comp_face_value_usd,
  SUM(points_spent) / (SUM(face_value_cents) / 100.0) AS points_per_face_dollar,
  SUM(points_spent) / (SUM(economic_cost_cents) / 100.0) AS points_per_cost_dollar
FROM silver_redemptions
GROUP BY gaming_date, month;

CREATE OR REFRESH MATERIALIZED VIEW gold_comp_month
COMMENT 'Comp program by month: cost, reinvestment (comp cost / tracked theo), points flow and carded share of play.'
AS WITH pp AS (
  SELECT month,
    SUM(theo_usd) AS tracked_theo_usd,
    SUM(comp_cost_usd) AS comp_cost_usd,
    SUM(comp_face_value_usd) AS comp_face_value_usd,
    SUM(comps_redeemed) AS comps_redeemed,
    SUM(points_earned) AS points_earned,
    SUM(points_redeemed) AS points_redeemed,
    SUM(observed_visits) AS visits,
    COUNT(DISTINCT CASE WHEN tracked_coin_in_usd > 0 THEN player_id END) AS playing_players
  FROM silver_player_period GROUP BY month
), md AS (
  SELECT month,
    SUM(carded_coin_in_cents) / SUM(coin_in_cents) AS carded_share_of_coin_in,
    SUM(coin_in_cents - carded_coin_in_cents) / 100.0 AS uncarded_coin_in_usd,
    SUM(carded_coin_in_cents) / 100.0 AS carded_coin_in_usd
  FROM silver_machine_day GROUP BY month
), price AS (
  SELECT month, SUM(points_spent) / (SUM(face_value_cents) / 100.0) AS points_per_face_dollar
  FROM silver_redemptions GROUP BY month
)
SELECT pp.*, pp.comp_cost_usd / pp.tracked_theo_usd AS comp_reinvestment,
  pp.visits / pp.playing_players AS visits_per_playing_player,
  md.carded_share_of_coin_in, md.carded_coin_in_usd, md.uncarded_coin_in_usd,
  price.points_per_face_dollar
FROM pp JOIN md USING (month) LEFT JOIN price USING (month);

CREATE OR REFRESH MATERIALIZED VIEW gold_comp_change_test
COMMENT 'Did the 2025-05-01 comp price cut change anything? Before (Jan-Apr) vs. after (May-Jun), carded play tested against uncarded play.'
AS WITH m AS (
  SELECT *, CASE WHEN month >= '2025-05' THEN 'after' ELSE 'before' END AS period FROM gold_comp_month
), days AS (
  SELECT CASE WHEN month >= '2025-05' THEN 'after' ELSE 'before' END AS period, COUNT(*) AS n_days
  FROM silver_calendar GROUP BY CASE WHEN month >= '2025-05' THEN 'after' ELSE 'before' END
), agg AS (
  SELECT period,
    SUM(points_redeemed) AS points_redeemed,
    SUM(comps_redeemed) AS comps_redeemed,
    SUM(comp_cost_usd) AS comp_cost_usd,
    SUM(tracked_theo_usd) AS tracked_theo_usd,
    SUM(carded_coin_in_usd) AS carded_coin_in_usd,
    SUM(uncarded_coin_in_usd) AS uncarded_coin_in_usd,
    SUM(points_redeemed) / (SUM(comp_face_value_usd)) AS points_per_face_dollar
  FROM m GROUP BY period
)
SELECT a.period, d.n_days,
  a.points_per_face_dollar,
  a.comps_redeemed / d.n_days AS comps_per_day,
  a.comp_cost_usd / d.n_days AS comp_cost_per_day,
  a.comp_cost_usd / a.tracked_theo_usd AS comp_reinvestment,
  a.carded_coin_in_usd / d.n_days AS carded_coin_in_per_day,
  a.uncarded_coin_in_usd / d.n_days AS uncarded_coin_in_per_day,
  a.carded_coin_in_usd / (a.carded_coin_in_usd + a.uncarded_coin_in_usd) AS carded_share
FROM agg a JOIN days d USING (period);
