from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf

_source = Path(__file__).with_name("app_v30_overlay.py").read_text(encoding="utf-8")
_core = _source.split("\ntop_page = _text_nav(", 1)[0]
exec(compile(_core, "app_v30_core", "exec"), globals(), globals())


_original_render_asset_allocation_tool = render_asset_allocation_tool


def render_asset_allocation_tool():
    st.title("Asset Allocation Backtesting Tool")
    st.caption(
        "Freie Wertpapiersuche über Yahoo Finance. Name, Ticker oder ISIN eingeben; "
        "bei nicht eindeutig auflösbaren ISINs funktioniert der Yahoo-Ticker am zuverlässigsten."
    )

    st.markdown("### Wertpapier hinzufügen")
    query = st.text_input(
        "Name, Ticker oder ISIN",
        key="aa_search_query",
        placeholder="z. B. Apple, AAPL oder US0378331005",
    )
    results = yahoo_search(query) if query else []
    if results:
        labels = [
            f"{x['name']} · {x['symbol']}"
            + (f" · {x['exchange']}" if x["exchange"] else "")
            for x in results
        ]
        selected_label = st.selectbox(
            "Suchergebnis",
            labels,
            key="aa_search_result",
        )
        selected_result = results[labels.index(selected_label)]
        add_col, benchmark_col = st.columns(2)
        with add_col:
            if st.button("Zum Portfolio hinzufügen", use_container_width=True):
                add_asset(selected_result)
                st.rerun()
        with benchmark_col:
            if st.button("Als Benchmark verwenden", use_container_width=True):
                st.session_state.aa_benchmark = selected_result
                st.rerun()

    assets = _aa_assets()
    if assets:
        st.markdown("### Portfolio")
        for i, asset in enumerate(list(assets)):
            c1, c2, c3 = st.columns([.54, .28, .18], vertical_alignment="center")
            with c1:
                st.markdown(f"**{asset['name']}**  \n`{asset['symbol']}`")
            with c2:
                new_weight = st.number_input(
                    "Gewicht %",
                    min_value=0.0,
                    max_value=100.0,
                    value=float(asset["weight"]),
                    step=1.0,
                    key=f"aa_weight_{asset['symbol']}",
                )
                asset["weight"] = float(new_weight)
            with c3:
                if st.button(
                    "Entfernen",
                    key=f"aa_remove_{asset['symbol']}",
                    use_container_width=True,
                ):
                    remove_asset(asset["symbol"])
                    st.rerun()

        total_weight = sum(x["weight"] for x in assets)
        st.caption(f"Summe Gewichte: {total_weight:.2f} %")
    else:
        st.info("Noch keine Wertpapiere im Portfolio.")

    benchmark = st.session_state.get("aa_benchmark")
    if benchmark:
        st.markdown(
            f"**Benchmark:** {benchmark['name']} · `{benchmark['symbol']}`"
        )

    # Neue Funktion: Zeitraum ändern
    st.markdown("### Backtesting-Einstellungen")
    c1, c2, c3 = st.columns(3, gap="large")
    
    with c1:
        rebalance = st.selectbox(
            "Rebalancing",
            [
                "Monatlich",
                "Quartalsweise",
                "Halbjährlich",
                "Jährlich",
                "Kein Rebalancing",
            ],
            index=1,
            key="aa_rebalance",
        )
    
    with c2:
        time_period_option = st.selectbox(
            "Zeitraum",
            [
                "Gesamter Datenzeitraum",
                "Letzte 1 Jahr",
                "Letzte 3 Jahre",
                "Letzte 5 Jahre",
                "Letzte 10 Jahre",
                "Benutzerdefiniert",
            ],
            index=0,
            key="aa_time_period",
        )
    
    with c3:
        if time_period_option == "Benutzerdefiniert":
            custom_years = st.number_input(
                "Jahre zurück",
                min_value=1,
                max_value=50,
                value=5,
                step=1,
                key="aa_custom_years",
            )
        else:
            custom_years = None

    if st.button("Backtest starten", type="primary", use_container_width=True):
        if not assets:
            st.error("Mindestens ein Wertpapier hinzufügen.")
            return
        if not benchmark:
            st.error("Bitte eine Benchmark auswählen.")
            return
        weights = np.array([x["weight"] for x in assets], dtype=float)
        if weights.sum() <= 0:
            st.error("Die Summe der Gewichte muss größer als 0 sein.")
            return

        price_series = {}
        errors = []
        with st.spinner("Kursdaten werden geladen …"):
            for asset in assets:
                try:
                    series, _ = asset_series_eur(asset["symbol"])
                    price_series[asset["symbol"]] = series
                except Exception as exc:
                    errors.append(str(exc))
            try:
                benchmark_series, _ = asset_series_eur(benchmark["symbol"])
            except Exception as exc:
                benchmark_series = None
                errors.append(f"Benchmark: {exc}")

        if errors:
            for error in errors:
                st.warning(error)
        if len(price_series) != len(assets) or benchmark_series is None:
            st.error("Backtest konnte nicht vollständig geladen werden.")
            return

        prices = pd.concat(price_series, axis=1).dropna()
        benchmark_series = benchmark_series.reindex(prices.index).dropna()
        common_index = prices.index.intersection(benchmark_series.index)
        prices = prices.loc[common_index]
        benchmark_series = benchmark_series.loc[common_index]
        
        # Zeitraum filtern
        if time_period_option != "Gesamter Datenzeitraum":
            if time_period_option == "Letzte 1 Jahr":
                years_back = 1
            elif time_period_option == "Letzte 3 Jahre":
                years_back = 3
            elif time_period_option == "Letzte 5 Jahre":
                years_back = 5
            elif time_period_option == "Letzte 10 Jahre":
                years_back = 10
            else:  # Benutzerdefiniert
                years_back = custom_years
            
            cutoff_date = pd.Timestamp.now() - pd.DateOffset(years=years_back)
            prices = prices[prices.index >= cutoff_date]
            benchmark_series = benchmark_series[benchmark_series.index >= cutoff_date]
            common_index = prices.index.intersection(benchmark_series.index)
            prices = prices.loc[common_index]
            benchmark_series = benchmark_series.loc[common_index]
        
        if len(prices) < 30:
            st.error("Zu wenig gemeinsamer Datenzeitraum.")
            return

        portfolio = backtest_portfolio(
            prices,
            weights,
            rebalance,
        )
        benchmark_indexed = benchmark_series / benchmark_series.iloc[0] * 100.0

        comparison = pd.concat(
            [portfolio.rename("Portfolio"), benchmark_indexed.rename("Benchmark")],
            axis=1,
        ).dropna()

        perf = go.Figure()
        perf.add_trace(go.Scatter(
            x=comparison.index,
            y=comparison["Portfolio"],
            mode="lines",
            name="Portfolio",
            line=dict(width=2.8),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>%{y:.2f}</b>"
                "<extra></extra>"
            ),
        ))
        perf.add_trace(go.Scatter(
            x=comparison.index,
            y=comparison["Benchmark"],
            mode="lines",
            name="Benchmark",
            line=dict(
                width=2.0,
                dash="dash",
            ),
            hovertemplate=(
                "%{x|%d.%m.%Y}<br>"
                "<b>%{y:.2f}</b>"
                "<extra></extra>"
            ),
        ))
        perf_layout = base_layout(True)
        perf_layout["yaxis"] = dict(
            showgrid=False,
            type="log",
            title="Indexiert (log)",
        )
        perf.update_layout(**perf_layout)

        dd = comparison / comparison.cummax() - 1
        dd_fig = go.Figure()
        for col in dd.columns:
            dd_fig.add_trace(go.Scatter(
                x=dd.index,
                y=dd[col] * 100,
                mode="lines",
                name=col,
                line=dict(width=2.5 if col == "Portfolio" else 2.0,
                          dash="dash" if col == "Benchmark" else "solid"),
            ))
        dd_layout = base_layout(True)
        dd_layout["showlegend"] = True
        dd_layout["yaxis"] = dict(showgrid=False, title="Drawdown in %")
        dd_fig.update_layout(**dd_layout)

        c1, c2 = st.columns(2, gap="large")
        with c1:
            st.markdown("#### Wertentwicklung")
            st.plotly_chart(
                perf,
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
            )
        with c2:
            st.markdown("#### Drawdown")
            st.plotly_chart(
                dd_fig,
                width="stretch",
                config={"displaylogo": False, "scrollZoom": True},
            )

        stats = pd.DataFrame(
            {
                "Portfolio": backtest_metrics(comparison["Portfolio"]),
                "Benchmark": backtest_metrics(comparison["Benchmark"]),
            }
        ).T
        st.markdown("#### Kennzahlen")
        st.dataframe(
            style_heat(stats),
            width="stretch",
            height=compact_height(len(stats)),
        )

        weights_display = pd.DataFrame(
            {
                "Wertpapier": [x["name"] for x in assets],
                "Ticker": [x["symbol"] for x in assets],
                "Gewicht": weights / weights.sum(),
            }
        )
        st.markdown("#### Backtest-Konfiguration")
        st.dataframe(
            weights_display.style.format({"Gewicht": "{:.2%}"}),
            width="stretch",
            hide_index=True,
            height=compact_height(len(weights_display)),
        )
        st.caption(
            f"Rebalancing: {rebalance} · Zeitraum: "
            f"{comparison.index.min():%d.%m.%Y} – {comparison.index.max():%d.%m.%Y}"
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
