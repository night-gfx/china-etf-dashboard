from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

from src.data import (
    combine_series,
    load_registry,
    resolve_oldest_available_for_index,
    resolve_selected_rows,
)
from src.dashboard_ui import (
    CHART_CONFIG,
    annual_volatility,
    cagr,
    common_max_frame,
    drawdown_figure,
    fmt_date,
    heatmap_styles,
    max_drawdown,
    performance_figure,
    render_standard,
    sharpe,
    sortino,
    style_metrics,
    tracking_error_and_ir,
)
from src.metrics import calendar_returns
from src.tax import effective_german_equity_etf_tax_rate

ROOT = Path(__file__).resolve().parent
TECH_PATH = ROOT / "data_tech_etfs.csv"

st.set_page_config(
    page_title="China ETF Index Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

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
    "MSCI China All Shares Stock Connect Select": "ca. 700+",
    "S&P China 500": "500",
    "FTSE China 30/18 Capped": "ca. 900+",
    "MSCI China": "ca. 550+",
    "MSCI China ex A Shares": "ca. 450+",
    "Dow Jones China Offshore 50": "50",
    "FTSE China 50": "50",
    "CSI Overseas China Internet": "ca. 30–50",
    "MSCI China A": "ca. 500+",
    "CSI A 500": "500",
    "MSCI China A Inclusion": "ca. 400+",
    "CSI 300": "300",
    "S&P China A 300": "300",
    "SSE Science and Technology Innovation Board 50": "50",
    "ChiNext 50 Capped": "50",
}

UNIVERSE_BENCHMARK_INDEX = {
    "All Shares": "MSCI China All Shares Stock Connect Select",
    "Offshore": "Dow Jones China Offshore 50",
    "Onshore": "MSCI China A Inclusion",
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
            "Aktienklassen": ", ".join(sorted(INDEX_SHARE_CLASSES.get(name, set()))),
            "Mitglieder": INDEX_MEMBERS.get(name, "–"),
            "Proxy-ETF (längste Historie)": r["etf_name"],
            "TER": r["ter"],
            "Auflage": fmt_date(r["inception"]),
            "Index-URL": r["index_url"],
        })
    return pd.DataFrame(rows)


def tech_metrics(frame: pd.DataFrame, meta: pd.DataFrame, benchmarks: dict[str, pd.Series], benchmark_labels: dict[str, str], rf: float) -> pd.DataFrame:
    meta = meta.set_index("label")
    rows = []
    for label in frame.columns:
        if label not in meta.index:
            continue
        s = frame[label].dropna()
        universe = meta.loc[label, "universe"]
        b = benchmarks.get(universe)
        if b is None or b.empty:
            te, ir, ir_start = np.nan, np.nan, None
        else:
            te, ir, ir_start = tracking_error_and_ir(s, b)
        cr = calendar_returns(s)
        dd = max_drawdown(s)
        cg = cagr(s)
        rows.append({
            "ETF (Index)": label,
            "Universum": universe,
            "Benchmark": benchmark_labels.get(universe, "–"),
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


registry = registry_cached()
index_order = (
    registry[["index_order", "index_name"]]
    .drop_duplicates()
    .sort_values("index_order")["index_name"]
    .tolist()
)
if "selected_etf_index" not in st.session_state:
    st.session_state.selected_etf_index = index_order[0]

after_tax = st.session_state.after_tax
rf = st.session_state.rf
effective_tax = effective_german_equity_etf_tax_rate(
    st.session_state.base_rate,
    st.session_state.soli,
    st.session_state.teilfreistellung,
)

st.title("China ETF Dashboard")
index_tab, etf_tab, tech_tab = st.tabs(["Indizes vergleichen", "ETFs vergleichen", "Tech ETFs vergleichen"])

with index_tab:
    left, right = st.columns([0.34, 0.66], gap="large")
    with left:
        st.markdown("#### Auswahl")
        scope = st.pills(
            "Index-Hierarchie",
            ["Alle", "All Shares", "Onshore", "Offshore"],
            selection_mode="single",
            key="index_scope",
        ) or "Alle"
        classes = st.pills(
            "Zulässige Anlageklassen",
            SHARE_CLASS_ORDER,
            selection_mode="multi",
            key="selected_share_classes",
        ) or []

    allowed = set(classes)
    selected_indices = [
        i for i in index_order
        if INDEX_SHARE_CLASSES.get(i, set()).issubset(allowed)
        and (scope == "Alle" or INDEX_SCOPE.get(i) == scope)
    ]

    with right:
        st.markdown("#### Index-Informationen")
        overview = index_overview(selected_indices, registry)
        if overview.empty:
            st.info("Keine Indizes für diese Auswahl.")
        else:
            st.dataframe(
                overview.style.format({"TER": "{:.2f}%"}).apply(heatmap_styles, reverse=True, subset=["TER"]),
                width="stretch",
                hide_index=True,
                column_config={"Index-URL": st.column_config.LinkColumn(display_text="Index öffnen")},
            )

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
        labels = {x.label: x.index_name for x in resolved}
        render_standard(resolved, benchmark.label, labels, after_tax, effective_tax, rf, "indices")

with etf_tab:
    left, right = st.columns([0.34, 0.66], gap="large")
    with left:
        selected_index = st.pills(
            "Index",
            index_order,
            selection_mode="single",
            key="selected_etf_index",
        ) or index_order[0]
    sub = registry[registry["index_name"] == selected_index].sort_values("inception")
    names = sub["etf_name"].tolist()
    with right:
        st.markdown("#### ETF-Informationen")
        table = sub[["etf_name", "isin", "inception", "ter", "distribution", "index_url"]].copy()
        table["inception"] = table["inception"].map(fmt_date)
        table = table.rename(columns={
            "etf_name": "ETF", "isin": "ISIN", "inception": "Auflage", "ter": "TER",
            "distribution": "Ertragsverwendung", "index_url": "Index-URL",
        })
        st.dataframe(
            table.style.format({"TER": "{:.2f}%"}).apply(heatmap_styles, reverse=True, subset=["TER"]),
            width="stretch",
            hide_index=True,
            column_config={"Index-URL": st.column_config.LinkColumn(display_text="Index öffnen")},
        )
    resolved, warnings = resolve_rows_cached(selected_index, tuple(names))
    for warning in warnings:
        st.warning(warning)
    if resolved:
        benchmark = min(resolved, key=lambda x: x.inception)
        labels = {x.label: x.etf_name for x in resolved}
        render_standard(resolved, benchmark.label, labels, after_tax, effective_tax, rf, "etfs")

with tech_tab:
    tech = tech_registry_cached()
    st.markdown("### China-Tech-ETFs")
    st.caption(
        "Mehrere ETFs und Anteilsklassen auf demselben Index bleiben separat. Information Ratio und Tracking Error werden gegen den breiten Proxy-ETF des jeweiligen Ausgangsuniversums gerechnet."
    )
    scope = st.pills(
        "Ausgangsuniversum",
        ["Alle", "All Shares", "Onshore", "Offshore"],
        selection_mode="single",
        key="tech_scope",
    ) or "Alle"
    filtered = tech if scope == "Alle" else tech[tech["universe"] == scope]
    chosen = st.multiselect(
        "Tech-ETFs",
        filtered["etf_name"].tolist(),
        default=filtered["etf_name"].tolist(),
        key="tech_etfs",
    )
    selected = filtered[filtered["etf_name"].isin(chosen)].copy()

    if not selected.empty:
        table = selected[[
            "etf_name", "index_name", "universe", "share_classes", "members", "isin",
            "inception", "ter", "distribution", "source_url",
        ]].copy()
        table["Benchmark"] = table["universe"].map(UNIVERSE_BENCHMARK_INDEX)
        table["inception"] = table["inception"].map(fmt_date)
        table = table.rename(columns={
            "etf_name": "ETF", "index_name": "Index", "universe": "Universum",
            "share_classes": "Aktienklassen", "members": "Mitglieder", "isin": "ISIN",
            "inception": "Auflage", "ter": "TER", "distribution": "Ertragsverwendung",
            "source_url": "Quelle",
        })
        st.dataframe(
            table.style.format({"TER": "{:.2f}%"}).apply(heatmap_styles, reverse=True, subset=["TER"]),
            width="stretch",
            hide_index=True,
            column_config={"Quelle": st.column_config.LinkColumn(display_text="ETF öffnen")},
        )

        resolved, warnings = resolve_tech_cached(tuple(chosen))
        for warning in warnings:
            st.warning(warning)

        if resolved:
            raw = combine_series(resolved)
            frame = common_max_frame(raw, after_tax, effective_tax)
            labels = {x.label: x.etf_name for x in resolved}

            benchmark_series = {}
            benchmark_labels = {}
            for universe in sorted(set(selected["universe"])):
                broad_index = UNIVERSE_BENCHMARK_INDEX[universe]
                try:
                    b = resolve_index_cached(broad_index)
                    benchmark_labels[universe] = b.label
                    b_raw = pd.DataFrame({b.label: b.series_eur})
                    b_frame = common_max_frame(b_raw, after_tax, effective_tax)
                    benchmark_series[universe] = b_frame[b.label]
                except Exception as exc:
                    st.warning(f"Benchmark {universe}: {exc}")

            benchmark_text = " · ".join(
                f"{u}: {benchmark_labels.get(u, UNIVERSE_BENCHMARK_INDEX[u])}"
                for u in sorted(set(selected["universe"]))
            )
            st.info(f"Benchmarks für Information Ratio / Tracking Error — {benchmark_text}")
            if not frame.empty:
                st.caption(f"Vergleichszeitraum: MAX · {fmt_date(frame.index.min())} – {fmt_date(frame.index.max())}")
                c1, c2 = st.columns(2, gap="large")
                with c1:
                    st.markdown("#### Wertentwicklung")
                    st.plotly_chart(performance_figure(frame, labels), width="stretch", config=CHART_CONFIG, key="tech_perf")
                with c2:
                    st.markdown("#### Drawdown")
                    st.plotly_chart(drawdown_figure(frame, labels), width="stretch", config=CHART_CONFIG, key="tech_dd")

                meta = selected.copy()
                meta["label"] = meta["etf_name"] + " (" + meta["index_name"] + ")"
                metrics = tech_metrics(frame, meta, benchmark_series, benchmark_labels, rf)
                st.markdown("#### Kennzahlen je Tech-ETF")
                st.dataframe(
                    style_metrics(metrics, {"Tracking Error p.a.", "Volatilität p.a."}),
                    width="stretch",
                    height=520,
                )

st.divider()
with st.expander("Zusätzliche Einstellungen"):
    st.markdown(
        "**Vergleichszeitraum:** MAX. Alle Vergleiche werden automatisch auf das maximale gemeinsame Datenfenster der dargestellten Serien gesetzt."
    )
    c1, c2 = st.columns(2)
    with c1:
        st.toggle("Nach Kapitalertragsteuer (vereinfacht)", key="after_tax")
    with c2:
        st.number_input(
            "Risikofreier Zins p.a. für Sharpe",
            min_value=-0.10, max_value=0.20, step=0.005, format="%.3f", key="rf",
        )
    c1, c2, c3 = st.columns(3)
    with c1:
        st.number_input("Kapitalertragsteuer", min_value=0.0, max_value=1.0, step=0.0025, format="%.4f", key="base_rate")
    with c2:
        st.number_input("Solidaritätszuschlag auf Steuer", min_value=0.0, max_value=0.20, step=0.005, format="%.3f", key="soli")
    with c3:
        st.number_input("Teilfreistellung Aktienfonds", min_value=0.0, max_value=1.0, step=0.05, format="%.2f", key="teilfreistellung")

    current_tax = effective_german_equity_etf_tax_rate(
        st.session_state.base_rate, st.session_state.soli, st.session_state.teilfreistellung
    )
    st.caption(f"Effektiver Steuersatz auf positive Gewinne: {current_tax:.4%}")
    st.markdown(
        """
**Charts.** Wertentwicklung ist logarithmisch. Drawdown bleibt linear. Gitternetzlinien sind entfernt. Scroll-/Touchpad-Zoom ist aktiviert; Doppelklick setzt den Chart zurück.

**Total Return.** Yahoo `Adj Close` dient als Total-Return-Näherung und berücksichtigt Ausschüttungen und Splits.

**Tech-Benchmarks.** All Shares = MSCI China All Shares Stock Connect Select; Offshore = Dow Jones China Offshore 50; Onshore = MSCI China A Inclusion. Jeweils wird der in der Indexübersicht verwendete ETF mit der längsten verfügbaren Historie herangezogen.
        """
    )
