from pathlib import Path
from urllib.parse import quote, unquote
import html

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

# Load the stable v9 implementation without executing its top-level page switch.
_source = Path(__file__).with_name("app_v9_direct.py").read_text(encoding="utf-8")
_core = _source.split("# ---------- top-level app ----------", 1)[0]
exec(compile(_core, "app_v9_core", "exec"), globals(), globals())

st.markdown(
    """
    <style>
    .block-container { padding-top:.7rem !important; }
    div[data-testid="stRadio"] [role="radiogroup"] {
      display:flex !important; gap:1.7rem !important; flex-wrap:wrap !important;
      border-bottom:1px solid #e5e7eb !important; margin-bottom:.45rem !important;
    }
    div[data-testid="stRadio"] label {
      background:transparent !important; border:none !important; border-radius:0 !important;
      padding:.55rem .05rem .45rem .05rem !important; margin:0 !important; white-space:nowrap !important;
    }
    div[data-testid="stRadio"] label:has(input:checked) { border-bottom:2px solid #111827 !important; }
    div[data-testid="stRadio"] label:has(input:checked) p { font-weight:700 !important; color:#111827 !important; }
    div[data-testid="stRadio"] input { display:none !important; }
    [data-testid="stDataFrame"] input[type="checkbox"],
    [data-testid="stDataFrame"] [role="checkbox"] { display:none !important; }
    .selector-box {
      display:block; width:100%; box-sizing:border-box; padding:.58rem .72rem;
      margin:.05rem 0 .45rem 0; border-radius:.58rem; text-decoration:none !important;
      line-height:1.25;
    }
    .selector-box:hover { filter:brightness(.98); }
    .meta-line { color:#4b5563; font-size:.82rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


def base_layout(showlegend=False):
    return dict(
        showlegend=showlegend, hovermode="closest", clickmode="event+select",
        dragmode="zoom", height=520, plot_bgcolor="white", paper_bgcolor="white",
        font=dict(color="#111827"), margin=dict(l=50, r=18, t=18, b=45),
        xaxis=dict(showgrid=False, zeroline=False, autorange=True),
    )


def line_fig(frame, colors, focus=None, dd=False, benchmark_map=None):
    fig = go.Figure()
    for col in frame.columns:
        if col.startswith("__BENCH__"):
            continue
        s = frame[col].dropna()
        y = (s / s.cummax() - 1) * 100 if dd else s
        focused = focus == col
        fig.add_trace(go.Scatter(
            x=y.index, y=y, mode="lines+markers", name=col,
            line=dict(width=4.8 if focused else 1.8, color=colors.get(col)),
            opacity=1.0 if focus is None or focused else .55,
            marker=dict(size=18, opacity=.003),
            selected=dict(marker=dict(opacity=.003)), unselected=dict(marker=dict(opacity=.003)),
            customdata=[col] * len(y),
            hovertemplate=("%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra></extra>" if dd
                           else "%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra></extra>"),
        ))
        if benchmark_map and col in benchmark_map and benchmark_map[col] in frame.columns:
            b = frame[benchmark_map[col]].dropna()
            by = (b / b.cummax() - 1) * 100 if dd else b
            fig.add_trace(go.Scatter(
                x=by.index, y=by, mode="lines", name="Market Proxy",
                line=dict(width=2, color=colors.get(col), dash="dash"),
                opacity=1.0 if focus is None or focused else .35,
                hovertemplate=("%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra>Market Proxy</extra>" if dd
                               else "%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>Market Proxy</extra>"),
            ))
    layout = base_layout(False)
    layout["yaxis"] = dict(showgrid=False, zeroline=False, autorange=True,
                           type="linear" if dd else "log",
                           title="Drawdown in %" if dd else "Indexiert (log)")
    fig.update_layout(**layout)
    return fig


def _cell_color(value, lo, hi, reverse=False):
    if pd.isna(value):
        return "color:#111827;background-color:#fff"
    p = .5 if hi == lo else (float(value) - lo) / (hi - lo)
    if reverse:
        p = 1 - p
    if p <= .5:
        w, a, b = p * 2, (248, 190, 190), (255, 244, 176)
    else:
        w, a, b = (p - .5) * 2, (255, 244, 176), (183, 229, 190)
    rgb = tuple(round(x + (y - x) * w) for x, y in zip(a, b))
    return f"background-color:rgb{rgb};color:#111827"


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
        sty = sty.apply(lambda row: [
            "font-weight:800;border-top:2px solid #111827;border-bottom:2px solid #111827"
            if row.name == focus else "" for _ in row
        ], axis=1)
    return sty


def status_text(host, done, total, label="Marktdaten geladen"):
    pct = 100 if total == 0 else round(done / total * 100)
    host.markdown(f"{label} — ({pct} %)")


def hex_rgba(hex_color, alpha):
    value = hex_color.lstrip("#")
    r, g, b = int(value[:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    return f"rgba({r},{g},{b},{alpha})"


def selector_box(label, state_key, item, color, active):
    token = quote(f"{state_key}|||{item}", safe="")
    background = hex_rgba(color, .10) if active else "rgba(255,255,255,0)"
    weight = 700 if active else 400
    st.markdown(
        f'<a class="selector-box" href="?toggle={token}" target="_self" '
        f'style="border:1.5px solid {color};background:{background};color:{color};font-weight:{weight};">'
        f'{html.escape(str(label))}</a>',
        unsafe_allow_html=True,
    )


def process_toggle_query():
    token = st.query_params.get("toggle")
    if not token:
        return
    try:
        state_key, item = unquote(str(token)).split("|||", 1)
        current = list(st.session_state.get(state_key, []))
        if item in current:
            current.remove(item)
        else:
            current.append(item)
        st.session_state[state_key] = current
    except Exception:
        pass
    st.query_params.clear()
    st.rerun()


TECH_NAMES = tech_registry_cached()["etf_name"].drop_duplicates().tolist()
TECH_COLOR = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(TECH_NAMES)}
process_toggle_query()


def market_category(title, items, key):
    selected = ensure_selected(key, items)
    dialog = None
    with st.expander(title, expanded=False):
        for name in items:
            selector_box(name, key, name, INDEX_COLOR[name], name in selected)
            index_details(name)
            left, right = st.columns(2, gap="small")
            with left:
                st.link_button("Methodology", INDEX_INFO[name]["url"], use_container_width=True)
            with right:
                if st.button("ETF-Vergleich", key=f"etf_{key}_{name}", use_container_width=True):
                    dialog = name
            st.divider()
    return list(ensure_selected(key, items)), dialog


def tech_category(title, rows, key, offset=0):
    items = rows["etf_name"].tolist()
    selected = ensure_selected(key, items)
    with st.expander(title, expanded=False):
        for _, row in rows.iterrows():
            name = row["etf_name"]
            color = TECH_COLOR.get(name, "#6b7280")
            proxy = MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(row["share_classes"]), "–")
            selector_box(name, key, name, color, name in selected)
            st.markdown(
                f"• **Index:** {row['index_name']}  \n"
                f"• **Aktienklassen:** {row['share_classes']}  \n"
                f"• **Mitglieder:** {row['members']}  \n"
                f"• **Market Proxy (Benchmark für IR/TE):** {proxy}  \n"
                f"• **TER:** {row['ter']:.2f}%"
            )
            st.link_button("ETF / Methodology", row["source_url"], use_container_width=True)
            st.divider()
    return list(ensure_selected(key, items))


def handle_table_focus(event, df, focus_key):
    try:
        rows = event.selection.rows
    except Exception:
        return
    if not rows:
        return
    idx = int(rows[0])
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
        event = st.plotly_chart(line_fig(frame, colors, focus_col, False, benchmark_map),
                                width="stretch", config={"displaylogo":False,"scrollZoom":True},
                                key=key, on_select="rerun", selection_mode="points")
        handle_plot_focus(event, display, focus_key, key)
    with c2:
        st.markdown("#### Drawdown")
        key = f"{key_prefix}_dd"
        event = st.plotly_chart(line_fig(frame, colors, focus_col, True, benchmark_map),
                                width="stretch", config={"displaylogo":False,"scrollZoom":True},
                                key=key, on_select="rerun", selection_mode="points")
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
                             on_select="rerun", selection_mode="single-row",
                             key=f"{key_prefix}_annual_{abs(hash(focus or 'none'))}")
        handle_table_focus(event, annual, focus_key)
    with c2:
        st.markdown("#### Gesamtperformance")
        event = st.dataframe(style_heat(total, focus), width="stretch", height=compact_height(len(total)),
                             on_select="rerun", selection_mode="single-row",
                             key=f"{key_prefix}_total_{abs(hash(focus or 'none'))}")
        handle_table_focus(event, total, focus_key)


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
            if quote_type.upper() not in {"EQUITY","ETF","MUTUALFUND","INDEX","CRYPTOCURRENCY"}:
                continue
            results.append({
                "symbol": symbol,
                "name": str(item.get("longname") or item.get("shortname") or item.get("name") or symbol),
                "exchange_code": str(item.get("exchange") or "").strip(),
                "exchange_name": str(item.get("exchDisp") or item.get("fullExchangeName") or item.get("exchangeName") or "").strip(),
                "type": quote_type,
            })
    except Exception:
        pass
    if not results:
        results.append({"symbol":query.upper(),"name":query,"exchange_code":"","exchange_name":"","type":"Direkteingabe"})
    seen, unique = set(), []
    for item in results:
        if item["symbol"] not in seen:
            seen.add(item["symbol"]); unique.append(item)
    return unique[:10]


def asset_range_text(symbol):
    try:
        series, _ = asset_series_eur(symbol)
        return f"{series.index.min():%d.%m.%Y} – {series.index.max():%d.%m.%Y}"
    except Exception:
        return "–"


def correlation_heatmap(frame):
    corr = frame.pct_change(fill_method=None).dropna().corr()
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=corr.columns, y=corr.index, zmin=-1, zmax=1, zmid=0,
        colorscale="RdYlGn", text=np.round(corr.values,2), texttemplate="%{text:.2f}",
        hovertemplate="%{y} ↔ %{x}<br><b>%{z:.3f}</b><extra></extra>"))
    fig.update_layout(height=500, margin=dict(l=30,r=15,t=15,b=30),
                      plot_bgcolor="white", paper_bgcolor="white", font=dict(color="#111827"))
    return fig


def rolling_benchmark_corr(frame):
    returns = frame.pct_change(fill_method=None).dropna()
    fig = go.Figure()
    for col in frame.columns:
        if col == "Benchmark":
            continue
        rolling = returns[col].rolling(252, min_periods=126).corr(returns["Benchmark"])
        fig.add_trace(go.Scatter(x=rolling.index, y=rolling, mode="lines",
                                 name=f"{col} ↔ Benchmark", line=dict(width=2)))
    layout = base_layout(True)
    layout["height"] = 500
    layout["yaxis"] = dict(showgrid=False, zeroline=True, range=[-1,1], title="Korrelation")
    fig.update_layout(**layout)
    return fig


def render_asset_allocation_tool():
    query = st.text_input("Name, Ticker oder ISIN", key="aa_search_query",
                          placeholder="z. B. Micron, MU oder US5951121038")
    results = yahoo_search(query) if query else []
    if results:
        labels = []
        for x in results:
            venue = f"{x['symbol']}-{x['exchange_code']}" if x['exchange_code'] else x['symbol']
            if x['exchange_name']:
                venue += f" · {x['exchange_name']}"
            labels.append(f"{x['name']} — {venue}")
        selected_label = st.selectbox("Suchergebnis", labels, key="aa_search_result")
        selected_result = results[labels.index(selected_label)]
        c1, c2 = st.columns(2)
        with c1:
            if st.button("Zum Portfolio hinzufügen", use_container_width=True):
                add_asset(selected_result); st.session_state.aa_run = False; st.rerun()
        with c2:
            if st.button("Als Benchmark verwenden", use_container_width=True):
                st.session_state.aa_benchmark = selected_result; st.session_state.aa_run = False; st.rerun()

    assets = _aa_assets()
    if assets:
        st.markdown("#### Portfolio")
        for asset in list(assets):
            c1, c2, c3 = st.columns([.56,.30,.14], vertical_alignment="center")
            with c1:
                st.markdown(f"**{asset['name']}**  \n`{asset['symbol']}`  \n"
                            f"<span class='meta-line'>{asset_range_text(asset['symbol'])}</span>",
                            unsafe_allow_html=True)
            with c2:
                new_weight = st.number_input("Gewicht %", min_value=0.0, max_value=100.0,
                                             value=float(asset['weight']), step=1.0,
                                             key=f"aa_weight_{asset['symbol']}")
                if float(new_weight) != float(asset['weight']):
                    asset['weight'] = float(new_weight); st.session_state.aa_run = False
            with c3:
                if st.button("🗑️", key=f"aa_remove_{asset['symbol']}", use_container_width=True):
                    remove_asset(asset['symbol']); st.rerun()

    benchmark = st.session_state.get("aa_benchmark")
    if benchmark:
        st.markdown(f"**Benchmark:** {benchmark['name']} · `{benchmark['symbol']}`  \n"
                    f"<span class='meta-line'>{asset_range_text(benchmark['symbol'])}</span>",
                    unsafe_allow_html=True)

    rebalance = st.selectbox("Rebalancing",
                             ["Monatlich","Quartalsweise","Halbjährlich","Jährlich","Kein Rebalancing"],
                             index=1, key="aa_rebalance")
    if st.button("Backtest starten", type="primary", use_container_width=True):
        st.session_state.aa_run = True
    if not st.session_state.get("aa_run") or not assets or not benchmark:
        return

    weights = np.array([x['weight'] for x in assets], dtype=float)
    if weights.sum() <= 0:
        st.error("Die Summe der Gewichte muss größer als 0 sein."); return
    price_series, errors = {}, []
    for asset in assets:
        try:
            series, _ = asset_series_eur(asset['symbol']); price_series[asset['symbol']] = series
        except Exception as exc:
            errors.append(str(exc))
    try:
        benchmark_series, _ = asset_series_eur(benchmark['symbol'])
    except Exception as exc:
        benchmark_series = None; errors.append(f"Benchmark: {exc}")
    for error in errors:
        st.warning(error)
    if len(price_series) != len(assets) or benchmark_series is None:
        return

    prices = pd.concat(price_series, axis=1).dropna()
    benchmark_series = benchmark_series.reindex(prices.index).dropna()
    common_index = prices.index.intersection(benchmark_series.index)
    prices, benchmark_series = prices.loc[common_index], benchmark_series.loc[common_index]
    if len(prices) < 30:
        return
    portfolio = backtest_portfolio(prices, weights, rebalance)
    benchmark_indexed = benchmark_series / benchmark_series.iloc[0] * 100
    comparison = pd.concat([portfolio.rename("Portfolio"), benchmark_indexed.rename("Benchmark")], axis=1).dropna()

    perf = go.Figure()
    perf.add_trace(go.Scatter(x=comparison.index,y=comparison['Portfolio'],mode='lines',name='Portfolio',line=dict(width=2.8)))
    perf.add_trace(go.Scatter(x=comparison.index,y=comparison['Benchmark'],mode='lines',name='Benchmark',line=dict(width=2,dash='dash')))
    layout = base_layout(True); layout['yaxis'] = dict(showgrid=False,type='log',title='Indexiert (log)'); perf.update_layout(**layout)
    dd = comparison / comparison.cummax() - 1
    dd_fig = go.Figure()
    dd_fig.add_trace(go.Scatter(x=dd.index,y=dd['Portfolio']*100,mode='lines',name='Portfolio',line=dict(width=2.8)))
    dd_fig.add_trace(go.Scatter(x=dd.index,y=dd['Benchmark']*100,mode='lines',name='Benchmark',line=dict(width=2,dash='dash')))
    layout = base_layout(True); layout['yaxis'] = dict(showgrid=False,title='Drawdown in %'); dd_fig.update_layout(**layout)
    c1,c2 = st.columns(2,gap='large')
    with c1:
        st.markdown('#### Wertentwicklung'); st.plotly_chart(perf,width='stretch',config={'displaylogo':False,'scrollZoom':True})
    with c2:
        st.markdown('#### Drawdown'); st.plotly_chart(dd_fig,width='stretch',config={'displaylogo':False,'scrollZoom':True})

    name_map = {x['symbol']:f"{x['name']} ({x['symbol']})" for x in assets}
    component = (prices / prices.iloc[0] * 100).rename(columns=name_map)
    component['Benchmark'] = benchmark_indexed.reindex(component.index)
    comp_fig = go.Figure()
    for col in component.columns:
        comp_fig.add_trace(go.Scatter(x=component.index,y=component[col],mode='lines',name=col,
                                      line=dict(width=2,dash='dash' if col=='Benchmark' else 'solid')))
    layout = base_layout(True); layout['yaxis'] = dict(showgrid=False,type='log',title='Indexiert (log)'); comp_fig.update_layout(**layout)
    st.markdown('#### Bestandteile'); st.plotly_chart(comp_fig,width='stretch',config={'displaylogo':False,'scrollZoom':True})

    corr_input = component.copy(); corr_input['Portfolio'] = portfolio.reindex(corr_input.index)
    c1,c2 = st.columns(2,gap='large')
    with c1:
        st.markdown('#### Korrelogramm'); st.plotly_chart(correlation_heatmap(corr_input),width='stretch',config={'displaylogo':False})
    with c2:
        st.markdown('#### Rollierende 1-Jahres-Korrelation')
        st.plotly_chart(rolling_benchmark_corr(corr_input),width='stretch',config={'displaylogo':False,'scrollZoom':True})

    stats = pd.DataFrame({'Portfolio':backtest_metrics(comparison['Portfolio']),
                          'Benchmark':backtest_metrics(comparison['Benchmark'])}).T
    st.markdown('#### Kennzahlen')
    st.dataframe(style_heat(stats, reverse_columns={'Volatilität p.a.'}),
                 width='stretch', height=compact_height(len(stats)))


def render_china_dashboard():
    nav, status_col = st.columns([.68,.32], vertical_alignment='center')
    with nav:
        page = st.radio('Bereich', ['Market ETFs vergleichen','Tech ETFs vergleichen'], horizontal=True,
                        index=0 if st.session_state.get('china_page','Market ETFs vergleichen')=='Market ETFs vergleichen' else 1,
                        key='china_page_radio', label_visibility='collapsed')
        st.session_state.china_page = page
    if page == 'Market ETFs vergleichen':
        selected, dialog = market_tree()
        status, progress = status_col.empty(), status_col.progress(0)
        cache = _cache('v9_index_data')
        done = sum(name in cache for name in selected)
        status_text(status, done, len(selected)); progress.progress(100 if not selected else round(done/len(selected)*100))
        for name in selected:
            if name not in cache:
                session_index(name); done += 1; status_text(status,done,len(selected)); progress.progress(round(done/len(selected)*100))
        resolved, warnings = [], []
        for name in selected:
            item, error = cache[name]
            if item is not None: resolved.append(item)
            if error: warnings.append(f"{name}: {error}")
        for warning in warnings: st.warning(warning)
        render_outputs(resolved,'market','market_focus')
        if dialog: etf_dialog(dialog)
    else:
        render_tech(status_col)


# Page-style navigation without duplicate page headings.
top_page = st.radio('App', ['China ETF Dashboard','Asset Allocation Backtesting Tool'], horizontal=True,
                    index=0 if st.session_state.get('top_page','China ETF Dashboard')=='China ETF Dashboard' else 1,
                    key='top_page_radio_v10', label_visibility='collapsed')
st.session_state.top_page = top_page
st.session_state.after_tax = True

if top_page == 'China ETF Dashboard':
    render_china_dashboard()
else:
    render_asset_allocation_tool()
