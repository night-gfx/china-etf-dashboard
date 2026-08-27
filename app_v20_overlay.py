from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go

_source = Path(__file__).with_name("app_v19_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v19_core", "exec"), globals(), globals())


def _entry_exit_sector_backtest(
    series_map,
    under_tails,
    rolling_diff,
    entry_tail_threshold,
    exit_diff_threshold,
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
        return [
            sector for sector in allocations
            if sector != SECTOR_BENCHMARK_LABEL
        ]

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

        # Ausstiegssignal: Sektor erreicht Y %-Pkt. 1Y-Renditedifferenz.
        held_sectors = sector_holdings()
        if held_sectors and signal_date in rolling_diff.index:
            diff_row = pd.to_numeric(
                rolling_diff.loc[signal_date],
                errors="coerce",
            )
            exits = [
                sector for sector in held_sectors
                if sector in diff_row.index
                and pd.notna(diff_row.loc[sector])
                and float(diff_row.loc[sector]) >= float(exit_diff_threshold)
            ]
            for sector in exits:
                sell_sector_to_sp500(sector)

        # Einstiegssignal: Tail fällt von oberhalb X auf X oder tiefer.
        if signal_date in under_tails.index:
            current_tail_row = pd.to_numeric(
                under_tails.loc[signal_date],
                errors="coerce",
            )

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
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


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
