from pathlib import Path
import re

# Build v6 from the stable v5 implementation, replacing only the UI/interaction
# sections requested in the latest review. This keeps the data/research metadata
# in one place while avoiding a second large duplicate file.
_source = Path(__file__).with_name("app_v5.py").read_text(encoding="utf-8")

STYLE_HEAT = r'''
def style_heat(df, focus=None):
    pct={"CAGR p.a.","Volatilität p.a.","Max. Drawdown","Tracking Error p.a."}
    nums={"Sharpe Ratio","Sortino","Calmar","Information Ratio p.a."}
    fmts={c:(lambda x: "–" if pd.isna(x) else f"{x:.2%}") for c in df.columns if c in pct}
    fmts.update({c:(lambda x: "–" if pd.isna(x) else f"{x:.2f}") for c in df.columns if c in nums or str(c).isdigit()})
    sty=df.style.format(fmts,na_rep="–").set_properties(**{"color":"#111827","background-color":"#ffffff"})
    numeric=df.select_dtypes(include="number").columns.tolist()
    # Excel-like red -> yellow -> green heatmap implemented directly, so no
    # matplotlib dependency is needed on Streamlit Community Cloud.
    for column in numeric:
        vals=pd.to_numeric(df[column],errors="coerce")
        valid=vals.dropna()
        if valid.empty:
            continue
        lo,hi=float(valid.min()),float(valid.max())
        def _paint(v):
            if pd.isna(v): return "color:#111827;background-color:#ffffff"
            p=.5 if hi==lo else (float(v)-lo)/(hi-lo)
            if p<=.5:
                w=p*2; a=(248,190,190); b=(255,244,176)
            else:
                w=(p-.5)*2; a=(255,244,176); b=(183,229,190)
            rgb=tuple(round(x+(y-x)*w) for x,y in zip(a,b))
            return f"background-color:rgb{rgb};color:#111827"
        sty=sty.map(_paint,subset=[column])
    if focus is not None and focus in df.index:
        sty=sty.apply(lambda row:["font-weight:800;border-top:2px solid #111827;border-bottom:2px solid #111827" if row.name==focus else "" for _ in row],axis=1)
    return sty
'''
_source = re.sub(r'def style_heat\(df, focus=None\):.*?\n\ndef base_layout', STYLE_HEAT+'\n\ndef base_layout', _source, flags=re.S)

TREE = r'''
def _category_pills(title, items, key_prefix, expanded=True):
    with st.expander(title, expanded=expanded):
        state_key=f"{key_prefix}_pills"
        if state_key not in st.session_state:
            st.session_state[state_key]=items.copy()
        b1,b2=st.columns(2)
        with b1:
            if st.button("Alle auswählen",key=f"{key_prefix}_all",use_container_width=True):
                st.session_state[state_key]=items.copy()
                st.rerun()
        with b2:
            if st.button("Alle abwählen",key=f"{key_prefix}_none",use_container_width=True):
                st.session_state[state_key]=[]
                st.rerun()
        selected=st.pills("Indizes",items,selection_mode="multi",key=state_key,label_visibility="collapsed") or []
        dialog=None
        for n in selected:
            info=INDEX_INFO[n]
            c1,c2=st.columns([.82,.18],vertical_alignment="top")
            with c1:
                st.markdown(index_card(n),unsafe_allow_html=True)
            with c2:
                if st.button("ETF-Vergleich",key=f"open_{key_prefix}_{n}",use_container_width=True):
                    dialog=n
        return selected,dialog

def render_tree():
    allshares=[x for x in index_order if INDEX_SCOPE[x]=="All Shares"]
    onshore=[x for x in index_order if INDEX_SCOPE[x]=="Onshore"]
    offshore=[x for x in index_order if INDEX_SCOPE[x]=="Offshore"]
    selected=[];dialog=None
    s,d=_category_pills("All Shares",allshares,"market_all",True);selected+=s;dialog=dialog or d
    left,right=st.columns(2,gap="large")
    with left:
        s,d=_category_pills("Onshore",onshore,"market_on",True);selected+=s;dialog=dialog or d
    with right:
        s,d=_category_pills("Offshore",offshore,"market_off",True);selected+=s;dialog=dialog or d
    return selected,dialog
'''
_source = re.sub(r'def render_tree\(\):.*?\n\ndef render_outputs', TREE+'\n\ndef render_outputs', _source, flags=re.S)

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
    focus=st.session_state.get(focus_key)
    if focus not in [display.get(c,c) for c in frame.columns]: focus=None
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

    annual=yearly_sharpe_matrix(corr_frame,display)
    metric_bench=None
    if benchmark_map:
        metric_bench={col:frame[bcol] for col,bcol in benchmark_map.items() if col in frame.columns and bcol in frame.columns}
    total=total_stats(corr_frame,display,metric_bench if key_prefix=="tech" else None)
    t1,t2=st.columns(2,gap="large")
    with t1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        ev=st.dataframe(style_heat(annual,focus),width="stretch",height=430,on_select="rerun",selection_mode="single-row",key=f"{key_prefix}_annual")
        update_focus_from_table(ev,annual,focus_key)
    with t2:
        st.markdown("#### Gesamtperformance")
        ev=st.dataframe(style_heat(total,focus),width="stretch",height=430,on_select="rerun",selection_mode="single-row",key=f"{key_prefix}_total")
        update_focus_from_table(ev,total,focus_key)
'''
_source = re.sub(r'def render_outputs\(resolved,key_prefix,focus_key,benchmark_map=None,benchmark_by_col=None\):.*?\n\n@st.dialog', OUTPUTS+'\n\n@st.dialog', _source, flags=re.S)

DIALOG = r'''
@st.dialog("ETFs des Index",width="large")
def market_etf_dialog(index_name):
    sub=registry[registry["index_name"]==index_name].sort_values("inception").copy()
    if sub.empty:
        st.info("Keine ETFs hinterlegt.");return
    top_left,top_right=st.columns([.62,.38],vertical_alignment="center")
    with top_left: st.markdown(f"### {index_name}")
    status=top_right.empty();bar=top_right.progress(0)
    table=sub.copy();table["Auflage"]=table["inception"].map(fmt_date)
    table["Mitglieder"]=INDEX_INFO[index_name]["members"]
    table["JustETF"]=table["isin"].map(lambda x:f"https://www.justetf.com/de/etf-profile.html?isin={x}")
    show=table[["etf_name","isin","Auflage","Mitglieder","ter","distribution","JustETF"]].rename(columns={"etf_name":"ETF","isin":"ISIN","ter":"TER","distribution":"Ertragsverwendung"})
    st.dataframe(show.style.set_properties(**{"color":"#111827","background-color":"#fff"}).format({"TER":"{:.2f}%"}),width="stretch",hide_index=True,column_config={"JustETF":st.column_config.LinkColumn("Link",display_text="Öffnen")})
    resolved=[];warnings=[];n=len(sub)
    for i,(_,row) in enumerate(sub.iterrows(),1):
        status.caption(f"ETF-Daten · {i-1} von {n}")
        rr,ww=resolve_rows_cached(index_name,(row["etf_name"],));resolved+=rr;warnings+=ww
        bar.progress(int(i/n*100))
    status.caption(f"ETF-Daten geladen · {n} von {n} · 100 %")
    for w in warnings: st.warning(w)
    if resolved:
        render_outputs(resolved,f"dlg_{abs(hash(index_name))}",f"dialog_focus_{abs(hash(index_name))}")
'''
_source = re.sub(r'@st.dialog\("ETFs des Index",width="large"\).*?\n\ndef parse_share_classes', DIALOG+'\n\ndef parse_share_classes', _source, flags=re.S)

TECH = r'''
def _tech_category(universe, rows, key_prefix):
    selected=[]
    with st.expander(universe,expanded=True):
        names=rows["etf_name"].tolist()
        state_key=f"{key_prefix}_pills"
        if state_key not in st.session_state: st.session_state[state_key]=names.copy()
        b1,b2=st.columns(2)
        with b1:
            if st.button("Alle auswählen",key=f"{key_prefix}_all",use_container_width=True):
                st.session_state[state_key]=names.copy();st.rerun()
        with b2:
            if st.button("Alle abwählen",key=f"{key_prefix}_none",use_container_width=True):
                st.session_state[state_key]=[];st.rerun()
        selected=st.pills("Tech-ETFs",names,selection_mode="multi",key=state_key,label_visibility="collapsed") or []
        for i,(_,row) in enumerate(rows[rows["etf_name"].isin(selected)].iterrows()):
            proxy=MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(row["share_classes"]),"–")
            st.markdown(f"""<div class="tree-card"><div class="tree-title"><span class="swatch" style="background:{PALETTE[i%len(PALETTE)]}"></span><a href="{row['source_url']}" target="_blank">{row['etf_name']}</a></div>
            <div class="tree-bullets">• <b>Index:</b> {row['index_name']}<br>• <b>Aktienklassen:</b> {row['share_classes']}<br>• <b>Mitglieder:</b> {row['members']}<br>• <b>Market Proxy (Benchmark für IR/TE):</b> {proxy}<br>• <b>TER:</b> {row['ter']:.2f}%</div></div>""",unsafe_allow_html=True)
    return selected

def render_tech(status_host):
    tech=tech_registry_cached().copy();selected=[]
    st.markdown("### Tech ETFs")
    a=tech[tech["universe"]=="All Shares"]
    selected+=_tech_category("All Shares",a,"tech_all") if not a.empty else []
    left,right=st.columns(2,gap="large")
    with left:
        r=tech[tech["universe"]=="Onshore"]
        if not r.empty: selected+=_tech_category("Onshore",r,"tech_on")
    with right:
        r=tech[tech["universe"]=="Offshore"]
        if not r.empty: selected+=_tech_category("Offshore",r,"tech_off")
    if not selected:
        st.info("Tech-ETFs auswählen.");return
    resolved=[];warnings=[];n=len(selected);bar=status_host.progress(0);txt=status_host.empty()
    for i,name in enumerate(selected,1):
        txt.caption(f"Marktdaten · {i-1} von {n}")
        rr,ww=resolve_tech_cached((name,));resolved+=rr;warnings+=ww;bar.progress(int(i/n*100))
    txt.caption(f"Marktdaten geladen · {n} von {n} · 100 %")
    for w in warnings: st.warning(w)
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
_source = re.sub(r'def render_tech\(status_host\):.*?\n\nst.title\("China ETF Dashboard"\)', TECH+'\n\nst.title("China ETF Dashboard")', _source, flags=re.S)

# Keep main results rendered before opening the dialog. This prevents the
# background market page from appearing empty while ETF data are being loaded.
_source = _source.replace(
    '    selected,dialog=render_tree()\n    if dialog:market_etf_dialog(dialog)\n    resolved=[];warnings=[];n=len(selected)',
    '    selected,dialog=render_tree()\n    resolved=[];warnings=[];n=len(selected)'
)
_source = _source.replace(
    '    render_outputs(resolved,"market","market_focus")\nelse:',
    '    render_outputs(resolved,"market","market_focus")\n    if dialog: market_etf_dialog(dialog)\nelse:'
)

_code=compile(_source,str(Path(__file__).with_name("app_v5.py")),"exec")
exec(_code,globals(),globals())
