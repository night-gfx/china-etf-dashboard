from pathlib import Path
import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

from src.data import download_adjusted_close, detect_currency, convert_to_eur

# Stable definitions, metadata and cached resolvers from v5.
# This is a normal executable app; no regex/source patching is used.
_base = Path(__file__).with_name("app_v5.py").read_text(encoding="utf-8")
_prefix = _base.split("registry=registry_cached()", 1)[0]
exec(compile(_prefix, "app_v5_core", "exec"), globals(), globals())

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
    div[data-testid="stButton"] > button[kind="primary"] p,
    button[data-testid="stBaseButton-primary"] p {
      font-weight: 800 !important;
    }
    div[data-testid="stButton"] > button[kind="secondary"] p,
    button[data-testid="stBaseButton-secondary"] p {
      font-weight: 400 !important;
    }
    div[data-testid="stButton"] > button[kind="primary"],
    button[data-testid="stBaseButton-primary"] {
      background: #ffffff !important;
      color: #111827 !important;
      border-color: #6b7280 !important;
    }
    [data-testid="stDataFrame"] * { color:#111827 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

# No legend and no multi-series unified hover box.
def base_layout(showlegend=False):
    return dict(
        showlegend=False,
        hovermode="closest",
        clickmode="event+select",
        dragmode="zoom",
        height=520,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#111827"),
        margin=dict(l=50, r=18, t=18, b=45),
        xaxis=dict(showgrid=False, zeroline=False, autorange=True),
    )


def line_fig(frame, colors, focus=None, dd=False, benchmark_map=None):
    fig = go.Figure()
    for col in frame.columns:
        if col.startswith("__BENCH__"):
            continue
        s = frame[col].dropna()
        y = (s / s.cummax() - 1) * 100 if dd else s
        width = 4.5 if col == focus else 1.8
        fig.add_trace(
            go.Scatter(
                x=y.index,
                y=y,
                mode="lines+markers",
                name=col,
                line=dict(width=width, color=colors.get(col)),
                marker=dict(size=8, opacity=0.01),
                selected=dict(marker=dict(opacity=0.01)),
                unselected=dict(marker=dict(opacity=0.01)),
                customdata=[col] * len(y),
                hovertemplate=(
                    "%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra></extra>"
                    if dd else
                    "%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra></extra>"
                ),
            )
        )
        if benchmark_map and col in benchmark_map and benchmark_map[col] in frame.columns:
            b = frame[benchmark_map[col]].dropna()
            by = (b / b.cummax() - 1) * 100 if dd else b
            fig.add_trace(
                go.Scatter(
                    x=by.index,
                    y=by,
                    mode="lines",
                    name="Market Proxy",
                    line=dict(width=2, color=colors.get(col), dash="dash"),
                    hovertemplate=(
                        "%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra>Market Proxy</extra>"
                        if dd else
                        "%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>Market Proxy</extra>"
                    ),
                )
            )
    layout = base_layout(False)
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        autorange=True,
        type="linear" if dd else "log",
        title="Drawdown in %" if dd else "Indexiert (log)",
    )
    fig.update_layout(**layout)
    return fig


def style_heat(df, focus=None):
    pct_cols = {
        "CAGR p.a.", "Volatilität p.a.", "Max. Drawdown",
        "Tracking Error p.a."
    }
    ratio_cols = {
        "Sharpe Ratio", "Sortino", "Calmar", "Information Ratio p.a."
    }
    formats = {
        c: (lambda x: "–" if pd.isna(x) else f"{x:.2%}")
        for c in df.columns if c in pct_cols
    }
    formats.update({
        c: (lambda x: "–" if pd.isna(x) else f"{x:.2f}")
        for c in df.columns if c in ratio_cols or str(c).isdigit()
    })
    sty = df.style.format(formats, na_rep="–").set_properties(
        **{"color": "#111827", "background-color": "#ffffff"}
    )
    for column in df.select_dtypes(include="number").columns:
        values = pd.to_numeric(df[column], errors="coerce")
        valid = values.dropna()
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


def color_dot(i):
    return ["🔵", "🔴", "🟢", "🟣", "🟠", "🟦", "🟥", "🟩", "🟪", "🟧"][i % 10]


def _cache(name):
    if name not in st.session_state:
        st.session_state[name] = {}
    return st.session_state[name]


def session_index(name):
    cache = _cache("v9_index_data")
    if name not in cache:
        try:
            cache[name] = (resolve_index_cached(name), None)
        except Exception as exc:
            cache[name] = (None, str(exc))
    return cache[name]


def session_tech(name):
    cache = _cache("v9_tech_data")
    if name not in cache:
        cache[name] = resolve_tech_cached((name,))
    return cache[name]


def session_etf(index_name, etf_name):
    cache = _cache("v9_etf_data")
    key = (index_name, etf_name)
    if key not in cache:
        cache[key] = resolve_rows_cached(index_name, (etf_name,))
    return cache[key]


def status_text(host, done, total, label="Marktdaten geladen"):
    pct = 100 if total == 0 else round(done / total * 100)
    host.markdown(f"**{label} — {pct} %**")


def ensure_selected(key, items):
    if key not in st.session_state:
        st.session_state[key] = items.copy()
    st.session_state[key] = [x for x in st.session_state[key] if x in items]
    return st.session_state[key]


def toggle_selected(key, item, items):
    selected = list(ensure_selected(key, items))
    if item in selected:
        selected.remove(item)
    else:
        selected.append(item)
    st.session_state[key] = selected
    st.rerun()


def toggle_category(key, items):
    selected = ensure_selected(key, items)
    st.session_state[key] = [] if len(selected) == len(items) else items.copy()
    st.rerun()


def toggle_focus(name, focus_key):
    st.session_state[focus_key] = (
        None if st.session_state.get(focus_key) == name else name
    )


def handle_plot_focus(event, display, focus_key, widget_key):
    try:
        points = event.selection.points
    except Exception:
        return
    state_key = f"{widget_key}_point_signature"
    if not points:
        return
    point = points[0]
    if not isinstance(point, dict):
        return
    col = point.get("customdata")
    if col not in display:
        return
    signature = (col, point.get("point_index"), str(point.get("x")))
    if st.session_state.get(state_key) == signature:
        return
    st.session_state[state_key] = signature
    toggle_focus(display[col], focus_key)
    st.rerun()


def handle_table_focus(event, df, focus_key, widget_key):
    try:
        cells = event.selection.cells
    except Exception:
        return
    if not cells:
        return
    cell = cells[0]
    if isinstance(cell, dict):
        row_idx = cell.get("row")
        column = cell.get("column")
    elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
        row_idx, column = cell[0], cell[1]
    else:
        return
    if row_idx is None or not 0 <= int(row_idx) < len(df):
        return
    signature = (int(row_idx), str(column))
    state_key = f"{widget_key}_cell_signature"
    if st.session_state.get(state_key) == signature:
        return
    st.session_state[state_key] = signature
    toggle_focus(df.index[int(row_idx)], focus_key)
    st.rerun()


registry = registry_cached()
index_order = (
    registry[["index_order", "index_name"]]
    .drop_duplicates()
    .sort_values("index_order")["index_name"]
    .tolist()
)
INDEX_COLOR = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(index_order)}
INDEX_DOT = {name: color_dot(i) for i, name in enumerate(index_order)}


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
    all_active = len(selected) == len(items)
    header, bulk = st.columns([.90, .10], vertical_alignment="center")
    with header:
        expander = st.expander(title, expanded=False)
    with bulk:
        if st.button(
            "Alle",
            key=f"bulk_{key}",
            type="primary" if all_active else "secondary",
            help="Gesamte Kategorie auswählen/abwählen",
            use_container_width=True,
        ):
            toggle_category(key, items)

    dialog = None
    with expander:
        for name in items:
            active = name in selected
            with st.container(border=True):
                label = f"{INDEX_DOT[name]}  {name}"
                if st.button(
                    label,
                    key=f"sel_{key}_{name}",
                    type="primary" if active else "secondary",
                    use_container_width=True,
                ):
                    toggle_selected(key, name, items)
                index_details(name)
                left, right = st.columns(2, gap="small")
                with left:
                    st.link_button(
                        "Methodology",
                        INDEX_INFO[name]["url"],
                        use_container_width=True,
                    )
                with right:
                    if st.button(
                        "ETF-Vergleich",
                        key=f"etf_{key}_{name}",
                        use_container_width=True,
                    ):
                        dialog = name
    return list(ensure_selected(key, items)), dialog


def market_tree():
    all_shares = [x for x in index_order if INDEX_SCOPE[x] == "All Shares"]
    onshore = [x for x in index_order if INDEX_SCOPE[x] == "Onshore"]
    offshore = [x for x in index_order if INDEX_SCOPE[x] == "Offshore"]

    selected = []
    dialog = None
    s, d = market_category("All Shares", all_shares, "m_all")
    selected += s
    dialog = dialog or d

    left, right = st.columns(2, gap="large")
    with left:
        s, d = market_category("Onshore", onshore, "m_on")
        selected += s
        dialog = dialog or d
    with right:
        s, d = market_category("Offshore", offshore, "m_off")
        selected += s
        dialog = dialog or d
    return selected, dialog


def render_outputs(resolved, key_prefix, focus_key, benchmark_map=None, benchmark_series=None):
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
            if key_prefix == "market"
            else PALETTE[i % len(PALETTE)]
        )
        for i, x in enumerate(resolved)
    }

    if benchmark_map and benchmark_series:
        for _, benchmark_col in benchmark_map.items():
            if benchmark_col in benchmark_series:
                series[benchmark_col] = benchmark_series[benchmark_col]

    frame = common_frame(series)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum.")
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
    if (
        not pair
        or any(x not in corr_frame.columns for x in pair)
        or pair[0] == pair[1]
    ):
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
            points = event.selection.points
            if points:
                custom = points[0].get("customdata")
                if custom and "|||" in custom:
                    selected_pair = tuple(custom.split("|||", 1))
                    if selected_pair[0] != selected_pair[1]:
                        st.session_state[pair_key] = selected_pair
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
    benchmark_stats = {}
    if benchmark_map:
        benchmark_stats = {
            label: frame[benchmark_col]
            for label, benchmark_col in benchmark_map.items()
            if label in corr_frame.columns and benchmark_col in frame.columns
        }
    total = total_stats(
        corr_frame,
        display,
        benchmark_stats if benchmark_map else None,
    )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        key = f"{key_prefix}_annual"
        event = st.dataframe(
            style_heat(annual, focus),
            width="stretch",
            height=compact_height(len(annual)),
            on_select="rerun",
            selection_mode="single-cell",
            key=key,
        )
        handle_table_focus(event, annual, focus_key, key)

    with c2:
        st.markdown("#### Gesamtperformance")
        key = f"{key_prefix}_total"
        event = st.dataframe(
            style_heat(total, focus),
            width="stretch",
            height=compact_height(len(total)),
            on_select="rerun",
            selection_mode="single-cell",
            key=key,
        )
        handle_table_focus(event, total, focus_key, key)


@st.dialog("ETFs des Index", width="large")
def etf_dialog(index_name):
    sub = registry[registry["index_name"] == index_name].sort_values("inception").copy()
    if sub.empty:
        st.info("Keine ETFs hinterlegt.")
        return

    top, status_col = st.columns([.68, .32])
    with top:
        st.markdown(f"### {index_name}")
    status = status_col.empty()
    progress = status_col.progress(0)

    table = sub.copy()
    table["Auflage"] = table["inception"].map(fmt_date)
    table["Mitglieder"] = INDEX_INFO[index_name]["members"]
    table["JustETF"] = table["isin"].map(
        lambda x: f"https://www.justetf.com/de/etf-profile.html?isin={x}"
    )
    show = table[
        ["etf_name", "isin", "Auflage", "Mitglieder", "ter", "distribution", "JustETF"]
    ].rename(
        columns={
            "etf_name": "ETF",
            "isin": "ISIN",
            "ter": "TER",
            "distribution": "Ertragsverwendung",
        }
    )
    st.dataframe(
        show.style.set_properties(
            **{"color": "#111827", "background-color": "#fff"}
        ).format({"TER": "{:.2f}%"}),
        width="stretch",
        height=compact_height(len(show)),
        hide_index=True,
        column_config={
            "JustETF": st.column_config.LinkColumn("Link", display_text="Öffnen")
        },
    )

    cache = _cache("v9_etf_data")
    names = sub["etf_name"].tolist()
    resolved, warnings = [], []
    done = sum((index_name, name) in cache for name in names)
    status_text(status, done, len(names), "ETF-Daten geladen")
    progress.progress(100 if not names else round(done / len(names) * 100))

    for name in names:
        if (index_name, name) not in cache:
            session_etf(index_name, name)
            done += 1
            status_text(status, done, len(names), "ETF-Daten geladen")
            progress.progress(round(done / len(names) * 100))
        rows, row_warnings = cache[(index_name, name)]
        resolved += rows
        warnings += row_warnings

    for warning in warnings:
        st.warning(warning)
    if resolved:
        render_outputs(
            resolved,
            f"dlg_{abs(hash(index_name))}",
            f"dlg_focus_{abs(hash(index_name))}",
        )


def parse_share_classes(value):
    result = []
    for item in [x.strip() for x in str(value).split(",") if x.strip()]:
        result.append(
            "Auslandslistings / ADRs"
            if item in {"ADRs", "Foreign listings", "Auslandslistings"}
            else item
        )
    return frozenset(result)


def tech_category(title, rows, key, offset=0):
    items = rows["etf_name"].tolist()
    selected = ensure_selected(key, items)
    all_active = len(selected) == len(items)

    header, bulk = st.columns([.90, .10], vertical_alignment="center")
    with header:
        expander = st.expander(title, expanded=False)
    with bulk:
        if st.button(
            "Alle",
            key=f"tech_bulk_{key}",
            type="primary" if all_active else "secondary",
            help="Gesamte Kategorie auswählen/abwählen",
            use_container_width=True,
        ):
            toggle_category(key, items)

    with expander:
        for j, (_, row) in enumerate(rows.iterrows()):
            name = row["etf_name"]
            active = name in selected
            proxy = MARKET_PROXY_BY_SIGNATURE.get(
                parse_share_classes(row["share_classes"]), "–"
            )
            with st.container(border=True):
                if st.button(
                    f"{color_dot(offset + j)}  {name}",
                    key=f"tech_{key}_{name}",
                    type="primary" if active else "secondary",
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
                st.link_button(
                    "ETF / Methodology",
                    row["source_url"],
                    use_container_width=True,
                )
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
                "Offshore",
                off_rows,
                "t_off",
                len(all_rows) + len(on_rows),
            )

    if not selected:
        st.info("Tech-ETFs auswählen.")
        return

    cache = _cache("v9_tech_data")
    status = status_host.empty()
    progress = status_host.progress(0)
    done = sum(name in cache for name in selected)
    status_text(status, done, len(selected))
    progress.progress(round(done / len(selected) * 100))

    for name in selected:
        if name not in cache:
            session_tech(name)
            done += 1
            status_text(status, done, len(selected))
            progress.progress(round(done / len(selected) * 100))

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
        proxy = MARKET_PROXY_BY_SIGNATURE.get(
            parse_share_classes(meta.loc[item.etf_name, "share_classes"])
        )
        if not proxy:
            continue
        benchmark, error = session_index(proxy)
        if benchmark is None:
            continue
        benchmark_col = f"__BENCH__{item.label}"
        benchmark_map[item.label] = benchmark_col
        benchmark_series[benchmark_col] = benchmark.series_eur

    render_outputs(
        resolved,
        "tech",
        "tech_focus",
        benchmark_map,
        benchmark_series,
    )


# ---------- Asset Allocation Backtesting ----------

@st.cache_data(ttl=60 * 60, show_spinner=False)
def yahoo_search(query):
    query = str(query or "").strip()
    if not query:
        return []
    results = []
    try:
        search = yf.Search(query, max_results=10)
        for item in (getattr(search, "quotes", None) or []):
            symbol = str(item.get("symbol") or "").strip()
            if not symbol:
                continue
            quote_type = str(item.get("quoteType") or item.get("typeDisp") or "")
            if quote_type.upper() not in {
                "EQUITY", "ETF", "MUTUALFUND", "INDEX", "CRYPTOCURRENCY"
            }:
                continue
            name = (
                item.get("longname")
                or item.get("shortname")
                or item.get("name")
                or symbol
            )
            exchange = item.get("exchange") or item.get("exchDisp") or ""
            results.append(
                {
                    "symbol": symbol,
                    "name": str(name),
                    "exchange": str(exchange),
                    "type": quote_type,
                }
            )
    except Exception:
        pass

    if not results:
        results.append(
            {"symbol": query.upper(), "name": query, "exchange": "", "type": "Direkteingabe"}
        )
    seen = set()
    unique = []
    for item in results:
        if item["symbol"] in seen:
            continue
        seen.add(item["symbol"])
        unique.append(item)
    return unique[:10]


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def asset_series_eur(symbol):
    prices = download_adjusted_close(symbol, start="2000-01-01")
    if len(prices) < 30:
        raise RuntimeError(f"{symbol}: zu wenig Kursdaten")
    currency = detect_currency(symbol, "EUR")
    eur, detected = convert_to_eur(prices, currency)
    if len(eur) < 30:
        raise RuntimeError(f"{symbol}: zu wenig EUR-Daten")
    return eur.rename(symbol), detected


def _aa_assets():
    if "aa_assets" not in st.session_state:
        st.session_state.aa_assets = []
    return st.session_state.aa_assets


def add_asset(result):
    assets = _aa_assets()
    if any(x["symbol"] == result["symbol"] for x in assets):
        return
    assets.append(
        {
            "symbol": result["symbol"],
            "name": result["name"],
            "weight": 0.0,
        }
    )
    equal = 100.0 / len(assets)
    for asset in assets:
        asset["weight"] = equal


def remove_asset(symbol):
    assets = _aa_assets()
    st.session_state.aa_assets = [x for x in assets if x["symbol"] != symbol]
    assets = st.session_state.aa_assets
    if assets:
        equal = 100.0 / len(assets)
        for asset in assets:
            asset["weight"] = equal


def rebalance_key(date, frequency):
    if frequency == "Monatlich":
        return (date.year, date.month)
    if frequency == "Quartalsweise":
        return (date.year, (date.month - 1) // 3)
    if frequency == "Halbjährlich":
        return (date.year, (date.month - 1) // 6)
    if frequency == "Jährlich":
        return (date.year,)
    return None


def backtest_portfolio(prices, weights, frequency):
    returns = prices.pct_change(fill_method=None).fillna(0.0)
    weights = np.asarray(weights, dtype=float)
    weights = weights / weights.sum()
    values = weights.copy()
    output = []
    last_key = None

    for date, row in returns.iterrows():
        key = rebalance_key(pd.Timestamp(date), frequency)
        if (
            frequency != "Kein Rebalancing"
            and key != last_key
            and len(output) > 0
        ):
            total = float(values.sum())
            values = total * weights
        values = values * (1.0 + row.to_numpy(dtype=float))
        output.append(float(values.sum()))
        last_key = key

    return pd.Series(output, index=returns.index, name="Portfolio") * 100.0


def backtest_metrics(series):
    series = series.dropna()
    if len(series) < 2:
        return {}
    returns = series.pct_change(fill_method=None).dropna()
    cg = cagr(series)
    vola = returns.std(ddof=1) * math.sqrt(252) if len(returns) > 1 else np.nan
    shp = (
        returns.mean() / returns.std(ddof=1) * math.sqrt(252)
        if len(returns) > 1 and returns.std(ddof=1) != 0
        else np.nan
    )
    dd = max_drawdown(series)
    srt = sortino(series, 0.0)
    calmar = cg / abs(dd) if dd and not np.isnan(dd) else np.nan
    return {
        "CAGR p.a.": cg,
        "Volatilität p.a.": vola,
        "Sharpe Ratio": shp,
        "Max. Drawdown": dd,
        "Sortino": srt,
        "Calmar": calmar,
    }


def render_asset_allocation_tool():
    st.title("Asset Allocation Backtesting Tool")
    st.caption(
        "Freie Wertpapiersuche über Yahoo Finance. Name, Ticker oder ISIN eingeben; "
        "bei nicht eindeutig auflösbaren ISINs funktioniert der Yahoo-Ticker am zuverlässigsten."
    )

    st.markdown("### Wertpapier hinzufügen")
    query = st.text_input(
        "Name, Ticker oder ISIN",
        key="aa_search_query",
        placeholder="z. B. Apple, AAPL oder US0378331005",
    )
    results = yahoo_search(query) if query else []
    if results:
        labels = [
            f"{x['name']} · {x['symbol']}"
            + (f" · {x['exchange']}" if x["exchange"] else "")
            for x in results
        ]
        selected_label = st.selectbox(
            "Suchergebnis",
            labels,
            key="aa_search_result",
        )
        selected_result = results[labels.index(selected_label)]
        add_col, benchmark_col = st.columns(2)
        with add_col:
            if st.button("Zum Portfolio hinzufügen", use_container_width=True):
                add_asset(selected_result)
                st.rerun()
        with benchmark_col:
            if st.button("Als Benchmark verwenden", use_container_width=True):
                st.session_state.aa_benchmark = selected_result
                st.rerun()

    assets = _aa_assets()
    if assets:
        st.markdown("### Portfolio")
        for i, asset in enumerate(list(assets)):
            c1, c2, c3 = st.columns([.54, .28, .18], vertical_alignment="center")
            with c1:
                st.markdown(f"**{asset['name']}**  \n`{asset['symbol']}`")
            with c2:
                new_weight = st.number_input(
                    "Gewicht %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(asset["weight"]),
                    step=1.0,
                    key=f"aa_weight_{asset['symbol']}",
                )
                asset["weight"] = float(new_weight)
            with c3:
                if st.button(
                    "Entfernen",
                    key=f"aa_remove_{asset['symbol']}",
                    use_container_width=True,
                ):
                    remove_asset(asset["symbol"])
                    st.rerun()

        total_weight = sum(x["weight"] for x in assets)
        st.caption(f"Summe Gewichte: {total_weight:.2f} %")
    else:
        st.info("Noch keine Wertpapiere im Portfolio.")

    benchmark = st.session_state.get("aa_benchmark")
    if benchmark:
        st.markdown(
            f"**Benchmark:** {benchmark['name']} · `{benchmark['symbol']}`"
        )

    rebalance = st.selectbox(
        "Rebalancing",
        [
            "Monatlich",
            "Quartalsweise",
            "Halbjährlich",
            "Jährlich",
            "Kein Rebalancing",
        ],
        index=1,
        key="aa_rebalance",
    )

    if st.button("Backtest starten", type="primary", use_container_width=True):
        if not assets:
            st.error("Mindestens ein Wertpapier hinzufügen.")
            return
        if not benchmark:
            st.error("Bitte eine Benchmark auswählen.")
            return
        weights = np.array([x["weight"] for x in assets], dtype=float)
        if weights.sum() <= 0:
            st.error("Die Summe der Gewichte muss größer als 0 sein.")
            return

        price_series = {}
        errors = []
        with st.spinner("Kursdaten werden geladen …"):
            for asset in assets:
                try:
                    series, _ = asset_series_eur(asset["symbol"])
                    price_series[asset["symbol"]] = series
                except Exception as exc:
                    errors.append(str(exc))
            try:
                benchmark_series, _ = asset_series_eur(benchmark["symbol"])
            except Exception as exc:
                benchmark_series = None
                errors.append(f"Benchmark: {exc}")

        if errors:
            for error in errors:
                st.warning(error)
        if len(price_series) != len(assets) or benchmark_series is None:
            st.error("Backtest konnte nicht vollständig geladen werden.")
            return

        prices = pd.concat(price_series, axis=1).dropna()
        benchmark_series = benchmark_series.reindex(prices.index).dropna()
        common_index = prices.index.intersection(benchmark_series.index)
        prices = prices.loc[common_index]
        benchmark_series = benchmark_series.loc[common_index]
        if len(prices) < 30:
            st.error("Zu wenig gemeinsamer Datenzeitraum.")
            return

        portfolio = backtest_portfolio(
            prices,
            weights,
            rebalance,
        )
        benchmark_indexed = benchmark_series / benchmark_series.iloc[0] * 100.0

        comparison = pd.concat(
            [portfolio.rename("Portfolio"), benchmark_indexed.rename("Benchmark")],
            axis=1,
        ).dropna()

        perf = go.Figure()
        perf.add_trace(
            go.Scatter(
                x=comparison.index,
                y=comparison["Portfolio"],
                mode="lines",
                name="Portfolio",
                line=dict(width=2.8),
            )
        )
        perf.add_trace(
            go.Scatter(
                x=comparison.index,
                y=comparison["Benchmark"],
                mode="lines",
                name="Benchmark",
                line=dict(width=2.0, dash="dash"),
            )
        )
        layout = base_layout(True)
        layout["showlegend"] = True
        layout["yaxis"] = dict(showgrid=False, type="log", title="Indexiert (log)")
        perf.update_layout(**layout)

        dd = comparison / comparison.cummax() - 1.0
        dd_fig = go.Figure()
        for col in dd.columns:
            dd_fig.add_trace(
                go.Scatter(
                    x=dd.index,
                    y=dd[col] * 100,
                    mode="lines",
                    name=col,
                    line=dict(width=2.5 if col == "Portfolio" else 2.0,
                              dash="dash" if col == "Benchmark" else "solid"),
                )
            )
        dd_layout = base_layout(True)
        dd_layout["showlegend"] = True
        dd_layout["yaxis"] = dict(showgrid=False, title="Drawdown in %")
        dd_fig.update_layout(**dd_layout)

        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown("#### Wertentwicklung")
            st.plotly_chart(
                perf,
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
            )
        with c2:
            st.markdown("#### Drawdown")
            st.plotly_chart(
                dd_fig,
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
            )

        stats = pd.DataFrame(
            {
                "Portfolio": backtest_metrics(comparison["Portfolio"]),
                "Benchmark": backtest_metrics(comparison["Benchmark"]),
            }
        ).T
        st.markdown("#### Kennzahlen")
        st.dataframe(
            style_heat(stats),
            width="stretch",
            height=compact_height(len(stats)),
        )

        weights_display = pd.DataFrame(
            {
                "Wertpapier": [x["name"] for x in assets],
                "Ticker": [x["symbol"] for x in assets],
                "Gewicht": weights / weights.sum(),
            }
        )
        st.markdown("#### Backtest-Konfiguration")
        st.dataframe(
            weights_display.style.format({"Gewicht": "{:.2%}"}),
            width="stretch",
            hide_index=True,
            height=compact_height(len(weights_display)),
        )
        st.caption(
            f"Rebalancing: {rebalance} · Zeitraum: "
            f"{comparison.index.min():%d.%m.%Y} – {comparison.index.max():%d.%m.%Y}"
        )


def render_china_dashboard():
    st.title("China ETF Dashboard")
    nav, status_col = st.columns([.58, .42], vertical_alignment="center")
    with nav:
        page = st.segmented_control(
            "Bereich",
            ["Market ETFs vergleichen", "Tech ETFs vergleichen"],
            selection_mode="single",
            default=st.session_state.get("china_page", "Market ETFs vergleichen"),
            key="china_subpage",
            label_visibility="collapsed",
        ) or "Market ETFs vergleichen"
        st.session_state.china_page = page

    if page == "Market ETFs vergleichen":
        selected, dialog = market_tree()
        status = status_col.empty()
        progress = status_col.progress(0)
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


# ---------- top-level app ----------
top_page = st.segmented_control(
    "App",
    ["China ETF Dashboard", "Asset Allocation Backtesting Tool"],
    selection_mode="single",
    default=st.session_state.get("top_page", "China ETF Dashboard"),
    key="top_page_selector",
    label_visibility="collapsed",
) or "China ETF Dashboard"
st.session_state.top_page = top_page

# Tax settings intentionally removed from the UI. Keep the same default tax
# treatment for all China ETF comparisons.
st.session_state.after_tax = True

if top_page == "China ETF Dashboard":
    render_china_dashboard()
else:
    render_asset_allocation_tool()
