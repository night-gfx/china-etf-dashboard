from pathlib import Path
import pandas as pd
import streamlit as st

# Load the enhanced v10 core only; no page switch is executed.
_source = Path(__file__).with_name("app_v10_overlay.py").read_text(encoding="utf-8")
_core = _source.split("# Page-style navigation without duplicate page headings.", 1)[0]
exec(compile(_core, "app_v10_core", "exec"), globals(), globals())

st.markdown(
    """
    <style>
    .block-container { padding-top:.65rem !important; }

    /* Page navigation: equal-width, plain text, active = bold + underline only. */
    .st-key-top_text_nav button,
    .st-key-china_text_nav button {
        background:transparent !important;
        border:none !important;
        border-radius:0 !important;
        box-shadow:none !important;
        color:#6b7280 !important;
        padding:.42rem .08rem .32rem .08rem !important;
        min-height:0 !important;
        justify-content:center !important;
    }
    .st-key-top_text_nav button p,
    .st-key-china_text_nav button p {
        white-space:normal !important;
        text-align:center !important;
        font-weight:400 !important;
        color:#6b7280 !important;
    }
    .st-key-top_text_nav button[kind="primary"],
    .st-key-china_text_nav button[kind="primary"],
    .st-key-top_text_nav button[data-testid="stBaseButton-primary"],
    .st-key-china_text_nav button[data-testid="stBaseButton-primary"] {
        border-bottom:2px solid #111827 !important;
    }
    .st-key-top_text_nav button[kind="primary"] p,
    .st-key-china_text_nav button[kind="primary"] p,
    .st-key-top_text_nav button[data-testid="stBaseButton-primary"] p,
    .st-key-china_text_nav button[data-testid="stBaseButton-primary"] p {
        font-weight:700 !important;
        color:#111827 !important;
    }

    /* Compact selection grid. */
    .selection-summary {
        font-size:.82rem;
        line-height:1.38;
        color:#374151;
        padding:.22rem .05rem .38rem .05rem;
    }
    .selection-summary b { color:#111827; }

    /* No selection checkboxes in dataframes. */
    [data-testid="stDataFrame"] input[type="checkbox"],
    [data-testid="stDataFrame"] [role="checkbox"] { display:none !important; }
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


def _selector_button(label, state_key, item, color, active, key_prefix):
    widget_key = f"{key_prefix}_{abs(hash(state_key + '|||' + str(item)))}"
    bg = hex_rgba(color, .11) if active else "#ffffff"
    text = color if active else "#374151"
    weight = 700 if active else 400
    border = color if active else hex_rgba(color, .62)
    st.markdown(
        f"""
        <style>
        .st-key-{widget_key} button {{
            width:100% !important;
            min-height:2.6rem !important;
            border:1.5px solid {border} !important;
            background:{bg} !important;
            color:{text} !important;
            font-weight:{weight} !important;
            justify-content:flex-start !important;
            text-align:left !important;
            border-radius:.52rem !important;
            box-shadow:none !important;
            padding:.42rem .58rem !important;
        }}
        .st-key-{widget_key} button p {{
            color:{text} !important;
            font-weight:{weight} !important;
            text-align:left !important;
            line-height:1.15 !important;
        }}
        .st-key-{widget_key} button:hover {{
            background:{hex_rgba(color, .15) if active else hex_rgba(color, .04)} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.button(
        label,
        key=widget_key,
        type="secondary",
        use_container_width=True,
        on_click=_toggle_selector,
        args=(state_key, item),
    )


CONCISE_SPECIAL = {
    "MSCI China All Shares Stock Connect Select": "Breite China-Benchmark mit Onshore- und Offshore-Markt.",
    "S&P China 500": "Breite, sektorübergreifende China-Benchmark.",
    "FTSE China 30/18 Capped": "Breite China-Benchmark mit Konzentrationsbegrenzung.",
    "MSCI China": "Breite Standardbenchmark für chinesische Large- und Mid-Caps.",
    "MSCI China ex A Shares": "Offshore-China-Benchmark ohne Mainland-A-Aktien.",
    "Dow Jones China Offshore 50": "Large-Cap-Benchmark für chinesische Offshore-Unternehmen.",
    "FTSE China 50": "Hongkong-notierte China-Large-Cap-Benchmark.",
    "CSI Overseas China Internet": "Offshore-Benchmark für chinesische Internetunternehmen.",
    "MSCI China A": "Breite Mainland-China-Benchmark.",
    "CSI A 500": "Breite Mainland-China-Benchmark mit stärkerer Branchenabdeckung.",
    "MSCI China A Inclusion": "Benchmark für die schrittweise MSCI-Integration chinesischer A-Aktien.",
    "CSI 300": "Leitbenchmark für große und mittelgroße Mainland-China-Unternehmen.",
    "S&P China A 300": "Mainland-China-Benchmark für liquide Large- und Mid-Caps.",
    "SSE Science and Technology Innovation Board 50": "Technologie-/Innovationsfokus auf dem STAR Market.",
    "ChiNext 50 Capped": "Wachstums-/Innovationsfokus auf dem ChiNext-Markt.",
}


def _market_detail(name, key):
    info = INDEX_INFO[name]
    st.markdown(
        f"<div class='selection-summary'><b>{name}</b><br>"
        f"Segment: {info['segment']} · Gewichtung: {info['weight']} · Rebalancing: {info['rebalance']}<br>"
        f"Besonderheit: {CONCISE_SPECIAL.get(name, info['special'])}</div>",
        unsafe_allow_html=True,
    )
    c1, c2 = st.columns(2, gap="small")
    with c1:
        st.link_button("Methodology", info["url"], use_container_width=True)
    with c2:
        if st.button("ETF-Vergleich", key=f"etf_{key}_{name}", use_container_width=True):
            return name
    return None


def market_category(title, items, key):
    selected = ensure_selected(key, items)
    dialog = None
    with st.expander(title, expanded=False):
        for start in range(0, len(items), 3):
            cols = st.columns(3, gap="small")
            for col, name in zip(cols, items[start:start + 3]):
                with col:
                    _selector_button(name, key, name, INDEX_COLOR[name], name in selected, "market_sel")

        active_items = [name for name in items if name in selected]
        if active_items:
            st.divider()
            for name in active_items:
                d = _market_detail(name, key)
                dialog = dialog or d
    return list(ensure_selected(key, items)), dialog


def tech_category(title, rows, key, offset=0):
    items = rows["etf_name"].tolist()
    selected = ensure_selected(key, items)
    with st.expander(title, expanded=False):
        row_map = rows.set_index("etf_name")
        for start in range(0, len(items), 2):
            cols = st.columns(2, gap="small")
            for col, name in zip(cols, items[start:start + 2]):
                with col:
                    color = TECH_COLOR.get(name, "#6b7280")
                    _selector_button(name, key, name, color, name in selected, "tech_sel")

        active_items = [name for name in items if name in selected]
        if active_items:
            st.divider()
            for name in active_items:
                row = row_map.loc[name]
                proxy = MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(row["share_classes"]), "–")
                st.markdown(
                    f"<div class='selection-summary'><b>{name}</b><br>"
                    f"Index: {row['index_name']} · TER: {row['ter']:.2f}%<br>"
                    f"Market Proxy: {proxy}</div>",
                    unsafe_allow_html=True,
                )
                st.link_button("ETF / Methodology", row["source_url"], use_container_width=True)
    return list(ensure_selected(key, items))


def style_heat(df, focus=None, reverse_columns=None):
    reverse_columns = set(reverse_columns or [])
    pct = {"CAGR p.a.", "Volatilität p.a.", "Max. Drawdown", "Tracking Error p.a."}
    ratios = {"Sharpe Ratio", "Sortino", "Calmar", "Information Ratio p.a."}
    fmts = {c: (lambda x: "–" if pd.isna(x) else f"{x:.2%}") for c in df.columns if c in pct}
    fmts.update({c: (lambda x: "–" if pd.isna(x) else f"{x:.2f}")
                 for c in df.columns if c in ratios or str(c).isdigit()})
    sty = df.style.format(fmts, na_rep="–").set_properties(**{"color":"#111827", "background-color":"#fff"})
    for col in df.select_dtypes(include="number").columns:
        vals = pd.to_numeric(df[col], errors="coerce").dropna()
        if vals.empty:
            continue
        lo, hi = float(vals.min()), float(vals.max())
        rev = col in reverse_columns
        sty = sty.map(lambda v, lo=lo, hi=hi, rev=rev: _cell_color(v, lo, hi, rev), subset=[col])
    if focus is not None and focus in df.index:
        row_style = "font-weight:800;border-top:2px solid #111827;border-bottom:2px solid #111827"
        sty = sty.apply(lambda row: [row_style if row.name == focus else "" for _ in row], axis=1)
        sty = sty.apply_index(lambda values: [row_style if value == focus else "" for value in values], axis=0)
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
    series = {x.label:x.series_eur for x in resolved}
    display = {x.label:(x.index_name if key_prefix == "market" else x.etf_name) for x in resolved}
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
    focus_col = next((c for c,n in display.items() if n == focus), None)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        key = f"{key_prefix}_perf"
        event = st.plotly_chart(line_fig(frame, colors, focus_col, False, benchmark_map), width="stretch",
                                config={"displaylogo":False,"scrollZoom":True}, key=key,
                                on_select="rerun", selection_mode="points")
        handle_plot_focus(event, display, focus_key, key)
    with c2:
        st.markdown("#### Drawdown")
        key = f"{key_prefix}_dd"
        event = st.plotly_chart(line_fig(frame, colors, focus_col, True, benchmark_map), width="stretch",
                                config={"displaylogo":False,"scrollZoom":True}, key=key,
                                on_select="rerun", selection_mode="points")
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
        event = st.plotly_chart(correlation_fig(corr_frame, display, focus_col), width="stretch",
                                config={"displaylogo":False}, key=f"{key_prefix}_corr",
                                on_select="rerun", selection_mode="points")
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
            st.plotly_chart(rolling_corr_fig(corr_frame, pair[0], pair[1], display), width="stretch",
                            config={"displaylogo":False,"scrollZoom":True}, key=f"{key_prefix}_roll")

    annual = yearly_sharpe_matrix(corr_frame, display)
    bench_stats = {}
    if benchmark_map:
        bench_stats = {lab:frame[bcol] for lab,bcol in benchmark_map.items()
                       if lab in corr_frame.columns and bcol in frame.columns}
    total = total_stats(corr_frame, display, bench_stats if benchmark_map else None)
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        event = st.dataframe(style_heat(annual, focus), width="stretch", height=compact_height(len(annual)),
                             on_select="rerun", selection_mode="single-cell",
                             key=f"{key_prefix}_annual_{abs(hash(focus or 'none'))}")
        handle_table_focus(event, annual, focus_key)
    with c2:
        st.markdown("#### Gesamtperformance")
        event = st.dataframe(style_heat(total, focus), width="stretch", height=compact_height(len(total)),
                             on_select="rerun", selection_mode="single-cell",
                             key=f"{key_prefix}_total_{abs(hash(focus or 'none'))}")
        handle_table_focus(event, total, focus_key)


@st.dialog("ETFs des Index", width="large")
def etf_dialog(index_name):
    sub = registry[registry["index_name"] == index_name].sort_values("inception").copy()
    if sub.empty:
        return
    st.markdown(f"### {index_name}")
    table = sub.copy()
    table["Auflage"] = table["inception"].map(fmt_date)
    table["Mitglieder"] = INDEX_INFO[index_name]["members"]
    table["JustETF"] = table["isin"].map(lambda x: f"https://www.justetf.com/de/etf-profile.html?isin={x}")
    show = table[["etf_name","isin","Auflage","Mitglieder","ter","distribution","JustETF"]].rename(
        columns={"etf_name":"ETF","isin":"ISIN","ter":"TER","distribution":"Ertragsverwendung"})
    st.dataframe(show.style.set_properties(**{"color":"#111827","background-color":"#fff"}).format({"TER":"{:.2f}%"}),
                 width="stretch", height=compact_height(len(show)), hide_index=True,
                 column_config={"JustETF":st.column_config.LinkColumn("Link",display_text="Öffnen")})

    cache = _cache("v9_etf_data")
    names = sub["etf_name"].tolist()
    resolved, warnings = [], []
    for name in names:
        if (index_name, name) not in cache:
            session_etf(index_name, name)
        rows, row_warnings = cache[(index_name, name)]
        resolved += rows
        warnings += row_warnings
    for warning in warnings:
        st.warning(warning)
    if resolved:
        render_outputs(resolved, f"dlg_{abs(hash(index_name))}", f"dlg_focus_{abs(hash(index_name))}")


def render_tech(_status_host=None):
    tech = tech_registry_cached().copy()
    selected = []
    all_rows = tech[tech["universe"] == "All Shares"]
    on_rows = tech[tech["universe"] == "Onshore"]
    off_rows = tech[tech["universe"] == "Offshore"]
    if not all_rows.empty:
        selected += tech_category("All Shares", all_rows, "t_all", 0)
    left, right = st.columns(2, gap="large")
    with left:
        if not on_rows.empty:
            selected += tech_category("Onshore", on_rows, "t_on", len(all_rows))
    with right:
        if not off_rows.empty:
            selected += tech_category("Offshore", off_rows, "t_off", len(all_rows) + len(on_rows))
    if not selected:
        return

    cache = _cache("v9_tech_data")
    for name in selected:
        if name not in cache:
            session_tech(name)
    resolved, warnings = [], []
    for name in selected:
        items, item_warnings = cache[name]
        resolved += items
        warnings += item_warnings
    for warning in warnings:
        st.warning(warning)
    if not resolved:
        return

    meta = tech.set_index("etf_name")
    benchmark_map, benchmark_series = {}, {}
    for item in resolved:
        if item.etf_name not in meta.index:
            continue
        proxy = MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(meta.loc[item.etf_name, "share_classes"]))
        if not proxy:
            continue
        benchmark, error = session_index(proxy)
        if benchmark is None:
            continue
        bcol = f"__BENCH__{item.label}"
        benchmark_map[item.label] = bcol
        benchmark_series[bcol] = benchmark.series_eur
    render_outputs(resolved, "tech", "tech_focus", benchmark_map, benchmark_series)


def _text_nav(options, state_key, default, container_key):
    current = st.session_state.get(state_key, default)
    if current not in options:
        current = default
        st.session_state[state_key] = current
    with st.container(key=container_key):
        cols = st.columns([1] * len(options), gap="small")
        for col, option in zip(cols, options):
            with col:
                st.button(option, key=f"{container_key}_{abs(hash(option))}",
                          type="primary" if current == option else "secondary",
                          use_container_width=True, on_click=_set_state, args=(state_key, option))
    return st.session_state.get(state_key, current)


def render_china_dashboard():
    page = _text_nav(
        ["Market ETFs vergleichen", "Tech ETFs vergleichen"],
        "china_page", "Market ETFs vergleichen", "china_text_nav"
    )
    if page == "Market ETFs vergleichen":
        selected, dialog = market_tree()
        cache = _cache("v9_index_data")
        for name in selected:
            if name not in cache:
                session_index(name)
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
        render_tech()


top_page = _text_nav(
    ["China ETF Dashboard", "Asset Allocation Backtesting Tool"],
    "top_page", "China ETF Dashboard", "top_text_nav"
)
st.session_state.after_tax = True

if top_page == "China ETF Dashboard":
    render_china_dashboard()
else:
    render_asset_allocation_tool()
