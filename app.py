# Streamlit entry point with a small stability hotfix for Streamlit Community Cloud.
# The tech ETF multiselect no longer preselects every ETF on first load, which
# avoids dozens of simultaneous Yahoo Finance requests across inactive tabs.
import streamlit as st

_original_multiselect = st.multiselect


def _cloud_safe_multiselect(*args, **kwargs):
    if kwargs.get("key") == "tech_etfs" and "tech_etfs" not in st.session_state:
        kwargs["default"] = []
    return _original_multiselect(*args, **kwargs)


st.multiselect = _cloud_safe_multiselect

from app_v3 import *  # noqa: F401,F403,E402
