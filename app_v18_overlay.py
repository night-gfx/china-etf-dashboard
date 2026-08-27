from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v17_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v17_core", "exec"), globals(), globals())

ACTIVE_SECTOR_COLORS = {
    SECTOR_LABELS[item["ticker"]]: PALETTE[i % len(PALETTE)]
    for i, item in enumerate(SECTOR_ETFS)
    if item["ticker"] not in EXCLUDED_SECTOR_TICKERS
}


def _sector_rank_colored_figure(probabilities, side, measure):
    fig = go.Figure()
    is_out = side == "out"
    prefixes = ["Out 1", "Out 2"] if is_out else ["Under 1", "Under 2"]
    field = "Differenz" if measure == "diff" else "Tail"
    seen = set()

    for rank_idx, prefix in enumerate(prefixes, start=1):
        sector_col = f"{prefix} Sektor"
        value_col = f"{prefix} {field}"
        for sector in probabilities[sector_col].dropna().astype(str).unique():
            mask = probabilities[sector_col].astype(str).eq(sector)
            y = pd.to_numeric(probabilities[value_col], errors="coerce").where(mask)
            if y.dropna().empty:
                continue

            custom = np.column_stack([
                probabilities[sector_col].astype(str),
                pd.to_numeric(probabilities[f"{prefix} Differenz"], errors="coerce"),
                pd.to_numeric(probabilities[f"{prefix} Perzentil"], errors="coerce"),
                pd.to_numeric(probabilities[f"{prefix} Tail"], errors="coerce"),
            ])

            color = ACTIVE_SECTOR_COLORS.get(sector, "#6b7280")
            showlegend = sector not in seen
            if showlegend:
                seen.add(sector)

            fig.add_trace(go.Scatter(
                x=probabilities.index,
                y=y,
                mode="lines",
                name=sector,
                legendgroup=sector,
                showlegend=showlegend,
                customdata=custom,
                connectgaps=False,
                line=dict(
                    width=2.2 if rank_idx == 1 else 1.5,
                    dash="solid" if rank_idx == 1 else "dot",
                    color=color,
                ),
                hovertemplate=(
                    "%{x|%d.%m.%Y}<br>"
                    f"Rang: <b>#{rank_idx}</b><br>"
                    "<b>%{customdata[0]}</b><br>"
                    "1Y-Differenz: %{customdata[1]:.2f} %-Pkt.<br>"
                    "Historisches Perzentil: %{customdata[2]:.2f} %<br>"
                    "Tail-Wahrscheinlichkeit: <b>%{customdata[3]:.2f} %</b>"
                    "<extra></extra>"
                ),
            ))

    layout = base_layout(True)
    layout["height"] = 500
    layout["hovermode"] = "closest"
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.18,
        x=0,
        title=dict(text="#1 durchgezogen · #2 gepunktet"),
    )

    if measure == "diff":
        layout["yaxis"] = dict(
            showgrid=False,
            zeroline=True,
            zerolinewidth=1,
            title="1Y-Renditedifferenz in %-Pkt.",
        )
    else:
        layout["yaxis"] = dict(
            showgrid=False,
            zeroline=False,
            range=[0, 100],
            title="Tail-Wahrscheinlichkeit",
            ticksuffix=" %",
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
            key="sector_perf_v18",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd_v18",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v18",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr_v18",
        )

    rolling_diff = _sector_rolling_return_diff(series_map)
    if not rolling_diff.empty:
        st.markdown("#### Rollierende 1-Jahres-Renditedifferenz zum S&P 500 (seit Inception)")
        st.plotly_chart(
            _sector_rolling_return_diff_figure(rolling_diff),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_return_diff_v18",
        )

        probabilities = _sector_top2_extreme_probabilities(rolling_diff, warmup_years=10)
        if not probabilities.empty:
            c1, c2 = st.columns(2, gap="large")
            with c1:
                st.markdown("#### Top 2 Outperformance – 1Y-Differenz ab Auswertungsstart")
                st.plotly_chart(
                    _sector_rank_colored_figure(probabilities, "out", "diff"),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_top2_out_diff_v18",
                )
            with c2:
                st.markdown("#### Bottom 2 Underperformance – 1Y-Differenz ab Auswertungsstart")
                st.plotly_chart(
                    _sector_rank_colored_figure(probabilities, "under", "diff"),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_bottom2_under_diff_v18",
                )

            c1, c2 = st.columns(2, gap="large")
            with c1:
                st.markdown("#### Wahrscheinlichkeit – Top 2 Outperformance")
                st.plotly_chart(
                    _sector_rank_colored_figure(probabilities, "out", "tail"),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_top2_out_prob_v18",
                )
            with c2:
                st.markdown("#### Wahrscheinlichkeit – Bottom 2 Underperformance")
                st.plotly_chart(
                    _sector_rank_colored_figure(probabilities, "under", "tail"),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_bottom2_under_prob_v18",
                )

            threshold = st.slider(
                "Schwellenwert x – maximale Tail-Wahrscheinlichkeit für Umschichtung",
                min_value=1,
                max_value=25,
                value=10,
                step=1,
                format="%d %%",
                key="sector_rotation_tail_threshold",
            )
            strategy_frame = _sector_rotation_backtests(
                series_map,
                probabilities,
                tail_threshold=threshold,
            )
            if not strategy_frame.empty:
                st.markdown("#### Top-2-Sektorstrategien vs. S&P 500")
                st.plotly_chart(
                    _sector_rotation_figure(strategy_frame),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_rotation_backtests_v18",
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
