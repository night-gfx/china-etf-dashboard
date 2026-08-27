from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v21_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v21_core", "exec"), globals(), globals())


def _extreme_diff_vs_sp500_figure(diff_figure):
    series = {}

    for trace in diff_figure.data:
        if getattr(trace, "x", None) is None or getattr(trace, "y", None) is None:
            continue
        name = str(getattr(trace, "name", "") or "")
        if not name:
            continue

        x = pd.to_datetime(list(trace.x), errors="coerce")
        y = pd.to_numeric(pd.Series(list(trace.y)), errors="coerce")
        if len(x) != len(y):
            continue

        s = pd.Series(y.to_numpy(), index=x, name=name)
        s = s[~s.index.isna()]
        if not s.empty:
            series[name] = s

    if not series:
        return None

    frame = pd.concat(series, axis=1).sort_index().dropna(how="all")
    if frame.empty:
        return None

    max_values = frame.max(axis=1)
    min_values = frame.min(axis=1)
    max_sectors = frame.idxmax(axis=1)
    min_sectors = frame.idxmin(axis=1)

    raw = sector_prices_usd()
    spy_raw = raw.get("SPY") if raw else None
    if spy_raw is None or spy_raw.empty:
        return None

    spy = pd.to_numeric(spy_raw, errors="coerce").reindex(frame.index).ffill()
    spy = spy.dropna()
    if spy.empty:
        return None

    common_index = frame.index.intersection(spy.index)
    if common_index.empty:
        return None

    max_values = max_values.reindex(common_index)
    min_values = min_values.reindex(common_index)
    max_sectors = max_sectors.reindex(common_index)
    min_sectors = min_sectors.reindex(common_index)
    spy = spy.reindex(common_index)

    first_spy = float(spy.iloc[0])
    if not np.isfinite(first_spy) or first_spy == 0:
        return None
    spy_indexed = spy / first_spy * 100.0

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=common_index,
        y=max_values,
        mode="lines",
        name="Maximum aller Sektoren",
        customdata=np.asarray(max_sectors.astype(str)).reshape(-1, 1),
        line=dict(width=2.0),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>Maximum: %{y:.2f} %-Pkt.</b><br>"
            "Sektor: %{customdata[0]}"
            "<extra></extra>"
        ),
    ))

    fig.add_trace(go.Scatter(
        x=common_index,
        y=min_values,
        mode="lines",
        name="Minimum aller Sektoren",
        customdata=np.asarray(min_sectors.astype(str)).reshape(-1, 1),
        line=dict(width=2.0),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>Minimum: %{y:.2f} %-Pkt.</b><br>"
            "Sektor: %{customdata[0]}"
            "<extra></extra>"
        ),
    ))

    fig.add_trace(go.Scatter(
        x=common_index,
        y=spy_indexed,
        mode="lines",
        name="S&P 500 (Start = 100)",
        yaxis="y2",
        line=dict(width=2.2, dash="dash"),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>S&P 500: %{y:.2f}</b>"
            "<extra></extra>"
        ),
    ))

    layout = base_layout(True)
    layout["height"] = 560
    layout["hovermode"] = "x unified"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=True,
        zerolinewidth=1,
        title="Max./Min. 1Y-Renditedifferenz in %-Pkt.",
    )
    layout["yaxis2"] = dict(
        overlaying="y",
        side="right",
        showgrid=False,
        zeroline=False,
        title="S&P 500 (Start = 100)",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


_render_sp500_sector_etfs_core = render_sp500_sector_etfs


def render_sp500_sector_etfs():
    original_plotly_chart = st.plotly_chart

    def _plotly_chart_with_extremes(fig, *args, **kwargs):
        result = original_plotly_chart(fig, *args, **kwargs)

        if kwargs.get("key") == "sector_rolling_return_diff_v23":
            extreme_fig = _extreme_diff_vs_sp500_figure(fig)
            if extreme_fig is not None:
                st.markdown(
                    "#### Maximum / Minimum der 1Y-Renditedifferenzen vs. S&P 500"
                )
                original_plotly_chart(
                    extreme_fig,
                    width="stretch",
                    config={
                        "displaylogo": False,
                        "scrollZoom": True,
                    },
                    key="sector_extreme_diff_vs_sp500_v24",
                )

        return result

    st.plotly_chart = _plotly_chart_with_extremes
    try:
        _render_sp500_sector_etfs_core()
    finally:
        st.plotly_chart = original_plotly_chart


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
