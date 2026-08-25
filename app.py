# Streamlit entry point.
# Execute the current dashboard script on every Streamlit rerun.
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v4.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
