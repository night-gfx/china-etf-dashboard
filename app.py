# Streamlit entry point.
# Execute the current dashboard script on every Streamlit rerun.
from pathlib import Path

_dashboard_path = Path(__file__).with_name("app_v4.py")
_source = _dashboard_path.read_text(encoding="utf-8")

# Runtime hotfix: avoid passing Plotly's yaxis keyword twice in the rolling-correlation chart.
_source = _source.replace(
    '    fig.update_layout(**base_layout(False), yaxis=dict(title=f"Rollierende 1J-Korrelation<br>{display_names.get(a,a)} ↔ {display_names.get(b,b)}", showgrid=False, zeroline=True, range=[-1, 1]))\n',
    '    _layout = base_layout(False)\n    _layout["yaxis"] = dict(title=f"Rollierende 1J-Korrelation<br>{display_names.get(a,a)} ↔ {display_names.get(b,b)}", showgrid=False, zeroline=True, range=[-1, 1])\n    fig.update_layout(**_layout)\n',
)

_code = compile(_source, str(_dashboard_path), "exec")
exec(_code, globals(), globals())
