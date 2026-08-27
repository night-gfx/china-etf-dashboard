from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Load v26 only up to the point before it overwrites v25's renderer alias.
_source = Path(__file__).with_name("app_v26_overlay.py").read_text(encoding="utf-8")
_core = _source.split(
    "\n_render_sp500_sector_etfs_core = render_sp500_sector_etfs",
    1,
)[0]
exec(compile(_core, "app_v26_event_helpers", "exec"), globals(), globals())

# At this point this is the working v25 wrapper. Its own
# _render_sp500_sector_etfs_core still points to the direct v24 renderer.
_render_sp500_sector_etfs_v25 = render_sp500_sector_etfs


def _two_year_trough_events(series_map, horizon_years=5):
    two_year_diff = _rolling_relative_return_diff(
        series_map,
        24,
    )
    if two_year_diff.empty:
        return [], two_year_diff

    prices = pd.DataFrame(series_map).dropna().sort_index()
    if prices.empty:
        return [], two_year_diff

    last_date = pd.Timestamp(prices.index.max())
    latest_start = last_date - pd.DateOffset(
        years=int(horizon_years)
    )

    events = []
    for label in two_year_diff.columns:
        s = pd.to_numeric(
            two_year_diff[label],
            errors="coerce",
        ).dropna()

        # Only use troughs for which a complete 5-year follow-up exists.
        eligible = s.loc[s.index <= latest_start]
        if eligible.empty:
            continue

        trough_date = pd.Timestamp(eligible.idxmin())
        trough_value = float(eligible.loc[trough_date])
        end_date = trough_date + pd.DateOffset(
            years=int(horizon_years)
        )

        events.append({
            "date": trough_date,
            "sector": label,
            "signal": trough_value,
            "end_date": end_date,
        })

    return events, two_year_diff


def _trough_indexed_figure(series_map, event):
    sector_label = event["sector"]
    start_date = event["date"]
    end_date = event["end_date"]

    frame = pd.DataFrame({
        sector_label: series_map[sector_label],
        SECTOR_BENCHMARK_LABEL: series_map[
            SECTOR_BENCHMARK_LABEL
        ],
    }).dropna().sort_index()

    frame = frame.loc[
        (frame.index >= start_date)
        & (frame.index <= end_date)
    ].copy()
    if frame.empty:
        return None

    frame = frame / frame.iloc[0] * 100.0
    sector_color = ACTIVE_SECTOR_COLORS.get(
        sector_label,
        "#9ca3af",
    )

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=frame.index,
        y=frame[sector_label],
        mode="lines",
        name=sector_label,
        line=dict(
            width=2.5,
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
            width=2.3,
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
    layout["height"] = 560
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="Indexiert (Tiefpunkt = 100)",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.12,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _trough_two_year_diff_figure(two_year_diff, event):
    sector_label = event["sector"]
    start_date = event["date"]
    end_date = event["end_date"]

    if sector_label not in two_year_diff.columns:
        return None

    s = pd.to_numeric(
        two_year_diff[sector_label],
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
            width=2.5,
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

    layout = base_layout(True)
    layout["height"] = 500
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="2Y-Renditedifferenz in %-Pkt.",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.12,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def _render_two_year_trough_analysis(original_plotly_chart):
    raw = sector_prices_usd()
    if not raw:
        return

    series_map = _common_active_sector_series(raw)
    if not series_map:
        return

    events, two_year_diff = _two_year_trough_events(
        series_map,
        horizon_years=5,
    )
    if not events:
        return

    index_key = "sector_2y_trough_index_v30"
    idx = int(st.session_state.get(index_key, 0))
    idx = max(0, min(idx, len(events) - 1))
    st.session_state[index_key] = idx

    st.markdown(
        "#### Tiefpunkt der 2-Jahres-Renditedifferenz"
    )

    left, center, right = st.columns(
        [1, 6, 1],
        gap="small",
    )

    with left:
        if st.button(
            "←",
            key="sector_2y_trough_prev_v30",
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
            key="sector_2y_trough_next_v30",
            disabled=idx >= len(events) - 1,
        ):
            st.session_state[index_key] = idx + 1
            st.rerun()

    indexed_fig = _trough_indexed_figure(
        series_map,
        event,
    )
    if indexed_fig is not None:
        st.markdown("##### Entwicklung ab Tiefpunkt")
        original_plotly_chart(
            indexed_fig,
            width="stretch",
            config={
                "displaylogo": False,
                "scrollZoom": True,
            },
            key=f"sector_2y_trough_indexed_v30_{idx}",
        )

    diff_fig = _trough_two_year_diff_figure(
        two_year_diff,
        event,
    )
    if diff_fig is not None:
        st.markdown(
            "##### Verlauf der 2-Jahres-Renditedifferenz"
        )
        original_plotly_chart(
            diff_fig,
            width="stretch",
            config={
                "displaylogo": False,
                "scrollZoom": True,
            },
            key=f"sector_2y_trough_diff_v30_{idx}",
        )


def render_sp500_sector_etfs():
    original_plotly_chart = st.plotly_chart
    trough_rendered = False

    def _plotly_chart_with_trough_analysis(
        fig,
        *args,
        **kwargs,
    ):
        nonlocal trough_rendered

        result = original_plotly_chart(
            fig,
            *args,
            **kwargs,
        )

        if (
            not trough_rendered
            and kwargs.get("key")
            == "sector_all_forward_scatter_v27"
        ):
            trough_rendered = True
            _render_two_year_trough_analysis(
                original_plotly_chart
            )

        return result

    st.plotly_chart = _plotly_chart_with_trough_analysis
    try:
        _render_sp500_sector_etfs_v25()
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
