from pathlib import Path
import pandas as pd
import streamlit as st

# Load v10 definitions only; do not execute its page switch.
_source = Path(__file__).with_name("app_v10_overlay.py").read_text(encoding="utf-8")
_core = _source.split("# Page-style navigation without duplicate page headings.", 1)[0]
exec(compile(_core, "app_v10_core", "exec"), globals(), globals())

st.markdown(
    """
    <style>
    /* Native text tabs: no radio pointer, no pill/background. */
    .st-key-top_text_nav button,
    .st-key-china_text_nav button {
        background: transparent !important;
        border: none !important;
        border-radius: 0 !important;
        box-shadow: none !important;
        color: #6b7280 !important;
        padding: .45rem .08rem .35rem .08rem !important;
        min-height: 0 !important;
        justify-content: flex-start !important;
    }
    .st-key-top_text_nav button p,
    .st-key-china_text_nav button p {
        white-space: normal !important;
        text-align: left !important;
        font-weight: 400 !important;
        color: #6b7280 !important;
    }
    .st-key-top_text_nav button[kind="primary"],
    .st-key-china_text_nav button[kind="primary"],
    .st-key-top_text_nav button[data-testid="stBaseButton-primary"],
    .st-key-china_text_nav button[data-testid="stBaseButton-primary"] {
        border-bottom: 2px solid #111827 !important;
    }
    .st-key-top_text_nav button[kind="primary"] p,
    .st-key-china_text_nav button[kind="primary"] p,
    .st-key-top_text_nav button[data-testid="stBaseButton-primary"] p,
    .st-key-china_text_nav button[data-testid="stBaseButton-primary"] p {
        font-weight: 700 !important;
        color: #111827 !important;
    }

    /* Single-cell dataframe selection has no row-selection checkbox column. */
    [data-testid="stDataFrame"] input[type="checkbox"],
    [data-testid="stDataFrame"] [role="checkbox"] {
        display: none !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def _set_state(key, value):
    st.session_state[key] = value


def _toggle_selector(state_key, item):
    current = list(st.session_state.get(state_key, []))
    if item in current:
        current.remove(item)
    else:
        current.append(item)
    st.session_state[state_key] = current


def selector_box(label, state_key, item, color, active):
    widget_key = f"selector_{abs(hash(state_key + '|||' + str(item)))}"
    background = hex_rgba(color, .10) if active else "rgba(255,255,255,0)"
    text_color = color if active else "#111827"
    weight = 700 if active else 400
    st.markdown(
        f"""
        <style>
        .st-key-{widget_key} button {{
            width:100% !important;
            border:1.5px solid {color} !important;
            background:{background} !important;
            color:{text_color} !important;
            font-weight:{weight} !important;
            justify-content:flex-start !important;
            text-align:left !important;
            border-radius:.58rem !important;
            box-shadow:none !important;
        }}
        .st-key-{widget_key} button p {{
            color:{text_color} !important;
            font-weight:{weight} !important;
            text-align:left !important;
            width:100% !important;
        }}
        .st-key-{widget_key} button:hover {{
            background:{hex_rgba(color, .14) if active else hex_rgba(color, .035)} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.button(
        str(label),
        key=widget_key,
        type="secondary",
        use_container_width=True,
        on_click=_toggle_selector,
        args=(state_key, item),
    )


def style_heat(df, focus=None, reverse_columns=None):
    reverse_columns = set(reverse_columns or [])
    pct = {"CAGR p.a.", "Volatilität p.a.", "Max. Drawdown", "Tracking Error p.a."}
    ratios = {"Sharpe Ratio", "Sortino", "Calmar", "Information Ratio p.a."}
    fmts = {
        c: (lambda x: "–" if pd.isna(x) else f"{x:.2%}")
        for c in df.columns if c in pct
    }
    fmts.update({
        c: (lambda x: "–" if pd.isna(x) else f"{x:.2f}")
        for c in df.columns if c in ratios or str(c).isdigit()
    })
    sty = df.style.format(fmts, na_rep="–").set_properties(
        **{"color": "#111827", "background-color": "#fff"}
    )
    for col in df.select_dtypes(include="number").columns:
        vals = pd.to_numeric(df[col], errors="coerce").dropna()
        if vals.empty:
            continue
        lo, hi = float(vals.min()), float(vals.max())
        rev = col in reverse_columns
        sty = sty.map(
            lambda v, lo=lo, hi=hi, rev=rev: _cell_color(v, lo, hi, rev),
            subset=[col],
        )
    if focus is not None and focus in df.index:
        row_style = "font-weight:800;border-top:2px solid #111827;border-bottom:2px solid #111827"
        sty = sty.apply(
            lambda row: [row_style if row.name == focus else "" for _ in row],
            axis=1,
        )
        sty = sty.apply_index(
            lambda values: [row_style if value == focus else "" for value in values],
            axis=0,
        )
    return sty


def handle_table_focus(event, df, focus_key):
    try:
        cells = event.selection.cells
    except Exception:
        return
    if not cells:
        return
    cell = cells[0]
    if isinstance(cell, dict):
        row_idx = cell.get("row")
    elif isinstance(cell, (list, tuple)) and cell:
        row_idx = cell[0]
    else:
        return
    if row_idx is None:
        return
    idx = int(row_idx)
    if 0 <= idx < len(df):
        toggle_focus(df.index[idx], focus_key)
        st.rerun()


def render_outputs(resolved, key_prefix, focus_key, benchmark_map=None, benchmark_series=None):
    if not resolved:
        return
    series = {x.label: x.series_eur for x in resolved}
    display = {
        x.label: (x.index_name if key_prefix == "market" else x.etf_name)
        for x in resolved
    }
    colors = {}
    for i, item in enumerate(resolved):
        if key_prefix == "market":
            colors[item.label] = INDEX_COLOR.get(item.index_name, PALETTE[i % len(PALETTE)])
        elif key_prefix == "tech":
            colors[item.label] = TECH_COLOR.get(item.etf_name, PALETTE[i % len(PALETTE)])
        else:
            colors[item.label] = PALETTE[i % len(PALETTE)]

    if benchmark_map and benchmark_series:
        for _, bcol in benchmark_map.items():
            if bcol in benchmark_series:
                series[bcol] = benchmark_series[bcol]

    frame = common_frame(series)
    if frame.empty:
        return

    focus = st.session_state.get(focus_key)
    focus_col = next((c for c, n in display.items() if n == focus), None)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        key = f"{key_prefix}_perf"
        event = st.plotly_chart(
            line_fig(frame, colors, focus_col, False, benchmark_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key=key,
            on_select="rerun",
            selection_mode="points",
        )
        handle_plot_focus(event, display, focus_key, key)
    with c2:
        st.markdown("#### Drawdown")
        key = f"{key_prefix}_dd"
        event = st.plotly_chart(
            line_fig(frame, colors, focus_col, True, benchmark_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key=key,
            on_select="rerun",
            selection_mode="points",
        )
        handle_plot_focus(event, display, focus_key, key)

    corr_cols = [c for c in frame.columns if not c.startswith("__BENCH__")]
    corr_frame = frame[corr_cols]
    pair_key = f"{key_prefix}_corr_pair"
    pair = st.session_state.get(pair_key)
    if not pair or any(x not in corr_frame.columns for x in pair) or pair[0] == pair[1]:
        pair = (corr_cols[0], corr_cols[1]) if len(corr_cols) >= 2 else None

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        event = st.plotly_chart(
            correlation_fig(corr_frame, display, focus_col),
            width="stretch",
            config={"displaylogo": False},
            key=f"{key_prefix}_corr",
            on_select="rerun",
            selection_mode="points",
        )
        try:
            pts = event.selection.points
            if pts:
                custom = pts[0].get("customdata")
                if custom and "|||" in custom:
                    p = tuple(custom.split("|||", 1))
                    if p[0] != p[1]:
                        st.session_state[pair_key] = p
        except Exception:
            pass
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation")
        pair = st.session_state.get(pair_key) or pair
        if pair:
            st.plotly_chart(
                rolling_corr_fig(corr_frame, pair[0], pair[1], display),
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
                key=f"{key_prefix}_roll",
            )

    annual = yearly_sharpe_matrix(corr_frame, display)
    bench_stats = {}
    if benchmark_map:
        bench_stats = {
            lab: frame[bcol]
            for lab, bcol in benchmark_map.items()
            if lab in corr_frame.columns and bcol in frame.columns
        }
    total = total_stats(corr_frame, display, bench_stats if benchmark_map else None)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        event = st.dataframe(
            style_heat(annual, focus),
            width="stretch",
            height=compact_height(len(annual)),
            on_select="rerun",
            selection_mode="single-cell",
            key=f"{key_prefix}_annual_{abs(hash(focus or 'none'))}",
        )
        handle_table_focus(event, annual, focus_key)
    with c2:
        st.markdown("#### Gesamtperformance")
        event = st.dataframe(
            style_heat(total, focus),
            width="stretch",
            height=compact_height(len(total)),
            on_select="rerun",
            selection_mode="single-cell",
            key=f"{key_prefix}_total_{abs(hash(focus or 'none'))}",
        )
        handle_table_focus(event, total, focus_key)


def _text_nav(options, state_key, default, container_key, widths=None):
    current = st.session_state.get(state_key, default)
    if current not in options:
        current = default
        st.session_state[state_key] = current
    with st.container(key=container_key):
        cols = st.columns(widths or [1] * len(options), gap="small")
        for col, option in zip(cols, options):
            with col:
                st.button(
                    option,
                    key=f"{container_key}_{abs(hash(option))}",
                    type="primary" if current == option else "secondary",
                    use_container_width=True,
                    on_click=_set_state,
                    args=(state_key, option),
                )
    return st.session_state.get(state_key, current)


def render_china_dashboard():
    nav, status_col = st.columns([.68, .32], vertical_alignment="center")
    with nav:
        page = _text_nav(
            ["Market ETFs vergleichen", "Tech ETFs vergleichen"],
            "china_page",
            "Market ETFs vergleichen",
            "china_text_nav",
            [1, 1],
        )

    if page == "Market ETFs vergleichen":
        selected, dialog = market_tree()
        status, progress = status_col.empty(), status_col.progress(0)
        cache = _cache("v9_index_data")
        done = sum(name in cache for name in selected)
        status_text(status, done, len(selected))
        progress.progress(100 if not selected else round(done / len(selected) * 100))
        for name in selected:
            if name not in cache:
                session_index(name)
                done += 1
                status_text(status, done, len(selected))
                progress.progress(round(done / len(selected) * 100))
        resolved, warnings = [], []
        for name in selected:
            item, error = cache[name]
            if item is not None:
                resolved.append(item)
            if error:
                warnings.append(f"{name}: {error}")
        for warning in warnings:
            st.warning(warning)
        render_outputs(resolved, "market", "market_focus")
        if dialog:
            etf_dialog(dialog)
    else:
        render_tech(status_col)


top_page = _text_nav(
    ["China ETF Dashboard", "Asset Allocation Backtesting Tool"],
    "top_page",
    "China ETF Dashboard",
    "top_text_nav",
    [.36, .64],
)
st.session_state.after_tax = True

if top_page == "China ETF Dashboard":
    render_china_dashboard()
else:
    render_asset_allocation_tool()
