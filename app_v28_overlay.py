from pathlib import Path

import pandas as pd
import streamlit as st

_source = Path(__file__).with_name("app_v27_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v27_core", "exec"), globals(), globals())


def _common_active_sector_series(raw):
    if not raw or "SPY" not in raw:
        return {}

    benchmark = pd.to_numeric(
        raw.get("SPY"),
        errors="coerce",
    ).dropna().sort_index()
    if benchmark.empty:
        return {}

    series = {
        SECTOR_BENCHMARK_LABEL: benchmark,
    }

    for item in SECTOR_ETFS:
        ticker = item["ticker"]
        if ticker in EXCLUDED_SECTOR_TICKERS:
            continue
        raw_series = raw.get(ticker)
        if raw_series is None:
            continue
        s = pd.to_numeric(
            raw_series,
            errors="coerce",
        ).dropna().sort_index()
        if s.empty:
            continue
        series[SECTOR_LABELS[ticker]] = s

    if len(series) <= 1:
        return {}

    frame = pd.concat(
        series,
        axis=1,
        join="inner",
    ).dropna(how="any").sort_index()

    if frame.empty:
        return {}

    return {
        col: frame[col].copy()
        for col in frame.columns
    }


top_page = _text_nav(
    [
        "China ETF Dashboard",
        "Asset Allocation Backtesting Tool",
        "S&P 500 Sector ETFs",
    ],
    "top_page",
    "China ETF Dashboard",
    "top_text_nav",
)
st.session_state.after_tax = True

if top_page == "China ETF Dashboard":
    render_china_dashboard()
elif top_page == "Asset Allocation Backtesting Tool":
    render_asset_allocation_tool()
else:
    render_sp500_sector_etfs()
