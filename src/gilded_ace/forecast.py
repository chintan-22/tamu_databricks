"""Daily floor coin-in forecast with an honest, time-based validation.

Protocol (no leakage):
  1. Model *selection* uses only January-April: fit on Jan-Mar, score on April.
  2. The selected model and the required simple baseline (constant training mean) are
     refit on Jan-Apr and *frozen* as of 2025-04-30.
  3. Both are scored once on the May-June holdout.
  4. An event can be a feature only if it was announced on or before the freeze date
     (the Locals Appreciation Week was announced 2025-05-26, so the frozen model never sees it).

Decision use: the frozen forecast is the yardstick for the July promotion weekend. Its
weekend-level error tells us the smallest lift a single test weekend can reveal.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
FREEZE_DATE = pd.Timestamp("2025-04-30")
TRAIN_END = pd.Timestamp("2025-04-30")
INNER_TRAIN_END = pd.Timestamp("2025-03-31")
FUTURE = pd.date_range("2025-07-01", "2025-07-30", freq="D")
JULY_HOLIDAYS = {pd.Timestamp("2025-07-04"): "Independence Day"}


@dataclass
class ForecastResult:
    predictions: pd.DataFrame
    metrics: pd.DataFrame
    selection: pd.DataFrame
    chosen: str
    params: dict
    model: "FrozenForecast"


class FrozenForecast:
    """The frozen model as a plain object (picklable for MLflow): calendar rows in, coin-in out."""

    def __init__(self, fn, events: pd.DataFrame, name: str):
        self.fn, self.events, self.name = fn, events, name

    def predict(self, calendar: pd.DataFrame) -> np.ndarray:
        df = calendar.copy()
        df["gaming_date"] = pd.to_datetime(df["gaming_date"])
        if "federal_holiday" not in df:
            df["federal_holiday"] = None
        return self.fn(_features(df.reset_index(drop=True), self.events))


def _event_frame(dates: pd.Series, events: pd.DataFrame, known_by: pd.Timestamp) -> pd.DataFrame:
    """Event flags per date, using only events announced by `known_by`."""
    ev = events.copy()
    for c in ("start_date", "end_date", "announced_date"):
        ev[c] = pd.to_datetime(ev[c])
    ev = ev[ev.announced_date <= known_by]
    out = pd.DataFrame(index=dates.index)
    for kind in ["convention", "sports_viewing", "festival", "property_promotion"]:
        flag = np.zeros(len(dates), dtype=int)
        for _, e in ev[ev.event_type == kind].iterrows():
            flag |= ((dates >= e.start_date) & (dates <= e.end_date)).to_numpy().astype(int)
        out[f"ev_{kind}"] = flag
    out["ev_any"] = out.max(axis=1)
    return out


def _features(df: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    f["weekday"] = df["local_weekday"].values
    f["holiday"] = df["federal_holiday"].notna().astype(int).values
    f = f.join(_event_frame(df["gaming_date"], events, FREEZE_DATE))
    f["weekend"] = f["weekday"].isin(["Fri", "Sat", "Sun"]).astype(int)
    f["big_weekend_event"] = ((f[["ev_sports_viewing", "ev_festival", "ev_property_promotion"]].max(axis=1) == 1) & (f.weekend == 1)).astype(int)
    return f


# --- candidate models: fit(train_X, train_y) -> predict(X) ------------------------------
def constant_mean(Xtr, ytr):
    m = float(ytr.mean())
    return lambda X: np.full(len(X), m)


def weekday_mean(Xtr, ytr):
    prof = ytr.groupby(Xtr.weekday.values).mean()
    return lambda X: X.weekday.map(prof).to_numpy()


def weekday_median_clean(Xtr, ytr):
    """Median of ordinary days (no event, no holiday) for each weekday: robust to one-off spikes."""
    clean = (Xtr.ev_any == 0) & (Xtr.holiday == 0)
    prof = ytr[clean.values].groupby(Xtr.weekday[clean].values).median()
    return lambda X: X.weekday.map(prof).to_numpy()


def weekday_median_events(Xtr, ytr):
    """Ordinary-day weekday median x a pooled uplift for big weekend events seen in training."""
    base_fn = weekday_median_clean(Xtr, ytr)
    base_tr = base_fn(Xtr)
    big = Xtr.big_weekend_event.values == 1
    mult = float(np.median(ytr.values[big] / base_tr[big])) if big.any() else 1.0
    return lambda X: base_fn(X) * np.where(X.big_weekend_event.values == 1, mult, 1.0)


def ridge_log(Xtr, ytr, alpha: float = 1.0):
    """Log-linear ridge on weekday, holiday and event-type flags (closed form, no sklearn needed)."""
    cols = ["holiday", "ev_convention", "ev_sports_viewing", "ev_festival", "ev_property_promotion"]

    def design(X):
        d = pd.get_dummies(pd.Categorical(X.weekday, categories=WEEKDAYS)).astype(float).to_numpy()
        return np.hstack([d, X[cols].to_numpy(dtype=float)])

    A = design(Xtr)
    y = np.log(ytr.to_numpy())
    pen = alpha * np.eye(A.shape[1])
    pen[:7, :7] = 0  # weekday levels act as intercepts; do not shrink them
    beta = np.linalg.solve(A.T @ A + pen, A.T @ y)
    return lambda X: np.exp(design(X) @ beta)


CANDIDATES = {
    "constant_mean (baseline)": constant_mean,
    "weekday_mean": weekday_mean,
    "weekday_median_clean": weekday_median_clean,
    "weekday_median_events": weekday_median_events,
    "ridge_log_events": ridge_log,
}
BASELINE = "constant_mean (baseline)"


def _score(y: np.ndarray, p: np.ndarray) -> dict:
    err = p - y
    return {
        "mae": float(np.mean(np.abs(err))),
        "mape": float(np.mean(np.abs(err) / y)),
        "bias": float(np.mean(err)),
        "rmse": float(np.sqrt(np.mean(err**2))),
        "n": int(len(y)),
    }


def run(floor: pd.DataFrame, events: pd.DataFrame) -> ForecastResult:
    df = floor[["gaming_date", "local_weekday", "federal_holiday", "coin_in_usd", "events_active"]].copy()
    df["gaming_date"] = pd.to_datetime(df["gaming_date"])
    df = df.sort_values("gaming_date").reset_index(drop=True)
    X = _features(df, events)
    y = df["coin_in_usd"].astype(float)

    inner_tr = df.gaming_date <= INNER_TRAIN_END
    inner_va = (df.gaming_date > INNER_TRAIN_END) & (df.gaming_date <= TRAIN_END)
    train = df.gaming_date <= TRAIN_END
    hold = df.gaming_date > TRAIN_END

    # 1. select on April using Jan-Mar fits only
    sel = []
    for name, fn in CANDIDATES.items():
        model = fn(X[inner_tr], y[inner_tr])
        sel.append({"model": name, **_score(y[inner_va].to_numpy(), model(X[inner_va]))})
    selection = pd.DataFrame(sel).sort_values("mae").reset_index(drop=True)
    chosen = next(m for m in selection.model if m != BASELINE)

    # 2. refit chosen + baseline on Jan-Apr and freeze
    frozen = {name: CANDIDATES[name](X[train], y[train]) for name in (chosen, BASELINE)}

    # 3. score once on the May-June holdout (plus in-sample fit for reference)
    rows = []
    for name, model in frozen.items():
        for period, mask in (("train Jan-Apr (in-sample)", train), ("holdout May-Jun", hold)):
            rows.append({"model": name, "period": period, **_score(y[mask].to_numpy(), model(X[mask]))})
    # Transparency only: how every candidate would have scored on the holdout. Never used to
    # choose (switching after seeing these numbers would leak the holdout into the decision).
    for name, fn in CANDIDATES.items():
        if name in frozen:
            continue
        rows.append({"model": name, "period": "holdout May-Jun (post-hoc, not used to choose)",
                     **_score(y[hold].to_numpy(), fn(X[train], y[train])(X[hold]))})
    metrics = pd.DataFrame(rows)

    pred = df[["gaming_date", "local_weekday", "events_active"]].copy()
    pred["split"] = np.where(inner_tr, "train", np.where(inner_va, "validation (Apr)", "holdout"))
    pred.loc[train & ~inner_tr & ~inner_va, "split"] = "train"
    pred["actual_coin_in_usd"] = y.values
    pred["model_coin_in_usd"] = frozen[chosen](X)
    pred["baseline_coin_in_usd"] = frozen[BASELINE](X)

    # empirical 80% band from holdout residual ratios (honest: measured out of sample)
    ratio = (y[hold] / pred.loc[hold, "model_coin_in_usd"]).to_numpy()
    lo_q, hi_q = np.quantile(ratio, [0.1, 0.9])

    # weekend-level error: the smallest promo lift one weekend can reveal (2 x RMSE of Fri-Sun sums)
    h = pred[hold].copy()
    h["wk"] = h.gaming_date.dt.to_period("W-MON")
    wk = h[h.local_weekday.isin(["Fri", "Sat", "Sun"])].groupby("wk").agg(
        a=("actual_coin_in_usd", "sum"), p=("model_coin_in_usd", "sum"), n=("actual_coin_in_usd", "size"))
    wk = wk[(wk.n == 3)]
    clean_wk = wk[~wk.index.isin(h[h.events_active.notna()].wk.unique())]
    weekend_rmse_pct = float(np.sqrt(np.mean((clean_wk.a / clean_wk.p - 1) ** 2))) if len(clean_wk) else float("nan")

    # 4. July plan: frozen model on the July calendar (inputs known in advance only)
    fut = pd.DataFrame({"gaming_date": FUTURE})
    fut["local_weekday"] = fut.gaming_date.dt.strftime("%a")
    fut["federal_holiday"] = fut.gaming_date.map(JULY_HOLIDAYS)
    fut["events_active"] = None
    Xf = _features(fut, events)
    fut["split"] = "forecast Jul"
    fut["actual_coin_in_usd"] = np.nan
    fut["model_coin_in_usd"] = frozen[chosen](Xf)
    fut["baseline_coin_in_usd"] = frozen[BASELINE](Xf)
    pred = pd.concat([pred, fut[pred.columns]], ignore_index=True)
    pred["lower_80_usd"] = pred.model_coin_in_usd * lo_q
    pred["upper_80_usd"] = pred.model_coin_in_usd * hi_q
    pred["model"] = chosen
    pred["gaming_date"] = pred.gaming_date.dt.date

    hm = metrics[metrics.period == "holdout May-Jun"].set_index("model")
    params = {
        "chosen_model": chosen,
        "freeze_date": str(FREEZE_DATE.date()),
        "holdout_mae_model": hm.loc[chosen, "mae"],
        "holdout_mae_baseline": hm.loc[BASELINE, "mae"],
        "holdout_mape_model": hm.loc[chosen, "mape"],
        "mae_improvement_vs_baseline": 1 - hm.loc[chosen, "mae"] / hm.loc[BASELINE, "mae"],
        "band_80_low_ratio": float(lo_q),
        "band_80_high_ratio": float(hi_q),
        "weekend_rmse_pct": weekend_rmse_pct,
        "min_detectable_promo_lift": 2 * weekend_rmse_pct,
        "july_forecast_coin_in_usd": float(fut.model_coin_in_usd.sum()),
    }
    return ForecastResult(pred, metrics, selection, chosen, params, FrozenForecast(frozen[chosen], events, chosen))
