from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v16_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v16_core", "exec"), globals(), globals())


def _sector_top2_extreme_probabilities(diff_frame, warmup_years=10):
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
        current = pd.to_numeric(row, errors="coerce").dropna()

        if date >= evaluation_start and history_count > 0 and len(current) >= 4:
            descending = current.sort_values(ascending=False)
            ascending = current.sort_values(ascending=True)

            record = {
                "Datum": date,
                "Historische Beobachtungen": history_count,
            }

            for rank, (label, value) in enumerate(descending.iloc[:2].items(), start=1):
                value = float(value)
                le = prefix_count(value, inclusive=True)
                lt = prefix_count(value, inclusive=False)
                percentile = 100.0 * le / history_count
                upper_tail = 100.0 * (history_count - lt) / history_count
                record[f"Out {rank} Sektor"] = label
                record[f"Out {rank} Differenz"] = value
                record[f"Out {rank} Perzentil"] = percentile
                record[f"Out {rank} Tail"] = upper_tail
                record[f"Out {rank} Extremität"] = 100.0 - upper_tail

            for rank, (label, value) in enumerate(ascending.iloc[:2].items(), start=1):
                value = float(value)
                le = prefix_count(value, inclusive=True)
                percentile = 100.0 * le / history_count
                lower_tail = percentile
                record[f"Under {rank} Sektor"] = label
                record[f"Under {rank} Differenz"] = value
                record[f"Under {rank} Perzentil"] = percentile
                record[f"Under {rank} Tail"] = lower_tail
                record[f"Under {rank} Extremität"] = 100.0 - lower_tail

            rows.append(record)

        for value in current.to_numpy(dtype=float):
            if np.isfinite(value):
                add(float(value))
                history_count += 1

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).set_index("Datum")


def _sector_top2_probability_figure(probabilities):
    fig = go.Figure()
    specs = [
        ("Out 1", "Outperformance #1"),
        ("Out 2", "Outperformance #2"),
        ("Under 1", "Underperformance #1"),
        ("Under 2", "Underperformance #2"),
    ]

    for prefix, label in specs:
        custom = np.column_stack([
            probabilities[f"{prefix} Sektor"].astype(str),
            probabilities[f"{prefix} Differenz"].to_numpy(dtype=float),
            probabilities[f"{prefix} Perzentil"].to_numpy(dtype=float),
            probabilities[f"{prefix} Tail"].to_numpy(dtype=float),
            probabilities["Historische Beobachtungen"].to_numpy(dtype=int),
        ])
        comparator = "≥ aktuell" if prefix.startswith("Out") else "≤ aktuell"
        fig.add_trace(go.Scatter(
            x=probabilities.index,
            y=probabilities[f"{prefix} Tail"],
            mode="lines",
            name=label,
            customdata=custom,
            line=dict(width=1.8),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>%{customdata[0]}</b><br>"
                "1Y-Differenz: %{customdata[1]:.2f} %-Pkt.<br>"
                "Historisches Perzentil: %{customdata[2]:.2f} %<br>"
                f"Tail-Wahrscheinlichkeit {comparator}: "
                "<b>%{customdata[3]:.2f} %</b><br>"
                "Historische Beobachtungen: %{customdata[4]:,.0f}"
                "<extra></extra>"
            ),
        ))

    layout = base_layout(True)
    layout["height"] = 570
    layout["hovermode"] = "x unified"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        range=[0, 100],
        title="Historische Tail-Wahrscheinlichkeit",
        ticksuffix=" %",
    )
    layout["legend"] = dict(orientation="h", yanchor="top", y=-0.15, x=0)
    fig.update_layout(**layout)
    return fig


def _sector_rotation_backtests(series_map, probabilities, tail_threshold):
    if probabilities.empty or SECTOR_BENCHMARK_LABEL not in series_map:
        return pd.DataFrame()

    prices = pd.DataFrame(series_map).dropna().sort_index()
    if prices.empty:
        return pd.DataFrame()

    returns = prices.pct_change(fill_method=None)
    available_dates = probabilities.index.intersection(prices.index)
    if available_dates.empty:
        return pd.DataFrame()

    start_date = pd.Timestamp(available_dates.min())
    try:
        start_pos = prices.index.get_loc(start_date)
    except KeyError:
        return pd.DataFrame()

    if isinstance(start_pos, slice) or start_pos >= len(prices.index) - 1:
        return pd.DataFrame()

    out_value = 100.0
    under_value = 100.0
    benchmark_value = 100.0

    dates = [prices.index[start_pos]]
    out_values = [out_value]
    under_values = [under_value]
    benchmark_values = [benchmark_value]

    for pos in range(start_pos + 1, len(prices.index)):
        date = prices.index[pos]
        signal_date = prices.index[pos - 1]
        daily = returns.loc[date]

        benchmark_return = float(daily.get(SECTOR_BENCHMARK_LABEL, np.nan))
        if not np.isfinite(benchmark_return):
            continue

        out_return = benchmark_return
        under_return = benchmark_return

        if signal_date in probabilities.index:
            signal = probabilities.loc[signal_date]

            out_active = (
                float(signal["Out 1 Tail"]) <= float(tail_threshold)
                and float(signal["Out 2 Tail"]) <= float(tail_threshold)
            )
            if out_active:
                out_labels = [signal["Out 1 Sektor"], signal["Out 2 Sektor"]]
                candidate = pd.to_numeric(daily.reindex(out_labels), errors="coerce").dropna()
                if len(candidate) == 2:
                    out_return = float(candidate.mean())

            under_active = (
                float(signal["Under 1 Tail"]) <= float(tail_threshold)
                and float(signal["Under 2 Tail"]) <= float(tail_threshold)
            )
            if under_active:
                under_labels = [signal["Under 1 Sektor"], signal["Under 2 Sektor"]]
                candidate = pd.to_numeric(daily.reindex(under_labels), errors="coerce").dropna()
                if len(candidate) == 2:
                    under_return = float(candidate.mean())

        out_value *= 1.0 + out_return
        under_value *= 1.0 + under_return
        benchmark_value *= 1.0 + benchmark_return

        dates.append(date)
        out_values.append(out_value)
        under_values.append(under_value)
        benchmark_values.append(benchmark_value)

    return pd.DataFrame(
        {
            "Top 2 Outperformance": out_values,
            "Top 2 Underperformance": under_values,
            "S&P 500": benchmark_values,
        },
        index=pd.DatetimeIndex(dates),
    )


def _sector_rotation_figure(frame):
    fig = go.Figure()
    for col in frame.columns:
        is_benchmark = col == "S&P 500"
        fig.add_trace(go.Scatter(
            x=frame.index,
            y=frame[col],
            mode="lines",
            name=col,
            line=dict(
                width=2.5 if is_benchmark else 2.0,
                dash="dash" if is_benchmark else "solid",
            ),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>%{fullData.name}</extra>",
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
            key="sector_perf_v17",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd_v17",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v17",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr_v17",
        )

    rolling_diff = _sector_rolling_return_diff(series_map)
    if not rolling_diff.empty:
        st.markdown("#### Rollierende 1-Jahres-Renditedifferenz zum S&P 500")
        st.plotly_chart(
            _sector_rolling_return_diff_figure(rolling_diff),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_return_diff_v17",
        )

        probabilities = _sector_top2_extreme_probabilities(rolling_diff, warmup_years=10)
        if not probabilities.empty:
            st.markdown("#### Historische Wahrscheinlichkeit der Top-2-Extremsektoren")
            st.plotly_chart(
                _sector_top2_probability_figure(probabilities),
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
                key="sector_top2_probabilities_v17",
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
                    key="sector_rotation_backtests_v17",
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
