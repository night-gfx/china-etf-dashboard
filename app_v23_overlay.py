from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v18_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v18_core", "exec"), globals(), globals())


def _rolling_relative_return_diff(series_map, lookback_months):
    benchmark = series_map.get(SECTOR_BENCHMARK_LABEL)
    if benchmark is None:
        return pd.DataFrame()

    periods = max(int(round(float(lookback_months) * 21)), 1)
    benchmark_return = benchmark / benchmark.shift(periods) - 1.0

    data = {}
    for label, series in series_map.items():
        if label == SECTOR_BENCHMARK_LABEL:
            continue
        sector_return = series / series.shift(periods) - 1.0
        data[label] = (sector_return - benchmark_return) * 100.0

    return pd.DataFrame(data).dropna(how="all")


def _rolling_relative_return_figure(diff_frame, lookback_months):
    fig = go.Figure()

    for label in diff_frame.columns:
        s = pd.to_numeric(diff_frame[label], errors="coerce").dropna()
        if s.empty:
            continue
        color = ACTIVE_SECTOR_COLORS.get(label, "#9ca3af")
        fig.add_trace(go.Scatter(
            x=s.index,
            y=s,
            mode="lines",
            name=label,
            line=dict(width=1.7, color=color),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>%{y:.2f} %-Pkt.</b>"
                "<extra>%{fullData.name}</extra>"
            ),
        ))

    fig.add_hline(y=0, line_width=1, line_dash="dot")

    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title=f"{lookback_months}M-Renditedifferenz in %-Pkt.",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _forward_relative_return_scatter(
    series_map,
    current_diff,
    history_years,
    forward_months,
):
    benchmark = series_map.get(SECTOR_BENCHMARK_LABEL)
    if benchmark is None or current_diff.empty:
        return None

    forward_periods = max(int(round(float(forward_months) * 21)), 1)
    benchmark_forward = benchmark.shift(-forward_periods) / benchmark - 1.0

    latest_date = pd.Timestamp(current_diff.index.max())
    start_date = latest_date - pd.DateOffset(years=int(history_years))

    fig = go.Figure()
    points_found = False

    for label in current_diff.columns:
        sector = series_map.get(label)
        if sector is None:
            continue

        sector_forward = sector.shift(-forward_periods) / sector - 1.0
        forward_diff = (sector_forward - benchmark_forward) * 100.0

        pair = pd.concat(
            [
                pd.to_numeric(current_diff[label], errors="coerce").rename("current"),
                pd.to_numeric(forward_diff, errors="coerce").rename("forward"),
            ],
            axis=1,
        ).dropna()
        pair = pair.loc[pair.index >= start_date]
        if pair.empty:
            continue

        points_found = True
        color = ACTIVE_SECTOR_COLORS.get(label, "#9ca3af")
        dates = pair.index.strftime("%d.%m.%Y").to_numpy().reshape(-1, 1)

        fig.add_trace(go.Scattergl(
            x=pair["current"],
            y=pair["forward"],
            mode="markers",
            name=label,
            marker=dict(size=5, opacity=0.42, color=color),
            customdata=dates,
            hovertemplate=(
                "Datum: %{customdata[0]}<br>"
                "Aktuell: %{x:.2f} %-Pkt.<br>"
                f"Forward {forward_months}M: "
                "%{y:.2f} %-Pkt."
                "<extra>%{fullData.name}</extra>"
            ),
        ))

    if not points_found:
        return None

    fig.add_hline(y=0, line_width=1, line_dash="dot")
    fig.add_vline(x=0, line_width=1, line_dash="dot")

    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["xaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="Aktuelle rollierende Renditedifferenz in %-Pkt.",
    )
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title=f"Forward {forward_months}M-Renditedifferenz in %-Pkt.",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
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
            key="sector_perf_v25",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd_v25",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v25",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr_v25",
        )

    s1, s2, s3 = st.columns(3, gap="large")
    with s1:
        lookback_months = st.slider(
            "Lookback Renditedifferenz (Monate)",
            min_value=1,
            max_value=60,
            value=12,
            step=1,
            key="sector_diff_lookback_months_v25",
        )
    with s2:
        history_years = st.slider(
            "Historie Forward-Analyse (Jahre)",
            min_value=1,
            max_value=20,
            value=10,
            step=1,
            key="sector_forward_history_years_v25",
        )
    with s3:
        forward_months = st.slider(
            "Forward-Horizont Y (Monate)",
            min_value=1,
            max_value=36,
            value=12,
            step=1,
            key="sector_forward_months_v25",
        )

    rolling_diff = _rolling_relative_return_diff(
        series_map,
        lookback_months,
    )

    if not rolling_diff.empty:
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown(
                f"#### Rollierende {lookback_months}-Monats-Renditedifferenz zum S&P 500"
            )
            st.plotly_chart(
                _rolling_relative_return_figure(
                    rolling_diff,
                    lookback_months,
                ),
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
                key="sector_dynamic_rolling_diff_v25",
            )

        with c2:
            st.markdown(
                f"#### Renditedifferenz vs. Forward {forward_months}M – letzte {history_years} Jahre"
            )
            forward_fig = _forward_relative_return_scatter(
                series_map,
                rolling_diff,
                history_years,
                forward_months,
            )
            if forward_fig is not None:
                st.plotly_chart(
                    forward_fig,
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_forward_scatter_v25",
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
