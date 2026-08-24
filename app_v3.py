from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data import combine_series, load_registry, resolve_oldest_available_for_index, resolve_selected_rows
from src.dashboard_ui import (
    CHART_CONFIG,
    annual_volatility,
    cagr,
    common_max_frame,
    fmt_date,
    heatmap_styles,
    max_drawdown,
    render_standard,
    sharpe,
    sortino,
    style_metrics,
    tracking_error_and_ir,
)
from src.metrics import calendar_returns, drawdown
from src.tax import effective_german_equity_etf_tax_rate, transform_frame

ROOT = Path(__file__).resolve().parent
TECH_PATH = ROOT / "data_tech_etfs.csv"

st.set_page_config(page_title="China ETF Index Dashboard", page_icon="📈", layout="wide", initial_sidebar_state="collapsed")

for key, value in {
    "after_tax": True,
    "base_rate": 0.25,
    "soli": 0.055,
    "teilfreistellung": 0.30,
    "rf": 0.02,
    "index_scope": "Alle",
    "tech_scope": "Alle",
}.items():
    if key not in st.session_state:
        st.session_state[key] = value

SHARE_CLASS_ORDER = ["A-Shares", "B-Shares", "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"]

INDEX_SHARE_CLASSES = {
    "MSCI China All Shares Stock Connect Select": set(SHARE_CLASS_ORDER),
    "S&P China 500": set(SHARE_CLASS_ORDER),
    "FTSE China 30/18 Capped": set(SHARE_CLASS_ORDER),
    "MSCI China": set(SHARE_CLASS_ORDER),
    "MSCI China ex A Shares": {"B-Shares", "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"},
    "Dow Jones China Offshore 50": {"H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"},
    "FTSE China 50": {"H-Shares", "Red Chips", "P-Chips"},
    "CSI Overseas China Internet": {"H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"},
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

INDEX_MEMBERS = {
    "MSCI China All Shares Stock Connect Select": "576",
    "S&P China 500": "500",
    "FTSE China 30/18 Capped": "–",
    "MSCI China": "576",
    "MSCI China ex A Shares": "166",
    "Dow Jones China Offshore 50": "50",
    "FTSE China 50": "50",
    "CSI Overseas China Internet": "ca. 30–50",
    "MSCI China A": "–",
    "CSI A 500": "500",
    "MSCI China A Inclusion": "–",
    "CSI 300": "300",
    "S&P China A 300": "300",
    "SSE Science and Technology Innovation Board 50": "50",
    "ChiNext 50 Capped": "50",
}

SIGNATURE_TO_BENCHMARK = {
    frozenset(SHARE_CLASS_ORDER): "MSCI China All Shares Stock Connect Select",
    frozenset({"B-Shares", "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"}): "MSCI China ex A Shares",
    frozenset({"H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs"}): "Dow Jones China Offshore 50",
    frozenset({"H-Shares", "Red Chips", "P-Chips"}): "FTSE China 50",
    frozenset({"A-Shares"}): "MSCI China A Inclusion",
}

if "selected_share_classes" not in st.session_state:
    st.session_state.selected_share_classes = SHARE_CLASS_ORDER.copy()

st.markdown(
    """
    <style>
      .block-container {max-width:1600px;padding-top:1.5rem;padding-bottom:3rem}
      html,body,p,label,h1,h2,h3,h4,h5,h6,[data-testid="stAppViewContainer"]{color:#111827!important}
      [data-testid="stCaptionContainer"] p{color:#6b7280!important}
      [data-baseweb="tab-list"]{gap:.5rem;border-bottom:1px solid #dfe5ec}
      [data-baseweb="tab"]{height:3.25rem;padding:0 1.25rem;font-weight:650}
      [data-testid="stPlotlyChart"]{border:1px solid #e2e8f0;border-radius:.75rem;padding:.35rem;background:white}
    </style>
    """,
    unsafe_allow_html=True,
)

@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def registry_cached():
    return load_registry()

@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def tech_registry_cached():
    df = pd.read_csv(TECH_PATH, parse_dates=["inception"])
    df = df.sort_values(["universe", "inception", "etf_name"]).reset_index(drop=True)
    df["label"] = df["etf_name"] + " (" + df["index_name"] + ")"
    return df

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def resolve_index_cached(index_name: str):
    return resolve_oldest_available_for_index(index_name, registry_cached())

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def resolve_rows_cached(index_name: str, names: tuple[str, ...]):
    reg = registry_cached()
    sub = reg[(reg["index_name"] == index_name) & (reg["etf_name"].isin(names))]
    return resolve_selected_rows([r for _, r in sub.iterrows()])

@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def resolve_tech_cached(names: tuple[str, ...]):
    reg = tech_registry_cached()
    sub = reg[reg["etf_name"].isin(names)]
    return resolve_selected_rows([r for _, r in sub.iterrows()])


def parse_share_classes(value: str) -> frozenset[str]:
    parts = [x.strip() for x in str(value).split(",") if x.strip()]
    normalized = ["Auslandslistings / ADRs" if x in {"ADRs", "Foreign listings", "Auslandslistings"} else x for x in parts]
    return frozenset(normalized)


def benchmark_index_for_share_classes(value: str) -> str | None:
    return SIGNATURE_TO_BENCHMARK.get(parse_share_classes(value))


def index_overview(names: list[str], registry: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name in names:
        sub = registry[registry["index_name"] == name].sort_values("inception")
        if sub.empty:
            continue
        r = sub.iloc[0]
        rows.append({
            "Index": name,
            "Universum": INDEX_SCOPE.get(name, "–"),
            "Aktienklassen": ", ".join(c for c in SHARE_CLASS_ORDER if c in INDEX_SHARE_CLASSES.get(name, set())),
            "Mitglieder": INDEX_MEMBERS.get(name, "–"),
            "Proxy-ETF (längste Historie)": r["etf_name"],
            "TER": r["ter"],
            "Auflage": fmt_date(r["inception"]),
            "Index-URL": r["index_url"],
        })
    return pd.DataFrame(rows)


def tech_metrics(frame: pd.DataFrame, meta: pd.DataFrame, benchmarks_by_label: dict[str, pd.Series], benchmark_labels: dict[str, str], rf: float) -> pd.DataFrame:
    meta = meta.set_index("label")
    rows = []
    for label in frame.columns:
        if label not in meta.index:
            continue
        s = frame[label].dropna()
        b = benchmarks_by_label.get(label)
        if b is None or b.empty:
            te, ir, ir_start = np.nan, np.nan, None
        else:
            te, ir, ir_start = tracking_error_and_ir(s, b)
        cr = calendar_returns(s)
        dd, cg = max_drawdown(s), cagr(s)
        rows.append({
            "ETF (Index)": label,
            "Universum": meta.loc[label, "universe"],
            "Aktienklassen": meta.loc[label, "share_classes"],
            "Benchmark": benchmark_labels.get(label, "–"),
            "IR-Start": fmt_date(ir_start),
            "Gesamtrendite": s.iloc[-1] / s.iloc[0] - 1,
            "CAGR p.a.": cg,
            "Information Ratio p.a.": ir,
            "Tracking Error p.a.": te,
            "Volatilität p.a.": annual_volatility(s),
            "Max. Drawdown": dd,
            "Sharpe": sharpe(s, rf),
            "Sortino": sortino(s, rf),
            "Calmar": cg / abs(dd) if dd and not np.isnan(dd) else np.nan,
            "Bestes Jahr": cr.max() if not cr.empty else np.nan,
            "Schlechtestes Jahr": cr.min() if not cr.empty else np.nan,
        })
    return pd.DataFrame(rows).set_index("ETF (Index)") if rows else pd.DataFrame()


def tech_figures(frame: pd.DataFrame, selected_labels: list[str], benchmark_columns: dict[str, str], display_labels: dict[str, str]):
    perf = go.Figure()
    dd_fig = go.Figure()
    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b", "#e377c2", "#7f7f7f", "#bcbd22", "#17becf"]

    for idx, label in enumerate(selected_labels):
        if label not in frame.columns:
            continue
        color = palette[idx % len(palette)]
        s = frame[label].dropna()
        perf.add_trace(go.Scatter(
            x=s.index, y=s, mode="lines", name=display_labels.get(label, label),
            line=dict(width=2.3, color=color),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>%{fullData.name}</extra>",
        ))
        dd = drawdown(s) * 100
        dd_fig.add_trace(go.Scatter(
            x=dd.index, y=dd, mode="lines", name=display_labels.get(label, label),
            line=dict(width=2.3, color=color),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra>%{fullData.name}</extra>",
        ))

        bcol = benchmark_columns.get(label)
        if bcol and bcol in frame.columns:
            b = frame[bcol].dropna()
            bname = f"Benchmark · {display_labels.get(bcol, bcol)}"
            perf.add_trace(go.Scatter(
                x=b.index, y=b, mode="lines", name=bname,
                line=dict(width=2.0, color=color, dash="dash"),
                hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>%{fullData.name}</extra>",
            ))
            bdd = drawdown(b) * 100
            dd_fig.add_trace(go.Scatter(
                x=bdd.index, y=bdd, mode="lines", name=bname,
                line=dict(width=2.0, color=color, dash="dash"),
                hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra>%{fullData.name}</extra>",
            ))

    common_layout = dict(
        hovermode="x unified", dragmode="zoom", height=560,
        plot_bgcolor="white", paper_bgcolor="white", font=dict(color="#111827"),
        legend=dict(orientation="h", yanchor="top", y=-0.17, xanchor="left", x=0, font=dict(size=9)),
        margin=dict(l=55, r=20, t=20, b=170),
        xaxis=dict(showgrid=False, zeroline=False, autorange=True),
    )
    perf.update_layout(**common_layout, yaxis=dict(title="Indexiert (Start = 100, logarithmisch)", showgrid=False, zeroline=False, type="log", autorange=True))
    dd_fig.update_layout(**common_layout, yaxis=dict(title="Drawdown in %", showgrid=False, zeroline=False, type="linear", autorange=True))
    return perf, dd_fig


registry = registry_cached()
index_order = registry[["index_order", "index_name"]].drop_duplicates().sort_values("index_order")["index_name"].tolist()
if "selected_etf_index" not in st.session_state:
    st.session_state.selected_etf_index = index_order[0]

after_tax = st.session_state.after_tax
rf = st.session_state.rf
effective_tax = effective_german_equity_etf_tax_rate(st.session_state.base_rate, st.session_state.soli, st.session_state.teilfreistellung)

st.title("China ETF Dashboard")
index_tab, etf_tab, tech_tab = st.tabs(["Indizes vergleichen", "ETFs vergleichen", "Tech ETFs vergleichen"])

with index_tab:
    left, right = st.columns([0.34, 0.66], gap="large")
    with left:
        st.markdown("#### Auswahl")
        scope = st.pills("Index-Hierarchie", ["Alle", "All Shares", "Onshore", "Offshore"], selection_mode="single", key="index_scope") or "Alle"
        classes = st.pills("Zulässige Anlageklassen", SHARE_CLASS_ORDER, selection_mode="multi", key="selected_share_classes") or []
    allowed = set(classes)
    selected_indices = [i for i in index_order if INDEX_SHARE_CLASSES.get(i, set()).issubset(allowed) and (scope == "Alle" or INDEX_SCOPE.get(i) == scope)]
    with right:
        st.markdown("#### Index-Informationen")
        overview = index_overview(selected_indices, registry)
        if overview.empty:
            st.info("Keine Indizes für diese Auswahl.")
        else:
            st.dataframe(overview.style.format({"TER": "{:.2f}%"}).apply(heatmap_styles, reverse=True, subset=["TER"]), width="stretch", hide_index=True, column_config={"Index-URL": st.column_config.LinkColumn(display_text="Index öffnen")})
    resolved, warnings = [], []
    with st.spinner("Yahoo-Finance-Daten werden geladen …"):
        for index_name in selected_indices:
            try:
                resolved.append(resolve_index_cached(index_name))
            except Exception as exc:
                warnings.append(f"{index_name}: {exc}")
    for warning in warnings:
        st.warning(warning)
    if resolved:
        benchmark = min(resolved, key=lambda x: x.inception)
        render_standard(resolved, benchmark.label, {x.label: x.index_name for x in resolved}, after_tax, effective_tax, rf, "indices")

with etf_tab:
    left, right = st.columns([0.34, 0.66], gap="large")
    with left:
        selected_index = st.pills("Index", index_order, selection_mode="single", key="selected_etf_index") or index_order[0]
    sub = registry[registry["index_name"] == selected_index].sort_values("inception")
    names = sub["etf_name"].tolist()
    with right:
        st.markdown("#### ETF-Informationen")
        table = sub[["etf_name", "isin", "inception", "ter", "distribution", "index_url"]].copy()
        table["inception"] = table["inception"].map(fmt_date)
        table = table.rename(columns={"etf_name": "ETF", "isin": "ISIN", "inception": "Auflage", "ter": "TER", "distribution": "Ertragsverwendung", "index_url": "Index-URL"})
        st.dataframe(table.style.format({"TER": "{:.2f}%"}).apply(heatmap_styles, reverse=True, subset=["TER"]), width="stretch", hide_index=True, column_config={"Index-URL": st.column_config.LinkColumn(display_text="Index öffnen")})
    resolved, warnings = resolve_rows_cached(selected_index, tuple(names))
    for warning in warnings:
        st.warning(warning)
    if resolved:
        benchmark = min(resolved, key=lambda x: x.inception)
        render_standard(resolved, benchmark.label, {x.label: x.etf_name for x in resolved}, after_tax, effective_tax, rf, "etfs")

with tech_tab:
    tech = tech_registry_cached()
    st.markdown("### China-Tech-ETFs")
    st.caption("Jeder Tech-Index wird gegen ein breites Ausgangsuniversum mit derselben zulässigen Share-Class-Menge verglichen. Die Benchmark erscheint im Chart in derselben Farbe wie der Tech-ETF, aber gestrichelt.")
    scope = st.pills("Ausgangsuniversum", ["Alle", "All Shares", "Onshore", "Offshore"], selection_mode="single", key="tech_scope") or "Alle"
    filtered = tech if scope == "Alle" else tech[tech["universe"] == scope]
    chosen = st.multiselect("Tech-ETFs", filtered["etf_name"].tolist(), default=filtered["etf_name"].tolist(), key="tech_etfs")
    selected = filtered[filtered["etf_name"].isin(chosen)].copy()

    if not selected.empty:
        selected["benchmark_index"] = selected["share_classes"].map(benchmark_index_for_share_classes)
        table = selected[["etf_name", "index_name", "universe", "share_classes", "members", "benchmark_index", "isin", "inception", "ter", "distribution", "source_url"]].copy()
        table["inception"] = table["inception"].map(fmt_date)
        table = table.rename(columns={
            "etf_name": "ETF", "index_name": "Index", "universe": "Universum", "share_classes": "Aktienklassen",
            "members": "Mitglieder", "benchmark_index": "Benchmark-Universum", "isin": "ISIN", "inception": "Auflage",
            "ter": "TER", "distribution": "Ertragsverwendung", "source_url": "Quelle",
        })
        st.dataframe(table.style.format({"TER": "{:.2f}%"}).apply(heatmap_styles, reverse=True, subset=["TER"]), width="stretch", hide_index=True, column_config={"Quelle": st.column_config.LinkColumn(display_text="ETF öffnen")})

        resolved, warnings = resolve_tech_cached(tuple(chosen))
        for warning in warnings:
            st.warning(warning)

        if resolved:
            resolved_by_label = {x.label: x for x in resolved}
            selected["label"] = selected["etf_name"] + " (" + selected["index_name"] + ")"
            selected = selected[selected["label"].isin(resolved_by_label)]
            benchmark_objects = {}
            for bidx in selected["benchmark_index"].dropna().unique():
                try:
                    benchmark_objects[bidx] = resolve_index_cached(bidx)
                except Exception as exc:
                    st.warning(f"Benchmark {bidx}: {exc}")

            combined = {}
            benchmark_columns = {}
            benchmark_labels = {}
            display_labels = {}
            selected_labels = []
            for _, row in selected.iterrows():
                label = row["label"]
                item = resolved_by_label[label]
                combined[label] = item.series_eur
                display_labels[label] = item.etf_name
                selected_labels.append(label)
                bidx = row["benchmark_index"]
                b = benchmark_objects.get(bidx)
                if b is None:
                    continue
                bcol = f"__BENCH__{label}"
                combined[bcol] = b.series_eur
                benchmark_columns[label] = bcol
                benchmark_labels[label] = b.label
                display_labels[bcol] = f"{b.etf_name} ({b.index_name})"

            raw = pd.DataFrame(combined).sort_index()
            full_frame = transform_frame(raw, after_tax=after_tax, effective_tax_rate=effective_tax, common_start=True)
            if not full_frame.empty:
                st.caption(f"Vergleichszeitraum: MAX · {fmt_date(full_frame.index.min())} – {fmt_date(full_frame.index.max())}")
                benchmark_text = " · ".join(f"{display_labels.get(label, label)} → {benchmark_labels.get(label, '–')}" for label in selected_labels)
                st.info(f"Benchmarks nach identischen Share Classes — {benchmark_text}")

                perf, dd_fig = tech_figures(full_frame, selected_labels, benchmark_columns, display_labels)
                c1, c2 = st.columns(2, gap="large")
                with c1:
                    st.markdown("#### Wertentwicklung")
                    st.plotly_chart(perf, width="stretch", config=CHART_CONFIG, key="tech_perf_v3")
                with c2:
                    st.markdown("#### Drawdown")
                    st.plotly_chart(dd_fig, width="stretch", config=CHART_CONFIG, key="tech_dd_v3")

                tech_only = full_frame[[c for c in selected_labels if c in full_frame.columns]]
                benchmarks_by_label = {label: full_frame[bcol] for label, bcol in benchmark_columns.items() if bcol in full_frame.columns}
                metrics = tech_metrics(tech_only, selected, benchmarks_by_label, benchmark_labels, rf)
                st.markdown("#### Kennzahlen je Tech-ETF")
                st.dataframe(style_metrics(metrics, {"Tracking Error p.a.", "Volatilität p.a."}), width="stretch", height=540)

st.divider()
with st.expander("Zusätzliche Einstellungen"):
    st.markdown("**Vergleichszeitraum:** MAX. Alle Vergleiche werden automatisch auf das maximale gemeinsame Datenfenster der dargestellten Serien gesetzt.")
    c1, c2 = st.columns(2)
    with c1:
        st.toggle("Nach Kapitalertragsteuer (vereinfacht)", key="after_tax")
    with c2:
        st.number_input("Risikofreier Zins p.a. für Sharpe", min_value=-0.10, max_value=0.20, step=0.005, format="%.3f", key="rf")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.number_input("Kapitalertragsteuer", min_value=0.0, max_value=1.0, step=0.0025, format="%.4f", key="base_rate")
    with c2:
        st.number_input("Solidaritätszuschlag auf Steuer", min_value=0.0, max_value=0.20, step=0.005, format="%.3f", key="soli")
    with c3:
        st.number_input("Teilfreistellung Aktienfonds", min_value=0.0, max_value=1.0, step=0.05, format="%.2f", key="teilfreistellung")
    current_tax = effective_german_equity_etf_tax_rate(st.session_state.base_rate, st.session_state.soli, st.session_state.teilfreistellung)
    st.caption(f"Effektiver Steuersatz auf positive Gewinne: {current_tax:.4%}")
    st.markdown("""
**Charts.** Wertentwicklung ist logarithmisch. Drawdown bleibt linear. Gitternetzlinien sind entfernt. Scroll-/Touchpad-Zoom ist aktiviert; Doppelklick setzt den Chart zurück.

**Total Return.** Yahoo `Adj Close` dient als Total-Return-Näherung und berücksichtigt Ausschüttungen und Splits.

**Tech-Benchmarks nach Share Classes.** Die Benchmark wird nicht mehr nur nach Onshore/Offshore/All Shares gewählt, sondern nach der konkreten zulässigen Share-Class-Menge des Tech-Index. Im Chart ist sie jeweils in derselben Farbe wie der zugehörige Tech-ETF und gestrichelt.
    """)
