from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

_source = Path(__file__).with_name("app_v12_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v12_core", "exec"), globals(), globals())

SECTOR_ETFS = [
    {"sector": "Communication Services", "ticker": "XLC", "inception": "18.06.2018"},
    {"sector": "Consumer Discretionary", "ticker": "XLY", "inception": "16.12.1998"},
    {"sector": "Consumer Staples", "ticker": "XLP", "inception": "16.12.1998"},
    {"sector": "Energy", "ticker": "XLE", "inception": "16.12.1998"},
    {"sector": "Financials", "ticker": "XLF", "inception": "16.12.1998"},
    {"sector": "Health Care", "ticker": "XLV", "inception": "16.12.1998"},
    {"sector": "Industrials", "ticker": "XLI", "inception": "16.12.1998"},
    {"sector": "Information Technology", "ticker": "XLK", "inception": "16.12.1998"},
    {"sector": "Materials", "ticker": "XLB", "inception": "16.12.1998"},
    {"sector": "Real Estate", "ticker": "XLRE", "inception": "07.10.2015"},
    {"sector": "Utilities", "ticker": "XLU", "inception": "16.12.1998"},
]
SECTOR_BENCHMARK = {"sector": "S&P 500", "ticker": "SPY", "inception": "22.01.1993"}
SECTOR_LABELS = {x["ticker"]: f"{x['sector']} ({x['ticker']})" for x in SECTOR_ETFS}
SECTOR_LABELS["SPY"] = "S&P 500 (SPY)"


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def sector_prices_usd():
    tickers = [x["ticker"] for x in SECTOR_ETFS] + [SECTOR_BENCHMARK["ticker"]]
    raw = yf.download(
        tickers=tickers,
        start="1990-01-01",
        auto_adjust=False,
        actions=False,
        progress=False,
        threads=True,
        timeout=30,
    )
    if raw is None or raw.empty:
        return {}
    if isinstance(raw.columns, pd.MultiIndex):
        first = raw.columns.get_level_values(0)
        if "Adj Close" in first:
            prices = raw["Adj Close"]
        elif "Close" in first:
            prices = raw["Close"]
        else:
            return {}
    else:
        col = "Adj Close" if "Adj Close" in raw.columns else "Close" if "Close" in raw.columns else None
        if col is None:
            return {}
        prices = raw[[col]].rename(columns={col: tickers[0]})
    if isinstance(prices, pd.Series):
        prices = prices.to_frame()
    if isinstance(prices.index, pd.DatetimeIndex):
        if prices.index.tz is not None:
            prices.index = prices.index.tz_localize(None)
        prices.index = prices.index.normalize()
    result = {}
    for ticker in tickers:
        if ticker not in prices.columns:
            continue
        s = pd.to_numeric(prices[ticker], errors="coerce").dropna()
        s = s[~s.index.duplicated(keep="last")].sort_index()
        if len(s) >= 30:
            result[ticker] = s.rename(SECTOR_LABELS[ticker])
    return result


def _indexed_individually(series_map):
    pieces = []
    for label, series in series_map.items():
        s = series.dropna()
        if s.empty:
            continue
        pieces.append((s / s.iloc[0] * 100.0).rename(label))
    return pd.concat(pieces, axis=1).sort_index() if pieces else pd.DataFrame()


def _sector_performance_figure(frame):
    fig = go.Figure()
    for col in frame.columns:
        is_benchmark = col == "S&P 500 (SPY)"
        fig.add_trace(go.Scatter(
            x=frame.index,
            y=frame[col],
            mode="lines",
            name=col,
            line=dict(width=2.5 if is_benchmark else 1.8, dash="dash" if is_benchmark else "solid"),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>%{fullData.name}</extra>",
        ))
    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(showgrid=False, zeroline=False, type="log", title="Indexiert (log)")
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.16, x=0)
    fig.update_layout(**layout)
    return fig


def _sector_drawdown_figure(series_map):
    fig = go.Figure()
    for label, series in series_map.items():
        s = series.dropna()
        dd = (s / s.cummax() - 1.0) * 100.0
        is_benchmark = label == "S&P 500 (SPY)"
        fig.add_trace(go.Scatter(
            x=dd.index,
            y=dd,
            mode="lines",
            name=label,
            line=dict(width=2.5 if is_benchmark else 1.8, dash="dash" if is_benchmark else "solid"),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f} %</b><extra>%{fullData.name}</extra>",
        ))
    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(showgrid=False, zeroline=True, title="Drawdown in %")
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.16, x=0)
    fig.update_layout(**layout)
    return fig


def _sector_correlation_figure(series_map):
    returns = pd.DataFrame({k: v.pct_change(fill_method=None) for k, v in series_map.items()})
    corr = returns.corr(min_periods=126)
    fig = go.Figure(go.Heatmap(
        z=corr.values,
        x=corr.columns,
        y=corr.index,
        zmin=-1,
        zmax=1,
        zmid=0,
        colorscale="RdYlGn",
        text=np.round(corr.values, 2),
        texttemplate="%{text:.2f}",
        hovertemplate="%{y} ↔ %{x}<br><b>%{z:.3f}</b><extra></extra>",
    ))
    fig.update_layout(
        height=540,
        margin=dict(l=25, r=15, t=15, b=30),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#111827"),
    )
    return fig


def _sector_rolling_corr_figure(series_map):
    benchmark = series_map.get("S&P 500 (SPY)")
    fig = go.Figure()
    if benchmark is None:
        return fig
    benchmark_returns = benchmark.pct_change(fill_method=None)
    for label, series in series_map.items():
        if label == "S&P 500 (SPY)":
            continue
        aligned = pd.concat([
            series.pct_change(fill_method=None).rename("sector"),
            benchmark_returns.rename("benchmark"),
        ], axis=1).dropna()
        if aligned.empty:
            continue
        rolling = aligned["sector"].rolling(252, min_periods=126).corr(aligned["benchmark"])
        fig.add_trace(go.Scatter(
            x=rolling.index,
            y=rolling,
            mode="lines",
            name=label,
            line=dict(width=1.8),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>%{fullData.name}</extra>",
        ))
    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(showgrid=False, zeroline=True, range=[-1, 1], title="Korrelation")
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.16, x=0)
    fig.update_layout(**layout)
    return fig


def _sector_metrics(series_map):
    rows = {}
    for label, series in series_map.items():
        metrics = backtest_metrics(series)
        if metrics:
            rows[label] = metrics
    return pd.DataFrame.from_dict(rows, orient="index")


def _sector_annual_sharpe(series_map):
    years = sorted({int(year) for s in series_map.values() for year in s.dropna().index.year})
    rows = {}
    for label, series in series_map.items():
        row = {}
        s = series.dropna()
        for year in years:
            sy = s[s.index.year == year]
            row[str(year)] = sharpe0(sy) if len(sy) >= 20 else np.nan
        rows[label] = row
    return pd.DataFrame.from_dict(rows, orient="index")


def render_sp500_sector_etfs():
    raw = sector_prices_usd()
    if not raw:
        st.error("Sektordaten konnten nicht geladen werden.")
        return

    series_map = {}
    overview_rows = []
    for item in SECTOR_ETFS + [SECTOR_BENCHMARK]:
        ticker = item["ticker"]
        if ticker not in raw:
            continue
        label = SECTOR_LABELS[ticker]
        series_map[label] = raw[ticker]
        overview_rows.append({
            "Sektor": item["sector"],
            "ETF": ticker,
            "Auflage": item["inception"],
            "Daten verfügbar": f"{raw[ticker].index.min():%d.%m.%Y} – {raw[ticker].index.max():%d.%m.%Y}",
        })

    overview = pd.DataFrame(overview_rows)
    st.dataframe(
        overview,
        width="stretch",
        hide_index=True,
        height=compact_height(len(overview), maximum=500),
    )

    indexed = _indexed_individually(series_map)
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung (jeweils ab Start = 100)")
        st.plotly_chart(
            _sector_performance_figure(indexed),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_perf",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr",
        )

    metrics = _sector_metrics(series_map)
    st.markdown("#### Kennzahlen")
    st.dataframe(
        style_heat(metrics, reverse_columns={"Volatilität p.a."}),
        width="stretch",
        height=compact_height(len(metrics), maximum=520),
    )

    annual_sharpe = _sector_annual_sharpe(series_map)
    st.markdown("#### Jährliche Sharpe Ratio")
    st.dataframe(
        style_heat(annual_sharpe),
        width="stretch",
        height=compact_height(len(annual_sharpe), maximum=520),
    )


top_page = _text_nav(
    ["China ETF Dashboard", "Asset Allocation Backtesting Tool", "S&P 500 Sector ETFs"],
    "top_page", "China ETF Dashboard", "top_text_nav"
)
st.session_state.after_tax = True

if top_page == "China ETF Dashboard":
    render_china_dashboard()
elif top_page == "Asset Allocation Backtesting Tool":
    render_asset_allocation_tool()
else:
    render_sp500_sector_etfs()
