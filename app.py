# Streamlit entry point.
# Deploy trigger: v27 recursion fix for monthly sector signal analysis
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v27_overlay.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
