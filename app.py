# Streamlit entry point.
# Deploy trigger: v23 configurable rolling differential and forward analysis
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v23_overlay.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
