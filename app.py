# Streamlit entry point.
# Deploy trigger: v30 commodities equal-weight index and rolling betas
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v30_overlay.py")
_code = compile(_dashboard_path.read_text(encoding="utf-8"), str(_dashboard_path), "exec")
exec(_code, globals(), globals())
