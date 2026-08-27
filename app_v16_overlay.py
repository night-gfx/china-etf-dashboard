from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v15_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v15_core", "exec"), globals(), globals())


def _sector_extreme_percentiles(diff_frame, warmup_years=10):
    frame = diff_frame.dropna(how="any").sort_index()
    if frame.empty:
        return pd.DataFrame()

    first_date = pd.Timestamp(frame.index.min())
    evaluation_start = first_date + pd.DateOffset(years=warmup_years)

    all_values = frame.to_numpy(dtype=float).ravel()
    all_values = all_values[np.isfinite(all_values)]
    if all_values.size == 0:
        return pd.DataFrame()
    coordinates = np.unique(all_values)

    tree = np.zeros(len(coordinates) + 1, dtype=np.int64)

    def add(value):
        idx = int(np.searchsorted(coordinates, value, side="left")) + 1
        while idx < len(tree):
            tree[idx] += 1
            idx += idx & -idx

    def prefix_count(value, inclusive=True):
        side = "right" if inclusive else "left"
        idx = int(np.searchsorted(coordinates, value, side=side))
        total = 0
        while idx > 0:
            total += int(tree[idx])
            idx -= idx & -idx
        return total

    history_count = 0
    rows = []

    for date, row in frame.iterrows():
        date = pd.Timestamp(date)
        current_values = pd.to_numeric(row, errors="coerce").dropna()

        if date >= evaluation_start and history_count and not current_values.empty:
            out_label = current_values.idxmax()
            out_value = float(current_values.loc[out_label])
            out_le = prefix_count(out_value, inclusive=True)
            out_lt = prefix_count(out_value, inclusive=False)
            out_percentile = 100.0 * out_le / history_count
            out_tail = 100.0 * (history_count - out_lt) / history_count

            under_label = current_values.idxmin()
            under_value = float(current_values.loc[under_label])
            under_le = prefix_count(under_value, inclusive=True)
            under_percentile = 100.0 * under_le / history_count
            under_tail = under_percentile

            rows.append({
                "Datum": date,
                "Outperformance Sektor": out_label,
                "Outperformance Differenz": out_value,
                "Outperformance Perzentil": out_percentile,
                "Outperformance Extremität": out_percentile,
                "Outperformance Tail": out_tail,
                "Underperformance Sektor": under_label,
                "Underperformance Differenz": under_value,
                "Underperformance Perzentil": under_percentile,
                "Underperformance Extremität": 100.0 - under_percentile,
                "Underperformance Tail": under_tail,
                "Historische Beobachtungen": history_count,
            })

        for value in current_values.to_numpy(dtype=float):
            if np.isfinite(value):
                add(float(value))
                history_count += 1

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).set_index("Datum")


def _sector_extreme_percentile_figure(percentiles):
    fig = go.Figure()

    out_custom = np.column_stack([
        percentiles["Outperformance Sektor"].astype(str),
        percentiles["Outperformance Differenz"].to_numpy(dtype=float),
        percentiles["Outperformance Perzentil"].to_numpy(dtype=float),
        percentiles["Outperformance Tail"].to_numpy(dtype=float),
        percentiles["Historische Beobachtungen"].to_numpy(dtype=int),
    ])
    fig.add_trace(go.Scatter(
        x=percentiles.index,
        y=percentiles["Outperformance Extremität"],
        mode="lines",
        name="Stärkste Outperformance",
        customdata=out_custom,
        line=dict(width=1.9),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>%{customdata[0]}</b><br>"
            "1Y-Differenz: %{customdata[1]:.2f} %-Pkt.<br>"
            "Historisches Perzentil: %{customdata[2]:.2f} %<br>"
            "Tail-Wahrscheinlichkeit ≥ aktuell: %{customdata[3]:.2f} %<br>"
            "Historische Beobachtungen: %{customdata[4]:,.0f}"
            "<extra></extra>"
        ),
    ))

    under_custom = np.column_stack([
        percentiles["Underperformance Sektor"].astype(str),
        percentiles["Underperformance Differenz"].to_numpy(dtype=float),
        percentiles["Underperformance Perzentil"].to_numpy(dtype=float),
        percentiles["Underperformance Tail"].to_numpy(dtype=float),
        percentiles["Historische Beobachtungen"].to_numpy(dtype=int),
    ])
    fig.add_trace(go.Scatter(
        x=percentiles.index,
        y=percentiles["Underperformance Extremität"],
        mode="lines",
        name="Stärkste Underperformance",
        customdata=under_custom,
        line=dict(width=1.9),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>%{customdata[0]}</b><br>"
            "1Y-Differenz: %{customdata[1]:.2f} %-Pkt.<br>"
            "Historisches Perzentil: %{customdata[2]:.2f} %<br>"
            "Tail-Wahrscheinlichkeit ≤ aktuell: %{customdata[3]:.2f} %<br>"
            "Historische Beobachtungen: %{customdata[4]:,.0f}"
            "<extra></extra>"
        ),
    ))

    layout = base_layout(True)
    layout["height"] = 560
    layout["hovermode"] = "x unified"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        range=[0, 100],
        title="Extremitätsperzentil",
        ticksuffix=" %",
    )
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.15, x=0)
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
            key="sector_perf_v16",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd_v16",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v16",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr_v16",
        )

    rolling_diff = _sector_rolling_return_diff(series_map)
    if not rolling_diff.empty:
        st.markdown("#### Rollierende 1-Jahres-Renditedifferenz zum S&P 500")
        st.plotly_chart(
            _sector_rolling_return_diff_figure(rolling_diff),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_return_diff_v16",
        )

        extreme_percentiles = _sector_extreme_percentiles(rolling_diff, warmup_years=10)
        if not extreme_percentiles.empty:
            st.markdown("#### Historische Extremität der stärksten Out- und Underperformance")
            st.plotly_chart(
                _sector_extreme_percentile_figure(extreme_percentiles),
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
                key="sector_extreme_percentiles_v16",
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
