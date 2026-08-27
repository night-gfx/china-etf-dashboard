# Streamlit entry point.
# Deploy trigger: v22 max/min rolling sector differential vs S&P 500
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v22_overlay.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
