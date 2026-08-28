from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

_source = Path(__file__).with_name("app_v29_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v29_core", "exec"), globals(), globals())


COMMODITY_UNIVERSE = [
    {"class": "Energie", "name": "WTI Rohöl", "ticker": "CL=F"},
    {"class": "Energie", "name": "Brent Rohöl", "ticker": "BZ=F"},
    {"class": "Energie", "name": "Erdgas", "ticker": "NG=F"},
    {"class": "Energie", "name": "RBOB Benzin", "ticker": "RB=F"},
    {"class": "Energie", "name": "Heizöl", "ticker": "HO=F"},
    {"class": "Metalle", "name": "Gold", "ticker": "GC=F"},
    {"class": "Metalle", "name": "Silber", "ticker": "SI=F"},
    {"class": "Metalle", "name": "Kupfer", "ticker": "HG=F"},
    {"class": "Metalle", "name": "Platin", "ticker": "PL=F"},
    {"class": "Metalle", "name": "Palladium", "ticker": "PA=F"},
    {"class": "Getreide & Ölsaaten", "name": "Mais", "ticker": "ZC=F"},
    {"class": "Getreide & Ölsaaten", "name": "Weizen", "ticker": "ZW=F"},
    {"class": "Getreide & Ölsaaten", "name": "Sojabohnen", "ticker": "ZS=F"},
    {"class": "Getreide & Ölsaaten", "name": "Sojaöl", "ticker": "ZL=F"},
    {"class": "Getreide & Ölsaaten", "name": "Sojaschrot", "ticker": "ZM=F"},
    {"class": "Soft Commodities", "name": "Kaffee", "ticker": "KC=F"},
    {"class": "Soft Commodities", "name": "Zucker", "ticker": "SB=F"},
    {"class": "Soft Commodities", "name": "Kakao", "ticker": "CC=F"},
    {"class": "Soft Commodities", "name": "Baumwolle", "ticker": "CT=F"},
    {"class": "Soft Commodities", "name": "Orangensaft", "ticker": "OJ=F"},
    {"class": "Vieh", "name": "Live Cattle", "ticker": "LE=F"},
    {"class": "Vieh", "name": "Lean Hogs", "ticker": "HE=F"},
]

COMMODITY_BY_TICKER = {item["ticker"]: item for item in COMMODITY_UNIVERSE}
COMMODITY_CLASS_ORDER = list(dict.fromkeys(item["class"] for item in COMMODITY_UNIVERSE))


@st.cache_data(ttl=21600, show_spinner=False)
def commodity_prices_usd():
    tickers = [item["ticker"] for item in COMMODITY_UNIVERSE]
    try:
        data = yf.download(
            tickers=tickers,
            start="1990-01-01",
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="column",
        )
    except Exception:
        return pd.DataFrame()

    if data is None or data.empty:
        return pd.DataFrame()

    if isinstance(data.columns, pd.MultiIndex):
        level0 = data.columns.get_level_values(0)
        if "Adj Close" in level0:
            prices = data["Adj Close"].copy()
        elif "Close" in level0:
            prices = data["Close"].copy()
        else:
            return pd.DataFrame()
    else:
        field = "Adj Close" if "Adj Close" in data.columns else "Close"
        if field not in data.columns:
            return pd.DataFrame()
        prices = data[[field]].copy()
        prices.columns = [tickers[0]]

    if isinstance(prices, pd.Series):
        prices = prices.to_frame()

    prices = prices.apply(pd.to_numeric, errors="coerce")
    prices = prices.sort_index()
    prices = prices.loc[:, prices.notna().sum(axis=0) >= 252]
    prices = prices.dropna(how="all")
    return prices


def _commodity_common_returns(prices):
    if prices.empty:
        return pd.DataFrame(), pd.Series(dtype=float)

    returns = prices.pct_change(fill_method=None)
    returns = returns.replace([np.inf, -np.inf], np.nan)

    common = returns.dropna(how="any").sort_index()
    if common.empty:
        return pd.DataFrame(), pd.Series(dtype=float)

    index_return = common.mean(axis=1)
    index_return.name = "Equal Weighted Commodity Index"
    return common, index_return


def _equal_weight_commodity_index(index_return):
    if index_return.empty:
        return pd.Series(dtype=float)
    index = (1.0 + index_return).cumprod() * 100.0
    index.name = "Equal Weighted Commodity Index"
    return index


def _rolling_commodity_beta(common_returns, index_return, window_days):
    if common_returns.empty or index_return.empty:
        return pd.DataFrame()

    market_var = index_return.rolling(
        int(window_days),
        min_periods=int(window_days),
    ).var()

    beta = {}
    for ticker in common_returns.columns:
        covariance = common_returns[ticker].rolling(
            int(window_days),
            min_periods=int(window_days),
        ).cov(index_return)
        beta[ticker] = covariance / market_var

    return pd.DataFrame(beta).replace([np.inf, -np.inf], np.nan)


def _commodity_index_figure(index_series):
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=index_series.index,
        y=index_series,
        mode="lines",
        name="Equal Weighted Commodity Index",
        line=dict(width=2.4),
        hovertemplate=(
            "%{x|%d.%m.%Y}<br>"
            "<b>%{y:.2f}</b>"
            "<extra></extra>"
        ),
    ))
    layout = base_layout(True)
    layout["height"] = 520
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title="Indexiert (Start = 100)",
    )
    fig.update_layout(**layout)
    return fig


def _commodity_beta_figure(beta_frame, selected_class, window_months):
    fig = go.Figure()

    selected_tickers = [
        item["ticker"]
        for item in COMMODITY_UNIVERSE
        if item["class"] == selected_class and item["ticker"] in beta_frame.columns
    ]

    for ticker in selected_tickers:
        s = pd.to_numeric(beta_frame[ticker], errors="coerce").dropna()
        if s.empty:
            continue
        item = COMMODITY_BY_TICKER[ticker]
        fig.add_trace(go.Scatter(
            x=s.index,
            y=s,
            mode="lines",
            name=f"{item['name']} ({ticker})",
            line=dict(width=1.8),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>Beta %{y:.2f}</b>"
                "<extra>%{fullData.name}</extra>"
            ),
        ))

    fig.add_hline(y=1, line_width=1, line_dash="dot")
    fig.add_hline(y=0, line_width=1, line_dash="dot")

    layout = base_layout(True)
    layout["height"] = 570
    layout["hovermode"] = "closest"
    layout["yaxis"] = dict(
        showgrid=False,
        zeroline=False,
        title=f"Rollierendes Beta ({window_months}M)",
    )
    layout["legend"] = dict(
        orientation="h",
        yanchor="top",
        y=-0.16,
        x=0,
    )
    fig.update_layout(**layout)
    return fig


def render_commodities():
    prices = commodity_prices_usd()
    if prices.empty:
        st.error("Commodity-Daten konnten nicht geladen werden.")
        return

    overview_rows = []
    for item in COMMODITY_UNIVERSE:
        ticker = item["ticker"]
        if ticker not in prices.columns:
            continue
        s = pd.to_numeric(prices[ticker], errors="coerce").dropna()
        if s.empty:
            continue
        overview_rows.append({
            "Oberklasse": item["class"],
            "Rohstoff": item["name"],
            "Symbol": ticker,
            "Daten ab": f"{s.index.min():%d.%m.%Y}",
            "Daten bis": f"{s.index.max():%d.%m.%Y}",
        })

    overview = pd.DataFrame(overview_rows)
    st.dataframe(
        overview,
        width="stretch",
        hide_index=True,
        height=compact_height(len(overview), maximum=650),
    )

    available_tickers = [
        item["ticker"]
        for item in COMMODITY_UNIVERSE
        if item["ticker"] in prices.columns
    ]
    prices = prices.reindex(columns=available_tickers)

    common_returns, index_return = _commodity_common_returns(prices)
    if common_returns.empty:
        st.error("Kein gemeinsamer Zeitraum für den Commodity Index verfügbar.")
        return

    index_series = _equal_weight_commodity_index(index_return)

    st.markdown("#### Equal Weighted Commodity Index")
    st.plotly_chart(
        _commodity_index_figure(index_series),
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
        key="commodity_equal_weight_index_v32",
    )

    c1, c2 = st.columns(2, gap="large")
    with c1:
        beta_months = st.slider(
            "Beta-Fenster (Monate)",
            min_value=3,
            max_value=36,
            value=12,
            step=1,
            key="commodity_beta_months_v32",
        )
    with c2:
        available_classes = [
            category
            for category in COMMODITY_CLASS_ORDER
            if any(
                item["class"] == category and item["ticker"] in common_returns.columns
                for item in COMMODITY_UNIVERSE
            )
        ]
        selected_class = st.selectbox(
            "Oberklasse",
            options=available_classes,
            index=0,
            key="commodity_beta_class_v32",
        )

    window_days = max(int(round(float(beta_months) * 21)), 1)
    beta_frame = _rolling_commodity_beta(
        common_returns,
        index_return,
        window_days,
    )

    st.markdown(f"#### Rollierendes Beta zum Commodity Index – {selected_class}")
    st.plotly_chart(
        _commodity_beta_figure(beta_frame, selected_class, beta_months),
        width="stretch",
        config={"displaylogo": False, "scrollZoom": True},
        key=f"commodity_beta_chart_v32_{selected_class}_{beta_months}",
    )

    current_rows = []
    for item in COMMODITY_UNIVERSE:
        ticker = item["ticker"]
        if item["class"] != selected_class or ticker not in beta_frame.columns:
            continue
        s = pd.to_numeric(beta_frame[ticker], errors="coerce").dropna()
        if s.empty:
            continue
        current_rows.append({
            "Rohstoff": item["name"],
            "Symbol": ticker,
            "Aktuelles Beta": float(s.iloc[-1]),
        })

    if current_rows:
        current = pd.DataFrame(current_rows)
        st.dataframe(
            current.style.format({"Aktuelles Beta": "{:.2f}"}),
            width="stretch",
            hide_index=True,
            height=compact_height(len(current), maximum=360),
        )


top_page = _text_nav(
    [
        "China ETF Dashboard",
        "Asset Allocation Backtesting Tool",
        "S&P 500 Sector ETFs",
        "Commodities",
    ],
    "top_page",
    "China ETF Dashboard",
    "top_text_nav",
)
st.session_state.after_tax = True

if top_page == "China ETF Dashboard":
    render_china_dashboard()
elif top_page == "Asset Allocation Backtesting Tool":
    render_asset_allocation_tool()
elif top_page == "S&P 500 Sector ETFs":
    render_sp500_sector_etfs()
else:
    render_commodities()
