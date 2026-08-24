from __future__ import annotations

import math
import numpy as np
import pandas as pd

TRADING_DAYS = 252


def daily_returns(series: pd.Series) -> pd.Series:
    return series.dropna().pct_change(fill_method=None).dropna()


def cagr(series: pd.Series) -> float:
    s = series.dropna()
    if len(s) < 2 or s.iloc[0] <= 0 or s.iloc[-1] <= 0:
        return np.nan
    years = max((s.index[-1] - s.index[0]).days / 365.2425, 1 / 365.2425)
    return (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1


def annual_volatility(series: pd.Series) -> float:
    r = daily_returns(series)
    return r.std(ddof=1) * math.sqrt(TRADING_DAYS) if len(r) > 1 else np.nan


def drawdown(series: pd.Series) -> pd.Series:
    s = series.dropna()
    if s.empty:
        return s
    return s / s.cummax() - 1.0


def max_drawdown(series: pd.Series) -> float:
    dd = drawdown(series)
    return dd.min() if not dd.empty else np.nan


def sharpe(series: pd.Series, rf_annual: float = 0.0) -> float:
    r = daily_returns(series)
    if len(r) < 2:
        return np.nan
    ann_vol = r.std(ddof=1) * math.sqrt(TRADING_DAYS)
    if ann_vol == 0 or np.isnan(ann_vol):
        return np.nan
    ann_arithmetic = r.mean() * TRADING_DAYS
    return (ann_arithmetic - rf_annual) / ann_vol


def sortino(series: pd.Series, rf_annual: float = 0.0) -> float:
    r = daily_returns(series)
    downside = r[r < 0]
    if len(r) < 2 or len(downside) < 2:
        return np.nan
    downside_dev = downside.std(ddof=1) * math.sqrt(TRADING_DAYS)
    if downside_dev == 0 or np.isnan(downside_dev):
        return np.nan
    ann_arithmetic = r.mean() * TRADING_DAYS
    return (ann_arithmetic - rf_annual) / downside_dev


def tracking_error_and_ir(series: pd.Series, benchmark: pd.Series) -> tuple[float, float, pd.Timestamp | None]:
    joined = pd.concat([series, benchmark], axis=1, join="inner").dropna()
    if len(joined) < 3:
        return np.nan, np.nan, None
    r = joined.pct_change(fill_method=None).dropna()
    if len(r) < 2:
        return np.nan, np.nan, joined.index.min()
    active = r.iloc[:, 0] - r.iloc[:, 1]
    te = active.std(ddof=1) * math.sqrt(TRADING_DAYS)
    ir = (active.mean() * TRADING_DAYS / te) if te and not np.isnan(te) else np.nan
    return te, ir, joined.index.min()


def calendar_returns(series: pd.Series) -> pd.Series:
    s = series.dropna()
    if s.empty:
        return pd.Series(dtype=float)
    # Include partial first/last years by using first observation as start anchor.
    yearly_last = s.resample("YE").last()
    vals = yearly_last.pct_change(fill_method=None)
    first_year = s[s.index.year == s.index[0].year]
    if len(first_year) >= 2:
        vals.loc[yearly_last.index[0]] = first_year.iloc[-1] / first_year.iloc[0] - 1
    vals.index = vals.index.year
    return vals.dropna()


def relative_table(frame: pd.DataFrame, benchmark_col: str) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    years = sorted({int(y) for c in frame.columns for y in calendar_returns(frame[c]).index}, reverse=True)
    rows = []
    for col in frame.columns:
        s = frame[col].dropna()
        if col == benchmark_col:
            te, ir, ir_start = 0.0, 0.0, s.index.min() if not s.empty else None
        else:
            te, ir, ir_start = tracking_error_and_ir(s, frame[benchmark_col].dropna())
        cr = calendar_returns(s)
        row = {
            "ETF (Index)": col,
            "CAGR p.a.": cagr(s),
            "Information Ratio p.a.": ir,
            "Tracking Error p.a.": te,
            "IR-Start": ir_start.date().isoformat() if ir_start is not None else "–",
        }
        for y in years:
            row[str(y)] = cr.get(y, np.nan)
        rows.append(row)
    return pd.DataFrame(rows).set_index("ETF (Index)")


def total_period_table(frame: pd.DataFrame, benchmark_col: str, rf_annual: float) -> pd.DataFrame:
    rows = []
    for col in frame.columns:
        s = frame[col].dropna()
        if len(s) < 2:
            continue
        cr = calendar_returns(s)
        if col == benchmark_col:
            te, ir = 0.0, 0.0
        else:
            te, ir, _ = tracking_error_and_ir(s, frame[benchmark_col].dropna())
        dd = max_drawdown(s)
        cg = cagr(s)
        rows.append({
            "ETF (Index)": col,
            "Start": s.index.min().date().isoformat(),
            "Ende": s.index.max().date().isoformat(),
            "Gesamtrendite": s.iloc[-1] / s.iloc[0] - 1,
            "CAGR p.a.": cg,
            "Volatilität p.a.": annual_volatility(s),
            "Max. Drawdown": dd,
            "Sharpe": sharpe(s, rf_annual),
            "Sortino": sortino(s, rf_annual),
            "Calmar": cg / abs(dd) if dd and not np.isnan(dd) else np.nan,
            "Tracking Error p.a.": te,
            "Information Ratio p.a.": ir,
            "Bestes Jahr": cr.max() if not cr.empty else np.nan,
            "Schlechtestes Jahr": cr.min() if not cr.empty else np.nan,
        })
    return pd.DataFrame(rows).set_index("ETF (Index)") if rows else pd.DataFrame()
