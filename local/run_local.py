"""End-to-end local run: bronze -> silver -> gold (same SQL as Databricks) -> forecast -> dashboard export.

Usage (from the repo root):
    python local/run_local.py --data ../dashboard-royale/data

Writes a DuckDB file to local/_work/gilded_ace.duckdb and the dashboard data to dashboard/data/.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "local"))

from gilded_ace.tables import RAW_TABLES  # noqa: E402
from lakeflow_duckdb import LocalPipeline  # noqa: E402

PIPELINE_FILES = [
    "silver.sql",
    "gold_machines.sql",
    "gold_operations.sql",
    "gold_floor.sql",
    "gold_guests.sql",
    "gold_actions.sql",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT.parent / "dashboard-royale" / "data"), help="challenge data folder")
    ap.add_argument("--db", default=str(ROOT / "local" / "_work" / "gilded_ace.duckdb"))
    ap.add_argument("--skip-export", action="store_true")
    args = ap.parse_args()

    data = Path(args.data)
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(args.db)
    con.execute("SET TimeZone = 'UTC'")

    t0 = time.time()
    print("bronze")
    for table, rel in RAW_TABLES.items():
        path = (data / rel).as_posix()
        con.execute(
            f"CREATE OR REPLACE VIEW bronze_{table} AS "
            f"SELECT *, '{path}' AS _source_file, now() AS _ingested_at FROM read_parquet('{path}')"
        )
    print(f"  {len(RAW_TABLES)} bronze views over {data}")

    pipe = LocalPipeline(con)
    for f in PIPELINE_FILES:
        p = ROOT / "src" / "pipeline" / f
        if p.exists():
            print(f.replace(".sql", ""))
            pipe.run_file(p)
    print(f"pipeline done in {time.time() - t0:.1f}s")

    from gilded_ace import forecast

    floor = con.execute("SELECT * FROM silver_property_day ORDER BY gaming_date").df()
    events = con.execute("SELECT * FROM bronze_events").df()
    result = forecast.run(floor, events)
    import pandas as pd

    for name, frame in {
        "gold_forecast": result.predictions,
        "gold_forecast_metrics": result.metrics,
        "gold_forecast_selection": result.selection,
        "gold_forecast_params": pd.DataFrame([{k: str(v) if isinstance(v, str) else float(v) for k, v in result.params.items()}]),
    }.items():
        con.register("_tmp", frame)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp")
        con.unregister("_tmp")
    print(f"forecast: selected {result.chosen} on April validation")
    print(result.metrics.round(1).to_string(index=False))

    if not args.skip_export:
        from gilded_ace import export

        out = ROOT / "dashboard" / "data"
        export.export_all(lambda sql: con.execute(sql).df(), out)
        print(f"exported dashboard data -> {out}")
    con.close()


if __name__ == "__main__":
    main()
