"""
Predictive analytics: Prophet (primary), statsmodels Holt-Winters, scikit-learn trend.

Assumption (business proxy): daily ISSUE quantity × unit_price ≈ sales; stock-out units ≈ units sold.
"""
from __future__ import annotations

import warnings
from typing import Any

import numpy as np
import pandas as pd

# Suppress noisy stan/cmdstan logs when Prophet is used
warnings.filterwarnings("ignore", category=FutureWarning)


def daily_to_prophet_df(daily: list[dict[str, Any]], value_key: str = "y_revenue") -> pd.DataFrame:
    """Build a continuous daily index with zeros on days without ISSUE activity."""
    if not daily:
        return pd.DataFrame(columns=["ds", "y"])
    df = pd.DataFrame(daily)
    df["ds"] = pd.to_datetime(df["ds"])
    y = df[value_key].astype(float)
    df = pd.DataFrame({"ds": df["ds"], "y": y}).sort_values("ds").groupby("ds", as_index=False)["y"].sum()
    full = pd.date_range(df["ds"].min(), df["ds"].max(), freq="D")
    ser = df.set_index("ds")["y"].reindex(full, fill_value=0.0)
    out = ser.reset_index()
    out.columns = ["ds", "y"]
    return out


def prophet_runtime_info() -> tuple[bool, str]:
    """Whether Prophet imports, and its package version (for UI)."""
    try:
        import prophet

        return True, str(getattr(prophet, "__version__", "unknown"))
    except ImportError:
        return False, ""


def run_prophet_forecast(
    df: pd.DataFrame, periods: int
) -> tuple[pd.DataFrame | None, pd.DataFrame | None, str | None]:
    """
    Returns (slim forecast: ds, yhat, yhat_lower, yhat_upper), (full predict output for components), error.
    """
    if df is None or len(df) < 10:
        return None, None, "Need at least 10 days of ISSUE history for Prophet."
    try:
        from prophet import Prophet
    except ImportError:
        return None, None, "Prophet is not installed (pip install prophet)."
    y = df["y"].values
    if np.nanmax(y) <= 0:
        return None, None, "All-zero demand proxy — add ISSUE (stock-out) movements to forecast."

    weekly = len(df) >= 14
    try:
        m = Prophet(
            daily_seasonality=False,
            weekly_seasonality=weekly,
            yearly_seasonality=len(df) >= 366,
            seasonality_mode="additive",
        )
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            m.fit(df)
        future = m.make_future_dataframe(periods=periods, freq="D")
        fc = m.predict(future)
    except Exception as e:
        return None, None, f"Prophet fit/predict failed: {e}"

    keep = ["ds", "yhat", "yhat_lower", "yhat_upper"]
    return fc[keep].copy(), fc.copy(), None


def apply_what_if_to_forecast(fc: pd.DataFrame, history_len: int, pct_delta: float) -> pd.Series:
    """Scale Prophet yhat on the future tail only (after history_len rows)."""
    factor = 1.0 + pct_delta / 100.0
    yhat = fc["yhat"].astype(float).copy()
    yhat.iloc[history_len:] *= factor
    return yhat


def holt_winters_forecast(y: np.ndarray, periods: int) -> tuple[np.ndarray | None, str | None]:
    """statsmodels exponential smoothing (additive trend, no season — robust on short series)."""
    if len(y) < 8:
        return None, "Need at least 8 observations for exponential smoothing."
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except ImportError:
        return None, "statsmodels is not installed (pip install statsmodels)."
    try:
        model = ExponentialSmoothing(
            y,
            trend="add",
            seasonal=None,
            initialization_method="estimated",
        )
        fit = model.fit(optimized=True)
        fc = fit.forecast(periods)
        return np.asarray(fc, dtype=float), None
    except Exception as e:
        return None, str(e)


def sklearn_trend_forecast(y: np.ndarray, periods: int) -> tuple[np.ndarray | None, str | None]:
    """Simple linear trend — baseline comparison to Prophet."""
    if len(y) < 3:
        return None, "Need at least 3 points for linear trend."
    try:
        from sklearn.linear_model import LinearRegression
    except ImportError:
        return None, "scikit-learn is not installed (pip install scikit-learn)."
    X = np.arange(len(y), dtype=float).reshape(-1, 1)
    reg = LinearRegression().fit(X, y)
    Xf = np.arange(len(y), len(y) + periods, dtype=float).reshape(-1, 1)
    pred = reg.predict(Xf)
    return pred.astype(float), None


def build_kpi_block(
    daily: list[dict[str, Any]],
    last_30_units: float,
    last_30_revenue: float,
    prophet_sum_next: float | None,
    prophet_note: str | None,
    whatif_pct: float,
) -> dict[str, Any]:
    """Structured KPIs for the UI layer."""
    n_days = len(daily)
    rev = [float(d.get("y_revenue", 0) or 0) for d in daily]
    units = [float(d.get("y_units", 0) or 0) for d in daily]
    avg_rev = float(np.mean(rev)) if rev else 0.0
    avg_units = float(np.mean(units)) if units else 0.0
    peak_rev = float(np.max(rev)) if rev else 0.0
    peak_day = daily[int(np.argmax(rev))]["ds"] if rev and max(rev) > 0 else "—"

    adj_note = ""
    if prophet_sum_next is not None and whatif_pct != 0:
        adj_note = f" (Prophet next-period total × {1 + whatif_pct / 100:.2f} what-if)"

    return {
        "history_days_loaded": n_days,
        "avg_daily_revenue_proxy": avg_rev,
        "avg_daily_units_out": avg_units,
        "last_30d_units": last_30_units,
        "last_30d_revenue_proxy": last_30_revenue,
        "peak_day_revenue_proxy": peak_rev,
        "peak_day": peak_day,
        "prophet_next_horizon_sum": prophet_sum_next,
        "prophet_status": prophet_note or "OK",
        "what_if_applied_note": adj_note,
    }
