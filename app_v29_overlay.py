from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v25_overlay.py").read_text(encoding="utf-8")
_core = _source.split(
    "\n_render_sp500_sector_etfs_core = render_sp500_sector_etfs",
    1,
)[0]
exec(compile(_core, "app_v25_helpers", "exec"), globals(), globals())


def _available_sector_series(raw):
    if not raw or "SPY" not in raw:
        return {}

    benchmark = pd.to_numeric(raw.get("SPY"), errors="coerce").dropna().sort_index()
    if benchmark.empty:
        return {}

    series = {SECTOR_BENCHMARK_LABEL: benchmark}
    for item in SECTOR_ETFS:
        ticker = item["ticker"]
        if ticker in EXCLUDED_SECTOR_TICKERS:
            continue
        raw_series = raw.get(ticker)
        if raw_series is None:
            continue
        s = pd.to_numeric(raw_series, errors="coerce").dropna().sort_index()
        if s.empty:
            continue
        series[SECTOR_LABELS[ticker]] = s

    if len(series) <= 1:
        return {}

    frame = pd.concat(series, axis=1, join="inner").dropna(how="any").sort_index()
    if frame.empty:
        return {}

    return {col: frame[col].copy() for col in frame.columns}


def _single_sector_12m_diff(series_map, sector_label):
    benchmark = series_map.get(SECTOR_BENCHMARK_LABEL)
    sector = series_map.get(sector_label)
    if benchmark is None or sector is None:
        return pd.Series(dtype=float)

    periods = 252
    benchmark_return = benchmark / benchmark.shift(periods) - 1.0
    sector_return = sector / sector.shift(periods) - 1.0
    return ((sector_return - benchmark_return) * 100.0).dropna()


def _two_year_block_troughs(diff_series):
    s = pd.to_numeric(diff_series, errors="coerce").dropna().sort_index()
    if s.empty:
        return []

    first_date = pd.Timestamp(s.index.min())
    last_date = pd.Timestamp(s.index.max())
    block_start = first_date
    events = []

    while block_start <= last_date:
        block_end = block_start + pd.DateOffset(years=2)
        block = s.loc[(s.index >= block_start) & (s.index < block_end)]
        if not block.empty:
            trough_date = pd.Timestamp(block.idxmin())
            events.append({
                "block_start": block_start,
                "block_end": min(block_end - pd.Timedelta(days=1), last_date),
                "date": trough_date,
                "signal": float(block.loc[trough_date]),
            })
        block_start = block_end

    return events


def _single_sector_diff_figure(diff_series, sector_label, events, selected_event_idx):
    s = pd.to_numeric(diff_series, errors="coerce").dropna()
    if s.empty:
        return None

    color = ACTIVE_SECTOR_COLORS.get(sector_label, "#9ca3af")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index,
        y=s,
        mode="lines",
        name=sector_label,
        line=dict(width=2.1, color=color),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>%{y:.2f} %-Pkt.</b>"
            "<extra>%{fullData.name}</extra>"
        ),
    ))

    if events:
        fig.add_trace(go.Scatter(
            x=[item["date"] for item in events],
            y=[item["signal"] for item in events],
            mode="markers",
            name="2Y-Tiefpunkte",
            marker=dict(size=7, color=color, symbol="circle-open"),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "2Y-Tiefpunkt: <b>%{y:.2f} %-Pkt.</b>"
                "<extra></extra>"
            ),
        ))

        idx = max(0, min(int(selected_event_idx), len(events) - 1))
        fig.add_vline(
            x=events[idx]["date"],
            line_width=1.4,
            line_dash="dash",
        )

    fig.add_hline(y=0, line_width=1, line_dash="dot")

    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="12M-Renditedifferenz in %-Pkt.",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _indexed_from_trough_figure(series_map, sector_label, event, max_follow_years=5):
    sector = series_map.get(sector_label)
    benchmark = series_map.get(SECTOR_BENCHMARK_LABEL)
    if sector is None or benchmark is None:
        return None

    start_date = pd.Timestamp(event["date"])
    latest_date = min(pd.Timestamp(sector.index.max()), pd.Timestamp(benchmark.index.max()))
    end_date = min(
        start_date + pd.DateOffset(years=int(max_follow_years)),
        latest_date,
    )

    frame = pd.concat(
        [
            pd.to_numeric(sector, errors="coerce").rename(sector_label),
            pd.to_numeric(benchmark, errors="coerce").rename(SECTOR_BENCHMARK_LABEL),
        ],
        axis=1,
        join="inner",
    ).dropna().sort_index()

    frame = frame.loc[(frame.index >= start_date) & (frame.index <= end_date)]
    if frame.empty:
        return None

    frame = frame / frame.iloc[0] * 100.0
    color = ACTIVE_SECTOR_COLORS.get(sector_label, "#9ca3af")

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=frame.index,
        y=frame[sector_label],
        mode="lines",
        name=sector_label,
        line=dict(width=2.5, color=color),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>%{y:.2f}</b>"
            "<extra>%{fullData.name}</extra>"
        ),
    ))
    fig.add_trace(go.Scatter(
        x=frame.index,
        y=frame[SECTOR_BENCHMARK_LABEL],
        mode="lines",
        name=SECTOR_BENCHMARK_LABEL,
        line=dict(width=2.3, color="#6b7280", dash="dash"),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>%{y:.2f}</b>"
            "<extra>%{fullData.name}</extra>"
        ),
    ))

    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="Indexiert (Tiefpunkt = 100)",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _render_sector_selector_analysis(series_map):
    sectors = [
        label for label in series_map
        if label != SECTOR_BENCHMARK_LABEL
    ]
    if not sectors:
        return

    selected_sector = st.selectbox(
        "Sektor",
        options=sectors,
        index=0,
        key="sector_focus_select_v31",
    )

    diff_series = _single_sector_12m_diff(series_map, selected_sector)
    if diff_series.empty:
        return

    events = _two_year_block_troughs(diff_series)
    if not events:
        return

    signature_key = "sector_focus_signature_v31"
    index_key = "sector_focus_trough_idx_v31"
    signature = (selected_sector, len(events), events[-1]["date"].isoformat())

    if st.session_state.get(signature_key) != signature:
        st.session_state[signature_key] = signature
        st.session_state[index_key] = len(events) - 1

    idx = int(st.session_state.get(index_key, len(events) - 1))
    idx = max(0, min(idx, len(events) - 1))
    st.session_state[index_key] = idx
    event = events[idx]

    c1, c2 = st.columns(2, gap="large")

    with c1:
        st.markdown("#### Rollierende 12-Monats-Renditedifferenz zum S&P 500")
        fig = _single_sector_diff_figure(
            diff_series,
            selected_sector,
            events,
            idx,
        )
        if fig is not None:
            st.plotly_chart(
                fig,
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
                key=f"sector_focus_diff_v31_{selected_sector}",
            )

    with c2:
        nav_left, nav_center, nav_right = st.columns([1, 6, 1], gap="small")

        with nav_left:
            if st.button(
                "←",
                key="sector_focus_prev_v31",
                disabled=idx <= 0,
            ):
                st.session_state[index_key] = idx - 1
                st.rerun()

        with nav_center:
            st.markdown(
                f"#### Tiefpunkt {idx + 1} / {len(events)} · "
                f"{event['date']:%d.%m.%Y}"
            )
            st.caption(
                f"2Y-Block: {event['block_start']:%d.%m.%Y} – "
                f"{event['block_end']:%d.%m.%Y} · "
                f"{event['signal']:.2f} %-Pkt."
            )

        with nav_right:
            if st.button(
                "→",
                key="sector_focus_next_v31",
                disabled=idx >= len(events) - 1,
            ):
                st.session_state[index_key] = idx + 1
                st.rerun()

        indexed_fig = _indexed_from_trough_figure(
            series_map,
            selected_sector,
            event,
            max_follow_years=5,
        )
        if indexed_fig is not None:
            st.plotly_chart(
                indexed_fig,
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
                key=f"sector_focus_indexed_v31_{selected_sector}_{idx}",
            )


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

    series_map = _available_sector_series(raw)
    if not series_map:
        st.error("Keine ausreichenden Sektordaten verfügbar.")
        return

    _render_sector_selector_analysis(series_map)

    indexed = _indexed_individually(series_map)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        st.plotly_chart(
            _sector_performance_figure(indexed),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_perf_v31",
        )
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            _sector_drawdown_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_dd_v31",
        )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        st.plotly_chart(
            _sector_correlation_figure(series_map),
            width="stretch",
            config={"displaylogo": False},
            key="sector_corr_v31",
        )
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation zum S&P 500")
        st.plotly_chart(
            _sector_rolling_corr_figure(series_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key="sector_rolling_corr_v31",
        )

    s1, s2 = st.columns(2, gap="large")
    with s1:
        lookback_months = st.slider(
            "Lookback Renditedifferenz (Monate)",
            min_value=1,
            max_value=60,
            value=12,
            step=1,
            key="sector_diff_lookback_months_v31",
        )
    with s2:
        min_forward = st.slider(
            "Forward-Fenster Minimum (Monate)",
            min_value=1,
            max_value=35,
            value=1,
            step=1,
            key="sector_forward_min_months_v31",
        )
        max_forward = st.slider(
            "Forward-Fenster Maximum (Monate)",
            min_value=int(min_forward),
            max_value=36,
            value=max(12, int(min_forward)),
            step=1,
            key="sector_forward_max_months_v31",
        )

    st.session_state["sector_forward_min_months_v28"] = int(min_forward)
    rolling_diff = _rolling_relative_return_diff(series_map, lookback_months)

    if not rolling_diff.empty:
        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown(
                f"#### Rollierende {lookback_months}-Monats-Renditedifferenz zum S&P 500"
            )
            st.plotly_chart(
                _rolling_relative_return_figure(rolling_diff, lookback_months),
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
                key="sector_dynamic_rolling_diff_v31",
            )

        with c2:
            st.markdown(
                f"#### Max. Forward-Renditedifferenz zwischen "
                f"{min_forward}M und {max_forward}M"
            )
            forward_fig = _all_sector_forward_relative_return_scatter(
                series_map,
                rolling_diff,
                int(max_forward),
            )
            if forward_fig is not None:
                st.plotly_chart(
                    forward_fig,
                    width="stretch",
                    config={"displaylogo": False, "scrollZoom": True},
                    key="sector_all_forward_scatter_v31",
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
