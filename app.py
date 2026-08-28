# Streamlit entry point.
# Deploy trigger: v29 sector selector with 12M differential and 2Y trough navigator
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v29_overlay.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
