from pathlib import Path
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Stable data/metric definitions from v5. No runtime source patching.
_base = Path(__file__).with_name("app_v5.py").read_text(encoding="utf-8")
_prefix = _base.split("registry=registry_cached()", 1)[0]
exec(compile(_prefix, "app_v5_core", "exec"), globals(), globals())

# ----- direct v8 UI -----
st.markdown(
    """
    <style>
    div[data-testid="stButton"] > button {
      justify-content: flex-start !important;
      text-align: left !important;
      background: #ffffff !important;
      color: #111827 !important;
      border-color: #d1d5db !important;
    }
    div[data-testid="stButton"] > button:hover {
      background: #f8fafc !important;
      border-color: #9ca3af !important;
    }
    div[data-testid="stButton"] > button p {
      width: 100% !important;
      text-align: left !important;
    }
    [data-testid="stDataFrame"] * { color:#111827 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# No chart legend and no unified multi-series hover box.
def base_layout(showlegend=False):
    return dict(
        showlegend=False,
        hovermode="closest",
        dragmode="zoom",
        height=520,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#111827"),
        margin=dict(l=50, r=18, t=18, b=45),
        xaxis=dict(showgrid=False, zeroline=False, autorange=True),
    )


def style_heat_v8(df, focus=None):
    pct = {"CAGR p.a.", "Volatilität p.a.", "Max. Drawdown", "Tracking Error p.a."}
    nums = {"Sharpe Ratio", "Sortino", "Calmar", "Information Ratio p.a."}
    fmts = {
        c: (lambda x: "–" if pd.isna(x) else f"{x:.2%}")
        for c in df.columns if c in pct
    }
    fmts.update({
        c: (lambda x: "–" if pd.isna(x) else f"{x:.2f}")
        for c in df.columns if c in nums or str(c).isdigit()
    })
    sty = df.style.format(fmts, na_rep="–").set_properties(
        **{"color": "#111827", "background-color": "#ffffff"}
    )
    for column in df.select_dtypes(include="number").columns:
        vals = pd.to_numeric(df[column], errors="coerce")
        valid = vals.dropna()
        if valid.empty:
            continue
        lo, hi = float(valid.min()), float(valid.max())

        def paint(v):
            if pd.isna(v):
                return "color:#111827;background-color:#fff"
            p = .5 if hi == lo else (float(v) - lo) / (hi - lo)
            if p <= .5:
                w, a, b = p * 2, (248, 190, 190), (255, 244, 176)
            else:
                w, a, b = (p - .5) * 2, (255, 244, 176), (183, 229, 190)
            rgb = tuple(round(x + (y - x) * w) for x, y in zip(a, b))
            return f"background-color:rgb{rgb};color:#111827"

        sty = sty.map(paint, subset=[column])
    if focus is not None and focus in df.index:
        sty = sty.apply(
            lambda row: [
                "font-weight:800;border-top:2px solid #111827;border-bottom:2px solid #111827"
                if row.name == focus else ""
                for _ in row
            ],
            axis=1,
        )
    return sty


def compact_height(n, row=35, base=40, maximum=420):
    return min(maximum, base + max(1, n) * row)


def dot_for(i):
    return ["🔵", "🔴", "🟢", "🟣", "🟠", "🟦", "🟥", "🟩", "🟪", "🟧"][i % 10]


def _session_cache(name):
    if name not in st.session_state:
        st.session_state[name] = {}
    return st.session_state[name]


def session_index(name):
    cache = _session_cache("v8_index_data")
    if name not in cache:
        try:
            cache[name] = (resolve_index_cached(name), None)
        except Exception as exc:
            cache[name] = (None, str(exc))
    return cache[name]


def session_tech(name):
    cache = _session_cache("v8_tech_data")
    if name not in cache:
        cache[name] = resolve_tech_cached((name,))
    return cache[name]


def session_etf(index_name, etf_name):
    cache = _session_cache("v8_etf_data")
    key = (index_name, etf_name)
    if key not in cache:
        cache[key] = resolve_rows_cached(index_name, (etf_name,))
    return cache[key]


def update_status(text_host, bar, done, total, label="Marktdaten geladen"):
    pct = 100 if total == 0 else round(done / total * 100)
    text_host.markdown(
        f"**{label} &nbsp;&nbsp; Version v8**<br>"
        f"<span style='font-size:.86rem;color:#4b5563'>({done}/{total}) &nbsp;&nbsp; {pct} %</span>",
        unsafe_allow_html=True,
    )
    bar.progress(pct)


def ensure_selected(key, items):
    if key not in st.session_state:
        st.session_state[key] = items.copy()
    st.session_state[key] = [x for x in st.session_state[key] if x in items]
    return st.session_state[key]


def toggle_selected(key, item, items):
    current = list(ensure_selected(key, items))
    if item in current:
        current.remove(item)
    else:
        current.append(item)
    st.session_state[key] = current
    st.rerun()


def _toggle_focus(name, focus_key):
    st.session_state[focus_key] = None if st.session_state.get(focus_key) == name else name


def _selection_signature(value):
    try:
        return tuple(value) if isinstance(value, (list, tuple)) else str(value)
    except Exception:
        return str(value)


def handle_plot_focus(event, display, focus_key, widget_key):
    try:
        points = event.selection.points
    except Exception:
        return
    guard_key = f"{widget_key}_last_point"
    if not points:
        if st.session_state.get(guard_key) is not None:
            st.session_state[guard_key] = None
            if st.session_state.get(focus_key) is not None:
                st.session_state[focus_key] = None
                st.rerun()
        return
    point = points[0]
    cd = point.get("customdata") if isinstance(point, dict) else None
    if cd not in display:
        return
    sig = (cd, point.get("point_index"), point.get("x")) if isinstance(point, dict) else _selection_signature(point)
    if st.session_state.get(guard_key) == sig:
        return
    st.session_state[guard_key] = sig
    _toggle_focus(display[cd], focus_key)
    st.rerun()


def handle_table_focus(event, df, focus_key, widget_key):
    try:
        cells = event.selection.cells
    except Exception:
        return
    guard_key = f"{widget_key}_last_cell"
    if not cells:
        if st.session_state.get(guard_key) is not None:
            st.session_state[guard_key] = None
            if st.session_state.get(focus_key) is not None:
                st.session_state[focus_key] = None
                st.rerun()
        return
    cell = cells[0]
    if isinstance(cell, dict):
        row_idx = cell.get("row")
        col = cell.get("column")
    elif isinstance(cell, (tuple, list)) and len(cell) >= 2:
        row_idx, col = cell[0], cell[1]
    else:
        return
    if row_idx is None or not (0 <= int(row_idx) < len(df)):
        return
    sig = (int(row_idx), str(col))
    if st.session_state.get(guard_key) == sig:
        return
    st.session_state[guard_key] = sig
    _toggle_focus(df.index[int(row_idx)], focus_key)
    st.rerun()


registry = registry_cached()
index_order = (
    registry[["index_order", "index_name"]]
    .drop_duplicates()
    .sort_values("index_order")["index_name"]
    .tolist()
)
INDEX_COLOR = {n: PALETTE[i % len(PALETTE)] for i, n in enumerate(index_order)}
INDEX_DOT = {n: dot_for(i) for i, n in enumerate(index_order)}


def index_details(name):
    info = INDEX_INFO[name]
    st.markdown(
        f"• **Aktienklassen:** {share_text(name)}  \n"
        f"• **Segment:** {info['segment']}  \n"
        f"• **Mitglieder:** {info['members']}  \n"
        f"• **Gewichtung:** {info['weight']}  \n"
        f"• **Rebalancing:** {info['rebalance']}  \n"
        f"• **Besonderheit:** {info['special']}"
    )


def market_category(title, items, key):
    selected = ensure_selected(key, items)
    dialog = None
    with st.expander(title, expanded=False):
        all_active = len(selected) == len(items)
        _, bulk = st.columns([.88, .12])
        with bulk:
            if st.button(
                "✓" if all_active else "+",
                key=f"bulk_{key}",
                help="Kategorie vollständig auswählen/abwählen",
                use_container_width=True,
            ):
                st.session_state[key] = [] if all_active else items.copy()
                st.rerun()
        for n in items:
            active = n in selected
            with st.container(border=True):
                label = f"{'✓  ' if active else ''}{INDEX_DOT[n]}  {n}"
                if st.button(label, key=f"sel_{key}_{n}", type="secondary", use_container_width=True):
                    toggle_selected(key, n, items)
                index_details(n)
                l1, l2 = st.columns(2, gap="small")
                with l1:
                    st.link_button("Methodology", INDEX_INFO[n]["url"], use_container_width=True)
                with l2:
                    if st.button("ETF-Vergleich", key=f"etf_{key}_{n}", use_container_width=True):
                        dialog = n
    return list(ensure_selected(key, items)), dialog


def market_tree():
    alls = [x for x in index_order if INDEX_SCOPE[x] == "All Shares"]
    ons = [x for x in index_order if INDEX_SCOPE[x] == "Onshore"]
    offs = [x for x in index_order if INDEX_SCOPE[x] == "Offshore"]
    selected, dialog = [], None
    s, d = market_category("All Shares", alls, "m_all")
    selected += s
    dialog = dialog or d
    left, right = st.columns(2, gap="large")
    with left:
        s, d = market_category("Onshore", ons, "m_on")
        selected += s
        dialog = dialog or d
    with right:
        s, d = market_category("Offshore", offs, "m_off")
        selected += s
        dialog = dialog or d
    return selected, dialog


def render_outputs_v8(resolved, key_prefix, focus_key, benchmark_map=None, benchmark_series=None):
    if not resolved:
        st.info("Keine verfügbaren Serien.")
        return
    series = {x.label: x.series_eur for x in resolved}
    display = {
        x.label: (x.index_name if key_prefix == "market" else x.etf_name)
        for x in resolved
    }
    colors = {
        x.label: (
            INDEX_COLOR.get(x.index_name, PALETTE[i % len(PALETTE)])
            if key_prefix == "market" else PALETTE[i % len(PALETTE)]
        )
        for i, x in enumerate(resolved)
    }
    if benchmark_map and benchmark_series:
        for _, bcol in benchmark_map.items():
            if bcol in benchmark_series:
                series[bcol] = benchmark_series[bcol]
    frame = common_frame(series)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum.")
        return

    focus = st.session_state.get(focus_key)
    focus_col = next((c for c, n in display.items() if n == focus), None)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        perf_key = f"{key_prefix}_perf"
        ev = st.plotly_chart(
            line_fig(frame, colors, focus_col, False, benchmark_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key=perf_key,
            on_select="rerun",
            selection_mode="points",
        )
        handle_plot_focus(ev, display, focus_key, perf_key)
    with c2:
        st.markdown("#### Drawdown")
        dd_key = f"{key_prefix}_dd"
        ev = st.plotly_chart(
            line_fig(frame, colors, focus_col, True, benchmark_map),
            width="stretch",
            config={"displaylogo": False, "scrollZoom": True},
            key=dd_key,
            on_select="rerun",
            selection_mode="points",
        )
        handle_plot_focus(ev, display, focus_key, dd_key)

    corr_cols = [c for c in frame.columns if not c.startswith("__BENCH__")]
    corr_frame = frame[corr_cols]
    pair_key = f"{key_prefix}_corr_pair"
    pair = st.session_state.get(pair_key)
    if not pair or any(x not in corr_frame.columns for x in pair) or pair[0] == pair[1]:
        pair = (corr_cols[0], corr_cols[1]) if len(corr_cols) >= 2 else None

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        corr_event = st.plotly_chart(
            correlation_fig(corr_frame, display, focus_col),
            width="stretch",
            config={"displaylogo": False},
            key=f"{key_prefix}_corr",
            on_select="rerun",
            selection_mode="points",
        )
        try:
            points = corr_event.selection.points
            if points:
                cd = points[0].get("customdata")
                if cd and "|||" in cd:
                    p = tuple(cd.split("|||", 1))
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
        else:
            st.info("Mindestens zwei Serien erforderlich.")

    annual = yearly_sharpe_matrix(corr_frame, display)
    metric_bench = {}
    if benchmark_map:
        metric_bench = {
            lab: frame[bcol]
            for lab, bcol in benchmark_map.items()
            if lab in corr_frame.columns and bcol in frame.columns
        }
    total = total_stats(corr_frame, display, metric_bench if benchmark_map else None)

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        annual_key = f"{key_prefix}_annual"
        ev = st.dataframe(
            style_heat_v8(annual, focus),
            width="stretch",
            height=compact_height(len(annual)),
            on_select="rerun",
            selection_mode="single-cell",
            key=annual_key,
        )
        handle_table_focus(ev, annual, focus_key, annual_key)
    with c2:
        st.markdown("#### Gesamtperformance")
        total_key = f"{key_prefix}_total"
        ev = st.dataframe(
            style_heat_v8(total, focus),
            width="stretch",
            height=compact_height(len(total)),
            on_select="rerun",
            selection_mode="single-cell",
            key=total_key,
        )
        handle_table_focus(ev, total, focus_key, total_key)


@st.dialog("ETFs des Index", width="large")
def etf_dialog(index_name):
    sub = registry[registry["index_name"] == index_name].sort_values("inception").copy()
    if sub.empty:
        st.info("Keine ETFs hinterlegt.")
        return
    top, status_col = st.columns([.64, .36])
    with top:
        st.markdown(f"### {index_name}")
    status = status_col.empty()
    bar = status_col.progress(0)

    table = sub.copy()
    table["Auflage"] = table["inception"].map(fmt_date)
    table["Mitglieder"] = INDEX_INFO[index_name]["members"]
    table["JustETF"] = table["isin"].map(
        lambda x: f"https://www.justetf.com/de/etf-profile.html?isin={x}"
    )
    show = table[["etf_name", "isin", "Auflage", "Mitglieder", "ter", "distribution", "JustETF"]].rename(
        columns={
            "etf_name": "ETF",
            "isin": "ISIN",
            "ter": "TER",
            "distribution": "Ertragsverwendung",
        }
    )
    st.dataframe(
        show.style.set_properties(**{"color": "#111827", "background-color": "#fff"}).format({"TER": "{:.2f}%"}),
        width="stretch",
        height=compact_height(len(show)),
        hide_index=True,
        column_config={"JustETF": st.column_config.LinkColumn("Link", display_text="Öffnen")},
    )

    resolved, warnings = [], []
    names = sub["etf_name"].tolist()
    cache = _session_cache("v8_etf_data")
    done = sum((index_name, name) in cache for name in names)
    update_status(status, bar, done, len(names), "ETF-Daten geladen")
    for name in names:
        if (index_name, name) not in cache:
            session_etf(index_name, name)
            done += 1
            update_status(status, bar, done, len(names), "ETF-Daten geladen")
        rr, ww = cache[(index_name, name)]
        resolved += rr
        warnings += ww
    update_status(status, bar, len(names), len(names), "ETF-Daten geladen")
    for warning in warnings:
        st.warning(warning)
    if resolved:
        render_outputs_v8(
            resolved,
            f"dlg_{abs(hash(index_name))}",
            f"dlg_focus_{abs(hash(index_name))}",
        )


def parse_share_classes_v8(value):
    out = []
    for x in [s.strip() for s in str(value).split(",") if s.strip()]:
        out.append(
            "Auslandslistings / ADRs"
            if x in {"ADRs", "Foreign listings", "Auslandslistings"}
            else x
        )
    return frozenset(out)


def tech_category(title, rows, key, offset=0):
    items = rows["etf_name"].tolist()
    selected = ensure_selected(key, items)
    with st.expander(title, expanded=False):
        all_active = len(selected) == len(items)
        _, bulk = st.columns([.88, .12])
        with bulk:
            if st.button(
                "✓" if all_active else "+",
                key=f"techbulk_{key}",
                help="Kategorie vollständig auswählen/abwählen",
                use_container_width=True,
            ):
                st.session_state[key] = [] if all_active else items.copy()
                st.rerun()
        for j, (_, row) in enumerate(rows.iterrows()):
            name = row["etf_name"]
            active = name in selected
            proxy = MARKET_PROXY_BY_SIGNATURE.get(
                parse_share_classes_v8(row["share_classes"]), "–"
            )
            with st.container(border=True):
                label = f"{'✓  ' if active else ''}{dot_for(offset + j)}  {name}"
                if st.button(
                    label,
                    key=f"techbtn_{key}_{name}",
                    type="secondary",
                    use_container_width=True,
                ):
                    toggle_selected(key, name, items)
                st.markdown(
                    f"• **Index:** {row['index_name']}  \n"
                    f"• **Aktienklassen:** {row['share_classes']}  \n"
                    f"• **Mitglieder:** {row['members']}  \n"
                    f"• **Market Proxy (Benchmark für IR/TE):** {proxy}  \n"
                    f"• **TER:** {row['ter']:.2f}%"
                )
                st.link_button("ETF-Link", row["source_url"], use_container_width=True)
    return list(ensure_selected(key, items))


def render_tech(status_host):
    tech = tech_registry_cached().copy()
    selected = []
    all_rows = tech[tech["universe"] == "All Shares"]
    if not all_rows.empty:
        selected += tech_category("All Shares", all_rows, "t_all", 0)
    left, right = st.columns(2, gap="large")
    on_rows = tech[tech["universe"] == "Onshore"]
    off_rows = tech[tech["universe"] == "Offshore"]
    with left:
        if not on_rows.empty:
            selected += tech_category("Onshore", on_rows, "t_on", len(all_rows))
    with right:
        if not off_rows.empty:
            selected += tech_category(
                "Offshore", off_rows, "t_off", len(all_rows) + len(on_rows)
            )

    if not selected:
        st.info("Tech-ETFs auswählen.")
        return

    cache = _session_cache("v8_tech_data")
    txt = status_host.empty()
    bar = status_host.progress(0)
    done = sum(name in cache for name in selected)
    update_status(txt, bar, done, len(selected))
    for name in selected:
        if name not in cache:
            session_tech(name)
            done += 1
            update_status(txt, bar, done, len(selected))

    resolved, warnings = [], []
    for name in selected:
        rr, ww = cache[name]
        resolved += rr
        warnings += ww
    update_status(txt, bar, len(selected), len(selected))
    for warning in warnings:
        st.warning(warning)
    if not resolved:
        return

    meta = tech.set_index("etf_name")
    bmap, bseries = {}, {}
    for item in resolved:
        if item.etf_name not in meta.index:
            continue
        proxy = MARKET_PROXY_BY_SIGNATURE.get(
            parse_share_classes_v8(meta.loc[item.etf_name, "share_classes"])
        )
        if not proxy:
            continue
        bench, err = session_index(proxy)
        if bench is None:
            continue
        bcol = f"__BENCH__{item.label}"
        bmap[item.label] = bcol
        bseries[bcol] = bench.series_eur
    render_outputs_v8(resolved, "tech", "tech_focus", bmap, bseries)


# ----- page -----
st.title("China ETF Dashboard")
nav, status_col = st.columns([.58, .42], vertical_alignment="center")
with nav:
    page = st.segmented_control(
        "Bereich",
        ["Market ETFs vergleichen", "Tech ETFs vergleichen"],
        selection_mode="single",
        default=st.session_state.get("page", "Market ETFs vergleichen"),
        key="v8_page_direct",
        label_visibility="collapsed",
    ) or "Market ETFs vergleichen"

if page == "Market ETFs vergleichen":
    selected, dialog = market_tree()
    txt = status_col.empty()
    bar = status_col.progress(0)
    cache = _session_cache("v8_index_data")
    done = sum(name in cache for name in selected)
    update_status(txt, bar, done, len(selected))
    for name in selected:
        if name not in cache:
            session_index(name)
            done += 1
            update_status(txt, bar, done, len(selected))

    resolved, warnings = [], []
    for name in selected:
        item, err = cache[name]
        if item is not None:
            resolved.append(item)
        if err:
            warnings.append(f"{name}: {err}")
    update_status(txt, bar, len(selected), len(selected))
    for warning in warnings:
        st.warning(warning)
    render_outputs_v8(resolved, "market", "market_focus")
    if dialog:
        etf_dialog(dialog)
else:
    render_tech(status_col)

with st.expander("Zusätzliche Einstellungen"):
    st.toggle("Nach Kapitalertragsteuer (vereinfacht)", key="after_tax")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.number_input(
            "Kapitalertragsteuer", 0.0, 1.0, step=.0025, format="%.4f", key="base_rate"
        )
    with c2:
        st.number_input(
            "Solidaritätszuschlag auf Steuer", 0.0, .2, step=.005, format="%.3f", key="soli"
        )
    with c3:
        st.number_input(
            "Teilfreistellung Aktienfonds", 0.0, 1.0, step=.05, format="%.2f", key="teilfreistellung"
        )
