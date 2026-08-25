from __future__ import annotations
from pathlib import Path
import math
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data import load_registry, resolve_oldest_available_for_index, resolve_selected_rows
from src.metrics import cagr, max_drawdown, sortino, tracking_error_and_ir
from src.tax import effective_german_equity_etf_tax_rate, transform_frame

ROOT = Path(__file__).resolve().parent
TECH_PATH = ROOT / "data_tech_etfs.csv"

st.set_page_config(page_title="China ETF Dashboard", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

DEFAULTS = {
    "after_tax": True, "base_rate": 0.25, "soli": 0.055, "teilfreistellung": 0.30,
    "page": "Market ETFs vergleichen", "market_focus": None, "tech_focus": None,
    "market_corr_pair": None, "tech_corr_pair": None,
}
for k,v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown("""
<style>
.block-container{max-width:1620px;padding-top:1.1rem;padding-bottom:3rem}
html,body,p,label,h1,h2,h3,h4,h5,h6,[data-testid="stAppViewContainer"]{color:#111827!important}
[data-testid="stCaptionContainer"] p{color:#374151!important}
[data-testid="stDataFrame"] *{color:#111827!important}
[data-testid="stPlotlyChart"]{border:1px solid #e5e7eb;border-radius:.8rem;padding:.3rem;background:#fff}
.tree-card{border:1px solid #e5e7eb;border-radius:.75rem;padding:.7rem .85rem;margin:.25rem 0 .6rem 0;background:#fff}
.tree-title{font-weight:750;font-size:.98rem;line-height:1.25}
.tree-bullets{font-size:.84rem;line-height:1.45;color:#111827;margin-top:.35rem}
.swatch{display:inline-block;width:.75rem;height:.75rem;border-radius:50%;margin-right:.45rem;vertical-align:middle}
.branch-line{height:22px;border-left:2px solid #d1d5db;margin-left:50%}
.branch-head{text-align:center;font-weight:750;margin:.1rem 0 .4rem 0}
.statusbox{padding-top:.15rem}
</style>
""", unsafe_allow_html=True)

SHARE_CLASS_ORDER = ["A-Shares","B-Shares","H-Shares","Red Chips","P-Chips","Auslandslistings / ADRs"]
INDEX_SHARE_CLASSES = {
    "MSCI China All Shares Stock Connect Select": set(SHARE_CLASS_ORDER),
    "S&P China 500": set(SHARE_CLASS_ORDER),
    "FTSE China 30/18 Capped": set(SHARE_CLASS_ORDER),
    "MSCI China": set(SHARE_CLASS_ORDER),
    "MSCI China ex A Shares": {"B-Shares","H-Shares","Red Chips","P-Chips","Auslandslistings / ADRs"},
    "Dow Jones China Offshore 50": {"H-Shares","Red Chips","P-Chips","Auslandslistings / ADRs"},
    "FTSE China 50": {"H-Shares","Red Chips","P-Chips"},
    "CSI Overseas China Internet": {"H-Shares","P-Chips","Auslandslistings / ADRs"},
    "MSCI China A": {"A-Shares"},
    "CSI A 500": {"A-Shares"},
    "MSCI China A Inclusion": {"A-Shares"},
    "CSI 300": {"A-Shares"},
    "S&P China A 300": {"A-Shares"},
    "SSE Science and Technology Innovation Board 50": {"A-Shares"},
    "ChiNext 50 Capped": {"A-Shares"},
}
INDEX_SCOPE = {
    "MSCI China All Shares Stock Connect Select":"All Shares","S&P China 500":"All Shares",
    "FTSE China 30/18 Capped":"All Shares","MSCI China":"All Shares",
    "MSCI China ex A Shares":"Offshore","Dow Jones China Offshore 50":"Offshore",
    "FTSE China 50":"Offshore","CSI Overseas China Internet":"Offshore",
    "MSCI China A":"Onshore","CSI A 500":"Onshore","MSCI China A Inclusion":"Onshore",
    "CSI 300":"Onshore","S&P China A 300":"Onshore",
    "SSE Science and Technology Innovation Board 50":"Onshore","ChiNext 50 Capped":"Onshore",
}
INDEX_INFO = {
    "MSCI China All Shares Stock Connect Select":{"url":"https://www.msci.com/indexes/index/732716/msci-china-all-shares-stock-connect-select-index","members":"576","segment":"Breit; Large & Mid Cap","weight":"Free-Float-Marktkapitalisierung","rebalance":"4× p.a.","special":"A-Shares nur Stock-Connect-fähig; zusätzlich B/H/Red/P und Foreign Listings."},
    "S&P China 500":{"url":"https://www.spglobal.com/spdji/en/indices/equity/sp-china-500","members":"500","segment":"Breit; Large & Mid Cap","weight":"Float-adjusted Market Cap","rebalance":"2× p.a.","special":"Sektor-repräsentatives China-Universum mit Onshore und Offshore."},
    "FTSE China 30/18 Capped":{"url":"https://www.lseg.com/en/ftse-russell","members":"variabel","segment":"Breit; Large & Mid Cap","weight":"Free-Float Market Cap; 30/18-Capping","rebalance":"4× p.a.","special":"Konzentrationsbegrenzung nach 30/18-Logik."},
    "MSCI China":{"url":"https://www.msci.com/indexes/index/302400/msci-china-index","members":"576","segment":"Breit; Large & Mid Cap","weight":"Free-Float-Marktkapitalisierung","rebalance":"4× p.a.","special":"A/B/H-Shares, Red/P Chips und Foreign Listings; A-Shares mit Inclusion Factor."},
    "MSCI China ex A Shares":{"url":"https://www.msci.com/","members":"variabel","segment":"Breit Offshore; Large & Mid Cap","weight":"Free-Float-Marktkapitalisierung","rebalance":"4× p.a.","special":"China ohne inländische A-Shares."},
    "Dow Jones China Offshore 50":{"url":"https://www.spglobal.com/spdji/tc/documents/methodologies/methodology-dj-china.pdf","members":"50","segment":"Offshore Large Cap","weight":"Float-adjusted Market Cap; 10%-Cap","rebalance":"4× p.a.","special":"50 große geeignete chinesische Offshore-Unternehmen."},
    "FTSE China 50":{"url":"https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-china-50-index-english-ground-rules.pdf","members":"50","segment":"Hongkong Large Cap","weight":"Free-Float Market Cap","rebalance":"4× p.a.","special":"50 große und liquide China-Unternehmen an der HKEX."},
    "CSI Overseas China Internet":{"url":"https://www.csindex.com.cn/","members":"≈ 30–50","segment":"Offshore Internet / Tech","weight":"Free-Float Market Cap","rebalance":"2× p.a.","special":"China-basierte Internetunternehmen mit primärer Notierung außerhalb Mainland China."},
    "MSCI China A":{"url":"https://www.msci.com/","members":"variabel","segment":"Breit Onshore; Large & Mid Cap","weight":"Free-Float-Marktkapitalisierung","rebalance":"4× p.a.","special":"Breites inländisches A-Share-Universum."},
    "CSI A 500":{"url":"https://www.csindex.com.cn/","members":"500","segment":"Breit Onshore; Mid/Large","weight":"Free-Float Market Cap","rebalance":"2× p.a.","special":"Breitere Branchenabdeckung als CSI 300."},
    "MSCI China A Inclusion":{"url":"https://www.msci.com/","members":"≈ 400","segment":"Onshore; Stock-Connect A-Shares","weight":"Free-Float mit Inclusion Factor","rebalance":"4× p.a.","special":"Spiegelt die MSCI-Einbeziehung von A-Shares wider."},
    "CSI 300":{"url":"https://www.csindex.com.cn/","members":"300","segment":"Onshore Large & Mid Cap","weight":"Free-Float Market Cap","rebalance":"2× p.a.","special":"300 große und liquide A-Shares aus Shanghai und Shenzhen."},
    "S&P China A 300":{"url":"https://www.spglobal.com/spdji/","members":"300","segment":"Onshore Large & Mid Cap","weight":"Float-adjusted Market Cap","rebalance":"2× p.a.","special":"300 liquide A-Shares als Mainland-China-Benchmark."},
    "SSE Science and Technology Innovation Board 50":{"url":"https://english.sse.com.cn/indices/indices/list/indexmethods/c/000688_000688hbooken_EN.pdf","members":"50","segment":"Onshore Tech; STAR Market","weight":"Market Cap & Liquidität","rebalance":"4× p.a.","special":"Technologie-/Innovationsfokus auf dem STAR Market."},
    "ChiNext 50 Capped":{"url":"http://www.cnindex.com.cn/en/module/pdf-detail.html?pdf=/docs/gz_399673_e.pdf&name=ChiNext%2050","members":"50","segment":"Onshore Growth / Tech","weight":"Free-Float Market Cap; Capped","rebalance":"4× p.a.","special":"Führende Wachstums-/Innovationsunternehmen des ChiNext-Markts."},
}
PALETTE=["#2563eb","#dc2626","#059669","#7c3aed","#ea580c","#0891b2","#be123c","#4f46e5","#65a30d","#a16207","#0f766e","#9333ea","#c2410c","#0369a1","#4d7c0f"]
MARKET_PROXY_BY_SIGNATURE={
    frozenset(SHARE_CLASS_ORDER):"MSCI China All Shares Stock Connect Select",
    frozenset({"B-Shares","H-Shares","Red Chips","P-Chips","Auslandslistings / ADRs"}):"MSCI China ex A Shares",
    frozenset({"H-Shares","Red Chips","P-Chips","Auslandslistings / ADRs"}):"Dow Jones China Offshore 50",
    frozenset({"H-Shares","Red Chips","P-Chips"}):"FTSE China 50",
    frozenset({"A-Shares"}):"MSCI China A Inclusion",
}

@st.cache_data(ttl=12*60*60, show_spinner=False)
def registry_cached():
    return load_registry()

@st.cache_data(ttl=12*60*60, show_spinner=False)
def tech_registry_cached():
    df=pd.read_csv(TECH_PATH, parse_dates=["inception"])
    df["label"]=df["etf_name"]+" ("+df["index_name"]+")"
    return df.sort_values(["universe","inception","etf_name"]).reset_index(drop=True)

@st.cache_data(ttl=6*60*60, show_spinner=False)
def resolve_index_cached(index_name):
    return resolve_oldest_available_for_index(index_name, registry_cached())

@st.cache_data(ttl=6*60*60, show_spinner=False)
def resolve_rows_cached(index_name, names):
    reg=registry_cached()
    sub=reg[(reg["index_name"]==index_name)&(reg["etf_name"].isin(names))]
    return resolve_selected_rows([r for _,r in sub.iterrows()])

@st.cache_data(ttl=6*60*60, show_spinner=False)
def resolve_tech_cached(names):
    reg=tech_registry_cached()
    sub=reg[reg["etf_name"].isin(names)]
    return resolve_selected_rows([r for _,r in sub.iterrows()])

def fmt_date(v):
    return "–" if v is None or pd.isna(v) else pd.Timestamp(v).strftime("%d.%m.%Y")

def share_text(name):
    return ", ".join(x for x in SHARE_CLASS_ORDER if x in INDEX_SHARE_CLASSES.get(name,set()))

def effective_tax():
    return effective_german_equity_etf_tax_rate(st.session_state.base_rate,st.session_state.soli,st.session_state.teilfreistellung)

def common_frame(series):
    raw=pd.DataFrame(series).sort_index()
    return transform_frame(raw, after_tax=st.session_state.after_tax, effective_tax_rate=effective_tax(), common_start=True)

def daily_returns(s):
    return s.dropna().pct_change(fill_method=None).dropna()

def vol(s):
    r=daily_returns(s)
    return r.std(ddof=1)*math.sqrt(252) if len(r)>1 else np.nan

def sharpe0(s):
    r=daily_returns(s)
    if len(r)<2 or r.std(ddof=1)==0:return np.nan
    return r.mean()/r.std(ddof=1)*math.sqrt(252)

def yearly_sharpe_matrix(frame, display):
    years=sorted({int(y) for c in frame.columns for y in frame[c].dropna().index.year})
    rows=[]
    for col in frame.columns:
        row={"":display.get(col,col)}
        s=frame[col].dropna()
        for y in years:
            sy=s[s.index.year==y]
            row[str(y)]=sharpe0(sy) if len(sy)>2 else np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("")

def total_stats(frame, display, benchmark_by_col=None):
    rows=[]
    for col in frame.columns:
        s=frame[col].dropna()
        if len(s)<2:continue
        cg=cagr(s); dd=max_drawdown(s)
        row={"":display.get(col,col),"CAGR p.a.":cg,"Volatilität p.a.":vol(s),"Sharpe Ratio":sharpe0(s),
             "Max. Drawdown":dd,"Sortino":sortino(s,0.0),"Calmar":cg/abs(dd) if dd and not np.isnan(dd) else np.nan}
        if benchmark_by_col and col in benchmark_by_col:
            b=benchmark_by_col[col]
            te,ir,_=tracking_error_and_ir(s,b)
            row["Tracking Error p.a."]=te; row["Information Ratio p.a."]=ir
        rows.append(row)
    return pd.DataFrame(rows).set_index("") if rows else pd.DataFrame()

def style_heat(df, focus=None):
    pct={"CAGR p.a.","Volatilität p.a.","Max. Drawdown","Tracking Error p.a."}
    nums={"Sharpe Ratio","Sortino","Calmar","Information Ratio p.a."}
    fmts={c:(lambda x: "–" if pd.isna(x) else f"{x:.2%}") for c in df.columns if c in pct}
    fmts.update({c:(lambda x: "–" if pd.isna(x) else f"{x:.2f}") for c in df.columns if c in nums or str(c).isdigit()})
    sty=df.style.format(fmts,na_rep="–").set_properties(**{"color":"#111827","background-color":"#ffffff"})
    numeric=df.select_dtypes(include="number").columns.tolist()
    if numeric:
        sty=sty.background_gradient(cmap="RdYlGn",subset=numeric,axis=0)
    if focus is not None and focus in df.index:
        sty=sty.apply(lambda row:["font-weight:800;border-top:2px solid #111827;border-bottom:2px solid #111827" if row.name==focus else "" for _ in row],axis=1)
    return sty

def base_layout(showlegend=False):
    return dict(showlegend=showlegend,hovermode="x unified",dragmode="zoom",height=520,plot_bgcolor="white",paper_bgcolor="white",
                font=dict(color="#111827"),margin=dict(l=50,r=18,t=18,b=45),
                xaxis=dict(showgrid=False,zeroline=False,autorange=True))

def line_fig(frame, colors, focus=None, dd=False, benchmark_map=None):
    fig=go.Figure()
    for col in frame.columns:
        if col.startswith("__BENCH__"):continue
        s=frame[col].dropna()
        y=(s/s.cummax()-1)*100 if dd else s
        width=4 if col==focus else 1.8
        fig.add_trace(go.Scatter(x=y.index,y=y,mode="lines",name=col,line=dict(width=width,color=colors.get(col)),customdata=[col]*len(y),
                                 hovertemplate=("%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra></extra>" if dd else "%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra></extra>")))
        if benchmark_map and col in benchmark_map and benchmark_map[col] in frame.columns:
            b=frame[benchmark_map[col]].dropna()
            by=(b/b.cummax()-1)*100 if dd else b
            fig.add_trace(go.Scatter(x=by.index,y=by,mode="lines",name="Market Proxy",line=dict(width=2,color=colors.get(col),dash="dash"),
                                     hovertemplate=("%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra>Market Proxy</extra>" if dd else "%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>Market Proxy</extra>")))
    yaxis=dict(showgrid=False,zeroline=False,autorange=True,type="linear" if dd else "log",title="Drawdown in %" if dd else "Indexiert (log)")
    fig.update_layout(**base_layout(False),yaxis=yaxis)
    return fig

def correlation_fig(frame, display, focus=None):
    rets=frame.pct_change(fill_method=None).dropna()
    corr=rets.corr()
    names=[display.get(c,c) for c in corr.columns]
    z=corr.values
    fig=go.Figure(go.Heatmap(z=z,x=names,y=names,zmin=-1,zmax=1,colorscale="RdYlGn",zmid=0,
                             text=np.round(z,2),texttemplate="%{text:.2f}",customdata=np.array([[f"{corr.index[i]}|||{corr.columns[j]}" for j in range(len(corr.columns))] for i in range(len(corr.index))],dtype=object),
                             hovertemplate="%{y} ↔ %{x}<br><b>%{z:.3f}</b><extra></extra>"))
    fig.update_layout(height=560,margin=dict(l=30,r=15,t=15,b=30),plot_bgcolor="white",paper_bgcolor="white",font=dict(color="#111827"))
    return fig

def rolling_corr_fig(frame,a,b,display):
    pair=frame[[a,b]].pct_change(fill_method=None).dropna()
    rolling=pair[a].rolling(252,min_periods=126).corr(pair[b])
    fig=go.Figure(go.Scatter(x=rolling.index,y=rolling,mode="lines",line=dict(width=2.2),hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.3f}</b><extra></extra>"))
    fig.update_layout(**base_layout(False),yaxis=dict(title=f"{display.get(a,a)} ↔ {display.get(b,b)}",showgrid=False,zeroline=True,range=[-1,1]))
    return fig

def update_focus_from_plot(event, label_map, state_key):
    try:
        pts=event.selection.points
        if pts:
            cd=pts[0].get("customdata")
            if cd in label_map:
                st.session_state[state_key]=label_map[cd]
    except Exception:
        pass

def update_focus_from_table(event, df, state_key):
    try:
        rows=event.selection.rows
        if rows:
            st.session_state[state_key]=df.index[rows[0]]
    except Exception:
        pass

registry=registry_cached()
index_order=registry[["index_order","index_name"]].drop_duplicates().sort_values("index_order")["index_name"].tolist()
INDEX_COLOR={n:PALETTE[i%len(PALETTE)] for i,n in enumerate(index_order)}

def index_card(name):
    info=INDEX_INFO[name]
    return f"""
    <div class="tree-card">
      <div class="tree-title"><span class="swatch" style="background:{INDEX_COLOR[name]}"></span><a href="{info['url']}" target="_blank">{name}</a></div>
      <div class="tree-bullets">
      • <b>Aktienklassen:</b> {share_text(name)}<br>
      • <b>Segment:</b> {info['segment']}<br>
      • <b>Mitglieder:</b> {info['members']}<br>
      • <b>Gewichtung:</b> {info['weight']}<br>
      • <b>Rebalancing:</b> {info['rebalance']}<br>
      • <b>Besonderheit:</b> {info['special']}
      </div>
    </div>"""

def render_tree():
    selected=[]; dialog=None
    allshares=[x for x in index_order if INDEX_SCOPE[x]=="All Shares"]
    onshore=[x for x in index_order if INDEX_SCOPE[x]=="Onshore"]
    offshore=[x for x in index_order if INDEX_SCOPE[x]=="Offshore"]
    st.markdown("### All Shares")
    for n in allshares:
        c0,c1,c2=st.columns([.06,.78,.16],vertical_alignment="center")
        with c0: chk=st.checkbox("x",value=True,key=f"sel_{n}",label_visibility="collapsed")
        with c1: st.markdown(index_card(n),unsafe_allow_html=True)
        with c2:
            if st.button("ETFs",key=f"btn_{n}",use_container_width=True):dialog=n
        if chk:selected.append(n)
    st.markdown('<div class="branch-line"></div>',unsafe_allow_html=True)
    left,right=st.columns(2,gap="large")
    for host,title,items in [(left,"Onshore",onshore),(right,"Offshore",offshore)]:
        with host:
            st.markdown(f'<div class="branch-head">{title}</div>',unsafe_allow_html=True)
            for n in items:
                c0,c1,c2=st.columns([.07,.73,.20],vertical_alignment="center")
                with c0: chk=st.checkbox("x",value=True,key=f"sel_{n}",label_visibility="collapsed")
                with c1: st.markdown(index_card(n),unsafe_allow_html=True)
                with c2:
                    if st.button("ETFs",key=f"btn_{n}",use_container_width=True):dialog=n
                if chk:selected.append(n)
    return selected,dialog

def render_outputs(resolved,key_prefix,focus_key,benchmark_map=None,benchmark_by_col=None):
    if not resolved:
        st.info("Keine verfügbaren Serien.");return
    series={x.label:x.series_eur for x in resolved}
    display={x.label:(x.index_name if key_prefix=="market" else x.etf_name) for x in resolved}
    colors={x.label:(INDEX_COLOR.get(x.index_name,PALETTE[i%len(PALETTE)]) if key_prefix=="market" else PALETTE[i%len(PALETTE)]) for i,x in enumerate(resolved)}
    if benchmark_map:
        for col,bcol in benchmark_map.items():
            if bcol in benchmark_by_col:
                series[bcol]=benchmark_by_col[bcol]
    frame=common_frame(series)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum.");return
    focus=st.session_state.get(focus_key)
    if focus not in [display.get(c,c) for c in frame.columns]:
        focus=None
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

    st.markdown("### Korrelogramm")
    corr_cols=[c for c in frame.columns if not c.startswith("__BENCH__")]
    corr_frame=frame[corr_cols]
    corr_event=st.plotly_chart(correlation_fig(corr_frame,display,focus_col),width="stretch",config={"displaylogo":False},key=f"{key_prefix}_corr",on_select="rerun",selection_mode="points")
    try:
        pts=corr_event.selection.points
        if pts:
            cd=pts[0].get("customdata")
            if cd and "|||" in cd:
                st.session_state[f"{key_prefix}_corr_pair"]=tuple(cd.split("|||",1))
    except Exception:
        pass
    st.markdown("### Rollierende 1-Jahres-Korrelation")
    pair=st.session_state.get(f"{key_prefix}_corr_pair")
    if not pair or pair[0] not in corr_frame.columns or pair[1] not in corr_frame.columns or pair[0]==pair[1]:
        if len(corr_cols)>=2: pair=(corr_cols[0],corr_cols[1])
    if pair and len(corr_cols)>=2:
        st.plotly_chart(rolling_corr_fig(corr_frame,pair[0],pair[1],display),width="stretch",config={"displaylogo":False,"scrollZoom":True},key=f"{key_prefix}_roll")
        st.caption("Paar wird durch Klick auf eine Zelle im Korrelogramm gewählt.")

    annual=yearly_sharpe_matrix(corr_frame,display)
    metric_bench = None
    if benchmark_map:
        metric_bench = {col: frame[bcol] for col, bcol in benchmark_map.items() if col in frame.columns and bcol in frame.columns}
    total=total_stats(corr_frame,display,metric_bench if key_prefix=="tech" else None)
    c1,c2=st.columns(2,gap="large")
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        ev=st.dataframe(style_heat(annual,focus),width="stretch",height=430,on_select="rerun",selection_mode="single-row",key=f"{key_prefix}_annual")
        update_focus_from_table(ev,annual,focus_key)
    with c2:
        st.markdown("#### Gesamtperformance")
        ev=st.dataframe(style_heat(total,focus),width="stretch",height=430,on_select="rerun",selection_mode="single-row",key=f"{key_prefix}_total")
        update_focus_from_table(ev,total,focus_key)

@st.dialog("ETFs des Index",width="large")
def market_etf_dialog(index_name):
    sub=registry[registry["index_name"]==index_name].sort_values("inception").copy()
    if sub.empty:
        st.info("Keine ETFs hinterlegt.");return
    top_left,top_right=st.columns([.62,.38],vertical_alignment="center")
    with top_left: st.markdown(f"### {index_name}")
    status=top_right.empty()
    table=sub.copy()
    table["Auflage"]=table["inception"].map(fmt_date)
    table["Mitglieder"]=INDEX_INFO[index_name]["members"]
    table["JustETF"]=table["isin"].map(lambda x:f"https://www.justetf.com/de/etf-profile.html?isin={x}")
    show=table[["etf_name","isin","Auflage","Mitglieder","ter","distribution","JustETF"]].rename(columns={"etf_name":"ETF","isin":"ISIN","ter":"TER","distribution":"Ertragsverwendung"})
    st.dataframe(show.style.set_properties(**{"color":"#111827","background-color":"#fff"}).format({"TER":"{:.2f}%"}),width="stretch",hide_index=True,column_config={"JustETF":st.column_config.LinkColumn("Link",display_text="Öffnen")})
    resolved=[];warnings=[];n=len(sub)
    bar=top_right.progress(0)
    for i,(_,row) in enumerate(sub.iterrows(),1):
        status.caption(f"ETF-Daten · {i-1} von {n}")
        rr,ww=resolve_rows_cached(index_name,(row["etf_name"],))
        resolved+=rr;warnings+=ww;bar.progress(int(i/n*100))
    status.caption(f"ETF-Daten geladen · {n} von {n} · 100 %")
    for w in warnings:st.warning(w)
    if resolved:
        render_outputs(resolved,f"dlg_{abs(hash(index_name))}","dialog_focus")

def parse_share_classes(value):
    out=[]
    for x in [s.strip() for s in str(value).split(",") if s.strip()]:
        out.append("Auslandslistings / ADRs" if x in {"ADRs","Foreign listings","Auslandslistings"} else x)
    return frozenset(out)

def render_tech(status_host):
    tech=tech_registry_cached().copy()
    selected=[]
    st.markdown("### Tech ETFs")
    for universe in ["All Shares","Onshore","Offshore"]:
        rows=tech[tech["universe"]==universe]
        if rows.empty:continue
        with st.expander(universe,expanded=True):
            for i,(_,row) in enumerate(rows.iterrows()):
                name=row["etf_name"]; proxy=MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(row["share_classes"]),"–")
                c0,c1=st.columns([.06,.94],vertical_alignment="center")
                with c0:chk=st.checkbox("x",value=False,key=f"tech_{name}",label_visibility="collapsed")
                with c1:
                    st.markdown(f"""<div class="tree-card"><div class="tree-title"><span class="swatch" style="background:{PALETTE[i%len(PALETTE)]}"></span><a href="{row['source_url']}" target="_blank">{name}</a></div>
                    <div class="tree-bullets">• <b>Index:</b> {row['index_name']}<br>• <b>Aktienklassen:</b> {row['share_classes']}<br>• <b>Mitglieder:</b> {row['members']}<br>• <b>Market Proxy:</b> {proxy}<br>• <b>TER:</b> {row['ter']:.2f}%</div></div>""",unsafe_allow_html=True)
                if chk:selected.append(name)
    if not selected:
        st.info("Tech-ETFs auswählen.");return
    resolved=[];warnings=[];n=len(selected);bar=status_host.progress(0);txt=status_host.empty()
    for i,name in enumerate(selected,1):
        txt.caption(f"Marktdaten · {i-1} von {n}")
        rr,ww=resolve_tech_cached((name,));resolved+=rr;warnings+=ww;bar.progress(int(i/n*100))
    txt.caption(f"Marktdaten geladen · {n} von {n} · 100 %")
    for w in warnings:st.warning(w)
    meta=tech[tech["etf_name"].isin(selected)].copy()
    bmap={};bseries={}
    if resolved:
        temp={x.label:x for x in resolved}
        for _,row in meta.iterrows():
            lab=row["etf_name"]+" ("+row["index_name"]+")"
            if lab not in temp:continue
            p=MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(row["share_classes"]))
            if not p:continue
            try:
                b=resolve_index_cached(p);bcol=f"__BENCH__{lab}";bmap[lab]=bcol;bseries[bcol]=b.series_eur
            except Exception:pass
        render_outputs(resolved,"tech","tech_focus",bmap,bseries)

st.title("China ETF Dashboard")
nav_col,status_col=st.columns([.58,.42],vertical_alignment="center")
with nav_col:
    page=st.segmented_control("Bereich",["Market ETFs vergleichen","Tech ETFs vergleichen"],selection_mode="single",default=st.session_state.page,key="page_selector",label_visibility="collapsed") or "Market ETFs vergleichen"
    st.session_state.page=page

if page=="Market ETFs vergleichen":
    selected,dialog=render_tree()
    if dialog:market_etf_dialog(dialog)
    resolved=[];warnings=[];n=len(selected)
    with status_col:
        txt=st.empty();bar=st.progress(0 if n else 100)
    for i,name in enumerate(selected,1):
        txt.caption(f"Marktdaten · {i-1} von {n}")
        try:resolved.append(resolve_index_cached(name))
        except Exception as exc:warnings.append(f"{name}: {exc}")
        bar.progress(int(i/n*100) if n else 100)
    txt.caption(f"Marktdaten geladen · {n} von {n} · 100 %")
    for w in warnings:st.warning(w)
    render_outputs(resolved,"market","market_focus")
else:
    render_tech(status_col)

with st.expander("Zusätzliche Einstellungen"):
    st.toggle("Nach Kapitalertragsteuer (vereinfacht)",key="after_tax")
    c1,c2,c3=st.columns(3)
    with c1:st.number_input("Kapitalertragsteuer",0.0,1.0,step=.0025,format="%.4f",key="base_rate")
    with c2:st.number_input("Solidaritätszuschlag auf Steuer",0.0,.2,step=.005,format="%.3f",key="soli")
    with c3:st.number_input("Teilfreistellung Aktienfonds",0.0,1.0,step=.05,format="%.2f",key="teilfreistellung")
