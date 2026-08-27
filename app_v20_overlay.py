from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v19_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v19_core", "exec"), globals(), globals())

HEALTHCARE_LABEL = SECTOR_LABELS["XLV"]
STAPLES_LABEL = SECTOR_LABELS["XLP"]
SWITCH_STRATEGIES = {
    "Healthcare-Strategie": HEALTHCARE_LABEL,
    "Consumer Staples-Strategie": STAPLES_LABEL,
}


def _strategy_signal_figure(rolling_diff, entry_threshold, exit_threshold):
    fig = go.Figure()

    for label in [HEALTHCARE_LABEL, STAPLES_LABEL]:
        if label not in rolling_diff.columns:
            continue
        s = pd.to_numeric(rolling_diff[label], errors="coerce").dropna()
        if s.empty:
            continue
        color = ACTIVE_SECTOR_COLORS.get(label, "#9ca3af")
        fig.add_trace(go.Scatter(
            x=s.index,
            y=s,
            mode="lines",
            name=label,
            line=dict(width=2.0, color=color),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>%{y:.2f} %-Pkt.</b>"
                "<extra>%{fullData.name}</extra>"
            ),
        ))

    fig.add_hline(
        y=float(entry_threshold),
        line_dash="dash",
        line_width=1.6,
        line_color="#16a34a",
        annotation_text="🟢 Einstieg X",
        annotation_position="top left",
    )
    fig.add_hline(
        y=float(exit_threshold),
        line_dash="dash",
        line_width=1.6,
        line_color="#dc2626",
        annotation_text="🔴 Ausstieg Y",
        annotation_position="bottom left",
    )

    layout = base_layout(True)
    layout["height"] = 520
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=True,
        zerolinewidth=1,
        title="1Y-Renditedifferenz zum S&P 500 in %-Pkt.",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _single_switch_backtest(
    prices,
    rolling_diff,
    sector_label,
    entry_threshold,
    exit_threshold,
    initial_capital=10000.0,
):
    if (
        SECTOR_BENCHMARK_LABEL not in prices.columns
        or sector_label not in prices.columns
        or sector_label not in rolling_diff.columns
    ):
        return pd.DataFrame(), pd.DataFrame()

    signal = pd.to_numeric(
        rolling_diff[sector_label],
        errors="coerce",
    ).dropna()
    if signal.empty:
        return pd.DataFrame(), pd.DataFrame()

    start_date = pd.Timestamp(signal.index.min())
    start_pos = int(prices.index.searchsorted(start_date))
    if start_pos >= len(prices.index) - 1:
        return pd.DataFrame(), pd.DataFrame()

    returns = prices.pct_change(fill_method=None)

    value = float(initial_capital)
    benchmark_value = float(initial_capital)
    in_sector = False

    dates = [prices.index[start_pos]]
    strategy_values = [value]
    benchmark_values = [benchmark_value]
    spy_weights = [100.0]
    sector_weights = [0.0]

    for pos in range(start_pos + 1, len(prices.index)):
        date = prices.index[pos]
        signal_date = prices.index[pos - 1]

        if signal_date in signal.index:
            diff_value = float(signal.loc[signal_date])

            if not in_sector and diff_value <= float(entry_threshold):
                in_sector = True
            elif in_sector and diff_value >= float(exit_threshold):
                in_sector = False

        daily = returns.loc[date]
        benchmark_return = float(
            daily.get(SECTOR_BENCHMARK_LABEL, np.nan)
        )
        sector_return = float(
            daily.get(sector_label, np.nan)
        )

        if not np.isfinite(benchmark_return):
            continue

        benchmark_value *= 1.0 + benchmark_return

        chosen_return = (
            sector_return
            if in_sector and np.isfinite(sector_return)
            else benchmark_return
        )
        value *= 1.0 + chosen_return

        dates.append(date)
        strategy_values.append(value)
        benchmark_values.append(benchmark_value)
        spy_weights.append(0.0 if in_sector else 100.0)
        sector_weights.append(100.0 if in_sector else 0.0)

    strategy = pd.DataFrame(
        {
            "Strategie": strategy_values,
            "S&P 500": benchmark_values,
        },
        index=pd.DatetimeIndex(dates),
    )
    weights = pd.DataFrame(
        {
            SECTOR_BENCHMARK_LABEL: spy_weights,
            sector_label: sector_weights,
        },
        index=pd.DatetimeIndex(dates),
    )

    return strategy, weights


def _two_switch_strategies(
    series_map,
    rolling_diff,
    entry_threshold,
    exit_threshold,
    initial_capital=10000.0,
):
    prices = pd.DataFrame(series_map).dropna().sort_index()
    if prices.empty:
        return pd.DataFrame(), {}

    combined = None
    weight_history = {}

    for strategy_name, sector_label in SWITCH_STRATEGIES.items():
        frame, weights = _single_switch_backtest(
            prices,
            rolling_diff,
            sector_label,
            entry_threshold,
            exit_threshold,
            initial_capital=initial_capital,
        )
        if frame.empty:
            continue

        renamed = frame.rename(columns={"Strategie": strategy_name})
        if combined is None:
            combined = renamed
        else:
            combined = combined.join(
                renamed[[strategy_name]],
                how="inner",
            )
        weight_history[strategy_name] = weights

    if combined is None or combined.empty:
        return pd.DataFrame(), {}

    ordered = [
        "Healthcare-Strategie",
        "Consumer Staples-Strategie",
        "S&P 500",
    ]
    combined = combined[
        [col for col in ordered if col in combined.columns]
    ]
    return combined, weight_history


def _switch_strategy_figure(frame):
    fig = go.Figure()

    for col in frame.columns:
        is_benchmark = col == "S&P 500"
        fig.add_trace(go.Scatter(
            x=frame.index,
            y=frame[col],
            mode="lines",
            name=col,
            line=dict(
                width=2.5 if is_benchmark else 2.1,
                dash="dash" if is_benchmark else "solid",
            ),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>€%{y:,.2f}</b>"
                "<extra>%{fullData.name}</extra>"
            ),
        ))

    layout = base_layout(True)
    layout["height"] = 560
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        type="log",
        title="Portfoliowert in € (log)",
        tickprefix="€",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _switch_drawdown_figure(frame):
    fig = go.Figure()

    for col in frame.columns:
        s = pd.to_numeric(
            frame[col],
            errors="coerce",
        ).dropna()
        dd = (s / s.cummax() - 1.0) * 100.0
        fig.add_trace(go.Scatter(
            x=dd.index,
            y=dd,
            mode="lines",
            name=col,
            line=dict(
                width=2.0,
                dash="dash" if col == "S&P 500" else "solid",
            ),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>%{y:.2f} %</b>"
                "<extra>%{fullData.name}</extra>"
            ),
        ))

    layout = base_layout(True)
    layout["height"] = 500
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=True,
        zerolinewidth=1,
        title="Drawdown",
        ticksuffix=" %",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _switch_metrics(frame):
    rows = []

    for col in frame.columns:
        s = pd.to_numeric(
            frame[col],
            errors="coerce",
        ).dropna()
        if len(s) < 2:
            continue

        r = s.pct_change(fill_method=None).dropna()
        years = max(
            (s.index[-1] - s.index[0]).days / 365.25,
            1.0 / 365.25,
        )
        cagr = (
            (float(s.iloc[-1]) / float(s.iloc[0])) ** (1.0 / years)
            - 1.0
        )
        vola = (
            float(r.std(ddof=1) * np.sqrt(252))
            if len(r) > 1
            else np.nan
        )
        sharpe = (
            float(
                r.mean()
                / r.std(ddof=1)
                * np.sqrt(252)
            )
            if len(r) > 1 and float(r.std(ddof=1)) > 0
            else np.nan
        )
        max_dd = float(
            (s / s.cummax() - 1.0).min()
        )

        rows.append({
            "Portfolio": col,
            "CAGR (%)": cagr * 100.0,
            "Volatilität p.a. (%)": vola * 100.0,
            "Sharpe Ratio": sharpe,
            "Max Drawdown (%)": max_dd * 100.0,
        })

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).set_index("Portfolio")


def _binary_weight_figure(weight_history):
    fig = go.Figure()

    for col in weight_history.columns:
        color = (
            "#6b7280"
            if col == SECTOR_BENCHMARK_LABEL
            else ACTIVE_SECTOR_COLORS.get(col, "#9ca3af")
        )
        fig.add_trace(go.Scatter(
            x=weight_history.index,
            y=weight_history[col],
            mode="lines",
            name=col,
            stackgroup="weights",
            line=dict(
                width=0.8,
                color=color,
            ),
            fillcolor=hex_rgba(color, 0.58),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>%{y:.0f} %</b>"
                "<extra>%{fullData.name}</extra>"
            ),
        ))

    layout = base_layout(True)
    layout["height"] = 400
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        range=[0, 100],
        title="Gewicht",
        ticksuffix=" %",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.18,
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
        height=compact_height(
            len(overview),
            maximum=500,
        ),
    )

    series_map = _common_active_sector_series(raw)
    if not series_map:
        st.error(
            "Kein gemeinsamer Datenzeitraum für alle Sektor-ETFs verfügbar."
        )
        return

    indexed = _indexed_individually(series_map)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        st.plotly_chart(
            _sector_performance_figure(indexed),
            width="stretch",
            config={
                "displaylogo": False,
                "scrollZoom": True,
            },
            key="sector_perf_v23",
        )

    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={
                "displaylogo": False,
                "scrollZoom": True,
            },
            key="sector_dd_v23",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v23",
        )

    with c2:
        st.markdown(
            "#### Rollierende 1-Jahres-Korrelation zum S&P 500"
        )
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={
                "displaylogo": False,
                "scrollZoom": True,
            },
            key="sector_rolling_corr_v23",
        )

    rolling_diff = _sector_rolling_return_diff(series_map)
    if not rolling_diff.empty:
        st.markdown(
            "#### Rollierende 1-Jahres-Renditedifferenz "
            "zum S&P 500 (seit Inception)"
        )
        st.plotly_chart(
            _sector_rolling_return_diff_figure(
                rolling_diff
            ),
            width="stretch",
            config={
                "displaylogo": False,
                "scrollZoom": True,
            },
            key="sector_rolling_return_diff_v23",
        )

        c1, c2 = st.columns(2, gap="large")
        with c1:
            entry_threshold = st.slider(
                "🟢 Einstiegssignal X – 1Y-Renditedifferenz ≤ (%-Pkt.)",
                min_value=-50,
                max_value=0,
                value=-10,
                step=1,
                key="switch_entry_diff_v23",
            )
        with c2:
            exit_threshold = st.slider(
                "🔴 Ausstiegssignal Y – 1Y-Renditedifferenz ≥ (%-Pkt.)",
                min_value=-20,
                max_value=50,
                value=0,
                step=1,
                key="switch_exit_diff_v23",
            )

        st.markdown(
            "#### Strategiesignale – Healthcare & Consumer Staples"
        )
        st.plotly_chart(
            _strategy_signal_figure(
                rolling_diff,
                entry_threshold,
                exit_threshold,
            ),
            width="stretch",
            config={
                "displaylogo": False,
                "scrollZoom": True,
            },
            key="switch_signal_chart_v23",
        )

        strategy_frame, weight_histories = (
            _two_switch_strategies(
                series_map,
                rolling_diff,
                entry_threshold,
                exit_threshold,
                initial_capital=10000.0,
            )
        )

        if not strategy_frame.empty:
            st.markdown(
                "#### Healthcare / Consumer Staples Strategien vs. S&P 500"
            )
            st.plotly_chart(
                _switch_strategy_figure(
                    strategy_frame
                ),
                width="stretch",
                config={
                    "displaylogo": False,
                    "scrollZoom": True,
                },
                key="switch_perf_v23",
            )

            st.markdown(
                "#### Drawdown – Strategien vs. S&P 500"
            )
            st.plotly_chart(
                _switch_drawdown_figure(
                    strategy_frame
                ),
                width="stretch",
                config={
                    "displaylogo": False,
                    "scrollZoom": True,
                },
                key="switch_dd_v23",
            )

            comparison = _switch_metrics(
                strategy_frame
            )
            if not comparison.empty:
                st.markdown(
                    "#### Kennzahlen – Strategien vs. S&P 500"
                )
                styled = style_heat(
                    comparison,
                    reverse_columns={
                        "Volatilität p.a. (%)",
                    },
                ).format({
                    "CAGR (%)": "{:.2f}",
                    "Volatilität p.a. (%)": "{:.2f}",
                    "Sharpe Ratio": "{:.2f}",
                    "Max Drawdown (%)": "{:.2f}",
                })
                st.dataframe(
                    styled,
                    width="stretch",
                    height=compact_height(
                        len(comparison),
                        maximum=250,
                    ),
                )

        if weight_histories:
            c1, c2 = st.columns(2, gap="large")
            with c1:
                if "Healthcare-Strategie" in weight_histories:
                    st.markdown(
                        "#### Gewichtung – Healthcare-Strategie"
                    )
                    st.plotly_chart(
                        _binary_weight_figure(
                            weight_histories[
                                "Healthcare-Strategie"
                            ]
                        ),
                        width="stretch",
                        config={
                            "displaylogo": False,
                            "scrollZoom": True,
                        },
                        key="switch_weights_health_v23",
                    )
            with c2:
                if "Consumer Staples-Strategie" in weight_histories:
                    st.markdown(
                        "#### Gewichtung – Consumer-Staples-Strategie"
                    )
                    st.plotly_chart(
                        _binary_weight_figure(
                            weight_histories[
                                "Consumer Staples-Strategie"
                            ]
                        ),
                        width="stretch",
                        config={
                            "displaylogo": False,
                            "scrollZoom": True,
                        },
                        key="switch_weights_staples_v23",
                    )

    metrics = _sector_metrics(series_map)
    st.markdown("#### Kennzahlen")
    st.dataframe(
        style_heat(
            metrics,
            reverse_columns={"Volatilität p.a."},
        ),
        width="stretch",
        height=compact_height(
            len(metrics),
            maximum=520,
        ),
    )

    annual_sharpe = _sector_annual_sharpe(series_map)
    st.markdown("#### Jährliche Sharpe Ratio")
    st.dataframe(
        style_heat(annual_sharpe),
        width="stretch",
        height=compact_height(
            len(annual_sharpe),
            maximum=520,
        ),
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
