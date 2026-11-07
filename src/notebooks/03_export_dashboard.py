# Databricks notebook source
# MAGIC %md
# MAGIC # 03 · Publish: data-quality log + dashboard export
# MAGIC
# MAGIC 1. Reads the Lakeflow **event log** for pass/fail counts of every expectation and joins them
# MAGIC    with the expectation definitions parsed from the pipeline SQL → `expectation_log`.
# MAGIC 2. Exports the gold layer to `/Volumes/<catalog>/<schema>/exports/gilded_ace.json`, the single
# MAGIC    file the public dashboard (`dashboard/index.html`) loads.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "gilded_ace")
dbutils.widgets.text("ml_schema", "gilded_ace_ml")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
ml_schema = dbutils.widgets.get("ml_schema")
prefix = f"`{catalog}`.`{schema}`."
ml_prefix = f"`{catalog}`.`{ml_schema}`."  # forecast + expectation_log (Free Edition: 100 tables per schema)

import os, sys, glob
from pathlib import Path
sys.path.append(os.path.abspath(".."))
from gilded_ace.lakeflow_sql import parse_pipeline_sql
from gilded_ace import export
import pandas as pd

# COMMAND ----------

# Expectation definitions straight from the pipeline source.
defs = []
for f in sorted(glob.glob(os.path.abspath("../pipeline/*.sql"))):
    for ds in parse_pipeline_sql(Path(f).read_text()):
        for e in ds.expectations:
            defs.append({"dataset": ds.name, "expectation": e.name, "action": e.action, "expr": e.expr})
defs = spark.createDataFrame(pd.DataFrame(defs))
defs.createOrReplaceTempView("expectation_defs")

# Pass/fail counts from the most recent pipeline update's event log.
spark.sql(f"""
CREATE OR REPLACE TABLE {ml_prefix}expectation_log AS
WITH ev AS (
  SELECT explode(from_json(details:flow_progress:data_quality:expectations,
         'array<struct<name:string,dataset:string,passed_records:bigint,failed_records:bigint>>')) AS e,
         origin.update_id AS update_id, timestamp
  FROM event_log(TABLE({prefix}gold_machine_scorecard))
  WHERE event_type = 'flow_progress' AND details:flow_progress:data_quality IS NOT NULL
), latest AS (
  SELECT * FROM ev WHERE update_id = (SELECT max_by(update_id, timestamp) FROM ev)
)
SELECT d.dataset, d.expectation, d.action, d.expr,
       COALESCE(SUM(l.e.passed_records + l.e.failed_records), 0) AS rows_in,
       COALESCE(SUM(l.e.failed_records), 0) AS rows_failed
FROM expectation_defs d
-- The event log names datasets fully qualified (catalog.schema.table); the SQL source uses the bare name.
LEFT JOIN latest l ON regexp_extract(l.e.dataset, '([^.]+)$', 1) = d.dataset AND l.e.name = d.expectation
GROUP BY d.dataset, d.expectation, d.action, d.expr
""")
display(spark.table(f"{ml_prefix}expectation_log"))

# COMMAND ----------

out_dir = Path(f"/Volumes/{catalog}/{schema}/exports")
path = export.export_all(lambda sql: spark.sql(sql).toPandas(), out_dir, schema_prefix=prefix, ml_prefix=ml_prefix)
print(f"Wrote {path} ({path.stat().st_size / 1e6:.1f} MB). Copy it to dashboard/data/ to publish.")
