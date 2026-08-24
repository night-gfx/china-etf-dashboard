from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.data import (
    combine_series,
    load_registry,
    resolve_oldest_available_for_index,
    resolve_selected_rows,
)
from src.metrics import drawdown, relative_table, total_period_table
from src.tax import effective_german_equity_etf_tax_rate, transform_frame


st.set_page_config(
    page_title="China ETF Index Dashboard",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

SETTING_DEFAULTS = {
    "common_start": True,
    "after_tax": True,
    "base_rate": 0.25,
    "soli": 0.055,
    "teilfreistellung": 0.30,
    "rf": 0.02,
}
for setting_key, setting_value in SETTING_DEFAULTS.items():
    if setting_key not in st.session_state:
        st.session_state[setting_key] = setting_value

SHARE_CLASS_ORDER = [
    "A-Shares",
    "B-Shares",
    "H-Shares",
    "Red Chips",
    "P-Chips",
    "Auslandslistings / ADRs",
]

# Eligible share classes according to the index providers' published index
# descriptions and methodologies. The filter below excludes an index as soon
# as one of its eligible share classes is deselected.
INDEX_SHARE_CLASSES = {
    "MSCI China All Shares Stock Connect Select": set(SHARE_CLASS_ORDER),
    "S&P China 500": set(SHARE_CLASS_ORDER),
    "FTSE China 30/18 Capped": set(SHARE_CLASS_ORDER),
    "MSCI China": set(SHARE_CLASS_ORDER),
    "MSCI China ex A Shares": {
        "B-Shares", "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs",
    },
    "Dow Jones China Offshore 50": {
        "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs",
    },
    "FTSE China 50": {"H-Shares", "Red Chips", "P-Chips"},
    "CSI Overseas China Internet": {
        "H-Shares", "Red Chips", "P-Chips", "Auslandslistings / ADRs",
    },
    "MSCI China A": {"A-Shares"},
    "CSI A 500": {"A-Shares"},
    "MSCI China A Inclusion": {"A-Shares"},
    "CSI 300": {"A-Shares"},
    "S&P China A 300": {"A-Shares"},
    "SSE Science and Technology Innovation Board 50": {"A-Shares"},
    "ChiNext 50 Capped": {"A-Shares"},
}

if "selected_share_classes" not in st.session_state:
    st.session_state.selected_share_classes = SHARE_CLASS_ORDER.copy()

st.markdown(
    """
    <style>
        .block-container { max-width: 1500px; padding-top: 2rem; padding-bottom: 3rem; }
        html, body, p, label, h1, h2, h3, h4, h5, h6,
        [data-testid="stAppViewContainer"], [data-testid="stSidebar"] {
            color: #111827 !important;
        }
        [data-testid="stCaptionContainer"] p { color: #6b7280 !important; }
        [data-baseweb="tab-list"] { gap: .5rem; border-bottom: 1px solid #dfe5ec; }
        [data-baseweb="tab"] { height: 3.25rem; padding: 0 1.25rem; font-weight: 650; }
        [data-testid="stPlotlyChart"] {
            border: 1px solid #e2e8f0; border-radius: .75rem;
            padding: .35rem; background: white;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=12 * 60 * 60, show_spinner=False)
def registry_cached() -> pd.DataFrame:
    return load_registry()


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def resolve_index_cached(index_name: str):
    return resolve_oldest_available_for_index(index_name, registry_cached())


@st.cache_data(ttl=6 * 60 * 60, show_spinner=False)
def resolve_rows_cached(index_name: str, etf_names: tuple[str, ...]):
    reg = registry_cached()
    subset = reg[(reg["index_name"] == index_name) & (reg["etf_name"].isin(etf_names))]
    rows = [row for _, row in subset.iterrows()]
    return resolve_selected_rows(rows)


def fmt_pct(value):
    return "–" if pd.isna(value) else f"{value:.2%}"


def fmt_num(value):
    return "–" if pd.isna(value) else f"{value:.2f}"


def heatmap_styles(series: pd.Series, reverse: bool = False) -> list[str]:
    numeric = pd.to_numeric(series, errors="coerce")
    valid = numeric.dropna()
    if valid.empty:
        return ["color: #111827" for _ in series]

    low, high = valid.min(), valid.max()
    styles = []
    for value in numeric:
        if pd.isna(value):
            styles.append("color: #111827")
            continue
        position = 0.5 if high == low else (value - low) / (high - low)
        if reverse:
            position = 1 - position
        if position <= 0.5:
            weight = position * 2
            start, end = (248, 190, 190), (255, 244, 176)
        else:
            weight = (position - 0.5) * 2
            start, end = (255, 244, 176), (183, 229, 190)
        rgb = tuple(round(a + (b - a) * weight) for a, b in zip(start, end))
        styles.append(f"background-color: rgb{rgb}; color: #111827")
    return styles


def style_metrics(
    df: pd.DataFrame,
    *,
    reverse_columns: set[str] | None = None,
    bold_index: str | None = None,
) -> pd.io.formats.style.Styler:
    reverse_columns = reverse_columns or set()
    pct_columns = {
        "Gesamtrendite", "CAGR p.a.", "Volatilität p.a.", "Max. Drawdown",
        "Tracking Error p.a.", "Bestes Jahr", "Schlechtestes Jahr",
    }
    num_columns = {"Sharpe", "Sortino", "Calmar", "Information Ratio p.a."}
    pct_columns.update(column for column in df.columns if column.isdigit())
    formatters = {column: fmt_pct for column in df.columns if column in pct_columns}
    formatters.update({column: fmt_num for column in df.columns if column in num_columns})

    styled = df.style.format(formatters, na_rep="–").set_properties(**{"color": "#111827"})
    for column in df.select_dtypes(include="number").columns:
        styled = styled.apply(
            heatmap_styles,
            reverse=column in reverse_columns,
            subset=[column],
        )
    if bold_index is not None and bold_index in df.index:
        styled = styled.apply(
            lambda row: [
                "font-weight: 750; border-top: 2px solid #111827; "
                "border-bottom: 2px solid #111827"
                if row.name == bold_index else ""
                for _ in row
            ],
            axis=1,
        )
    return styled


def style_relative(df: pd.DataFrame) -> pd.io.formats.style.Styler:
    return style_metrics(df, reverse_columns={"Tracking Error p.a."})


def style_total(df: pd.DataFrame, benchmark_label: str) -> pd.io.formats.style.Styler:
    return style_metrics(
        df,
        reverse_columns={"Volatilität p.a.", "Tracking Error p.a."},
        bold_index=benchmark_label,
    )


def chart_layout(yaxis_title: str, show_legend: bool) -> dict:
    return dict(
        yaxis_title=yaxis_title,
        xaxis_title=None,
        legend_title=None,
        showlegend=show_legend,
        hovermode="x unified",
        legend=dict(
            orientation="h",
            yanchor="top",
            y=-0.16,
            xanchor="left",
            x=0,
            entrywidth=145,
            entrywidthmode="pixels",
            font=dict(size=10, color="#111827"),
        ),
        margin=dict(l=55, r=20, t=20, b=145 if show_legend else 45),
        height=535,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#111827"),
    )


def performance_figure(
    frame: pd.DataFrame, labels: dict[str, str]
) -> go.Figure:
    fig = go.Figure()
    for column in frame.columns:
        series = frame[column].dropna()
        fig.add_trace(go.Scatter(
            x=series.index,
            y=series,
            mode="lines",
            name=labels.get(column, column),
            line=dict(width=2),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(**chart_layout("Indexiert (Start = 100)", True))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e8edf3", zeroline=False)
    return fig


def drawdown_figure(frame: pd.DataFrame, labels: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for column in frame.columns:
        dd = drawdown(frame[column]) * 100.0
        fig.add_trace(go.Scatter(
            x=dd.index,
            y=dd,
            mode="lines",
            name=labels.get(column, column),
            line=dict(width=2),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(**chart_layout("Drawdown in %", False))
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(gridcolor="#e8edf3", zeroline=False)
    return fig


def render_dashboard(
    *,
    mode: str,
    selected_indices: list[str],
    selected_index_for_etfs: str | None,
    selected_etfs: list[str],
    common_start: bool,
    after_tax: bool,
    effective_tax: float,
    rf: float,
    widget_key: str,
    date_container=None,
    show_date: bool = True,
) -> None:
    resolved = []
    warnings = []

    with st.spinner("Yahoo-Finance-Daten werden geladen …"):
        if mode == "indices":
            for index_name in selected_indices:
                try:
                    resolved.append(resolve_index_cached(index_name))
                except Exception as exc:
                    warnings.append(f"{index_name}: {exc}")
        elif selected_index_for_etfs and selected_etfs:
            resolved, warnings = resolve_rows_cached(
                selected_index_for_etfs, tuple(selected_etfs)
            )

    for warning in warnings:
        st.warning(warning)

    if not resolved:
        st.info("Bitte mindestens eine verfügbare Serie auswählen.")
        return

    benchmark_item = min(resolved, key=lambda item: item.inception)
    benchmark_label = benchmark_item.label
    raw = combine_series(resolved)
    if raw.empty:
        st.error("Keine Kursdaten verfügbar.")
        return

    if show_date:
        min_date = raw.dropna(how="all").index.min().date()
        max_date = raw.dropna(how="all").index.max().date()
        date_host = date_container if date_container is not None else st.container()
        with date_host:
            date_range = st.date_input(
                "Vergleichszeitraum",
                value=(min_date, max_date),
                min_value=min_date,
                max_value=max_date,
                key=f"date_range_{widget_key}",
            )
        if isinstance(date_range, tuple) and len(date_range) == 2:
            raw = raw.loc[pd.Timestamp(date_range[0]):pd.Timestamp(date_range[1])]

    frame = transform_frame(
        raw,
        after_tax=after_tax,
        effective_tax_rate=effective_tax,
        common_start=common_start,
    )
    if frame.empty:
        st.error("Im gewählten Zeitraum gibt es keinen gemeinsamen Datenbereich.")
        return

    if benchmark_label not in frame.columns:
        benchmark_item = min(
            [item for item in resolved if item.label in frame.columns],
            key=lambda item: item.inception,
        )
        benchmark_label = benchmark_item.label

    chart_labels = {
        item.label: item.index_name if mode == "indices" else item.etf_name
        for item in resolved
    }

    chart_config = {"displaylogo": False, "scrollZoom": True}
    performance_column, drawdown_column = st.columns(2, gap="large")
    with performance_column:
        st.markdown("#### Wertentwicklung")
        st.plotly_chart(
            performance_figure(frame, chart_labels),
            width="stretch",
            config=chart_config,
            key=f"performance_{widget_key}",
        )
    with drawdown_column:
        st.markdown("#### Drawdown")
        st.plotly_chart(
            drawdown_figure(frame, chart_labels),
            width="stretch",
            config=chart_config,
            key=f"drawdown_{widget_key}",
        )

    relative = relative_table(frame, benchmark_label)
    total = total_period_table(frame, benchmark_label, rf_annual=rf)
    if benchmark_label in total.index:
        total = pd.concat([total.loc[[benchmark_label]], total.drop(index=benchmark_label)])
    total = total.drop(columns=["Start", "Ende"], errors="ignore")
    preferred_total_columns = [
        "Gesamtrendite",
        "CAGR p.a.",
        "Information Ratio p.a.",
        "Tracking Error p.a.",
        "Volatilität p.a.",
        "Max. Drawdown",
        "Sharpe",
        "Sortino",
        "Calmar",
        "Bestes Jahr",
        "Schlechtestes Jahr",
    ]
    total = total[[
        column for column in preferred_total_columns if column in total.columns
    ]]

    year_columns = [column for column in relative.columns if column.isdigit()]
    marked_benchmark = f"★ BENCHMARK · {benchmark_label}"
    total = total.rename(index={benchmark_label: marked_benchmark})

    annual_column, risk_column = st.columns(2, gap="large")
    with annual_column:
        st.markdown("#### Jahresperformance (Information Ratio)")
        if year_columns:
            annual_columns = ["Information Ratio p.a.", *year_columns]
            annual = relative[[
                column for column in annual_columns if column in relative.columns
            ]]
            if benchmark_label in annual.index:
                annual = pd.concat([
                    annual.loc[[benchmark_label]], annual.drop(index=benchmark_label)
                ])
            annual_benchmark = f"★ BENCHMARK · {benchmark_label}"
            annual = annual.rename(index={benchmark_label: annual_benchmark})
            st.dataframe(
                style_metrics(annual, bold_index=annual_benchmark),
                width="stretch",
                height=430,
            )
        else:
            st.info("Für den gewählten Zeitraum ist keine Jahresperformance verfügbar.")
    with risk_column:
        st.markdown("#### Gesamtperformance")
        st.dataframe(
            style_total(total, marked_benchmark),
            width="stretch",
            height=430,
        )


registry = registry_cached()
index_order = (
    registry[["index_order", "index_name"]]
    .drop_duplicates()
    .sort_values("index_order")["index_name"]
    .tolist()
)
if "selected_etf_index" not in st.session_state:
    st.session_state.selected_etf_index = index_order[0]

st.title("China ETF Dashboard")
common_start = st.session_state.common_start
after_tax = st.session_state.after_tax
base_rate = st.session_state.base_rate
soli = st.session_state.soli
teilfreistellung = st.session_state.teilfreistellung
rf = st.session_state.rf
effective_tax = effective_german_equity_etf_tax_rate(
    base_rate, soli, teilfreistellung
)

index_tab, etf_tab = st.tabs(["Indizes vergleichen", "ETFs vergleichen"])

with index_tab:
    share_class_column, period_column = st.columns([1.7, 0.8], gap="large")
    with share_class_column:
        selected_share_classes = st.pills(
            "Zulässige Anlageklassen",
            SHARE_CLASS_ORDER,
            selection_mode="multi",
            key="selected_share_classes",
            help=(
                "Ein Index wird nur angezeigt, wenn alle von ihm abgedeckten "
                "Aktienklassen aktiviert sind."
            ),
        )
    selected_share_classes = selected_share_classes or []
    allowed_share_classes = set(selected_share_classes)
    filtered_index_order = [
        index_name for index_name in index_order
        if INDEX_SHARE_CLASSES.get(index_name, set()).issubset(allowed_share_classes)
    ]
    render_dashboard(
        mode="indices",
        selected_indices=filtered_index_order,
        selected_index_for_etfs=None,
        selected_etfs=[],
        common_start=common_start,
        after_tax=after_tax,
        effective_tax=effective_tax,
        rf=rf,
        widget_key="indices",
        date_container=period_column,
    )

with etf_tab:
    selection_column, overview_column = st.columns([0.38, 0.62], gap="large")
    with selection_column:
        selected_index = st.pills(
            "Index",
            index_order,
            selection_mode="single",
            key="selected_etf_index",
        )
    selected_index = selected_index or index_order[0]
    etf_subset = registry[registry["index_name"] == selected_index].sort_values("inception")
    selected_etfs = etf_subset["etf_name"].tolist()

    with overview_column:
        selected_etf_overview = (
            etf_subset[[
                "etf_name", "isin", "inception", "ter", "index_url",
            ]]
            .rename(columns={
                "etf_name": "ETF",
                "isin": "ISIN",
                "inception": "Auflage",
                "ter": "TER",
                "index_url": "Index-URL",
            })
        )
        selected_etf_overview["Auflage"] = selected_etf_overview["Auflage"].dt.date
        selected_etf_style = (
            selected_etf_overview.style
            .format({"TER": "{:.2f}%"})
            .apply(heatmap_styles, reverse=True, subset=["TER"])
            .set_properties(**{"color": "#111827"})
        )
        st.dataframe(
            selected_etf_style,
            width="stretch",
            hide_index=True,
            height=min(310, 38 + 35 * max(len(selected_etf_overview), 1)),
            column_config={
                "Index-URL": st.column_config.LinkColumn(display_text="Index öffnen")
            },
        )
    render_dashboard(
        mode="etfs",
        selected_indices=[],
        selected_index_for_etfs=selected_index,
        selected_etfs=selected_etfs,
        common_start=common_start,
        after_tax=after_tax,
        effective_tax=effective_tax,
        rf=rf,
        widget_key="etfs",
        show_date=False,
    )

st.divider()
with st.expander("Zusätzliche Einstellungen"):
    view_columns = st.columns(2)
    with view_columns[0]:
        st.toggle(
            "Gemeinsamer Vergleichszeitraum",
            key="common_start",
        )
    with view_columns[1]:
        st.toggle(
            "Nach Kapitalertragsteuer (vereinfacht)",
            key="after_tax",
        )

    parameter_columns = st.columns(4)
    with parameter_columns[0]:
        st.number_input(
            "Kapitalertragsteuer",
            min_value=0.0,
            max_value=1.0,
            step=0.0025,
            format="%.4f",
            key="base_rate",
        )
    with parameter_columns[1]:
        st.number_input(
            "Solidaritätszuschlag auf Steuer",
            min_value=0.0,
            max_value=0.20,
            step=0.005,
            format="%.3f",
            key="soli",
        )
    with parameter_columns[2]:
        st.number_input(
            "Teilfreistellung Aktienfonds",
            min_value=0.0,
            max_value=1.0,
            step=0.05,
            format="%.2f",
            key="teilfreistellung",
        )
    with parameter_columns[3]:
        st.number_input(
            "Risikofreier Zins p.a. für Sharpe",
            min_value=-0.10,
            max_value=0.20,
            step=0.005,
            format="%.3f",
            key="rf",
        )

    current_tax = effective_german_equity_etf_tax_rate(
        st.session_state.base_rate,
        st.session_state.soli,
        st.session_state.teilfreistellung,
    )
    st.caption(
        f"Effektiver Steuersatz auf positive Gewinne: {current_tax:.4%} · "
        "Marktdaten werden für 6 Stunden zwischengespeichert."
    )
    st.markdown(
        f"""
**Total Return.** Yahoo `Adj Close` dient als Total-Return-Näherung und berücksichtigt Ausschüttungen und Splits.

**EUR-Basis.** Nicht in EUR notierte Serien werden nach Möglichkeit über einen Yahoo-FX-Kurs umgerechnet.

**Kapitalertragsteuer.** Positive kumulierte Gewinne werden wie eine vollständige Veräußerung behandelt. Der effektive Steuersatz beträgt **{current_tax:.4%}**. Verluste erhalten keine fiktive Steuererstattung.

**Nicht enthalten:** Sparer-Pauschbetrag, Kirchensteuer, individuelle Verlustverrechnung, Vorabpauschale, die exakte zeitliche Besteuerung von Ausschüttungen und persönliche Steuermerkmale. Die Steueransicht ist eine vereinfachte Szenariorechnung, keine Steuerberatung.

**ETF-Proxys.** Die gezeigten UCITS-ETFs bilden Indizes näherungsweise ab. TER, Tracking Difference, Handelsplatz und mögliche FX-Effekte fließen in die beobachtete Serie ein.

**Relative Kennzahlen.** Benchmark ist die ausgewählte Serie mit dem frühesten Fonds-Auflegungsdatum. Information Ratio und Tracking Error basieren auf gemeinsam verfügbaren Tagesrenditen.
        """
    )
