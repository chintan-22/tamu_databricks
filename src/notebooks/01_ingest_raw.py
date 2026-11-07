# Databricks notebook source
# MAGIC %md
# MAGIC # 01 · Land the raw challenge files in a Unity Catalog volume
# MAGIC
# MAGIC Downloads each Parquet file from the public challenge repository into
# MAGIC `/Volumes/<catalog>/<schema>/raw/<table>/`. The Lakeflow pipeline's bronze layer
# MAGIC picks them up from there with Auto Loader, so re-running this notebook with a new
# MAGIC data release (`0.9.0-draft` → `1.0.0`) only re-processes what changed.

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "gilded_ace")
dbutils.widgets.text("ml_schema", "gilded_ace_ml")
dbutils.widgets.text("data_release_url", "https://raw.githubusercontent.com/tamu-datathon-org/dashboard-royale/main/data")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
ml_schema = dbutils.widgets.get("ml_schema")
base_url = dbutils.widgets.get("data_release_url").rstrip("/")

# COMMAND ----------

import os, sys, urllib.request, hashlib, json

sys.path.append(os.path.abspath(".."))  # make src/gilded_ace importable from the bundle
from gilded_ace.tables import RAW_TABLES

spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema}`")
# Forecast outputs + expectation_log live here: Free Edition caps one schema at 100 tables.
spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{ml_schema}`")
spark.sql(f"CREATE VOLUME IF NOT EXISTS `{catalog}`.`{schema}`.raw COMMENT 'Unmodified challenge release files'")
spark.sql(f"CREATE VOLUME IF NOT EXISTS `{catalog}`.`{schema}`.exports COMMENT 'Dashboard JSON exports'")
volume = f"/Volumes/{catalog}/{schema}/raw"

# The release ships a manifest with a SHA-256 per file; use it to verify every download.
manifest = json.loads(urllib.request.urlopen(f"{base_url}/manifest.json").read())
expected = {f["path"].removeprefix("data/"): f.get("sha256") for f in manifest.get("files", []) if "path" in f}

# COMMAND ----------

report = []
for table, rel_path in RAW_TABLES.items():
    target_dir = f"{volume}/{table}"
    os.makedirs(target_dir, exist_ok=True)
    target = f"{target_dir}/{os.path.basename(rel_path)}"
    payload = urllib.request.urlopen(f"{base_url}/{rel_path}").read()
    digest = hashlib.sha256(payload).hexdigest()
    want = expected.get(rel_path)
    if want and want != digest:
        raise ValueError(f"{rel_path}: checksum {digest} does not match manifest {want}")
    with open(target, "wb") as fh:
        fh.write(payload)
    report.append((table, len(payload), digest[:12], "verified" if want else "no manifest entry"))

display(spark.createDataFrame(report, "table string, bytes long, sha256_prefix string, check string"))
