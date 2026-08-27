from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

_source = Path(__file__).with_name("app_v24_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v24_core", "exec"), globals(), globals())


def _all_sector_forward_relative_return_scatter(
    series_map,
    current_diff,
    forward_months,
):
    benchmark = series_map.get(SECTOR_BENCHMARK_LABEL)
    if benchmark is None or current_diff.empty:
        return None

    max_months = int(forward_months)
    min_months = int(st.session_state.get("sector_forward_min_months_v28", 1))
    min_months = max(1, min(min_months, max_months))

    min_periods = max(int(round(float(min_months) * 21)), 1)
    max_periods = max(int(round(float(max_months) * 21)), min_periods)

    base_index = pd.DatetimeIndex(current_diff.index)

    benchmark_aligned = pd.to_numeric(
        benchmark.reindex(base_index),
        errors="coerce",
    )
    n = len(base_index)
    if n <= max_periods:
        return None

    usable_n = n - max_periods
    current_dates = base_index[:usable_n]
    benchmark_values = benchmark_aligned.to_numpy(dtype=float)
    benchmark_start = benchmark_values[:usable_n]

    fig = go.Figure()
    points_found = False

    for label in current_diff.columns:
        sector = series_map.get(label)
        if sector is None:
            continue

        sector_aligned = pd.to_numeric(
            sector.reindex(base_index),
            errors="coerce",
        )
        sector_values = sector_aligned.to_numpy(dtype=float)
        sector_start = sector_values[:usable_n]

        max_forward = np.full(usable_n, -np.inf, dtype=float)
        max_offset = np.zeros(usable_n, dtype=int)
        has_value = np.zeros(usable_n, dtype=bool)

        with np.errstate(divide="ignore", invalid="ignore"):
            for offset in range(min_periods, max_periods + 1):
                sector_future = sector_values[offset:offset + usable_n]
                benchmark_future = benchmark_values[offset:offset + usable_n]

                forward_diff = (
                    sector_future / sector_start
                    - benchmark_future / benchmark_start
                ) * 100.0

                valid = np.isfinite(forward_diff)
                better = valid & (
                    (~has_value)
                    | (forward_diff > max_forward)
                )

                max_forward[better] = forward_diff[better]
                max_offset[better] = offset
                has_value |= valid

        max_forward[~has_value] = np.nan

        current_values = pd.to_numeric(
            current_diff[label].reindex(current_dates),
            errors="coerce",
        ).to_numpy(dtype=float)

        valid_points = np.isfinite(current_values) & np.isfinite(max_forward)
        if not valid_points.any():
            continue

        points_found = True
        point_positions = np.flatnonzero(valid_points)
        max_positions = point_positions + max_offset[valid_points]

        point_dates = current_dates[valid_points].strftime("%d.%m.%Y")
        peak_dates = base_index[max_positions].strftime("%d.%m.%Y")
        customdata = np.column_stack([point_dates, peak_dates])

        color = ACTIVE_SECTOR_COLORS.get(label, "#9ca3af")

        fig.add_trace(go.Scattergl(
            x=current_values[valid_points],
            y=max_forward[valid_points],
            mode="markers",
            name=label,
            marker=dict(
                size=5,
                opacity=0.42,
                color=color,
            ),
            customdata=customdata,
            hovertemplate=(
                "Datum: %{customdata[0]}<br>"
                "Aktuelle Renditedifferenz: %{x:.2f} %-Pkt.<br>"
                f"Max. Forward-Differenz zwischen {min_months}M und {max_months}M: "
                "%{y:.2f} %-Pkt.<br>"
                "Maximum am: %{customdata[1]}"
                "<extra>%{fullData.name}</extra>"
            ),
        ))

    if not points_found:
        return None

    fig.add_hline(y=0, line_width=1, line_dash="dot")
    fig.add_vline(x=0, line_width=1, line_dash="dot")

    layout = base_layout(True)
    layout["height"] = 540
    layout["hovermode"] = "closest"
    layout["xaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="Aktuelle rollierende Renditedifferenz (Sektor − S&P 500) in %-Pkt.",
    )
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title=(
            f"Max. Forward-Renditedifferenz zwischen "
            f"{min_months}M und {max_months}M in %-Pkt."
        ),
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.15,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


_render_sp500_sector_etfs_core = render_sp500_sector_etfs


def render_sp500_sector_etfs():
    original_markdown = st.markdown
    original_slider = st.slider

    def _markdown_with_forward_window(body, *args, **kwargs):
        if (
            isinstance(body, str)
            and body.startswith("#### Renditedifferenz vs. Forward ")
            and body.endswith(" – alle Sektoren")
        ):
            min_months = int(
                st.session_state.get("sector_forward_min_months_v28", 1)
            )
            max_months = int(
                st.session_state.get("sector_forward_max_months_v28", 12)
            )
            body = (
                "#### Renditedifferenz vs. max. Forward-Renditedifferenz "
                f"zwischen {min_months}M und {max_months}M"
            )
        return original_markdown(body, *args, **kwargs)

    def _slider_with_forward_window(label, *args, **kwargs):
        if label == "Forward-Horizont Y (Monate)":
            min_months = original_slider(
                "Forward-Fenster Minimum (Monate)",
                min_value=1,
                max_value=35,
                value=1,
                step=1,
                key="sector_forward_min_months_v28",
            )
            default_max = max(12, int(min_months) + 1)
            max_months = original_slider(
                "Forward-Fenster Maximum (Monate)",
                min_value=int(min_months),
                max_value=36,
                value=min(default_max, 36),
                step=1,
                key="sector_forward_max_months_v28",
            )
            return max_months
        return original_slider(label, *args, **kwargs)

    st.markdown = _markdown_with_forward_window
    st.slider = _slider_with_forward_window
    try:
        _render_sp500_sector_etfs_core()
    finally:
        st.markdown = original_markdown
        st.slider = original_slider


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
