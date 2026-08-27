# Streamlit entry point.
# Deploy trigger: v20 10k capital with 25 percent sector entries
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v20_overlay.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
