from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v25_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v25_core", "exec"), globals(), globals())


def _monthly_sector_signal_events(
    series_map,
    threshold,
    horizon_years=3,
):
    one_year_diff = _rolling_relative_return_diff(
        series_map,
        12,
    )
    if one_year_diff.empty:
        return [], one_year_diff

    prices = pd.DataFrame(series_map).dropna().sort_index()
    if prices.empty:
        return [], one_year_diff

    last_price_date = pd.Timestamp(prices.index.max())
    events = []

    for label in one_year_diff.columns:
        s = pd.to_numeric(
            one_year_diff[label],
            errors="coerce",
        ).dropna()
        if s.empty:
            continue

        monthly_periods = s.index.to_period("M")
        monthly = s.loc[
            ~monthly_periods.duplicated(keep="last")
        ]

        hits = monthly.loc[
            monthly <= float(threshold)
        ]

        for date, value in hits.items():
            date = pd.Timestamp(date)
            end_target = date + pd.DateOffset(
                years=int(horizon_years)
            )

            if end_target > last_price_date:
                continue

            events.append({
                "date": date,
                "sector": label,
                "signal": float(value),
                "end_date": end_target,
            })

    events.sort(
        key=lambda item: (
            item["date"],
            item["sector"],
        )
    )
    return events, one_year_diff


def _event_indexed_figure(
    series_map,
    event,
):
    sector_label = event["sector"]
    start_date = event["date"]
    end_date = event["end_date"]

    prices = pd.DataFrame({
        sector_label: series_map[sector_label],
        SECTOR_BENCHMARK_LABEL: series_map[
            SECTOR_BENCHMARK_LABEL
        ],
    }).dropna().sort_index()

    frame = prices.loc[
        (prices.index >= start_date)
        & (prices.index <= end_date)
    ].copy()

    if frame.empty:
        return None

    frame = frame / frame.iloc[0] * 100.0

    fig = go.Figure()
    sector_color = ACTIVE_SECTOR_COLORS.get(
        sector_label,
        "#9ca3af",
    )

    fig.add_trace(go.Scatter(
        x=frame.index,
        y=frame[sector_label],
        mode="lines",
        name=sector_label,
        line=dict(
            width=2.3,
            color=sector_color,
        ),
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
        line=dict(
            width=2.2,
            color="#6b7280",
            dash="dash",
        ),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>%{y:.2f}</b>"
            "<extra>%{fullData.name}</extra>"
        ),
    ))

    layout = base_layout(True)
    layout["height"] = 500
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="Indexiert (Signal = 100)",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _event_one_year_diff_figure(
    one_year_diff,
    event,
    threshold,
):
    sector_label = event["sector"]
    start_date = event["date"]
    end_date = event["end_date"]

    if sector_label not in one_year_diff.columns:
        return None

    s = pd.to_numeric(
        one_year_diff[sector_label],
        errors="coerce",
    ).dropna()
    s = s.loc[
        (s.index >= start_date)
        & (s.index <= end_date)
    ]
    if s.empty:
        return None

    sector_color = ACTIVE_SECTOR_COLORS.get(
        sector_label,
        "#9ca3af",
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=s.index,
        y=s,
        mode="lines",
        name=sector_label,
        line=dict(
            width=2.3,
            color=sector_color,
        ),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>%{y:.2f} %-Pkt.</b>"
            "<extra>%{fullData.name}</extra>"
        ),
    ))

    fig.add_hline(
        y=0,
        line_width=1,
        line_dash="dot",
    )
    fig.add_hline(
        y=float(threshold),
        line_width=1.3,
        line_dash="dash",
    )

    layout = base_layout(True)
    layout["height"] = 500
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="1Y-Renditedifferenz in %-Pkt.",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _render_monthly_signal_event_analysis(
    original_plotly_chart,
):
    raw = sector_prices_usd()
    if not raw:
        return

    series_map = _common_active_sector_series(raw)
    if not series_map:
        return

    st.markdown(
        "#### Monats-Signale und 3-Jahres-Verlauf"
    )

    threshold = st.slider(
        "Schwelle – 1Y-Renditedifferenz ≤ (%-Pkt.)",
        min_value=-50,
        max_value=0,
        value=-10,
        step=1,
        key="sector_monthly_event_threshold_v29",
    )

    events, one_year_diff = _monthly_sector_signal_events(
        series_map,
        threshold,
        horizon_years=3,
    )

    if not events:
        st.info(
            "Keine Ereignisse mit vollständigem 3-Jahres-Verlauf."
        )
        return

    signature = (
        int(threshold),
        len(events),
        events[0]["date"].isoformat(),
        events[-1]["date"].isoformat(),
    )
    signature_key = "sector_monthly_event_signature_v29"
    index_key = "sector_monthly_event_index_v29"

    if (
        st.session_state.get(signature_key)
        != signature
    ):
        st.session_state[signature_key] = signature
        st.session_state[index_key] = len(events) - 1

    idx = int(
        st.session_state.get(
            index_key,
            len(events) - 1,
        )
    )
    idx = max(0, min(idx, len(events) - 1))
    st.session_state[index_key] = idx

    left, center, right = st.columns(
        [1, 6, 1],
        gap="small",
    )

    with left:
        if st.button(
            "←",
            key="sector_monthly_event_prev_v29",
            disabled=idx <= 0,
        ):
            st.session_state[index_key] = idx - 1
            st.rerun()

    event = events[idx]

    with center:
        st.markdown(
            f"**{idx + 1} / {len(events)} · "
            f"{event['sector']} · "
            f"{event['date']:%d.%m.%Y} · "
            f"{event['signal']:.2f} %-Pkt.**"
        )

    with right:
        if st.button(
            "→",
            key="sector_monthly_event_next_v29",
            disabled=idx >= len(events) - 1,
        ):
            st.session_state[index_key] = idx + 1
            st.rerun()

    indexed_fig = _event_indexed_figure(
        series_map,
        event,
    )
    diff_fig = _event_one_year_diff_figure(
        one_year_diff,
        event,
        threshold,
    )

    c1, c2 = st.columns(2, gap="large")

    with c1:
        st.markdown("##### Indexierte Entwicklung")
        if indexed_fig is not None:
            original_plotly_chart(
                indexed_fig,
                width="stretch",
                config={
                    "displaylogo": False,
                    "scrollZoom": True,
                },
                key=(
                    "sector_monthly_event_indexed_v29_"
                    f"{idx}"
                ),
            )

    with c2:
        st.markdown(
            "##### Verlauf der 1Y-Renditedifferenz"
        )
        if diff_fig is not None:
            original_plotly_chart(
                diff_fig,
                width="stretch",
                config={
                    "displaylogo": False,
                    "scrollZoom": True,
                },
                key=(
                    "sector_monthly_event_diff_v29_"
                    f"{idx}"
                ),
            )


_render_sp500_sector_etfs_core = render_sp500_sector_etfs


def render_sp500_sector_etfs():
    original_plotly_chart = st.plotly_chart
    event_rendered = False

    def _plotly_chart_with_event_analysis(
        fig,
        *args,
        **kwargs,
    ):
        nonlocal event_rendered

        result = original_plotly_chart(
            fig,
            *args,
            **kwargs,
        )

        if (
            not event_rendered
            and kwargs.get("key")
            == "sector_all_forward_scatter_v27"
        ):
            event_rendered = True
            _render_monthly_signal_event_analysis(
                original_plotly_chart
            )

        return result

    st.plotly_chart = _plotly_chart_with_event_analysis
    try:
        _render_sp500_sector_etfs_core()
    finally:
        st.plotly_chart = original_plotly_chart


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
