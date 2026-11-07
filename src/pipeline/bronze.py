# Bronze: one streaming table per challenge file, loaded incrementally with Auto Loader.
# Every row keeps where it came from (`_source_file`) and when it landed (`_ingested_at`).
import dlt
from pyspark.sql import functions as F

import os, sys
sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..")))
try:
    from gilded_ace.tables import RAW_TABLES
except ImportError:  # pipeline source root differs between workspace layouts
    sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "..", "..", "src")))
    from gilded_ace.tables import RAW_TABLES

RAW_PATH = spark.conf.get("gilded_ace.raw_volume_path")


def make_bronze(table: str):
    @dlt.table(
        name=f"bronze_{table}",
        comment=f"Raw `{table}` from the Dashboard Royale release, unmodified.",
        table_properties={"quality": "bronze"},
    )
    def _bronze():
        return (
            spark.readStream.format("cloudFiles")
            .option("cloudFiles.format", "parquet")
            .option("cloudFiles.schemaLocation", f"{RAW_PATH}/_schemas/{table}")
            .load(f"{RAW_PATH}/{table}")
            .withColumn("_source_file", F.col("_metadata.file_path"))
            .withColumn("_ingested_at", F.current_timestamp())
        )


for _table in RAW_TABLES:
    make_bronze(_table)
