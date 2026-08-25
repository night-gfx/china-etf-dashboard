from pathlib import Path
import re

# v7 builds on v6 and only replaces the interaction/layout pieces.
_source = Path(__file__).with_name("app_v6.py").read_text(encoding="utf-8")

# Categories start collapsed, no bulk select/deselect controls. Each item is a
# toggle button; cards keep methodology link and ETF comparison at bottom-right.
TREE = r'''
def _ensure_selected_state(state_key, items):
    if state_key not in st.session_state:
        st.session_state[state_key] = items.copy()
    # Drop stale items, preserve current user choices.
    st.session_state[state_key] = [x for x in st.session_state[state_key] if x in items]
    return st.session_state[state_key]

def _toggle_item(state_key, item, items):
    current = list(_ensure_selected_state(state_key, items))
    if item in current:
        current.remove(item)
    else:
        current.append(item)
    st.session_state[state_key] = current

def _color_dot(color):
    # Button-safe colored marker. Exact chart color remains shown as an HTML swatch in the card.
    return "●"

def _market_category(title, items, key_prefix):
    selected = _ensure_selected_state(f"{key_prefix}_selected", items)
    dialog = None
    with st.expander(title, expanded=False):
        for n in items:
            info = INDEX_INFO[n]
            active = n in selected
            with st.container(border=True):
                cbtn, cinfo = st.columns([.36, .64], vertical_alignment="top")
                with cbtn:
                    label = f"{'✓' if active else '○'}  {_color_dot(INDEX_COLOR[n])}  {n}"
                    if st.button(label, key=f"toggle_{key_prefix}_{n}", use_container_width=True, type="primary" if active else "secondary"):
                        _toggle_item(f"{key_prefix}_selected", n, items)
                        st.rerun()
                with cinfo:
                    st.markdown(f"""
                    <div class="tree-bullets">
                    <span class="swatch" style="background:{INDEX_COLOR[n]}"></span><b>{'Aktiv' if active else 'Nicht ausgewählt'}</b><br>
                    • <b>Aktienklassen:</b> {share_text(n)}<br>
                    • <b>Segment:</b> {info['segment']}<br>
                    • <b>Mitglieder:</b> {info['members']}<br>
                    • <b>Gewichtung:</b> {info['weight']}<br>
                    • <b>Rebalancing:</b> {info['rebalance']}<br>
                    • <b>Besonderheit:</b> {info['special']}
                    </div>
                    """, unsafe_allow_html=True)
                spacer, link_col, etf_col = st.columns([.50, .22, .28], vertical_alignment="center")
                with link_col:
                    st.link_button("Methodology", info['url'], use_container_width=True)
                with etf_col:
                    if st.button("ETF-Vergleich", key=f"open_{key_prefix}_{n}", use_container_width=True):
                        dialog = n
    return list(_ensure_selected_state(f"{key_prefix}_selected", items)), dialog

def render_tree():
    allshares=[x for x in index_order if INDEX_SCOPE[x]=="All Shares"]
    onshore=[x for x in index_order if INDEX_SCOPE[x]=="Onshore"]
    offshore=[x for x in index_order if INDEX_SCOPE[x]=="Offshore"]
    selected=[]; dialog=None
    s,d=_market_category("All Shares",allshares,"market_all"); selected+=s; dialog=dialog or d
    left,right=st.columns(2,gap="large")
    with left:
        s,d=_market_category("Onshore",onshore,"market_on"); selected+=s; dialog=dialog or d
    with right:
        s,d=_market_category("Offshore",offshore,"market_off"); selected+=s; dialog=dialog or d
    return selected,dialog
'''
_source = re.sub(r'def _category_pills\(title, items, key_prefix, expanded=True\):.*?\n\ndef render_outputs', TREE+'\n\ndef render_outputs', _source, flags=re.S)

# Unified focus: one state per page/dialog. Clicking the same selected series/row
# again clears focus. Plot and table selection feed exactly the same state key.
FOCUS = r'''
def _toggle_focus(state_key, name):
    st.session_state[state_key] = None if st.session_state.get(state_key) == name else name

def update_focus_from_plot(event, label_map, state_key):
    try:
        pts=event.selection.points
        if pts:
            cd=pts[0].get("customdata")
            if cd in label_map:
                _toggle_focus(state_key, label_map[cd])
    except Exception:
        pass

def update_focus_from_table(event, df, state_key):
    try:
        rows=event.selection.rows
        if rows:
            _toggle_focus(state_key, df.index[rows[0]])
    except Exception:
        pass
'''
_source = re.sub(r'def update_focus_from_plot\(event, label_map, state_key\):.*?\n\nregistry=', FOCUS+'\n\nregistry=', _source, flags=re.S)

# Keep Plotly legends permanently hidden, including hover interactions.
_source = _source.replace('fig.update_layout(**base_layout(False),yaxis=yaxis)', 'fig.update_layout(**base_layout(False),yaxis=yaxis,showlegend=False)')

# Dynamic table heights and synchronized focus across both tables + both charts.
OUTPUTS = r'''
def render_outputs(resolved,key_prefix,focus_key,benchmark_map=None,benchmark_by_col=None):
    if not resolved:
        st.info("Keine verfügbaren Serien.");return
    series={x.label:x.series_eur for x in resolved}
    display={x.label:(x.index_name if key_prefix=="market" else x.etf_name) for x in resolved}
    colors={x.label:(INDEX_COLOR.get(x.index_name,PALETTE[i%len(PALETTE)]) if key_prefix=="market" else PALETTE[i%len(PALETTE)]) for i,x in enumerate(resolved)}
    if benchmark_map:
        for col,bcol in benchmark_map.items():
            if benchmark_by_col and bcol in benchmark_by_col:
                series[bcol]=benchmark_by_col[bcol]
    frame=common_frame(series)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum.");return
    visible_names=[display.get(c,c) for c in frame.columns if not c.startswith("__BENCH__")]
    focus=st.session_state.get(focus_key)
    if focus not in visible_names: focus=None
    focus_col=next((c for c,n in display.items() if n==focus),None)

    c1,c2=st.columns(2,gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        ev=st.plotly_chart(line_fig(frame,colors,focus_col,False,benchmark_map),width="stretch",config={"displaylogo":False,"scrollZoom":True},key=f"{key_prefix}_perf",on_select="rerun",selection_mode="points")
        update_focus_from_plot(ev,display,focus_key)
    with c2:
        st.markdown("#### Drawdown")
        ev=st.plotly_chart(line_fig(frame,colors,focus_col,True,benchmark_map),width="stretch",config={"displaylogo":False,"scrollZoom":True},key=f"{key_prefix}_dd",on_select="rerun",selection_mode="points")
        update_focus_from_plot(ev,display,focus_key)

    annual=yearly_sharpe_matrix(frame[[c for c in frame.columns if not c.startswith("__BENCH__")]],display)
    metric_bench=None
    if benchmark_map:
        metric_bench={col:frame[bcol] for col,bcol in benchmark_map.items() if col in frame.columns and bcol in frame.columns}
    total=total_stats(frame[[c for c in frame.columns if not c.startswith("__BENCH__")]],display,metric_bench if key_prefix=="tech" else None)
    t1,t2=st.columns(2,gap="large")
    with t1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        h=min(64+35*max(len(annual),1),430)
        ev=st.dataframe(style_heat(annual,focus),width="stretch",height=h,on_select="rerun",selection_mode="single-row",key=f"{key_prefix}_annual")
        update_focus_from_table(ev,annual,focus_key)
    with t2:
        st.markdown("#### Gesamtperformance")
        h=min(64+35*max(len(total),1),430)
        ev=st.dataframe(style_heat(total,focus),width="stretch",height=h,on_select="rerun",selection_mode="single-row",key=f"{key_prefix}_total")
        update_focus_from_table(ev,total,focus_key)

    corr_cols=[c for c in frame.columns if not c.startswith("__BENCH__")]
    corr_frame=frame[corr_cols]
    pair=st.session_state.get(f"{key_prefix}_corr_pair")
    if not pair or pair[0] not in corr_frame.columns or pair[1] not in corr_frame.columns or pair[0]==pair[1]:
        pair=(corr_cols[0],corr_cols[1]) if len(corr_cols)>=2 else None
    cc1,cc2=st.columns(2,gap="large")
    with cc1:
        st.markdown("#### Korrelogramm")
        corr_event=st.plotly_chart(correlation_fig(corr_frame,display,focus_col),width="stretch",config={"displaylogo":False},key=f"{key_prefix}_corr",on_select="rerun",selection_mode="points")
        try:
            pts=corr_event.selection.points
            if pts:
                cd=pts[0].get("customdata")
                if cd and "|||" in cd:
                    p=tuple(cd.split("|||",1))
                    if p[0]!=p[1]: st.session_state[f"{key_prefix}_corr_pair"]=p
        except Exception: pass
    with cc2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation")
        pair=st.session_state.get(f"{key_prefix}_corr_pair") or pair
        if pair and len(corr_cols)>=2:
            st.plotly_chart(rolling_corr_fig(corr_frame,pair[0],pair[1],display),width="stretch",config={"displaylogo":False,"scrollZoom":True},key=f"{key_prefix}_roll")
            st.caption("Das Paar wird durch Klick auf eine Zelle im Korrelogramm gewählt.")
        else:
            st.info("Mindestens zwei Serien erforderlich.")
'''
_source = re.sub(r'def render_outputs\(resolved,key_prefix,focus_key,benchmark_map=None,benchmark_by_col=None\):.*?\n\n@st.dialog', OUTPUTS+'\n\n@st.dialog', _source, flags=re.S)

# ETF dialog: adapt dataframe height exactly to number of rows.
_source = _source.replace(
    'st.dataframe(show.style.set_properties(**{"color":"#111827","background-color":"#fff"}).format({"TER":"{:.2f}%"}),width="stretch",hide_index=True,column_config={"JustETF":st.column_config.LinkColumn("Link",display_text="Öffnen")})',
    'st.dataframe(show.style.set_properties(**{"color":"#111827","background-color":"#fff"}).format({"TER":"{:.2f}%"}),width="stretch",height=min(42+35*max(len(show),1),420),hide_index=True,column_config={"JustETF":st.column_config.LinkColumn("Link",display_text="Öffnen")})'
)

# Tech page mirrors Market layout one-to-one: collapsed categories, toggle button,
# detail card, and link at bottom-right. No bulk selection controls.
TECH = r'''
def _tech_category(universe, rows, key_prefix):
    names=rows["etf_name"].tolist()
    selected=_ensure_selected_state(f"{key_prefix}_selected",names)
    with st.expander(universe,expanded=False):
        for i,(_,row) in enumerate(rows.iterrows()):
            name=row["etf_name"]
            active=name in selected
            proxy=MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(row["share_classes"]),"–")
            color=PALETTE[i%len(PALETTE)]
            with st.container(border=True):
                cbtn,cinfo=st.columns([.36,.64],vertical_alignment="top")
                with cbtn:
                    label=f"{'✓' if active else '○'}  ●  {name}"
                    if st.button(label,key=f"toggle_{key_prefix}_{name}",use_container_width=True,type="primary" if active else "secondary"):
                        _toggle_item(f"{key_prefix}_selected",name,names);st.rerun()
                with cinfo:
                    st.markdown(f"""
                    <div class="tree-bullets">
                    <span class="swatch" style="background:{color}"></span><b>{'Aktiv' if active else 'Nicht ausgewählt'}</b><br>
                    • <b>Index:</b> {row['index_name']}<br>
                    • <b>Aktienklassen:</b> {row['share_classes']}<br>
                    • <b>Mitglieder:</b> {row['members']}<br>
                    • <b>Market Proxy (Benchmark für IR/TE):</b> {proxy}<br>
                    • <b>TER:</b> {row['ter']:.2f}%
                    </div>
                    """,unsafe_allow_html=True)
                spacer,link_col=st.columns([.72,.28])
                with link_col:
                    st.link_button("ETF / Methodology",row['source_url'],use_container_width=True)
    return list(_ensure_selected_state(f"{key_prefix}_selected",names))

def render_tech(status_host):
    tech=tech_registry_cached().copy();selected=[]
    a=tech[tech["universe"]=="All Shares"]
    if not a.empty:selected+=_tech_category("All Shares",a,"tech_all")
    left,right=st.columns(2,gap="large")
    with left:
        r=tech[tech["universe"]=="Onshore"]
        if not r.empty:selected+=_tech_category("Onshore",r,"tech_on")
    with right:
        r=tech[tech["universe"]=="Offshore"]
        if not r.empty:selected+=_tech_category("Offshore",r,"tech_off")
    if not selected:
        st.info("Tech-ETFs auswählen.");return
    resolved=[];warnings=[];n=len(selected);bar=status_host.progress(0);txt=status_host.empty()
    for i,name in enumerate(selected,1):
        txt.caption(f"Marktdaten · {i-1} von {n}")
        rr,ww=resolve_tech_cached((name,));resolved+=rr;warnings+=ww;bar.progress(int(i/n*100))
    txt.caption(f"Marktdaten geladen · {n} von {n} · 100 %")
    for w in warnings:st.warning(w)
    if not resolved:return
    meta=tech.set_index("etf_name");bmap={};bseries={}
    for item in resolved:
        if item.etf_name not in meta.index:continue
        p=MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(meta.loc[item.etf_name,"share_classes"]))
        if not p:continue
        try:
            b=resolve_index_cached(p);bcol=f"__BENCH__{item.label}";bmap[item.label]=bcol;bseries[bcol]=b.series_eur
        except Exception:pass
    render_outputs(resolved,"tech","tech_focus",bmap,bseries)
'''
_source = re.sub(r'def _tech_category\(universe, rows, key_prefix\):.*?\n\nst.title\("China ETF Dashboard"\)', TECH+'\n\nst.title("China ETF Dashboard")', _source, flags=re.S)

# Compile replacement result before execution so deployment fails early if a patch is malformed.
_code = compile(_source, str(Path(__file__).with_name("app_v7_runtime.py")), "exec")
exec(_code, globals(), globals())
