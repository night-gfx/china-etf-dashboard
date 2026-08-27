from pathlib import Path

import numpy as np
import pandas as pd

_source = Path(__file__).with_name("app_v20_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v20_core", "exec"), globals(), globals())


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

    spy_value = float(initial_capital)
    sector_value = 0.0
    benchmark_value = float(initial_capital)
    in_sector = False

    dates = [prices.index[start_pos]]
    strategy_values = [float(initial_capital)]
    benchmark_values = [float(initial_capital)]
    spy_weights = [100.0]
    sector_weights = [0.0]

    for pos in range(start_pos + 1, len(prices.index)):
        date = prices.index[pos]
        signal_date = prices.index[pos - 1]

        if signal_date in signal.index:
            diff_value = float(signal.loc[signal_date])

            if not in_sector and diff_value <= float(entry_threshold):
                total = spy_value + sector_value
                spy_value = total * 0.50
                sector_value = total * 0.50
                in_sector = True

            elif in_sector and diff_value >= float(exit_threshold):
                spy_value += sector_value
                sector_value = 0.0
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
        spy_value *= 1.0 + benchmark_return

        if in_sector and np.isfinite(sector_return):
            sector_value *= 1.0 + sector_return

        total = spy_value + sector_value
        spy_weight = (
            100.0 * spy_value / total
            if total
            else 0.0
        )
        sector_weight = (
            100.0 * sector_value / total
            if total
            else 0.0
        )

        dates.append(date)
        strategy_values.append(total)
        benchmark_values.append(benchmark_value)
        spy_weights.append(spy_weight)
        sector_weights.append(sector_weight)

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
