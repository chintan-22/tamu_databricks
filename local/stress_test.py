"""Stress test: re-derives the pipeline's key results independently, checks that the conclusions
are robust, and feeds deliberately broken data through the real pipeline to prove the guards fire.

Usage (repo root, after local/run_local.py):
    python local/stress_test.py [--data ../dashboard-royale/data] [--db local/_work/gilded_ace.duckdb]

Exits 1 if any check fails. INFO lines are context for the write-ups, not pass/fail.
"""
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "local")]
from gilded_ace.tables import RAW_TABLES  # noqa: E402
from lakeflow_duckdb import LocalPipeline  # noqa: E402

PIPELINE_FILES = ["silver.sql", "gold_machines.sql", "gold_operations.sql", "gold_floor.sql", "gold_guests.sql", "gold_actions.sql"]
results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok)))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}  {detail}")


def info(name: str, detail: str) -> None:
    print(f"[INFO] {name}  {detail}")


def invariants(con) -> None:
    df = lambda s: con.execute(s).df()
    one = lambda s: con.execute(s).fetchone()[0]
    print("=== A. invariants, recomputed independently ===")
    cat = df("select * from bronze_action_catalog").set_index("action_type_id")
    opts = df("select * from gold_action_options")
    worst, over = 0.0, []
    for _, r in opts.iterrows():
        c = cat.loc[r.action_type_id.split(" ")[0]]
        exp = r.quantity * (c.unit_cost_cents / 100 + c.recurring_cost_cents_per_day / 100 * max(0, 30 - c.lead_days))
        worst = max(worst, abs(exp - r.cost_usd))
        if r.quantity > c.quantity_limit:
            over.append(r.action_type_id)
    check("catalogue cost formula on every option", worst < 0.01, f"max diff ${worst:.4f}")
    check("quantities within catalogue limits", not over, ", ".join(over))
    rec = opts[opts.recommended]
    plan = df("select * from gold_action_plan").iloc[0]
    check("plan = sum of recommended rows", abs(rec.cost_usd.sum() - plan.total_cost_usd) < 0.01 and abs(rec.benefit_base_usd.sum() - plan.benefit_base_usd) < 0.01,
          f"cost ${rec.cost_usd.sum():,.0f}, base benefit ${rec.benefit_base_usd.sum():,.0f}")
    check("plan <= $100,000 and <= 3 action types", plan.total_cost_usd <= 100000 and plan.action_types <= 3)
    grp = cat.loc[[a.split(" ")[0] for a in rec.action_type_id], "incompatibility_group"].dropna()
    check("no two recommended actions share an incompatibility group", not grp.duplicated().any())
    check("no off-floor rows in silver_machine_day", one(
        "select count(*) from silver_machine_day where not active or location_id is null or gaming_date < install_date "
        "or (retire_date is not null and gaming_date > retire_date)") == 0)
    check("meters balance on every row", one("select count(*) from silver_machine_day where house_win_cents <> coin_in_cents - payout_cents") == 0)
    d = one("select max(abs(theo_cents - coin_in_cents * (1 - configured_rtp))) from silver_machine_day")
    check("theo = coin-in x (1 - RTP)", d < 1, f"max diff {d:.3f} cents")
    hrs = df("select scheduled_seconds / 3600 h, count(*) n from silver_calendar group by 1")
    check("gaming days are 24 h except DST days", set(hrs.h) <= {23, 24, 25} and hrs[hrs.h != 24].n.sum() <= 2)
    dup = one("select count(*) from (select machine_id, gaming_date from silver_machine_day group by all having count(*) > 1)")
    check("one row per machine-day", dup == 0, f"{dup} duplicates")
    r = one("select max(abs(gap_usd - (luck_usd + location_usd + downtime_usd + appeal_usd + hold_setting_usd + exposure_usd))) from gold_machine_scorecard")
    check("six-part decomposition adds up", r < 1, f"max residual ${r:.1e}")


def robustness(con) -> None:
    df = lambda s: con.execute(s).df()
    one = lambda s: con.execute(s).fetchone()[0]
    print("\n=== B. robustness of the conclusions ===")
    sc = df("select * from gold_machine_scorecard")
    opts = df("select * from gold_action_options").set_index("action_type_id")
    z = sc.luck_z.dropna()
    info("luck z across machines", f"mean {z.mean():+.2f}, sd {z.std():.2f}; |z|>2: {(z.abs() > 2).sum()} (chance ~{0.0455 * len(z):.0f})")
    check("luck z-scores are calibrated (sd 0.8-1.25)", 0.8 < z.std() < 1.25)
    h = sc.hit_rate_z.dropna()
    check("hit-rate z-scores are calibrated without the leak (sd 0.8-1.25)", 0.8 < h[h.abs() < 6].std() < 1.25)
    check("exactly one machine is off spec over the full period", (sc.verdict.str.startswith("Leak")).sum() == 1,
          ", ".join(sc.loc[sc.verdict.str.startswith("Leak"), "machine_id"]))
    targets = opts.loc["A-REPLACE-LEASE", "targets"].split(", ")
    check("none of the manager's bottom 10 is a replace target", not sc[sc.manager_rank <= 10].machine_id.isin(targets).any())
    halves = df("""select machine_id, case when gaming_date < date '2025-04-01' then 'H1' else 'H2' end h,
      sum(theo_cents) / nullif(sum(zone_expected_theo_cents), 0) fi from gold_machine_day_components group by all""").pivot(index="machine_id", columns="h", values="fi").dropna()
    rho = halves.rank().corr().iloc[0, 1]
    check("fair-index ranking is stable Jan-Mar vs Apr-Jun (Spearman > 0.8)", rho > 0.8, f"rho {rho:.3f}")
    mon = df("""select machine_id, month, sum(theo_cents) / nullif(sum(zone_expected_theo_cents), 0) fi
      from gold_machine_day_components join silver_calendar using (gaming_date) group by all""")
    worst = mon[mon.machine_id.isin(targets)].fi.max()
    check("every replace target is under 0.85 of par in every month", worst < 0.85, f"worst month {worst:.2f}")
    zd = df("select gaming_date, zone_id = 'Z-B40' t, sum(coin_in_cents) / count(*) ci from silver_machine_day group by all").pivot(index="gaming_date", columns="t", values="ci")
    zd.index = pd.to_datetime(zd.index)
    closed = np.asarray((zd.index >= "2025-03-03") & (zd.index <= "2025-04-06"))

    def did(mask, base):
        return (zd.loc[mask, True].mean() / zd.loc[base, True].mean()) / (zd.loc[mask, False].mean() / zd.loc[base, False].mean()) - 1

    real = did(closed, ~closed)
    plac = []
    for s in range(len(zd) - 35):
        m = np.zeros(len(zd), bool); m[s:s + 35] = True
        if not (m & closed).any():
            plac.append(did(m, ~m & ~closed))
    check("walkway-closure effect lies outside every placebo window", real < min(plac),
          f"real {real:+.1%}; {len(plac)} placebo windows {min(plac):+.1%}..{max(plac):+.1%}")
    au = df("""select (gaming_date - install_date) // 14 f, sum(theo_cents) / sum(zone_expected_theo_cents) fi
      from gold_machine_day_components join (select distinct machine_id, install_date, theme from silver_machine_day) using (machine_id)
      where theme = 'Aurora Link' group by 1 order by 1""")
    info("Aurora Link fair index by fortnight since install (novelty check)", " ".join(f"{v:.2f}" for v in au.fi))
    sel = df("select * from gold_forecast_selection"); p = df("select * from gold_forecast_params").iloc[0]
    check("forecast chosen = April-validation minimum", sel.sort_values("mae").model.iloc[0] == p.chosen_model, p.chosen_model)
    fc = df("select * from gold_forecast where gaming_date > date '2025-04-30' and actual_coin_in_usd is not null")
    mae = (fc.actual_coin_in_usd - fc.model_coin_in_usd).abs().mean()
    check("holdout MAE recomputes from gold_forecast", abs(mae - p.holdout_mae_model) < 1, f"${mae:,.0f} over {len(fc)} days")
    cov = ((fc.actual_coin_in_usd >= fc.lower_80_usd) & (fc.actual_coin_in_usd <= fc.upper_80_usd)).mean()
    check("80% forecast band covers 70-90% of holdout days", 0.7 <= cov <= 0.9, f"{cov:.0%}")
    lift = one("select avg(lift) from gold_event_lift where local_scope = 'property'")
    info("promotion test power", f"detectable lift {p.min_detectable_promo_lift:.1%} vs base-case lift {lift:.1%} (about even odds)")


def fault_injection(data: Path) -> None:
    print("\n=== C. fault injection: broken inputs through the real pipeline ===")

    def run(overrides: dict[str, str]) -> str:
        c = duckdb.connect(); c.execute("SET TimeZone = 'UTC'")
        for t, rel in RAW_TABLES.items():
            src = f"read_parquet('{(data / rel).as_posix()}')"
            body = overrides.get(t, "SELECT * FROM {src}").format(src=src)
            c.execute(f"CREATE OR REPLACE VIEW bronze_{t} AS SELECT *, 'x' AS _source_file, now() AS _ingested_at FROM ({body})")
        pipe = LocalPipeline(c)
        try:
            for f in PIPELINE_FILES:
                pipe.run_file(ROOT / "src" / "pipeline" / f, verbose=False)
            return "completed"
        except RuntimeError as e:
            return "stopped: " + str(e)
        finally:
            c.close()

    # change one on-floor row, keep every other row (the panel must stay complete)
    nth = ("SELECT * EXCLUDE (rn) REPLACE ({repl}) FROM (SELECT *, row_number() OVER () rn FROM {{src}} WHERE active) "
           "UNION ALL SELECT * FROM {{src}} WHERE NOT active")
    cases = [
        ("meters off by 1 cent on one row", "meters_balance",
         {"machine_day": nth.format(repl="CASE WHEN rn = 1 THEN house_win_cents + 1 ELSE house_win_cents END AS house_win_cents")}),
        ("negative coin-in (meters still balance)", "meters_nonnegative",
         {"machine_day": nth.format(repl="CASE WHEN rn = 7 THEN -coin_in_cents ELSE coin_in_cents END AS coin_in_cents, "
                                         "CASE WHEN rn = 7 THEN -coin_in_cents - payout_cents ELSE house_win_cents END AS house_win_cents")}),
        ("an RTP of 1.20 in game_math", "rtp_is_a_payback",
         {"game_math": "SELECT * REPLACE (CASE WHEN config_id = 'G-STD90' THEN 1.2 ELSE configured_rtp END AS configured_rtp) FROM {src}"}),
        ("500 duplicated machine-day rows", "complete_machine_panel",
         {"machine_day": "SELECT * FROM {src} UNION ALL (SELECT * FROM {src} WHERE active LIMIT 500)"}),
        ("a gaming day missing from machine_day", "complete_machine_panel",
         {"machine_day": "SELECT * FROM {src} WHERE gaming_date <> DATE '2025-03-15'"}),
        ("plan over budget (lease price x4)", "within_budget",
         {"action_catalog": "SELECT * REPLACE (CASE WHEN action_type_id = 'A-REPLACE-LEASE' THEN unit_cost_cents * 4 ELSE unit_cost_cents END AS unit_cost_cents) FROM {src}"}),
    ]
    for label, rule, ov in cases:
        t0 = time.time()
        out = run(ov)
        check(f"guard stops: {label}", out.startswith("stopped") and rule in out, f"{out[:110]} ({time.time() - t0:.1f}s)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT.parent / "dashboard-royale" / "data"))
    ap.add_argument("--db", default=str(ROOT / "local" / "_work" / "gilded_ace.duckdb"))
    args = ap.parse_args()
    con = duckdb.connect(args.db, read_only=True)
    invariants(con)
    robustness(con)
    con.close()
    fault_injection(Path(args.data))
    passed = sum(ok for _, ok in results)
    print(f"\n{passed}/{len(results)} checks passed")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
