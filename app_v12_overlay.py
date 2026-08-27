from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v11_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v11_core", "exec"), globals(), globals())

_original_render_asset_allocation_tool = render_asset_allocation_tool
_AA_LAST_WEIGHT_HISTORY = None
_AA_LAST_PORTFOLIO = None

def backtest_portfolio(prices, weights, frequency):
    global _AA_LAST_WEIGHT_HISTORY, _AA_LAST_PORTFOLIO
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    target = np.asarray(weights, dtype=float)
    target = target / target.sum()
    values = target.copy()
    portfolio_values = []
    weight_rows = []
    last_key = None
    for date, row in returns.iterrows():
        key = rebalance_key(pd.Timestamp(date), frequency)
        if frequency != "Kein Rebalancing" and key != last_key and portfolio_values:
            total_before = float(values.sum())
            values = total_before * target
        values = values * (1.0 + row.to_numpy(dtype=float))
        total = float(values.sum())
        portfolio_values.append(total)
        weight_rows.append(values / total if total != 0 else target.copy())
        last_key = key
    portfolio = pd.Series(portfolio_values, index=returns.index, name="Portfolio", dtype=float) * 100.0
    weight_history = pd.DataFrame(weight_rows, index=returns.index, columns=prices.columns, dtype=float)
    _AA_LAST_WEIGHT_HISTORY = weight_history
    _AA_LAST_PORTFOLIO = portfolio
    return portfolio

def annual_information_ratio(portfolio, benchmark):
    aligned = pd.concat([portfolio.rename("Portfolio"), benchmark.rename("Benchmark")], axis=1).dropna()
    returns = aligned.pct_change(fill_method=None).dropna()
    if returns.empty:
        return pd.Series(dtype=float)
    active = returns["Portfolio"] - returns["Benchmark"]
    values = {}
    for year, series in active.groupby(active.index.year):
        series = series.dropna()
        if len(series) < 20:
            values[int(year)] = np.nan
            continue
        tracking_error = float(series.std(ddof=1))
        if tracking_error == 0 or np.isnan(tracking_error):
            values[int(year)] = np.nan
        else:
            values[int(year)] = float(series.mean()) / tracking_error * np.sqrt(252)
    return pd.Series(values, name="Information Ratio", dtype=float)

def weight_history_figure(weight_history, assets):
    name_map = {asset["symbol"]: f"{asset['name']} ({asset['symbol']})" for asset in assets}
    frame = weight_history.rename(columns=name_map) * 100.0
    fig = go.Figure()
    for col in frame.columns:
        fig.add_trace(go.Scatter(
            x=frame.index, y=frame[col], mode="lines", name=col,
            stackgroup="portfolio_weights", line=dict(width=0.8),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f} %</b><extra>%{fullData.name}</extra>",
        ))
    layout = base_layout(True)
    layout["height"] = 500
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(showgrid=False, zeroline=False, range=[0, 100], title="Gewicht in %", ticksuffix=" %")
    fig.update_layout(**layout)
    return fig

def annual_ir_figure(information_ratio):
    clean = information_ratio.dropna()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[str(int(year)) for year in clean.index], y=clean.values,
        name="Information Ratio",
        hovertemplate="<b>%{x}</b><br>Information Ratio: %{y:.2f}<extra></extra>",
    ))
    layout = base_layout(False)
    layout["height"] = 430
    layout["hovermode"] = "closest"
    layout["xaxis"] = dict(showgrid=False, zeroline=False, title="Jahr")
    layout["yaxis"] = dict(showgrid=False, zeroline=True, zerolinewidth=1, title="Information Ratio")
    fig.update_layout(**layout)
    return fig

def render_asset_allocation_tool():
    global _AA_LAST_WEIGHT_HISTORY, _AA_LAST_PORTFOLIO
    _AA_LAST_WEIGHT_HISTORY = None
    _AA_LAST_PORTFOLIO = None
    _original_render_asset_allocation_tool()
    if not st.session_state.get("aa_run"):
        return
    assets = _aa_assets()
    benchmark = st.session_state.get("aa_benchmark")
    if not assets or not benchmark:
        return
    if _AA_LAST_WEIGHT_HISTORY is None or _AA_LAST_PORTFOLIO is None:
        return
    st.markdown("#### Gewichtsentwicklung")
    st.plotly_chart(
        weight_history_figure(_AA_LAST_WEIGHT_HISTORY, assets),
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
        key="aa_weight_history",
    )
    try:
        benchmark_series, _ = asset_series_eur(benchmark["symbol"])
    except Exception:
        return
    benchmark_aligned = benchmark_series.reindex(_AA_LAST_PORTFOLIO.index).dropna()
    common = _AA_LAST_PORTFOLIO.index.intersection(benchmark_aligned.index)
    if len(common) < 20:
        return
    portfolio_aligned = _AA_LAST_PORTFOLIO.loc[common]
    benchmark_indexed = benchmark_aligned.loc[common] / benchmark_aligned.loc[common].iloc[0] * 100.0
    annual_ir = annual_information_ratio(portfolio_aligned, benchmark_indexed)
    if annual_ir.dropna().empty:
        return
    st.markdown("#### Jährliche Information Ratio")
    st.plotly_chart(
        annual_ir_figure(annual_ir),
        width="stretch",
        config={"displaylogo": False},
        key="aa_annual_information_ratio",
    )

top_page = _text_nav(
    ["China ETF Dashboard", "Asset Allocation Backtesting Tool"],
    "top_page", "China ETF Dashboard", "top_text_nav"
)
st.session_state.after_tax = True

if top_page == "China ETF Dashboard":
    render_china_dashboard()
else:
    render_asset_allocation_tool()
