# Databricks notebook source
# MAGIC %md
# MAGIC # 02 · Forecast daily floor coin-in (MLflow + Unity Catalog)
# MAGIC
# MAGIC **Protocol (no leakage).** Candidates are compared on an inner split (fit Jan–Mar, score April).
# MAGIC The winner and the required constant-mean baseline are refit on Jan–Apr, *frozen* as of
# MAGIC 2025-04-30, and scored **once** on the May–June holdout. Events count as inputs only if they
# MAGIC were announced by the freeze date.
# MAGIC
# MAGIC Every candidate is an MLflow run; the frozen model is registered in Unity Catalog as
# MAGIC `<catalog>.<schema>.floor_coin_in_forecast` with the alias `champion`. Predictions, metrics and
# MAGIC the selection table land in gold Delta tables that the dashboard and Genie read.

# COMMAND ----------

# MAGIC %pip install -q "mlflow>=2.14" cloudpickle
# MAGIC %restart_python

# COMMAND ----------

dbutils.widgets.text("catalog", "workspace")
dbutils.widgets.text("schema", "gilded_ace")
dbutils.widgets.text("ml_schema", "gilded_ace_ml")
catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
ml_schema = dbutils.widgets.get("ml_schema")
fq = lambda name: f"`{catalog}`.`{schema}`.{name}"  # noqa: E731
fq_ml = lambda name: f"`{catalog}`.`{ml_schema}`.{name}"  # noqa: E731  (Free Edition: 100 tables per schema)

import os, sys
sys.path.append(os.path.abspath(".."))
from gilded_ace import forecast

import mlflow
import pandas as pd
import matplotlib.pyplot as plt

mlflow.set_registry_uri("databricks-uc")
user = spark.sql("SELECT current_user()").first()[0]
mlflow.set_experiment(f"/Users/{user}/gilded-ace-floor-forecast")

# COMMAND ----------

floor = spark.table(fq("silver_property_day")).toPandas()
events = spark.table(fq("bronze_events")).drop("_source_file", "_ingested_at").toPandas()
result = forecast.run(floor, events)
display(result.selection)
display(result.metrics)

# COMMAND ----------


class FloorForecast(mlflow.pyfunc.PythonModel):
    """Calendar rows (gaming_date, local_weekday, federal_holiday) -> forecast daily coin-in (USD)."""

    def __init__(self, frozen):
        self.frozen = frozen

    def predict(self, context, model_input: pd.DataFrame):
        return self.frozen.predict(model_input)


with mlflow.start_run(run_name="floor-coin-in-forecast") as parent:
    mlflow.set_tags({"protocol": "select on Apr (fit Jan-Mar); freeze 2025-04-30; score once on May-Jun",
                     "challenge": "TAMU Datathon 2026 - Dashboard Royale"})
    for row in result.selection.itertuples():
        with mlflow.start_run(run_name=f"candidate: {row.model}", nested=True):
            mlflow.log_param("model", row.model)
            mlflow.log_metrics({"april_validation_mae": row.mae, "april_validation_mape": row.mape,
                                "april_validation_bias": row.bias})
    mlflow.log_params({k: v for k, v in result.params.items() if isinstance(v, str)})
    mlflow.log_metrics({k: float(v) for k, v in result.params.items() if not isinstance(v, str)})

    hold = result.predictions[result.predictions.split == "holdout"]
    fig, ax = plt.subplots(figsize=(10, 3.5))
    ax.plot(pd.to_datetime(hold.gaming_date), hold.actual_coin_in_usd / 1e6, label="actual", color="#222")
    ax.plot(pd.to_datetime(hold.gaming_date), hold.model_coin_in_usd / 1e6, label=result.chosen, color="#c8102e")
    ax.plot(pd.to_datetime(hold.gaming_date), hold.baseline_coin_in_usd / 1e6, label="baseline", color="#999", ls="--")
    ax.set_ylabel("coin-in, $M"); ax.legend(); ax.set_title("May-June holdout (frozen forecast)")
    mlflow.log_figure(fig, "holdout_vs_actual.png")

    cal = result.predictions[["gaming_date", "local_weekday"]].head(5).copy()
    signature = mlflow.models.infer_signature(cal.astype({"gaming_date": "datetime64[ns]"}), result.model.predict(cal))
    mlflow.pyfunc.log_model(
        "model",
        python_model=FloorForecast(result.model),
        code_paths=[os.path.abspath("../gilded_ace")],
        signature=signature,
        registered_model_name=f"{catalog}.{schema}.floor_coin_in_forecast",
    )

client = mlflow.MlflowClient()
latest = max(client.search_model_versions(f"name='{catalog}.{schema}.floor_coin_in_forecast'"), key=lambda v: int(v.version))
client.set_registered_model_alias(f"{catalog}.{schema}.floor_coin_in_forecast", "champion", latest.version)

# COMMAND ----------

params = pd.DataFrame([{k: (v if isinstance(v, str) else float(v)) for k, v in result.params.items()}])
for name, frame in {
    "gold_forecast": result.predictions,
    "gold_forecast_metrics": result.metrics,
    "gold_forecast_selection": result.selection,
    "gold_forecast_params": params,
}.items():
    spark.createDataFrame(frame).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(fq_ml(name))

print(f"Selected {result.chosen}; holdout MAE ${result.params['holdout_mae_model']:,.0f} "
      f"vs baseline ${result.params['holdout_mae_baseline']:,.0f}")
