# Streamlit entry point.
# Deploy trigger: v19 without top/bottom-2 charts
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v19_overlay.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
