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

st.set_page_config(
    page_title="China ETF Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

DEFAULTS = {
    "after_tax": True,
    "base_rate": 0.25,
    "soli": 0.055,
    "teilfreistellung": 0.30,
    "market_page": "Market ETFs vergleichen",
    "market_scope": "Alle",
    "tech_scope": "Alle",
}
for k, v in DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

st.markdown(
    """
    <style>
      .block-container {max-width: 1620px; padding-top: 1.25rem; padding-bottom: 3rem;}
      html, body, p, label, h1, h2, h3, h4, h5, h6,
      [data-testid="stAppViewContainer"] {color:#111827 !important;}
      [data-testid="stCaptionContainer"] p {color:#4b5563 !important;}
      [data-testid="stDataFrame"] * {color:#111827 !important;}
      [data-testid="stPlotlyChart"] {
        border:1px solid #e5e7eb; border-radius:.8rem; padding:.35rem; background:#fff;
      }
      .tree-row {
        padding:.25rem .15rem .35rem .15rem;
        border-bottom:1px solid #f0f2f5;
      }
      .tree-title {font-weight:700; font-size:1rem; line-height:1.25;}
      .tree-meta {font-size:.82rem; color:#4b5563; line-height:1.35;}
      .swatch {
        display:inline-block; width:.72rem; height:.72rem; border-radius:50%;
        margin-right:.45rem; vertical-align:middle;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

SHARE_CLASS_ORDER = [
    "A-Shares", "B-Shares", "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"
]

INDEX_SHARE_CLASSES = {
    "MSCI China All Shares Stock Connect Select": set(SHARE_CLASS_ORDER),
    "S&P China 500": set(SHARE_CLASS_ORDER),
    "FTSE China 30/18 Capped": set(SHARE_CLASS_ORDER),
    "MSCI China": set(SHARE_CLASS_ORDER),
    "MSCI China ex A Shares": {"B-Shares", "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"},
    "Dow Jones China Offshore 50": {"H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"},
    "FTSE China 50": {"H-Shares", "Red Chips", "P-Chips"},
    "CSI Overseas China Internet": {"H-Shares", "P-Chips", "Auslandslistings / ADRs"},
    "MSCI China A": {"A-Shares"},
    "CSI A 500": {"A-Shares"},
    "MSCI China A Inclusion": {"A-Shares"},
    "CSI 300": {"A-Shares"},
    "S&P China A 300": {"A-Shares"},
    "SSE Science and Technology Innovation Board 50": {"A-Shares"},
    "ChiNext 50 Capped": {"A-Shares"},
}

INDEX_SCOPE = {
    "MSCI China All Shares Stock Connect Select": "All Shares",
    "S&P China 500": "All Shares",
    "FTSE China 30/18 Capped": "All Shares",
    "MSCI China": "All Shares",
    "MSCI China ex A Shares": "Offshore",
    "Dow Jones China Offshore 50": "Offshore",
    "FTSE China 50": "Offshore",
    "CSI Overseas China Internet": "Offshore",
    "MSCI China A": "Onshore",
    "CSI A 500": "Onshore",
    "MSCI China A Inclusion": "Onshore",
    "CSI 300": "Onshore",
    "S&P China A 300": "Onshore",
    "SSE Science and Technology Innovation Board 50": "Onshore",
    "ChiNext 50 Capped": "Onshore",
}

INDEX_INFO = {
    "MSCI China All Shares Stock Connect Select": {
        "url": "https://www.msci.com/indexes/index/732716/msci-china-all-shares-stock-connect-select-index",
        "members": "576",
        "method": "Large & Mid Cap; Free-Float-Marktkapitalisierung",
        "review": "MSCI GIMI Reviews",
        "note": "A-Shares nur Stock-Connect-fähig; zusätzlich B/H/Red/P und Foreign Listings.",
    },
    "S&P China 500": {
        "url": "https://www.spglobal.com/spdji/en/indices/equity/sp-china-500",
        "members": "578",
        "method": "Float-adjusted Market Cap; sektor-repräsentativ",
        "review": "Halbjährlich (Juni/Dezember)",
        "note": "Breites China-Universum; A-Shares und Offshore-Listings sind zulässig.",
    },
    "FTSE China 30/18 Capped": {
        "url": "https://www.lseg.com/en/ftse-russell",
        "members": "variabel",
        "method": "Free-Float Market Cap, 30/18-Capping",
        "review": "FTSE Russell Reviews",
        "note": "Breites China-Universum mit Konzentrationsbegrenzung nach 30/18-Logik.",
    },
    "MSCI China": {
        "url": "https://www.msci.com/indexes/index/302400/msci-china-index",
        "members": "576",
        "method": "MSCI GIMI; Large & Mid Cap",
        "review": "Quartals-/Halbjahresreviews",
        "note": "A-, B- und H-Shares, Red/P Chips sowie Foreign Listings; A-Shares aktuell mit Inclusion Factor.",
    },
    "MSCI China ex A Shares": {
        "url": "https://www.msci.com/documents/10199/c843449c-94e5-4a55-a606-fd0b7f234acb",
        "members": "variabel",
        "method": "MSCI GIMI; ex A-Shares",
        "review": "Quartals-/Halbjahresreviews",
        "note": "China ohne inländische A-Shares; fokussiert auf Offshore-/nicht-A-Share-Klassen.",
    },
    "Dow Jones China Offshore 50": {
        "url": "https://www.spglobal.com/spdji/tc/documents/methodologies/methodology-dj-china.pdf",
        "members": "50",
        "method": "Float-adjusted Market Cap; 10%-Cap",
        "review": "Regelmäßige Rebalancings",
        "note": "Hongkong- und US-gelistete chinesische Unternehmen; die 50 größten geeigneten Titel.",
    },
    "FTSE China 50": {
        "url": "https://www.lseg.com/content/dam/ftse-russell/en_us/documents/ground-rules/ftse-china-50-index-english-ground-rules.pdf",
        "members": "50",
        "method": "Free-Float Market Cap; Large Cap",
        "review": "Quartalsweise",
        "note": "50 große und liquide chinesische Unternehmen an der Hong Kong Stock Exchange.",
    },
    "CSI Overseas China Internet": {
        "url": "https://www.csindex.com.cn/",
        "members": "≈ 30–50",
        "method": "Free-Float Market Cap; Internet-Fokus",
        "review": "Halbjährlich (Juni/Dezember)",
        "note": "China-basierte Internetunternehmen mit primärer Notierung außerhalb Mainland China.",
    },
    "MSCI China A": {
        "url": "https://www.msci.com/documents/10199/c843449c-94e5-4a55-a606-fd0b7f234acb",
        "members": "variabel",
        "method": "MSCI GIMI; A-Shares",
        "review": "Quartals-/Halbjahresreviews",
        "note": "Breites inländisches China-A-Share-Universum.",
    },
    "CSI A 500": {
        "url": "https://www.csindex.com.cn/",
        "members": "500",
        "method": "500 A-Shares; breitere Branchenabdeckung",
        "review": "Regelmäßige CSI Reviews",
        "note": "Breiterer A-Share-Markt als CSI 300; 500 liquide repräsentative Titel.",
    },
    "MSCI China A Inclusion": {
        "url": "https://www.msci.com/documents/10199/055bcdf8-25b7-3469-55f3-e17d5bc4bcd3",
        "members": "≈ 400",
        "method": "MSCI GIMI; Stock-Connect-fähige A-Shares",
        "review": "Quartals-/Halbjahresreviews",
        "note": "Spiegelt die schrittweise Einbeziehung chinesischer A-Shares in globale MSCI-Indizes.",
    },
    "CSI 300": {
        "url": "https://www.csindex.com.cn/",
        "members": "300",
        "method": "Free-Float Market Cap; Large/Mid Cap A-Shares",
        "review": "Halbjährlich",
        "note": "300 große und liquide A-Shares aus Shanghai und Shenzhen.",
    },
    "S&P China A 300": {
        "url": "https://www.spglobal.com/spdji/",
        "members": "300",
        "method": "Float-adjusted Market Cap; A-Shares",
        "review": "S&P China Index Reviews",
        "note": "300 liquide chinesische A-Shares als Mainland-China-Marktbenchmark.",
    },
    "SSE Science and Technology Innovation Board 50": {
        "url": "https://english.sse.com.cn/indices/indices/list/indexmethods/c/000688_000688hbooken_EN.pdf",
        "members": "50",
        "method": "STAR Market; Market Cap & Liquidität",
        "review": "Regelmäßige SSE Reviews",
        "note": "50 große und liquide Titel des Shanghai STAR Market; Technologie-/Innovationsfokus.",
    },
    "ChiNext 50 Capped": {
        "url": "http://www.cnindex.com.cn/en/module/pdf-detail.html?pdf=/docs/gz_399673_e.pdf&name=ChiNext%2050",
        "members": "50",
        "method": "ChiNext 50; Capped",
        "review": "Regelmäßige Shenzhen/CNI Reviews",
        "note": "50 führende Wachstums-/Innovationsunternehmen des ChiNext-Markts.",
    },
}

PALETTE = [
    "#2563eb", "#dc2626", "#059669", "#7c3aed", "#ea580c",
    "#0891b2", "#be123c", "#4f46e5", "#65a30d", "#a16207",
    "#0f766e", "#9333ea", "#c2410c", "#0369a1", "#4d7c0f",
]

MARKET_PROXY_BY_SIGNATURE = {
    frozenset(SHARE_CLASS_ORDER): "MSCI China All Shares Stock Connect Select",
    frozenset({"B-Shares", "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"}): "MSCI China ex A Shares",
    frozenset({"H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"}): "Dow Jones China Offshore 50",
    frozenset({"H-Shares", "Red Chips", "P-Chips"}): "FTSE China 50",
    frozenset({"H-Shares", "P-Chips", "Auslandslistings / ADRs"}): "Dow Jones China Offshore 50",
    frozenset({"A-Shares"}): "MSCI China A Inclusion",
}

@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def registry_cached() -> pd.DataFrame:
    return load_registry()

@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def tech_registry_cached() -> pd.DataFrame:
    df = pd.read_csv(TECH_PATH, parse_dates=["inception"])
    df = df.sort_values(["universe", "inception", "etf_name"]).reset_index(drop=True)
    df["label"] = df["etf_name"] + " (" + df["index_name"] + ")"
    return df

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def resolve_index_cached(index_name: str):
    return resolve_oldest_available_for_index(index_name, registry_cached())

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def resolve_market_etfs_cached(index_name: str, names: tuple[str, ...]):
    reg = registry_cached()
    sub = reg[(reg["index_name"] == index_name) & reg["etf_name"].isin(names)]
    return resolve_selected_rows([r for _, r in sub.iterrows()])

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def resolve_tech_cached(names: tuple[str, ...]):
    reg = tech_registry_cached()
    sub = reg[reg["etf_name"].isin(names)]
    return resolve_selected_rows([r for _, r in sub.iterrows()])

def fmt_date(v) -> str:
    if v is None or pd.isna(v):
        return "–"
    return pd.Timestamp(v).strftime("%d.%m.%Y")

def share_text(index_name: str) -> str:
    values = INDEX_SHARE_CLASSES.get(index_name, set())
    return ", ".join(x for x in SHARE_CLASS_ORDER if x in values) or "–"

def common_frame(series_dict: dict[str, pd.Series], after_tax: bool, tax_rate: float) -> pd.DataFrame:
    if not series_dict:
        return pd.DataFrame()
    raw = pd.DataFrame(series_dict).sort_index()
    return transform_frame(raw, after_tax=after_tax, effective_tax_rate=tax_rate, common_start=True)

def load_indices_with_progress(index_names: list[str]):
    resolved, warnings = [], []
    if not index_names:
        return resolved, warnings
    host = st.empty()
    bar = st.progress(0)
    total = len(index_names)
    for i, name in enumerate(index_names, start=1):
        host.caption(f"Lade {i} von {total}: {name} · {round((i-1)/total*100)} %")
        try:
            resolved.append(resolve_index_cached(name))
        except Exception as exc:
            warnings.append(f"{name}: {exc}")
        bar.progress(int(i / total * 100))
    host.caption(f"Marktdaten geladen · {total} von {total} · 100 %")
    return resolved, warnings

TRADING_DAYS = 252

def daily_returns(s: pd.Series) -> pd.Series:
    return s.dropna().pct_change(fill_method=None).dropna()

def ann_vol(s: pd.Series) -> float:
    r = daily_returns(s)
    return r.std(ddof=1) * math.sqrt(TRADING_DAYS) if len(r) > 1 else np.nan

def sharpe_zero_rf(s: pd.Series) -> float:
    r = daily_returns(s)
    if len(r) < 2:
        return np.nan
    vol = r.std(ddof=1) * math.sqrt(TRADING_DAYS)
    if not vol or pd.isna(vol):
        return np.nan
    return (r.mean() * TRADING_DAYS) / vol

def calmar(s: pd.Series) -> float:
    cg, dd = cagr(s), max_drawdown(s)
    return cg / abs(dd) if dd and not pd.isna(dd) else np.nan

def annual_stats(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in frame.columns:
        s = frame[col].dropna()
        for year, y in s.groupby(s.index.year):
            if len(y) < 2:
                continue
            rows.append({
                "Serie": col,
                "Jahr": int(year),
                "Rendite": y.iloc[-1] / y.iloc[0] - 1,
                "Volatilität p.a.": ann_vol(y),
                "Sharpe Ratio": sharpe_zero_rf(y),
            })
    return pd.DataFrame(rows)

def total_stats(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for col in frame.columns:
        s = frame[col].dropna()
        if len(s) < 2:
            continue
        rows.append({
            "Serie": col,
            "CAGR p.a.": cagr(s),
            "Volatilität p.a.": ann_vol(s),
            "Sharpe Ratio": sharpe_zero_rf(s),
            "Max. Drawdown": max_drawdown(s),
            "Sortino": sortino(s, 0.0),
            "Calmar": calmar(s),
        })
    return pd.DataFrame(rows).set_index("Serie") if rows else pd.DataFrame()

def tech_total_stats(tech_frame: pd.DataFrame, proxy_by_tech: dict[str, pd.Series]) -> pd.DataFrame:
    rows = []
    for col in tech_frame.columns:
        s = tech_frame[col].dropna()
        if len(s) < 2:
            continue
        b = proxy_by_tech.get(col)
        te, ir, _ = tracking_error_and_ir(s, b.dropna()) if b is not None and not b.empty else (np.nan, np.nan, None)
        rows.append({
            "Serie": col,
            "CAGR p.a.": cagr(s),
            "Volatilität p.a.": ann_vol(s),
            "Sharpe Ratio": sharpe_zero_rf(s),
            "Max. Drawdown": max_drawdown(s),
            "Sortino": sortino(s, 0.0),
            "Calmar": calmar(s),
            "Tracking Error p.a.": te,
            "Information Ratio p.a.": ir,
        })
    return pd.DataFrame(rows).set_index("Serie") if rows else pd.DataFrame()

def metric_style(df: pd.DataFrame, focus: str | None = None):
    pct_cols = {"Rendite", "CAGR p.a.", "Volatilität p.a.", "Max. Drawdown", "Tracking Error p.a."}
    sty = df.style.set_properties(**{"color": "#111827", "background-color": "#ffffff"})
    formats = {}
    for c in df.columns:
        if c in pct_cols:
            formats[c] = lambda x: "–" if pd.isna(x) else f"{x:.2%}"
        elif c in {"Sharpe Ratio", "Sortino", "Calmar", "Information Ratio p.a."}:
            formats[c] = lambda x: "–" if pd.isna(x) else f"{x:.2f}"
    sty = sty.format(formats, na_rep="–")
    if focus is not None:
        sty = sty.apply(
            lambda row: ["font-weight:800" if row.name == focus or row.get("Serie", None) == focus else "" for _ in row],
            axis=1,
        )
    return sty

def base_layout(log_y=False):
    return dict(
        hovermode="x unified", dragmode="zoom", height=525,
        plot_bgcolor="white", paper_bgcolor="white", font=dict(color="#111827"),
        margin=dict(l=55, r=20, t=20, b=45), showlegend=False,
        xaxis=dict(showgrid=False, zeroline=False, autorange=True),
        yaxis=dict(showgrid=False, zeroline=False, autorange=True, type="log" if log_y else "linear"),
    )

CHART_CONFIG = {"displaylogo": False, "scrollZoom": True, "doubleClick": "reset+autosize", "responsive": True}

def line_fig(frame: pd.DataFrame, colors: dict[str, str], focus: str | None, drawdown=False, dashed: set[str] | None = None):
    fig = go.Figure()
    dashed = dashed or set()
    for col in frame.columns:
        s = frame[col].dropna()
        y = (s / s.cummax() - 1) * 100 if drawdown else s
        fig.add_trace(go.Scatter(
            x=y.index, y=y, mode="lines", name=col,
            line=dict(color=colors.get(col, "#6b7280"), width=4.0 if col == focus else (2.1 if col not in dashed else 1.8), dash="dash" if col in dashed else "solid"),
            hovertemplate=("%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra>%{fullData.name}</extra>" if drawdown else "%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>%{fullData.name}</extra>"),
        ))
    layout = base_layout(log_y=not drawdown)
    layout["yaxis"]["title"] = "Drawdown in %" if drawdown else "Indexiert (Start = 100, logarithmisch)"
    fig.update_layout(**layout)
    return fig

def correlation_fig(frame: pd.DataFrame, display_names: dict[str, str]) -> go.Figure:
    returns = frame.pct_change(fill_method=None).dropna(how="all")
    corr = returns.corr()
    labels = [display_names.get(x, x) for x in corr.columns]
    fig = go.Figure(go.Heatmap(
        z=corr.values, x=labels, y=labels, zmin=-1, zmax=1, zmid=0,
        text=np.round(corr.values, 2), texttemplate="%{text:.2f}",
        hovertemplate="%{y} ↔ %{x}<br>Korrelation: %{z:.3f}<extra></extra>", colorbar=dict(title="ρ"),
    ))
    fig.update_layout(height=520, margin=dict(l=40, r=20, t=20, b=90), paper_bgcolor="white", plot_bgcolor="white", font=dict(color="#111827"))
    return fig

def rolling_corr_fig(frame: pd.DataFrame, a: str, b: str, display_names: dict[str, str]) -> go.Figure:
    pair = frame[[a, b]].pct_change(fill_method=None).dropna()
    rolling = pair[a].rolling(252, min_periods=126).corr(pair[b])
    fig = go.Figure(go.Scatter(x=rolling.index, y=rolling, mode="lines", line=dict(width=2.2), hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.3f}</b><extra></extra>"))
    fig.update_layout(**base_layout(False), yaxis=dict(title=f"Rollierende 1J-Korrelation<br>{display_names.get(a,a)} ↔ {display_names.get(b,b)}", showgrid=False, zeroline=True, range=[-1, 1]))
    return fig

registry = registry_cached()
index_order = registry[["index_order", "index_name"]].drop_duplicates().sort_values("index_order")["index_name"].tolist()
INDEX_COLOR = {name: PALETTE[i % len(PALETTE)] for i, name in enumerate(index_order)}

def render_index_tree() -> tuple[list[str], str | None]:
    st.markdown("### Auswahl")
    scope = st.pills("Markt-Hierarchie", ["Alle", "All Shares", "Onshore", "Offshore"], selection_mode="single", key="market_scope") or "Alle"
    visible = [x for x in index_order if scope == "Alle" or INDEX_SCOPE.get(x) == scope]
    selected = []
    dialog_request = None
    for group in ["All Shares", "Onshore", "Offshore"]:
        group_items = [x for x in visible if INDEX_SCOPE.get(x) == group]
        if not group_items:
            continue
        with st.expander(f"{group} · {len(group_items)} Indizes", expanded=True):
            for name in group_items:
                info = INDEX_INFO.get(name, {})
                c0, c1, c2 = st.columns([0.08, 0.74, 0.18], vertical_alignment="center")
                with c0:
                    chosen = st.checkbox("Auswählen", value=True, key=f"market_select_{name}", label_visibility="collapsed")
                with c1:
                    st.markdown(f"""
                        <div class="tree-row">
                          <div class="tree-title">
                            <span class="swatch" style="background:{INDEX_COLOR[name]}"></span>
                            <a href="{info.get('url','#')}" target="_blank">{name}</a>
                          </div>
                          <div class="tree-meta">
                            Aktienklassen: {share_text(name)} · Mitglieder: {info.get('members','–')}<br>
                            {info.get('method','–')} · Review: {info.get('review','–')}<br>
                            {info.get('note','')}
                          </div>
                        </div>
                        """, unsafe_allow_html=True)
                with c2:
                    if st.button("ETFs anzeigen", key=f"show_etfs_{name}", use_container_width=True):
                        dialog_request = name
                if chosen:
                    selected.append(name)
    return selected, dialog_request

def focus_picker(selected: list[str], key: str, label: str) -> str | None:
    if not selected:
        return None
    current = st.session_state.get(key)
    if current not in selected:
        st.session_state[key] = selected[0]
    return st.selectbox(label, selected, key=key)

def render_market_outputs(resolved, focus_index_name: str | None, key_prefix: str):
    if not resolved:
        st.info("Bitte mindestens einen verfügbaren Index auswählen.")
        return
    series, display, colors, label_to_index = {}, {}, {}, {}
    for item in resolved:
        series[item.label] = item.series_eur
        display[item.label] = item.index_name
        colors[item.label] = INDEX_COLOR.get(item.index_name, "#6b7280")
        label_to_index[item.label] = item.index_name
    tax_rate = effective_german_equity_etf_tax_rate(st.session_state.base_rate, st.session_state.soli, st.session_state.teilfreistellung)
    frame = common_frame(series, st.session_state.after_tax, tax_rate)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum verfügbar.")
        return
    focus_label = next((lab for lab, idx in label_to_index.items() if idx == focus_index_name), None)
    st.caption(f"Vergleichszeitraum: MAX · {fmt_date(frame.index.min())} – {fmt_date(frame.index.max())}")
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        st.plotly_chart(line_fig(frame, colors, focus_label), width="stretch", config=CHART_CONFIG, key=f"{key_prefix}_perf")
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(line_fig(frame, colors, focus_label, drawdown=True), width="stretch", config=CHART_CONFIG, key=f"{key_prefix}_dd")
    annual = annual_stats(frame).copy()
    if not annual.empty:
        annual["Serie"] = annual["Serie"].map(display)
        annual = annual.sort_values(["Jahr", "Serie"], ascending=[False, True])
    total = total_stats(frame).rename(index=display)
    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        if annual.empty:
            st.info("Keine Jahresdaten verfügbar.")
        else:
            st.dataframe(metric_style(annual, focus_index_name), width="stretch", hide_index=True, height=430)
    with c2:
        st.markdown("#### Gesamtperformance")
        st.dataframe(metric_style(total, focus_index_name), width="stretch", height=430)
    st.markdown("#### Korrelation")
    c1, c2 = st.columns([0.55, 0.45], gap="large")
    with c1:
        st.plotly_chart(correlation_fig(frame, display), width="stretch", config=CHART_CONFIG, key=f"{key_prefix}_corr")
    with c2:
        cols = list(frame.columns)
        if len(cols) >= 2:
            a = st.selectbox("Serie A", cols, format_func=lambda x: display.get(x, x), key=f"{key_prefix}_corr_a")
            options_b = [x for x in cols if x != a]
            b = st.selectbox("Serie B", options_b, format_func=lambda x: display.get(x, x), key=f"{key_prefix}_corr_b")
            st.plotly_chart(rolling_corr_fig(frame, a, b, display), width="stretch", config=CHART_CONFIG, key=f"{key_prefix}_rollcorr")
        else:
            st.info("Für eine rollierende Korrelation werden mindestens zwei Serien benötigt.")

@st.dialog("ETFs des Index vergleichen", width="large")
def market_etf_dialog(index_name: str):
    st.markdown(f"### {index_name}")
    sub = registry[registry["index_name"] == index_name].sort_values("inception").copy()
    if sub.empty:
        st.info("Keine ETFs hinterlegt.")
        return
    names = sub["etf_name"].tolist()
    chosen = st.multiselect("ETFs auswählen", names, default=names, key=f"dialog_etfs_{index_name}")
    shown = sub[sub["etf_name"].isin(chosen)].copy()
    if not shown.empty:
        shown["JustETF"] = shown["isin"].map(lambda x: f"https://www.justetf.com/de/etf-profile.html?isin={x}")
        shown["Auflage"] = shown["inception"].map(fmt_date)
        table = shown[["etf_name", "isin", "Auflage", "ter", "distribution", "JustETF"]].rename(columns={"etf_name": "ETF", "isin": "ISIN", "ter": "TER", "distribution": "Ertragsverwendung"})
        sty = table.style.set_properties(**{"color":"#111827","background-color":"#ffffff"}).format({"TER":"{:.2f}%"})
        st.dataframe(sty, width="stretch", hide_index=True, column_config={"JustETF": st.column_config.LinkColumn("JustETF", display_text="Öffnen")})
    if not chosen:
        return
    focus_name = st.selectbox("Hervorheben", chosen, key=f"dialog_focus_{index_name}")
    status = st.empty(); bar = st.progress(0)
    resolved, warnings = [], []
    rows = sub[sub["etf_name"].isin(chosen)]
    total_n = len(rows)
    for i, (_, row) in enumerate(rows.iterrows(), start=1):
        status.caption(f"Lade ETF {i} von {total_n}: {row['etf_name']}")
        rr, ww = resolve_market_etfs_cached(index_name, (row["etf_name"],))
        resolved.extend(rr); warnings.extend(ww); bar.progress(int(i / total_n * 100))
    status.caption("ETF-Daten geladen · 100 %")
    for w in warnings: st.warning(w)
    if not resolved: return
    series = {x.label: x.series_eur for x in resolved}
    display = {x.label: x.etf_name for x in resolved}
    color_map = {x.label: PALETTE[i % len(PALETTE)] for i, x in enumerate(resolved)}
    tax_rate = effective_german_equity_etf_tax_rate(st.session_state.base_rate, st.session_state.soli, st.session_state.teilfreistellung)
    frame = common_frame(series, st.session_state.after_tax, tax_rate)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum."); return
    focus_label = next((x.label for x in resolved if x.etf_name == focus_name), None)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Wertentwicklung")
        st.plotly_chart(line_fig(frame, color_map, focus_label), width="stretch", config=CHART_CONFIG, key=f"dlg_perf_{index_name}")
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(line_fig(frame, color_map, focus_label, drawdown=True), width="stretch", config=CHART_CONFIG, key=f"dlg_dd_{index_name}")
    annual = annual_stats(frame); annual["Serie"] = annual["Serie"].map(display)
    total_df = total_stats(frame).rename(index=display)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        st.dataframe(metric_style(annual, focus_name), width="stretch", hide_index=True, height=400)
    with c2:
        st.markdown("#### Gesamtperformance")
        st.dataframe(metric_style(total_df, focus_name), width="stretch", height=400)
    st.markdown("#### Korrelation")
    c1, c2 = st.columns([0.55, 0.45])
    with c1:
        st.plotly_chart(correlation_fig(frame, display), width="stretch", config=CHART_CONFIG, key=f"dlg_corr_{index_name}")
    with c2:
        cols = list(frame.columns)
        if len(cols) >= 2:
            a = st.selectbox("Serie A", cols, format_func=lambda x: display.get(x, x), key=f"dlg_a_{index_name}")
            bopts = [x for x in cols if x != a]
            b = st.selectbox("Serie B", bopts, format_func=lambda x: display.get(x, x), key=f"dlg_b_{index_name}")
            st.plotly_chart(rolling_corr_fig(frame, a, b, display), width="stretch", config=CHART_CONFIG, key=f"dlg_roll_{index_name}")

def parse_share_classes(value: str) -> frozenset[str]:
    parts = [x.strip() for x in str(value).split(",") if x.strip()]
    norm = []
    for x in parts:
        if x in {"ADRs", "Foreign listings", "Auslandslistings"}: x = "Auslandslistings / ADRs"
        norm.append(x)
    return frozenset(norm)

def market_proxy_for_tech(row: pd.Series) -> str | None:
    return MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes(row["share_classes"]))

def render_tech_page():
    tech = tech_registry_cached().copy()
    st.markdown("## Tech ETFs vergleichen")
    scope = st.pills("Ausgangsuniversum", ["Alle", "All Shares", "Onshore", "Offshore"], selection_mode="single", key="tech_scope") or "Alle"
    if scope != "Alle": tech = tech[tech["universe"] == scope]
    if tech.empty:
        st.info("Keine Tech-ETFs für diese Auswahl."); return
    chosen = []; tech_colors = {}
    for i, (_, row) in enumerate(tech.iterrows()): tech_colors[row["etf_name"]] = PALETTE[i % len(PALETTE)]
    st.markdown("### Auswahl")
    for universe in ["All Shares", "Onshore", "Offshore"]:
        rows = tech[tech["universe"] == universe]
        if rows.empty: continue
        with st.expander(f"{universe} · {len(rows)} ETFs", expanded=True):
            for _, row in rows.iterrows():
                name = row["etf_name"]; proxy = market_proxy_for_tech(row) or "–"
                c0, c1 = st.columns([0.08, 0.92], vertical_alignment="center")
                with c0:
                    sel = st.checkbox("Auswählen", value=False, key=f"tech_select_{row['isin']}", label_visibility="collapsed")
                with c1:
                    st.markdown(f"""
                        <div class="tree-row"><div class="tree-title"><span class="swatch" style="background:{tech_colors[name]}"></span><a href="{row['source_url']}" target="_blank">{name}</a></div>
                        <div class="tree-meta">Index: {row['index_name']} · Aktienklassen: {row['share_classes']} · Mitglieder: {row['members']}<br>
                        Market-Proxy: <b>{proxy}</b> · TER: {row['ter']:.2f}% · Auflage: {fmt_date(row['inception'])}</div></div>
                    """, unsafe_allow_html=True)
                if sel: chosen.append(name)
    if not chosen:
        st.info("Bitte mindestens einen Tech-ETF auswählen."); return
    focus_name = focus_picker(chosen, "tech_focus", "Hervorheben")
    status = st.empty(); bar = st.progress(0); resolved, warnings = [], []
    total_n = len(chosen)
    for i, name in enumerate(chosen, start=1):
        status.caption(f"Lade Tech-ETF {i} von {total_n}: {name}")
        rr, ww = resolve_tech_cached((name,)); resolved.extend(rr); warnings.extend(ww); bar.progress(int(i / total_n * 100))
    status.caption("Tech-Daten geladen · 100 %")
    for w in warnings: st.warning(w)
    if not resolved: return
    selected_meta = tech[tech["etf_name"].isin(chosen)].copy(); resolved_by_name = {x.etf_name: x for x in resolved}
    tax_rate = effective_german_equity_etf_tax_rate(st.session_state.base_rate, st.session_state.soli, st.session_state.teilfreistellung)
    combined = {}; display = {}; colors = {}; dashed = set(); tech_labels = []; proxy_series_by_tech_label = {}
    for _, row in selected_meta.iterrows():
        name = row["etf_name"]; item = resolved_by_name.get(name)
        if item is None: continue
        tech_label = item.label; combined[tech_label] = item.series_eur; display[tech_label] = name; colors[tech_label] = tech_colors[name]; tech_labels.append(tech_label)
        proxy_index = market_proxy_for_tech(row)
        if proxy_index:
            try:
                proxy = resolve_index_cached(proxy_index); proxy_label = f"Market Proxy · {name}"
                combined[proxy_label] = proxy.series_eur; display[proxy_label] = f"{proxy.index_name} · Proxy für {name}"; colors[proxy_label] = tech_colors[name]; dashed.add(proxy_label)
            except Exception as exc: st.warning(f"Market-Proxy {proxy_index}: {exc}")
    frame = common_frame(combined, st.session_state.after_tax, tax_rate)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum."); return
    for _, row in selected_meta.iterrows():
        name = row["etf_name"]; item = resolved_by_name.get(name)
        if item is None: continue
        proxy_label = f"Market Proxy · {name}"
        if proxy_label in frame.columns: proxy_series_by_tech_label[item.label] = frame[proxy_label]
    focus_label = next((x.label for x in resolved if x.etf_name == focus_name), None)
    st.caption(f"Vergleichszeitraum: MAX · {fmt_date(frame.index.min())} – {fmt_date(frame.index.max())}")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Wertentwicklung")
        st.plotly_chart(line_fig(frame, colors, focus_label, dashed=dashed), width="stretch", config=CHART_CONFIG, key="tech_perf_v4")
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(line_fig(frame, colors, focus_label, drawdown=True, dashed=dashed), width="stretch", config=CHART_CONFIG, key="tech_dd_v4")
    tech_frame = frame[[x for x in tech_labels if x in frame.columns]]
    annual = annual_stats(tech_frame); annual["Serie"] = annual["Serie"].map({x.label: x.etf_name for x in resolved})
    total_df = tech_total_stats(tech_frame, proxy_series_by_tech_label).rename(index={x.label: x.etf_name for x in resolved})
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Jahresperformance (Sharpe Ratio)")
        st.dataframe(metric_style(annual, focus_name), width="stretch", hide_index=True, height=430)
    with c2:
        st.markdown("#### Gesamtperformance inkl. Market-Proxy")
        st.dataframe(metric_style(total_df, focus_name), width="stretch", height=430)
    st.markdown("#### Korrelation")
    c1, c2 = st.columns([0.55, 0.45])
    with c1:
        dmap = {x.label: x.etf_name for x in resolved}
        st.plotly_chart(correlation_fig(tech_frame, dmap), width="stretch", config=CHART_CONFIG, key="tech_corr_v4")
    with c2:
        cols = list(tech_frame.columns)
        if len(cols) >= 2:
            dmap = {x.label: x.etf_name for x in resolved}
            a = st.selectbox("Serie A", cols, format_func=lambda x: dmap.get(x, x), key="tech_corr_a_v4")
            bopts = [x for x in cols if x != a]
            b = st.selectbox("Serie B", bopts, format_func=lambda x: dmap.get(x, x), key="tech_corr_b_v4")
            st.plotly_chart(rolling_corr_fig(tech_frame, a, b, dmap), width="stretch", config=CHART_CONFIG, key="tech_roll_v4")

st.title("China ETF Dashboard")
page = st.pills("Bereich", ["Market ETFs vergleichen", "Tech ETFs vergleichen"], selection_mode="single", key="market_page") or "Market ETFs vergleichen"

if page == "Market ETFs vergleichen":
    selected_indices, dialog_request = render_index_tree()
    if dialog_request: market_etf_dialog(dialog_request)
    if selected_indices:
        focus = focus_picker(selected_indices, "market_focus", "Hervorheben")
        resolved, warnings = load_indices_with_progress(selected_indices)
        for w in warnings: st.warning(w)
        render_market_outputs(resolved, focus, "market_v4")
else:
    render_tech_page()

st.divider()
with st.expander("Zusätzliche Einstellungen"):
    st.markdown("**Vergleichszeitraum:** MAX und immer gemeinsamer Datenzeitraum der dargestellten Serien.")
    st.toggle("Nach Kapitalertragsteuer (vereinfachte Szenariorechnung)", key="after_tax")
    c1, c2, c3 = st.columns(3)
    with c1: st.number_input("Kapitalertragsteuer", 0.0, 1.0, step=0.0025, format="%.4f", key="base_rate")
    with c2: st.number_input("Solidaritätszuschlag auf Steuer", 0.0, 0.20, step=0.005, format="%.3f", key="soli")
    with c3: st.number_input("Teilfreistellung Aktienfonds", 0.0, 1.0, step=0.05, format="%.2f", key="teilfreistellung")
    st.caption("Sharpe Ratio wird in den neuen Market-/ETF-Tabellen mit risikofreiem Zins = 0 berechnet. Information Ratio und Tracking Error erscheinen nur bei Tech-ETFs und beziehen sich auf den jeweils passendsten Market-Proxy.")
