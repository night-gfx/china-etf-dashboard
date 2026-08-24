from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.metrics import (
    annual_volatility,
    calendar_returns,
    cagr,
    drawdown,
    max_drawdown,
    sharpe,
    sortino,
    tracking_error_and_ir,
)
from src.tax import transform_frame


def fmt_date(value) -> str:
    if value is None or pd.isna(value):
        return "–"
    return pd.Timestamp(value).strftime("%d.%m.%Y")


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
        p = 0.5 if high == low else (value - low) / (high - low)
        if reverse:
            p = 1 - p
        if p <= 0.5:
            w, start, end = p * 2, (248, 190, 190), (255, 244, 176)
        else:
            w, start, end = (p - 0.5) * 2, (255, 244, 176), (183, 229, 190)
        rgb = tuple(round(a + (b - a) * w) for a, b in zip(start, end))
        styles.append(f"background-color: rgb{rgb}; color: #111827")
    return styles


def style_metrics(df: pd.DataFrame, reverse_columns: set[str] | None = None, bold_index: str | None = None):
    reverse_columns = reverse_columns or set()
    pct_columns = {
        "Gesamtrendite", "CAGR p.a.", "Volatilität p.a.", "Max. Drawdown",
        "Tracking Error p.a.", "Bestes Jahr", "Schlechtestes Jahr",
    }
    pct_columns.update(c for c in df.columns if str(c).isdigit())
    num_columns = {"Sharpe", "Sortino", "Calmar", "Information Ratio p.a."}
    formatters = {c: fmt_pct for c in df.columns if c in pct_columns}
    formatters.update({c: fmt_num for c in df.columns if c in num_columns})
    styled = df.style.format(formatters, na_rep="–").set_properties(**{"color": "#111827"})
    for column in df.select_dtypes(include="number").columns:
        styled = styled.apply(heatmap_styles, reverse=column in reverse_columns, subset=[column])
    if bold_index and bold_index in df.index:
        styled = styled.apply(
            lambda row: [
                "font-weight:750;border-top:2px solid #111827;border-bottom:2px solid #111827"
                if row.name == bold_index else "" for _ in row
            ],
            axis=1,
        )
    return styled


def common_max_frame(raw: pd.DataFrame, after_tax: bool, effective_tax: float) -> pd.DataFrame:
    return transform_frame(raw, after_tax=after_tax, effective_tax_rate=effective_tax, common_start=True)


def chart_layout(title: str, legend: bool, log_y: bool = False):
    return dict(
        yaxis_title=title,
        xaxis_title=None,
        showlegend=legend,
        hovermode="x unified",
        dragmode="zoom",
        legend=dict(
            orientation="h", yanchor="top", y=-0.16, xanchor="left", x=0,
            entrywidth=145, entrywidthmode="pixels", font=dict(size=10, color="#111827"),
        ),
        margin=dict(l=55, r=20, t=20, b=145 if legend else 45),
        height=535,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(color="#111827"),
        xaxis=dict(showgrid=False, zeroline=False, autorange=True),
        yaxis=dict(showgrid=False, zeroline=False, type="log" if log_y else "linear", autorange=True),
    )


def performance_figure(frame: pd.DataFrame, labels: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for column in frame.columns:
        s = frame[column].dropna()
        fig.add_trace(go.Scatter(
            x=s.index, y=s, mode="lines", name=labels.get(column, column), line=dict(width=2),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}</b><extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(**chart_layout("Indexiert (Start = 100, logarithmisch)", True, True))
    return fig


def drawdown_figure(frame: pd.DataFrame, labels: dict[str, str]) -> go.Figure:
    fig = go.Figure()
    for column in frame.columns:
        dd = drawdown(frame[column]) * 100
        fig.add_trace(go.Scatter(
            x=dd.index, y=dd, mode="lines", name=labels.get(column, column), line=dict(width=2),
            hovertemplate="%{x|%d.%m.%Y}<br><b>%{y:.2f}%</b><extra>%{fullData.name}</extra>",
        ))
    fig.update_layout(**chart_layout("Drawdown in %", False, False))
    return fig


CHART_CONFIG = {
    "displaylogo": False,
    "scrollZoom": True,
    "doubleClick": "reset+autosize",
    "responsive": True,
}


def total_metrics(frame: pd.DataFrame, benchmark: str, rf: float) -> pd.DataFrame:
    rows = []
    for col in frame.columns:
        s = frame[col].dropna()
        if len(s) < 2:
            continue
        cr = calendar_returns(s)
        if col == benchmark:
            te, ir = 0.0, 0.0
        else:
            te, ir, _ = tracking_error_and_ir(s, frame[benchmark].dropna())
        dd, cg = max_drawdown(s), cagr(s)
        rows.append({
            "ETF (Index)": col,
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


def annual_relative(frame: pd.DataFrame, benchmark: str) -> pd.DataFrame:
    years = sorted({int(y) for c in frame.columns for y in calendar_returns(frame[c]).index}, reverse=True)
    rows = []
    for col in frame.columns:
        s = frame[col].dropna()
        if col == benchmark:
            te, ir, start = 0.0, 0.0, s.index.min()
        else:
            te, ir, start = tracking_error_and_ir(s, frame[benchmark].dropna())
        row = {
            "ETF (Index)": col,
            "Information Ratio p.a.": ir,
            "Tracking Error p.a.": te,
            "IR-Start": fmt_date(start),
        }
        cr = calendar_returns(s)
        for year in years:
            row[str(year)] = cr.get(year, np.nan)
        rows.append(row)
    return pd.DataFrame(rows).set_index("ETF (Index)")


def render_standard(resolved, benchmark_label: str, labels: dict[str, str], after_tax: bool, effective_tax: float, rf: float, key: str):
    from src.data import combine_series

    if not resolved:
        st.info("Keine verfügbaren Serien.")
        return
    raw = combine_series(resolved)
    frame = common_max_frame(raw, after_tax, effective_tax)
    if frame.empty:
        st.error("Kein gemeinsamer Datenzeitraum verfügbar.")
        return
    if benchmark_label not in frame.columns:
        benchmark_label = frame.columns[0]
    start, end = frame.index.min(), frame.index.max()
    st.caption(f"Vergleichszeitraum: MAX · {fmt_date(start)} – {fmt_date(end)} · Benchmark: {benchmark_label}")

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Wertentwicklung")
        st.plotly_chart(performance_figure(frame, labels), width="stretch", config=CHART_CONFIG, key=f"p_{key}")
    with c2:
        st.markdown("#### Drawdown")
        st.plotly_chart(drawdown_figure(frame, labels), width="stretch", config=CHART_CONFIG, key=f"d_{key}")

    total = total_metrics(frame, benchmark_label, rf)
    annual = annual_relative(frame, benchmark_label)
    if benchmark_label in total.index:
        total = pd.concat([total.loc[[benchmark_label]], total.drop(index=benchmark_label)])
    if benchmark_label in annual.index:
        annual = pd.concat([annual.loc[[benchmark_label]], annual.drop(index=benchmark_label)])
    marked = f"★ BENCHMARK · {benchmark_label}"
    total = total.rename(index={benchmark_label: marked})
    annual = annual.rename(index={benchmark_label: marked})

    c1, c2 = st.columns(2, gap="large")
    with c1:
        st.markdown("#### Jahresperformance / relative Kennzahlen")
        st.dataframe(style_metrics(annual, {"Tracking Error p.a."}, marked), width="stretch", height=430)
    with c2:
        st.markdown("#### Gesamtperformance")
        st.dataframe(style_metrics(total, {"Tracking Error p.a.", "Volatilität p.a."}, marked), width="stretch", height=430)
