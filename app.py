# Streamlit entry point.
# Execute the dashboard script on every Streamlit rerun instead of importing it
# as a cached Python module. This ensures the UI is rendered on every rerun.
from pathlib import Path

import streamlit as st

_original_multiselect = st.multiselect


def _cloud_safe_multiselect(*args, **kwargs):
    if kwargs.get("key") == "tech_etfs" and "tech_etfs" not in st.session_state:
        kwargs["default"] = []
    return _original_multiselect(*args, **kwargs)


st.multiselect = _cloud_safe_multiselect

_dashboard_path = Path(__file__).with_name("app_v3.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
