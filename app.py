# Streamlit entry point with cloud-safety and a visible global loading indicator.
import streamlit as st

_original_multiselect = st.multiselect


def _cloud_safe_multiselect(*args, **kwargs):
    if kwargs.get("key") == "tech_etfs" and "tech_etfs" not in st.session_state:
        kwargs["default"] = []
    return _original_multiselect(*args, **kwargs)


st.multiselect = _cloud_safe_multiselect

# Global loading feedback. This is shown immediately while the dashboard module
# is importing/executing (including Yahoo Finance downloads) and switches to
# 100% once the full Streamlit script has completed.
_load_text = st.empty()
_load_bar = st.progress(8)
_load_text.caption("Lade Dashboard und Marktdaten … 8 %")

try:
    from app_v3 import *  # noqa: F401,F403,E402
    _load_bar.progress(100)
    _load_text.caption("Fertig · 100 %")
except Exception:
    _load_bar.progress(100)
    _load_text.caption("Laden abgebrochen – Fehler in der App")
    raise
