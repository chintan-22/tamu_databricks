"""Export the gold layer to one compact JSON file for the public dashboard.

`export_all(query, out_dir)` takes any function that runs SQL and returns a pandas
DataFrame, so the same code runs on Databricks (spark.sql(...).toPandas()) and locally
(DuckDB). Machine-day facts ship as integer columns so the browser can recompute every
verdict for any analysis period the viewer picks.
"""
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

Query = Callable[[str], pd.DataFrame]


def _clean(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6) if abs(f) < 1e6 else round(f, 2)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()[:10]
    if isinstance(v, (np.ndarray, list)):
        return [_clean(x) for x in v]
    if pd.isna(v) if not isinstance(v, (str, bytes)) else False:
        return None
    return v


def records(df: pd.DataFrame) -> list[dict]:
    return [{k: _clean(v) for k, v in row.items()} for row in df.to_dict("records")]


def columns(df: pd.DataFrame) -> dict:
    return {c: [_clean(v) for v in df[c].tolist()] for c in df.columns}


def export_all(query: Query, out_dir: Path, schema_prefix: str = "") -> Path:
    t = lambda name: f"{schema_prefix}{name}"  # noqa: E731
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    dates = query(f"SELECT gaming_date, local_weekday, is_weekend, federal_holiday, scheduled_seconds FROM {t('silver_calendar')} ORDER BY gaming_date")
    date_idx = {str(d)[:10]: i for i, d in enumerate(dates.gaming_date)}

    machines = query(f"""
        SELECT m.machine_id, m.manufacturer, m.theme, m.lease_class, m.install_date, m.retire_date,
               s.config_id, CAST(g.configured_rtp AS DOUBLE) AS rtp, CAST(g.hit_probability AS DOUBLE) AS spec_hit,
               g.volatility_class
        FROM {t('bronze_machines')} m
        JOIN {t('gold_machine_scorecard')} s ON s.machine_id = m.machine_id
        JOIN {t('bronze_game_math')} g ON g.config_id = s.config_id
        ORDER BY m.machine_id""")
    m_idx = {m: i for i, m in enumerate(machines.machine_id)}

    locations = query(f"SELECT location_id, bank_id, zone_id, zone_name, x_m, y_m FROM {t('silver_locations')} ORDER BY location_id")
    l_idx = {l: i for i, l in enumerate(locations.location_id)}
    floor_nodes = query(f"SELECT location_id, node_type, zone_id, name, x_m, y_m, capacity FROM {t('bronze_floor_locations')} WHERE node_type <> 'slot'")
    walkways = query(f"SELECT walkway_id, zone_a, zone_b, length_m, closed_from_utc, closed_to_utc, closure_reason FROM {t('bronze_floor_walkways')}")

    md = query(f"""
        SELECT machine_id, gaming_date, location_id, coin_in_cents, house_win_cents, available_seconds,
               downtime_seconds, occupied_seconds, paid_spins, payout_positive_spins, win_variance_cents2, faults_opened
        FROM {t('silver_machine_day')} ORDER BY gaming_date, machine_id""")
    md_cols = {
        "m": [m_idx[x] for x in md.machine_id],
        "d": [date_idx[str(x)[:10]] for x in md.gaming_date],
        "l": [l_idx[x] for x in md.location_id],
        "ci": md.coin_in_cents.astype("int64").tolist(),
        "hw": md.house_win_cents.astype("int64").tolist(),
        "av": md.available_seconds.astype("int64").tolist(),
        "dn": md.downtime_seconds.astype("int64").tolist(),
        "oc": md.occupied_seconds.astype("int64").tolist(),
        "sp": md.paid_spins.astype("int64").tolist(),
        "hi": md.payout_positive_spins.astype("int64").tolist(),
        "vr": [float(f"{v:.4g}") for v in md.win_variance_cents2],
        "f": md.faults_opened.astype("int64").tolist(),
    }

    payload = {
        "meta": {
            "title": "Luck, Location, or a Leak?",
            "property": "The Gilded Ace (fictional; synthetic data)",
            "window": [str(dates.gaming_date.iloc[0])[:10], str(dates.gaming_date.iloc[-1])[:10]],
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        },
        "calendar": columns(dates),
        "machines": columns(machines),
        "locations": columns(locations),
        "floor_nodes": records(floor_nodes),
        "walkways": records(walkways),
        "machine_day": md_cols,
        "scorecard": records(query(f"SELECT * FROM {t('gold_machine_scorecard')} ORDER BY manager_rank")),
        "bank_summary": records(query(f"SELECT * FROM {t('gold_bank_summary')}")),
        "floor_day": records(query(f"SELECT * FROM {t('gold_floor_day')} ORDER BY gaming_date")),
        "zone_week": records(query(f"SELECT * FROM {t('gold_zone_week')} ORDER BY zone_id, week_start")),
        "experiments": records(query(f"SELECT * FROM {t('gold_natural_experiments')}")),
        "event_lift": records(query(f"SELECT * FROM {t('gold_event_lift')} ORDER BY start_date")),
        "downtime_lost": records(query(f"SELECT * FROM {t('gold_downtime_lost')} ORDER BY gaming_date")),
        "repair_response": records(query(f"SELECT * FROM {t('gold_repair_response')} ORDER BY month, tech_shift")),
        "wait_vs_staffing": records(query(f"SELECT * FROM {t('gold_wait_vs_staffing')} ORDER BY tech_shift, techs_on_shift")),
        "manufacturer_reliability": records(query(f"SELECT * FROM {t('gold_manufacturer_reliability')}")),
        "player_segment_month": records(query(f"SELECT * FROM {t('gold_player_segment_month')}")),
        "player_concentration": records(query(f"SELECT * FROM {t('gold_player_concentration')} ORDER BY band")),
        "comp_price_day": records(query(f"SELECT * FROM {t('gold_comp_price_day')} ORDER BY gaming_date")),
        "comp_month": records(query(f"SELECT * FROM {t('gold_comp_month')} ORDER BY month")),
        "comp_change_test": records(query(f"SELECT * FROM {t('gold_comp_change_test')}")),
        "action_options": records(query(f"SELECT * FROM {t('gold_action_options')} ORDER BY recommended DESC, net_base_usd DESC")),
        "action_plan": records(query(f"SELECT * FROM {t('gold_action_plan')}")),
        "action_catalog": records(query(f"SELECT * FROM {t('bronze_action_catalog')}")),
        "forecast": records(query(f"SELECT * FROM {t('gold_forecast')} ORDER BY gaming_date")),
        "forecast_metrics": records(query(f"SELECT * FROM {t('gold_forecast_metrics')}")),
        "forecast_selection": records(query(f"SELECT * FROM {t('gold_forecast_selection')}")),
        "forecast_params": records(query(f"SELECT * FROM {t('gold_forecast_params')}")),
        "expectations": records(query(f"SELECT * FROM {t('expectation_log')}")),
    }
    path = out_dir / "gilded_ace.json"
    path.write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False), encoding="utf-8")
    return path
