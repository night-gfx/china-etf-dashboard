from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v18_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v18_core", "exec"), globals(), globals())


def _sector_all_under_tail_probabilities(diff_frame, warmup_years=10):
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

    def prefix_count(value):
        idx = int(np.searchsorted(coordinates, value, side="right"))
        total = 0
        while idx > 0:
            total += int(tree[idx])
            idx -= idx & -idx
        return total

    history_count = 0
    rows = []
    dates = []

    for date, row in frame.iterrows():
        date = pd.Timestamp(date)
        current = pd.to_numeric(row, errors="coerce").dropna()

        if date >= evaluation_start and history_count > 0 and not current.empty:
            rows.append({
                label: 100.0 * prefix_count(float(value)) / history_count
                for label, value in current.items()
                if np.isfinite(value)
            })
            dates.append(date)

        for value in current.to_numpy(dtype=float):
            if np.isfinite(value):
                add(float(value))
                history_count += 1

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows, index=pd.DatetimeIndex(dates)).reindex(columns=frame.columns)


def _persistent_underperformance_backtest(
    series_map,
    under_tails,
    tail_threshold,
    max_holdings=5,
):
    if under_tails.empty or SECTOR_BENCHMARK_LABEL not in series_map:
        return pd.DataFrame()

    prices = pd.DataFrame(series_map).dropna().sort_index()
    if prices.empty:
        return pd.DataFrame()

    returns = prices.pct_change(fill_method=None)
    signal_dates = under_tails.index.intersection(prices.index)
    if signal_dates.empty:
        return pd.DataFrame()

    start_date = pd.Timestamp(signal_dates.min())
    start_pos = int(prices.index.searchsorted(start_date))
    if start_pos >= len(prices.index) - 1:
        return pd.DataFrame()

    portfolio_value = 100.0
    benchmark_value = 100.0
    holdings = {}

    dates = [prices.index[start_pos]]
    strategy_values = [portfolio_value]
    benchmark_values = [benchmark_value]
    holding_counts = [0]

    def rebalance_add(new_sector):
        nonlocal holdings, portfolio_value
        total = float(portfolio_value)
        n_after = len(holdings) + 1
        new_weight = 1.0 / n_after
        old_target = 1.0 - new_weight

        if holdings:
            old_total = float(sum(holdings.values()))
            if old_total > 0:
                holdings = {
                    sector: total * old_target * (value / old_total)
                    for sector, value in holdings.items()
                }
            else:
                equal_old = old_target / len(holdings)
                holdings = {
                    sector: total * equal_old
                    for sector in holdings
                }

        holdings[new_sector] = total * new_weight

    def rebalance_replace(old_sector, new_sector):
        nonlocal holdings, portfolio_value
        total = float(portfolio_value)
        holdings.pop(old_sector, None)

        new_weight = 1.0 / max_holdings
        old_target = 1.0 - new_weight
        old_total = float(sum(holdings.values()))

        if holdings:
            if old_total > 0:
                holdings = {
                    sector: total * old_target * (value / old_total)
                    for sector, value in holdings.items()
                }
            else:
                equal_old = old_target / len(holdings)
                holdings = {
                    sector: total * equal_old
                    for sector in holdings
                }

        holdings[new_sector] = total * new_weight

    previous_tail_row = None

    if start_date in under_tails.index:
        first_row = pd.to_numeric(under_tails.loc[start_date], errors="coerce")
        first_candidates = first_row[first_row <= float(tail_threshold)].dropna().sort_values()
        for sector in first_candidates.index:
            if sector == SECTOR_BENCHMARK_LABEL or sector in holdings:
                continue
            if len(holdings) < max_holdings:
                rebalance_add(sector)
            else:
                break
        previous_tail_row = first_row

    for pos in range(start_pos + 1, len(prices.index)):
        date = prices.index[pos]
        signal_date = prices.index[pos - 1]

        if signal_date in under_tails.index:
            current_tail_row = pd.to_numeric(under_tails.loc[signal_date], errors="coerce")
            if previous_tail_row is None:
                previous_tail_row = current_tail_row.copy()

            crossing = (
                current_tail_row.le(float(tail_threshold))
                & (
                    previous_tail_row.gt(float(tail_threshold))
                    | previous_tail_row.isna()
                )
            )
            candidates = current_tail_row[crossing].dropna().sort_values()

            for sector, candidate_tail in candidates.items():
                if sector == SECTOR_BENCHMARK_LABEL or sector in holdings:
                    continue

                if len(holdings) < max_holdings:
                    rebalance_add(sector)
                    continue

                held_tails = current_tail_row.reindex(list(holdings)).dropna()
                if held_tails.empty:
                    continue

                weakest_sector = held_tails.idxmax()
                weakest_tail = float(held_tails.loc[weakest_sector])

                if float(candidate_tail) < weakest_tail:
                    rebalance_replace(weakest_sector, sector)

            previous_tail_row = current_tail_row.copy()

        daily = returns.loc[date]
        benchmark_return = float(daily.get(SECTOR_BENCHMARK_LABEL, np.nan))
        if not np.isfinite(benchmark_return):
            continue

        benchmark_value *= 1.0 + benchmark_return

        if holdings:
            for sector in list(holdings):
                r = float(daily.get(sector, np.nan))
                if np.isfinite(r):
                    holdings[sector] *= 1.0 + r
            portfolio_value = float(sum(holdings.values()))
        else:
            portfolio_value *= 1.0 + benchmark_return

        dates.append(date)
        strategy_values.append(portfolio_value)
        benchmark_values.append(benchmark_value)
        holding_counts.append(len(holdings))

    return pd.DataFrame(
        {
            "Persistente Underperformance-Strategie": strategy_values,
            "S&P 500": benchmark_values,
            "Anzahl Sektoren": holding_counts,
        },
        index=pd.DatetimeIndex(dates),
    )


def _persistent_underperformance_figure(frame):
    fig = go.Figure()
    for col in ["Persistente Underperformance-Strategie", "S&P 500"]:
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
                "<b>%{y:.2f}</b><br>"
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
        title="Indexiert (Start = 100, log)",
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
            key="sector_perf_v19",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd_v19",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v19",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr_v19",
        )

    rolling_diff = _sector_rolling_return_diff(series_map)
    if not rolling_diff.empty:
        st.markdown("#### Rollierende 1-Jahres-Renditedifferenz zum S&P 500 (seit Inception)")
        st.plotly_chart(
            _sector_rolling_return_diff_figure(rolling_diff),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_return_diff_v19",
        )

        under_tails = _sector_all_under_tail_probabilities(rolling_diff, warmup_years=10)
        if not under_tails.empty:
            threshold = st.slider(
                "Schwellenwert x – maximale Tail-Wahrscheinlichkeit für Aufnahme",
                min_value=1,
                max_value=25,
                value=10,
                step=1,
                format="%d %%",
                key="sector_persistent_under_tail_threshold",
            )
            strategy_frame = _persistent_underperformance_backtest(
                series_map,
                under_tails,
                tail_threshold=threshold,
                max_holdings=5,
            )
            if not strategy_frame.empty:
                st.markdown("#### Persistente Underperformance-Strategie vs. S&P 500")
                st.plotly_chart(
                    _persistent_underperformance_figure(strategy_frame),
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_persistent_under_backtest_v19",
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
