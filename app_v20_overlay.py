from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v19_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v19_core", "exec"), globals(), globals())


def _entry_exit_sector_backtest(
    series_map,
    under_tails,
    entry_tail_threshold,
    exit_tail_threshold,
    max_holdings=5,
    initial_capital=10000.0,
    new_position_weight=0.25,
):
    if under_tails.empty or SECTOR_BENCHMARK_LABEL not in series_map:
        return pd.DataFrame(), pd.DataFrame()

    prices = pd.DataFrame(series_map).dropna().sort_index()
    if prices.empty or len(prices) < 2:
        return pd.DataFrame(), pd.DataFrame()

    signal_dates = under_tails.index.intersection(prices.index)
    if signal_dates.empty:
        return pd.DataFrame(), pd.DataFrame()

    start_date = pd.Timestamp(signal_dates.min())
    start_pos = int(prices.index.searchsorted(start_date))
    if start_pos >= len(prices.index) - 1:
        return pd.DataFrame(), pd.DataFrame()

    returns = prices.pct_change(fill_method=None)
    allocations = {SECTOR_BENCHMARK_LABEL: float(initial_capital)}
    benchmark_value = float(initial_capital)

    dates = [prices.index[start_pos]]
    strategy_values = [float(initial_capital)]
    benchmark_values = [float(initial_capital)]
    holding_counts = [0]
    weight_rows = [{
        col: (100.0 if col == SECTOR_BENCHMARK_LABEL else 0.0)
        for col in prices.columns
    }]

    def sector_holdings():
        return [asset for asset in allocations if asset != SECTOR_BENCHMARK_LABEL]

    def portfolio_total():
        return float(sum(allocations.values()))

    def add_sector(new_sector):
        total = portfolio_total()
        if total <= 0:
            return
        keep_fraction = 1.0 - float(new_position_weight)
        for asset in list(allocations):
            allocations[asset] *= keep_fraction
        allocations[new_sector] = total * float(new_position_weight)

    def sell_sector_to_sp500(sector):
        value = float(allocations.pop(sector, 0.0))
        allocations[SECTOR_BENCHMARK_LABEL] = (
            float(allocations.get(SECTOR_BENCHMARK_LABEL, 0.0)) + value
        )

    previous_tail_row = None

    for pos in range(start_pos + 1, len(prices.index)):
        date = prices.index[pos]
        signal_date = prices.index[pos - 1]

        if signal_date in under_tails.index:
            current_tail_row = pd.to_numeric(
                under_tails.loc[signal_date],
                errors="coerce",
            )

            # Rotes Ausstiegssignal: Tail-Wahrscheinlichkeit erreicht Y oder mehr.
            held_sectors = sector_holdings()
            exits = [
                sector for sector in held_sectors
                if sector in current_tail_row.index
                and pd.notna(current_tail_row.loc[sector])
                and float(current_tail_row.loc[sector]) >= float(exit_tail_threshold)
            ]
            for sector in exits:
                sell_sector_to_sp500(sector)

            # Grünes Einstiegssignal: Tail fällt von oberhalb X auf X oder tiefer.
            if previous_tail_row is None:
                crossing = current_tail_row.le(float(entry_tail_threshold))
            else:
                crossing = (
                    current_tail_row.le(float(entry_tail_threshold))
                    & (
                        previous_tail_row.gt(float(entry_tail_threshold))
                        | previous_tail_row.isna()
                    )
                )

            candidates = current_tail_row[crossing].dropna().sort_values()
            for sector, candidate_tail in candidates.items():
                if sector == SECTOR_BENCHMARK_LABEL or sector in allocations:
                    continue

                held_sectors = sector_holdings()
                if len(held_sectors) < max_holdings:
                    add_sector(sector)
                    continue

                held_tails = current_tail_row.reindex(held_sectors).dropna()
                if held_tails.empty:
                    continue

                weakest_sector = held_tails.idxmax()
                weakest_tail = float(held_tails.loc[weakest_sector])
                if float(candidate_tail) < weakest_tail:
                    sell_sector_to_sp500(weakest_sector)
                    add_sector(sector)

            previous_tail_row = current_tail_row.copy()

        daily = returns.loc[date]
        benchmark_return = float(daily.get(SECTOR_BENCHMARK_LABEL, np.nan))
        if not np.isfinite(benchmark_return):
            continue

        benchmark_value *= 1.0 + benchmark_return
        for asset in list(allocations):
            r = float(daily.get(asset, np.nan))
            if np.isfinite(r):
                allocations[asset] *= 1.0 + r

        total = portfolio_total()
        weights = {
            col: (100.0 * float(allocations.get(col, 0.0)) / total if total else 0.0)
            for col in prices.columns
        }

        dates.append(date)
        strategy_values.append(total)
        benchmark_values.append(benchmark_value)
        holding_counts.append(len(sector_holdings()))
        weight_rows.append(weights)

    strategy = pd.DataFrame(
        {
            "Einstiegs-/Ausstiegsstrategie": strategy_values,
            "S&P 500": benchmark_values,
            "Anzahl Sektoren": holding_counts,
        },
        index=pd.DatetimeIndex(dates),
    )
    weights = pd.DataFrame(
        weight_rows,
        index=pd.DatetimeIndex(dates),
    ).fillna(0.0)
    return strategy, weights


def _entry_exit_strategy_figure(frame):
    fig = go.Figure()
    for col in ["Einstiegs-/Ausstiegsstrategie", "S&P 500"]:
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
            customdata=frame[["Anzahl Sektoren"]].to_numpy(),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>€%{y:,.2f}</b><br>"
                "Gehaltene Sektoren: %{customdata[0]:.0f}"
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
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.15, x=0)
    fig.update_layout(**layout)
    return fig


def _sector_tail_probability_figure(under_tails, entry_threshold, exit_threshold):
    fig = go.Figure()
    for col in under_tails.columns:
        s = pd.to_numeric(under_tails[col], errors="coerce").dropna()
        if s.empty:
            continue
        color = ACTIVE_SECTOR_COLORS.get(col, "#9ca3af")
        fig.add_trace(go.Scatter(
            x=s.index,
            y=s,
            mode="lines",
            name=col,
            line=dict(width=1.7, color=color),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>%{y:.2f} %</b>"
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
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        range=[0, 100],
        title="Tail-Wahrscheinlichkeit",
        ticksuffix=" %",
    )
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.15, x=0)
    fig.update_layout(**layout)
    return fig


def _entry_exit_drawdown_figure(frame):
    fig = go.Figure()
    for col in ["Einstiegs-/Ausstiegsstrategie", "S&P 500"]:
        s = pd.to_numeric(frame[col], errors="coerce").dropna()
        dd = (s / s.cummax() - 1.0) * 100.0
        fig.add_trace(go.Scatter(
            x=dd.index,
            y=dd,
            mode="lines",
            name=col,
            line=dict(width=2.0, dash="dash" if col == "S&P 500" else "solid"),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f} %</b><extra>%{fullData.name}</extra>",
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
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.15, x=0)
    fig.update_layout(**layout)
    return fig


def _entry_exit_metrics(frame):
    rows = []
    for col in ["Einstiegs-/Ausstiegsstrategie", "S&P 500"]:
        s = pd.to_numeric(frame[col], errors="coerce").dropna()
        if len(s) < 2:
            continue
        r = s.pct_change(fill_method=None).dropna()
        years = max((s.index[-1] - s.index[0]).days / 365.25, 1.0 / 365.25)
        cagr = (float(s.iloc[-1]) / float(s.iloc[0])) ** (1.0 / years) - 1.0
        vola = float(r.std(ddof=1) * np.sqrt(252)) if len(r) > 1 else np.nan
        sharpe = (
            float(r.mean() / r.std(ddof=1) * np.sqrt(252))
            if len(r) > 1 and float(r.std(ddof=1)) > 0
            else np.nan
        )
        max_dd = float((s / s.cummax() - 1.0).min())
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
            key="sector_perf_v22",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd_v22",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v22",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr_v22",
        )

    rolling_diff = _sector_rolling_return_diff(series_map)
    if not rolling_diff.empty:
        st.markdown("#### Rollierende 1-Jahres-Renditedifferenz zum S&P 500 (seit Inception)")
        st.plotly_chart(
            _sector_rolling_return_diff_figure(rolling_diff),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_return_diff_v22",
        )

        under_tails = _sector_all_under_tail_probabilities(rolling_diff, warmup_years=10)
        if not under_tails.empty:
            c1, c2 = st.columns(2, gap="large")
            with c1:
                entry_threshold = st.slider(
                    "🟢 Einstiegssignal X – Tail-Wahrscheinlichkeit ≤ (%)",
                    min_value=1,
                    max_value=50,
                    value=10,
                    step=1,
                    key="sector_entry_tail_threshold_v22",
                )
            with c2:
                exit_threshold = st.slider(
                    "🔴 Ausstiegssignal Y – Tail-Wahrscheinlichkeit ≥ (%)",
                    min_value=5,
                    max_value=100,
                    value=50,
                    step=1,
                    key="sector_exit_tail_threshold_v22",
                )

            st.markdown("#### Tail-Wahrscheinlichkeiten")
            st.plotly_chart(
                _sector_tail_probability_figure(
                    under_tails,
                    entry_threshold,
                    exit_threshold,
                ),
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
                key="sector_tail_probabilities_v22",
            )

            strategy_frame, weight_history = _entry_exit_sector_backtest(
                series_map,
                under_tails,
                entry_tail_threshold=entry_threshold,
                exit_tail_threshold=exit_threshold,
                max_holdings=5,
                initial_capital=10000.0,
                new_position_weight=0.25,
            )

            if not strategy_frame.empty:
                st.markdown("#### Einstiegs-/Ausstiegsstrategie vs. S&P 500")
                st.plotly_chart(
                    _entry_exit_strategy_figure(strategy_frame),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_entry_exit_backtest_v22",
                )

                st.markdown("#### Drawdown – Strategie vs. S&P 500")
                st.plotly_chart(
                    _entry_exit_drawdown_figure(strategy_frame),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_entry_exit_drawdown_v22",
                )

                comparison = _entry_exit_metrics(strategy_frame)
                if not comparison.empty:
                    st.markdown("#### Kennzahlen – Strategie vs. S&P 500")
                    styled = style_heat(
                        comparison,
                        reverse_columns={"Volatilität p.a. (%)"},
                    ).format({
                        "CAGR (%)": "{:.2f}",
                        "Volatilität p.a. (%)": "{:.2f}",
                        "Sharpe Ratio": "{:.2f}",
                        "Max Drawdown (%)": "{:.2f}",
                    })
                    st.dataframe(
                        styled,
                        width="stretch",
                        height=compact_height(len(comparison), maximum=220),
                    )

            if not weight_history.empty:
                st.markdown("#### Gewichtsentwicklung der Strategie")
                st.plotly_chart(
                    _sector_strategy_weights_figure(weight_history),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_entry_exit_weights_v22",
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
