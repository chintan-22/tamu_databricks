"""Run the Lakeflow (DLT) SQL pipeline files on DuckDB, unchanged.

The pipeline's SQL is the single source of truth: the same files deploy to Databricks
as a Lakeflow Declarative Pipeline and run here for local verification. This module
understands the small part of Lakeflow syntax the project uses:

    CREATE OR REFRESH MATERIALIZED VIEW name (
      CONSTRAINT c EXPECT (expr) [ON VIOLATION DROP ROW | FAIL UPDATE], ...
    ) COMMENT '...' AS SELECT ...;

Expectations behave as on Databricks: warn (keep and count), drop the failing rows,
or stop the run. Results are kept in `expectation_log` for the dashboard's data-quality panel.
"""
from __future__ import annotations

import sys
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gilded_ace.lakeflow_sql import Dataset, Expectation, parse_pipeline_sql  # noqa: E402,F401

# Spark SQL functions used by the pipeline that DuckDB spells differently.
SPARK_SHIMS = [
    "CREATE OR REPLACE MACRO unix_timestamp(t) AS epoch(t)",
    # Spark's PERCENTILE is exact with linear interpolation, i.e. quantile_cont. (Avoid PERCENTILE_APPROX in
    # the pipeline: on Spark it returns an observed value, so it disagrees with quantile_cont on small groups.)
    "CREATE OR REPLACE MACRO percentile(x, p) AS quantile_cont(x, p)",
    "CREATE OR REPLACE MACRO percentile_approx(x, p) AS quantile_cont(x, p)",
    "CREATE OR REPLACE MACRO collect_list(x) AS list(x ORDER BY x)",
    "CREATE OR REPLACE MACRO array_join(a, sep) AS array_to_string(a, sep)",
]


class LocalPipeline:
    def __init__(self, con: duckdb.DuckDBPyConnection):
        self.con = con
        for shim in SPARK_SHIMS:
            con.execute(shim)
        con.execute(
            "CREATE OR REPLACE TABLE expectation_log (dataset VARCHAR, expectation VARCHAR, action VARCHAR, "
            "expr VARCHAR, rows_in BIGINT, rows_failed BIGINT)"
        )

    def run_file(self, path: Path, verbose: bool = True) -> list[str]:
        created = []
        for ds in parse_pipeline_sql(path.read_text(encoding="utf-8")):
            self.run_dataset(ds, verbose)
            created.append(ds.name)
        return created

    def run_dataset(self, ds: Dataset, verbose: bool = True) -> None:
        con = self.con
        con.execute(f"CREATE OR REPLACE TABLE {ds.name} AS {ds.body}")
        n = con.execute(f"SELECT COUNT(*) FROM {ds.name}").fetchone()[0]
        # Like Lakeflow: every expectation is counted against all input rows first (a row dropped by one
        # rule still counts as failing the others), and only then are the drop rules applied.
        counts = []
        for e in ds.expectations:
            failed = con.execute(f"SELECT COUNT(*) FROM {ds.name} WHERE NOT COALESCE(({e.expr}), FALSE)").fetchone()[0]
            con.execute("INSERT INTO expectation_log VALUES (?, ?, ?, ?, ?, ?)", [ds.name, e.name, e.action, e.expr, n, failed])
            counts.append((e, failed))
        for e, failed in counts:
            if failed and e.action == "fail":
                raise RuntimeError(f"{ds.name}: expectation {e.name} failed on {failed} rows -> update stopped")
        for e, failed in counts:
            if failed and e.action == "drop":
                con.execute(f"DELETE FROM {ds.name} WHERE NOT COALESCE(({e.expr}), FALSE)")
        if verbose:
            kept = con.execute(f"SELECT COUNT(*) FROM {ds.name}").fetchone()[0]
            flags = ", ".join(
                f"{e.name}:{f}" for e, f in (
                    (e, con.execute(
                        "SELECT rows_failed FROM expectation_log WHERE dataset=? AND expectation=? ORDER BY rowid DESC LIMIT 1",
                        [ds.name, e.name]).fetchone()[0]) for e in ds.expectations)
                if f
            )
            print(f"  {ds.name:<38} {kept:>9,} rows" + (f"   [{flags}]" if flags else ""))
