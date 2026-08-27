from pathlib import Path

import streamlit as st

# Load v26 only up to the point before it overwrites v25's renderer alias.
_source = Path(__file__).with_name("app_v26_overlay.py").read_text(encoding="utf-8")
_core = _source.split(
    "\n_render_sp500_sector_etfs_core = render_sp500_sector_etfs",
    1,
)[0]
exec(compile(_core, "app_v26_event_helpers", "exec"), globals(), globals())

# At this point this is the working v25 wrapper. Its own
# _render_sp500_sector_etfs_core still points to the direct v24 renderer.
_render_sp500_sector_etfs_v25 = render_sp500_sector_etfs


def render_sp500_sector_etfs():
    original_plotly_chart = st.plotly_chart
    event_rendered = False

    def _plotly_chart_with_event_analysis(fig, *args, **kwargs):
        nonlocal event_rendered

        result = original_plotly_chart(fig, *args, **kwargs)

        if (
            not event_rendered
            and kwargs.get("key") == "sector_all_forward_scatter_v27"
        ):
            event_rendered = True
            _render_monthly_signal_event_analysis(original_plotly_chart)

        return result

    st.plotly_chart = _plotly_chart_with_event_analysis
    try:
        _render_sp500_sector_etfs_v25()
    finally:
        st.plotly_chart = original_plotly_chart


top_page = _text_nav(
    [
        "China ETF Dashboard",
        "Asset Allocation Backtesting Tool",
        "S&P 500 Sector ETFs",
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
else:
    render_sp500_sector_etfs()
