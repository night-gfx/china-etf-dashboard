from pathlib import Path
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# Reuse only the stable data/metric definitions from v5, not its rendered UI.
_base = Path(__file__).with_name("app_v5.py").read_text(encoding="utf-8")
_prefix = _base.split("registry=registry_cached()", 1)[0]
exec(compile(_prefix, "app_v5_core", "exec"), globals(), globals())

# ----- v8 UI helpers -----

def style_heat_v8(df, focus=None):
    pct={"CAGR p.a.","Volatilität p.a.","Max. Drawdown","Tracking Error p.a."}
    nums={"Sharpe Ratio","Sortino","Calmar","Information Ratio p.a."}
    fmts={c:(lambda x: "–" if pd.isna(x) else f"{x:.2%}") for c in df.columns if c in pct}
    fmts.update({c:(lambda x: "–" if pd.isna(x) else f"{x:.2f}") for c in df.columns if c in nums or str(c).isdigit()})
    sty=df.style.format(fmts,na_rep="–").set_properties(**{"color":"#111827","background-color":"#ffffff"})
    for column in df.select_dtypes(include="number").columns:
        vals=pd.to_numeric(df[column],errors="coerce"); valid=vals.dropna()
        if valid.empty: continue
        lo,hi=float(valid.min()),float(valid.max())
        def paint(v):
            if pd.isna(v): return "color:#111827;background-color:#fff"
            p=.5 if hi==lo else (float(v)-lo)/(hi-lo)
            if p<=.5:
                w=p*2; a=(248,190,190); b=(255,244,176)
            else:
                w=(p-.5)*2; a=(255,244,176); b=(183,229,190)
            rgb=tuple(round(x+(y-x)*w) for x,y in zip(a,b))
            return f"background-color:rgb{rgb};color:#111827"
        sty=sty.map(paint,subset=[column])
    if focus is not None and focus in df.index:
        sty=sty.apply(lambda r:["font-weight:800;border-top:2px solid #111827;border-bottom:2px solid #111827" if r.name==focus else "" for _ in r],axis=1)
    return sty


def toggle_focus(name, key):
    st.session_state[key] = None if st.session_state.get(key)==name else name


def plot_focus_event(event, display, key):
    try:
        pts=event.selection.points
        if pts:
            cd=pts[0].get("customdata")
            if cd in display:
                toggle_focus(display[cd],key)
    except Exception:
        pass


def table_focus_event(event, df, key):
    try:
        rows=event.selection.rows
        if rows:
            toggle_focus(df.index[rows[0]],key)
    except Exception:
        pass


def compact_height(n, row=35, base=40, maximum=420):
    return min(maximum, base + max(1,n)*row)


def dot_for(i):
    return ["🔵","🔴","🟢","🟣","🟠","🟦","🟥","🟩","🟪","🟧"][i%10]

registry=registry_cached()
index_order=registry[["index_order","index_name"]].drop_duplicates().sort_values("index_order")["index_name"].tolist()
INDEX_COLOR={n:PALETTE[i%len(PALETTE)] for i,n in enumerate(index_order)}
INDEX_DOT={n:dot_for(i) for i,n in enumerate(index_order)}


def ensure_selected(key,items):
    if key not in st.session_state:
        st.session_state[key]=items.copy()
    st.session_state[key]=[x for x in st.session_state[key] if x in items]
    return st.session_state[key]


def toggle_selected(key,item,items):
    cur=list(ensure_selected(key,items))
    if item in cur: cur.remove(item)
    else: cur.append(item)
    st.session_state[key]=cur
    st.rerun()


def index_details(name):
    info=INDEX_INFO[name]
    st.markdown(
        f"• **Aktienklassen:** {share_text(name)}  \n"
        f"• **Segment:** {info['segment']}  \n"
        f"• **Mitglieder:** {info['members']}  \n"
        f"• **Gewichtung:** {info['weight']}  \n"
        f"• **Rebalancing:** {info['rebalance']}  \n"
        f"• **Besonderheit:** {info['special']}"
    )


def market_category(title,items,key):
    selected=ensure_selected(key,items)
    dialog=None
    with st.expander(title,expanded=False):
        for i,n in enumerate(items):
            active=n in selected
            with st.container(border=True):
                if st.button(f"{INDEX_DOT[n]}  {n}",key=f"sel_{key}_{n}",type="primary" if active else "secondary",use_container_width=True):
                    toggle_selected(key,n,items)
                index_details(n)
                spacer,l1,l2=st.columns([.48,.26,.26])
                with l1:
                    st.link_button("Methodology",INDEX_INFO[n]["url"],use_container_width=True)
                with l2:
                    if st.button("ETF-Vergleich",key=f"etf_{key}_{n}",use_container_width=True):
                        dialog=n
    return list(selected),dialog


def market_tree():
    alls=[x for x in index_order if INDEX_SCOPE[x]=="All Shares"]
    ons=[x for x in index_order if INDEX_SCOPE[x]=="Onshore"]
    offs=[x for x in index_order if INDEX_SCOPE[x]=="Offshore"]
    selected=[]; dialog=None
    s,d=market_category("All Shares",alls,"m_all"); selected+=s; dialog=dialog or d
    left,right=st.columns(2,gap="large")
    with left:
        s,d=market_category("Onshore",ons,"m_on"); selected+=s; dialog=dialog or d
    with right:
        s,d=market_category("Offshore",offs,"m_off"); selected+=s; dialog=dialog or d
    return selected,dialog


def render_outputs_v8(resolved,key_prefix,focus_key,benchmark_map=None,benchmark_series=None):
    if not resolved:
        st.info("Keine verfügbaren Serien."); return
    series={x.label:x.series_eur for x in resolved}
    display={x.label:(x.index_name if key_prefix=="market" else x.etf_name) for x in resolved}
    colors={x.label:(INDEX_COLOR.get(x.index_name,PALETTE[i%len(PALETTE)]) if key_prefix=="market" else PALETTE[i%len(PALETTE)]) for i,x in enumerate(resolved)}
    if benchmark_map and benchmark_series:
        for lab,bcol in benchmark_map.items():
            if bcol in benchmark_series: series[bcol]=benchmark_series[bcol]
    frame=common_frame(series)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum."); return
    focus=st.session_state.get(focus_key)
    focus_col=next((c for c,n in display.items() if n==focus),None)

    c1,c2=st.columns(2,gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        ev=st.plotly_chart(line_fig(frame,colors,focus_col,False,benchmark_map),width="stretch",config={"displaylogo":False,"scrollZoom":True},key=f"{key_prefix}_perf",on_select="rerun",selection_mode="points")
        plot_focus_event(ev,display,focus_key)
    with c2:
        st.markdown("#### Drawdown")
        ev=st.plotly_chart(line_fig(frame,colors,focus_col,True,benchmark_map),width="stretch",config={"displaylogo":False,"scrollZoom":True},key=f"{key_prefix}_dd",on_select="rerun",selection_mode="points")
        plot_focus_event(ev,display,focus_key)

    corr_cols=[c for c in frame.columns if not c.startswith("__BENCH__")]
    corr_frame=frame[corr_cols]
    pair_key=f"{key_prefix}_corr_pair"
    pair=st.session_state.get(pair_key)
    if not pair or any(x not in corr_frame.columns for x in pair) or pair[0]==pair[1]:
        pair=(corr_cols[0],corr_cols[1]) if len(corr_cols)>=2 else None
    c1,c2=st.columns(2,gap="large")
    with c1:
        st.markdown("#### Korrelogramm")
        ce=st.plotly_chart(correlation_fig(corr_frame,display,focus_col),width="stretch",config={"displaylogo":False},key=f"{key_prefix}_corr",on_select="rerun",selection_mode="points")
        try:
            pts=ce.selection.points
            if pts:
                cd=pts[0].get("customdata")
                if cd and "|||" in cd:
                    p=tuple(cd.split("|||",1))
                    if p[0]!=p[1]: st.session_state[pair_key]=p
        except Exception: pass
    with c2:
        st.markdown("#### Rollierende 1-Jahres-Korrelation")
        pair=st.session_state.get(pair_key) or pair
        if pair:
            st.plotly_chart(rolling_corr_fig(corr_frame,pair[0],pair[1],display),width="stretch",config={"displaylogo":False,"scrollZoom":True},key=f"{key_prefix}_roll")
        else:
            st.info("Mindestens zwei Serien erforderlich.")

    annual=yearly_sharpe_matrix(corr_frame,display)
    metric_bench={}
    if benchmark_map:
        metric_bench={lab:frame[bcol] for lab,bcol in benchmark_map.items() if lab in corr_frame.columns and bcol in frame.columns}
    total=total_stats(corr_frame,display,metric_bench if benchmark_map else None)
    c1,c2=st.columns(2,gap="large")
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        ev=st.dataframe(style_heat_v8(annual,focus),width="stretch",height=compact_height(len(annual)),on_select="rerun",selection_mode="single-row",key=f"{key_prefix}_annual")
        table_focus_event(ev,annual,focus_key)
    with c2:
        st.markdown("#### Gesamtperformance")
        ev=st.dataframe(style_heat_v8(total,focus),width="stretch",height=compact_height(len(total)),on_select="rerun",selection_mode="single-row",key=f"{key_prefix}_total")
        table_focus_event(ev,total,focus_key)


@st.dialog("ETFs des Index",width="large")
def etf_dialog(index_name):
    sub=registry[registry["index_name"]==index_name].sort_values("inception").copy()
    if sub.empty:
        st.info("Keine ETFs hinterlegt."); return
    top,statuscol=st.columns([.64,.36])
    with top: st.markdown(f"### {index_name}")
    status=statuscol.empty(); bar=statuscol.progress(0)
    table=sub.copy(); table["Auflage"]=table["inception"].map(fmt_date)
    table["Mitglieder"]=INDEX_INFO[index_name]["members"]
    table["JustETF"]=table["isin"].map(lambda x:f"https://www.justetf.com/de/etf-profile.html?isin={x}")
    show=table[["etf_name","isin","Auflage","Mitglieder","ter","distribution","JustETF"]].rename(columns={"etf_name":"ETF","isin":"ISIN","ter":"TER","distribution":"Ertragsverwendung"})
    st.dataframe(show.style.set_properties(**{"color":"#111827","background-color":"#fff"}).format({"TER":"{:.2f}%"}),width="stretch",height=compact_height(len(show)),hide_index=True,column_config={"JustETF":st.column_config.LinkColumn("Link",display_text="Öffnen")})
    resolved=[]; warnings=[]; n=len(sub)
    for i,(_,row) in enumerate(sub.iterrows(),1):
        status.caption(f"ETF-Daten · {i-1} von {n}")
        rr,ww=resolve_rows_cached(index_name,(row["etf_name"],)); resolved+=rr; warnings+=ww
        bar.progress(int(i/n*100))
    status.caption(f"ETF-Daten geladen · {n} von {n} · 100 %")
    for w in warnings: st.warning(w)
    if resolved:
        render_outputs_v8(resolved,f"dlg_{abs(hash(index_name))}",f"dlg_focus_{abs(hash(index_name))}")


def parse_share_classes_v8(value):
    out=[]
    for x in [s.strip() for s in str(value).split(",") if s.strip()]:
        out.append("Auslandslistings / ADRs" if x in {"ADRs","Foreign listings","Auslandslistings"} else x)
    return frozenset(out)


def tech_category(title,rows,key,offset=0):
    items=rows["etf_name"].tolist(); selected=ensure_selected(key,items)
    with st.expander(title,expanded=False):
        for j,(_,row) in enumerate(rows.iterrows()):
            name=row["etf_name"]; active=name in selected; color=PALETTE[(offset+j)%len(PALETTE)]
            proxy=MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes_v8(row["share_classes"]),"–")
            with st.container(border=True):
                if st.button(f"{dot_for(offset+j)}  {name}",key=f"techbtn_{key}_{name}",type="primary" if active else "secondary",use_container_width=True):
                    toggle_selected(key,name,items)
                st.markdown(
                    f"• **Index:** {row['index_name']}  \n"
                    f"• **Aktienklassen:** {row['share_classes']}  \n"
                    f"• **Mitglieder:** {row['members']}  \n"
                    f"• **Market Proxy (Benchmark für IR/TE):** {proxy}  \n"
                    f"• **TER:** {row['ter']:.2f}%"
                )
                _,link=st.columns([.74,.26])
                with link: st.link_button("ETF-Link",row["source_url"],use_container_width=True)
    return list(selected)


def render_tech(status_host):
    tech=tech_registry_cached().copy(); selected=[]
    a=tech[tech["universe"]=="All Shares"]
    if not a.empty: selected+=tech_category("All Shares",a,"t_all",0)
    l,r=st.columns(2,gap="large")
    with l:
        o=tech[tech["universe"]=="Onshore"]
        if not o.empty: selected+=tech_category("Onshore",o,"t_on",len(a))
    with r:
        o=tech[tech["universe"]=="Offshore"]
        if not o.empty: selected+=tech_category("Offshore",o,"t_off",len(a)+len(tech[tech["universe"]=="Onshore"]))
    if not selected:
        st.info("Tech-ETFs auswählen."); return
    resolved=[]; warnings=[]; n=len(selected); txt=status_host.empty(); bar=status_host.progress(0)
    for i,name in enumerate(selected,1):
        txt.caption(f"Marktdaten · {i-1} von {n}")
        rr,ww=resolve_tech_cached((name,)); resolved+=rr; warnings+=ww; bar.progress(int(i/n*100))
    txt.caption(f"Marktdaten geladen · {n} von {n} · 100 %")
    for w in warnings: st.warning(w)
    if not resolved: return
    meta=tech.set_index("etf_name"); bmap={}; bseries={}
    for item in resolved:
        if item.etf_name not in meta.index: continue
        proxy=MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes_v8(meta.loc[item.etf_name,"share_classes"]))
        if not proxy: continue
        try:
            b=resolve_index_cached(proxy); bcol=f"__BENCH__{item.label}"; bmap[item.label]=bcol; bseries[bcol]=b.series_eur
        except Exception: pass
    render_outputs_v8(resolved,"tech","tech_focus",bmap,bseries)


# ----- page -----
st.title("China ETF Dashboard")
nav,status_col=st.columns([.58,.42],vertical_alignment="center")
with nav:
    page=st.segmented_control("Bereich",["Market ETFs vergleichen","Tech ETFs vergleichen"],selection_mode="single",default=st.session_state.get("page","Market ETFs vergleichen"),key="v8_page",label_visibility="collapsed") or "Market ETFs vergleichen"
st.caption("Version v8")

if page=="Market ETFs vergleichen":
    selected,dialog=market_tree()
    resolved=[]; warnings=[]; n=len(selected)
    with status_col:
        txt=st.empty(); bar=st.progress(0 if n else 100)
    for i,name in enumerate(selected,1):
        txt.caption(f"Marktdaten · {i-1} von {n}")
        try: resolved.append(resolve_index_cached(name))
        except Exception as exc: warnings.append(f"{name}: {exc}")
        bar.progress(int(i/n*100) if n else 100)
    txt.caption(f"Marktdaten geladen · {n} von {n} · 100 %")
    for w in warnings: st.warning(w)
    render_outputs_v8(resolved,"market","market_focus")
    if dialog: etf_dialog(dialog)
else:
    render_tech(status_col)

with st.expander("Zusätzliche Einstellungen"):
    st.toggle("Nach Kapitalertragsteuer (vereinfacht)",key="after_tax")
    c1,c2,c3=st.columns(3)
    with c1: st.number_input("Kapitalertragsteuer",0.0,1.0,step=.0025,format="%.4f",key="base_rate")
    with c2: st.number_input("Solidaritätszuschlag auf Steuer",0.0,.2,step=.005,format="%.3f",key="soli")
    with c3: st.number_input("Teilfreistellung Aktienfonds",0.0,1.0,step=.05,format="%.2f",key="teilfreistellung")
