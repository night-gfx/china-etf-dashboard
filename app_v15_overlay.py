from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v14_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v14_core", "exec"), globals(), globals())

SECTOR_BENCHMARK_LABEL = "S&P 500 (SPY)"


def _sector_rolling_return_diff(series_map):
    benchmark = series_map.get(SECTOR_BENCHMARK_LABEL)
    if benchmark is None:
        return pd.DataFrame()

    benchmark_1y = benchmark / benchmark.shift(252) - 1.0
    data = {}
    for label, series in series_map.items():
        if label == SECTOR_BENCHMARK_LABEL:
            continue
        sector_1y = series / series.shift(252) - 1.0
        data[label] = (sector_1y - benchmark_1y) * 100.0
    return pd.DataFrame(data).dropna(how="all")


def _sector_rolling_return_diff_figure(diff_frame):
    fig = go.Figure()
    for col in diff_frame.columns:
        s = diff_frame[col].dropna()
        fig.add_trace(go.Scatter(
            x=s.index,
            y=s,
            mode="lines",
            name=col,
            line=dict(width=1.8),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f} %-Pkt.</b><extra>%{fullData.name}</extra>",
        ))
    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=True,
        zerolinewidth=1,
        title="Renditedifferenz in %-Pkt.",
    )
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.16, x=0)
    fig.update_layout(**layout)
    return fig


def _forward_max_return(series, window=252):
    s = series.dropna()
    future_max = (
        s.iloc[::-1]
        .rolling(window=window, min_periods=window)
        .max()
        .iloc[::-1]
        .shift(-1)
    )
    return (future_max / s - 1.0) * 100.0


def _sector_forward_max_scatter_data(series_map):
    benchmark = series_map.get(SECTOR_BENCHMARK_LABEL)
    if benchmark is None:
        return {}

    benchmark_1y = benchmark / benchmark.shift(252) - 1.0
    result = {}

    for label, series in series_map.items():
        if label == SECTOR_BENCHMARK_LABEL:
            continue

        sector_1y = series / series.shift(252) - 1.0
        trailing_diff = (sector_1y - benchmark_1y) * 100.0
        forward_max = _forward_max_return(series, 252)

        frame = pd.concat(
            [
                trailing_diff.rename("Renditedifferenz"),
                forward_max.rename("Max Folgejahresrendite"),
            ],
            axis=1,
        ).dropna()

        if frame.empty:
            continue

        frame = frame.groupby(frame.index.to_period("M")).tail(1)
        result[label] = frame

    return result


def _sector_forward_max_scatter_figure(scatter_data):
    fig = go.Figure()
    for label, frame in scatter_data.items():
        fig.add_trace(go.Scattergl(
            x=frame["Renditedifferenz"],
            y=frame["Max Folgejahresrendite"],
            mode="markers",
            name=label,
            customdata=np.array([frame.index.strftime("%d.%m.%Y")]).T,
            marker=dict(size=7, opacity=0.58),
            hovertemplate=(
                "%{customdata[0]}<br>"
                "1Y-Differenz: <b>%{x:.2f} %-Pkt.</b><br>"
                "Max. Folgejahresrendite: <b>%{y:.2f} %</b>"
                "<extra>%{fullData.name}</extra>"
            ),
        ))
    layout = base_layout(True)
    layout["height"] = 580
    layout["hovermode"] = "closest"
    layout["xaxis"] = dict(
        showgrid=False,
        zeroline=True,
        zerolinewidth=1,
        title="1Y-Renditedifferenz zum S&P 500 in %-Pkt.",
    )
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=True,
        zerolinewidth=1,
        title="Max. Rendite innerhalb der folgenden 12 Monate in %",
    )
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.18, x=0)
    fig.update_layout(**layout)
    return fig


def render_sp500_sector_etfs():
    raw = sector_prices_usd()
    if not raw:
        st.error("Sektordaten konnten nicht geladen werden.")
        return

    overview_rows = []
    for item in SECTOR_ETFS + [SECTOR_BENCHMARK]:
        ticker = item["ticker"]
        if ticker not in raw:
            continue
        overview_rows.append({
            "Sektor": item["sector"],
            "ETF": ticker,
            "Auflage": item["inception"],
            "Daten verfügbar": (
                f"{raw[ticker].index.min():%d.%m.%Y} – "
                f"{raw[ticker].index.max():%d.%m.%Y}"
            ),
        })

    overview = pd.DataFrame(overview_rows)
    st.dataframe(
        _sector_overview_style(overview),
        width="stretch",
        hide_index=True,
        height=compact_height(len(overview), maximum=500),
    )

    series_map = _common_active_sector_series(raw)
    if not series_map:
        st.error("Kein gemeinsamer Datenzeitraum für alle Sektor-ETFs verfügbar.")
        return

    indexed = _indexed_individually(series_map)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        st.plotly_chart(
            _sector_performance_figure(indexed),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_perf_v15",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd_v15",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v15",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr_v15",
        )

    rolling_diff = _sector_rolling_return_diff(series_map)
    if not rolling_diff.empty:
        st.markdown("#### Rollierende 1-Jahres-Renditedifferenz zum S&P 500")
        st.plotly_chart(
            _sector_rolling_return_diff_figure(rolling_diff),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_return_diff_v15",
        )

    scatter_data = _sector_forward_max_scatter_data(series_map)
    if scatter_data:
        st.markdown("#### Renditedifferenz vs. maximale Folgejahresperformance")
        st.plotly_chart(
            _sector_forward_max_scatter_figure(scatter_data),
            width="stretch",
            config={"displaylogo": False},
            key="sector_forward_max_scatter_v15",
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
