from pathlib import Path
import re

source = Path(__file__).with_name("app_v8.py").read_text(encoding="utf-8")

# Keep release label v8 while refining its UI behavior.
source = source.replace(
    '# ----- v8 UI helpers -----',
    '''# ----- v8 UI helpers -----\n\nst.markdown("""\n<style>\ndiv[data-testid="stButton"] > button, div[data-testid="stLinkButton"] > a {\n  justify-content: flex-start !important;\n  text-align: left !important;\n}\ndiv[data-testid="stButton"] > button[kind="primary"] {\n  background: #f3f4f6 !important;\n  color: #111827 !important;\n  border-color: #9ca3af !important;\n}\n</style>\n""", unsafe_allow_html=True)\n\ndef base_layout(showlegend=False):\n    return dict(\n        showlegend=False, hovermode="closest", dragmode="zoom", height=520,\n        plot_bgcolor="white", paper_bgcolor="white", font=dict(color="#111827"),\n        margin=dict(l=50,r=18,t=18,b=45),\n        xaxis=dict(showgrid=False,zeroline=False,autorange=True),\n    )\n'''
)

# Table focus uses a selected cell, not a dedicated row-checkbox column.
source = re.sub(
    r'def table_focus_event\(event, df, key\):.*?\n\ndef compact_height',
    '''def table_focus_event(event, df, key):\n    try:\n        cells = event.selection.cells\n        if not cells:\n            return\n        cell = cells[0]\n        row_idx = cell.get("row") if isinstance(cell, dict) else (cell[0] if isinstance(cell, (list, tuple)) and cell else None)\n        if row_idx is not None and 0 <= int(row_idx) < len(df):\n            toggle_focus(df.index[int(row_idx)], key)\n    except Exception:\n        pass\n\n\ndef compact_height''',
    source,
    flags=re.S,
)
source = source.replace('selection_mode="single-row"', 'selection_mode="single-cell"')

# Session-level cache so deselect/reselect reuses already resolved data.
cache_helpers = '''\n\ndef _session_cache(name):\n    if name not in st.session_state:\n        st.session_state[name] = {}\n    return st.session_state[name]\n\ndef session_index(name):\n    cache = _session_cache("v8_index_data")\n    if name not in cache:\n        try:\n            cache[name] = (resolve_index_cached(name), None)\n        except Exception as exc:\n            cache[name] = (None, str(exc))\n    return cache[name]\n\ndef session_tech(name):\n    cache = _session_cache("v8_tech_data")\n    if name not in cache:\n        rr, ww = resolve_tech_cached((name,))\n        cache[name] = (rr, ww)\n    return cache[name]\n\ndef session_etf(index_name, etf_name):\n    cache = _session_cache("v8_etf_data")\n    k = (index_name, etf_name)\n    if k not in cache:\n        cache[k] = resolve_rows_cached(index_name, (etf_name,))\n    return cache[k]\n\ndef status_block(host, done, total, label="Marktdaten geladen"):\n    pct = 100 if total == 0 else round(done / total * 100)\n    host.markdown(\n        f"**{label} &nbsp;&nbsp; Version v8**<br>"\n        f"<span style='font-size:.86rem;color:#4b5563'>({done}/{total}) &nbsp; {pct} %</span>",\n        unsafe_allow_html=True,\n    )\n'''
source = source.replace('registry=registry_cached()', cache_helpers + '\nregistry=registry_cached()', 1)

# Category-level select-all toggle integrated into each expander.
market_cat = '''def market_category(title,items,key):\n    selected=ensure_selected(key,items)\n    dialog=None\n    with st.expander(title,expanded=False):\n        all_active=len(selected)==len(items)\n        _,bulk=st.columns([.86,.14])\n        with bulk:\n            if st.button("✓" if all_active else "+",key=f"bulk_{key}",help="Kategorie vollständig auswählen/abwählen",use_container_width=True):\n                st.session_state[key]=[] if all_active else items.copy()\n                st.rerun()\n        for i,n in enumerate(items):\n            active=n in selected\n            with st.container(border=True):\n                label=f"{'✓  ' if active else ''}{n}"\n                if st.button(label,key=f"sel_{key}_{n}",type="secondary",use_container_width=True):\n                    toggle_selected(key,n,items)\n                index_details(n)\n                l1,l2=st.columns(2,gap="small")\n                with l1:\n                    st.link_button("Methodology",INDEX_INFO[n]["url"],use_container_width=True)\n                with l2:\n                    if st.button("ETF-Vergleich",key=f"etf_{key}_{n}",use_container_width=True):\n                        dialog=n\n    return list(ensure_selected(key,items)),dialog\n'''
source = re.sub(r'def market_category\(title,items,key\):.*?\n\ndef market_tree', market_cat + '\n\ndef market_tree', source, flags=re.S)

# Tech categories mirror the market categories. Keep generated source simple
# to avoid escaped-newline syntax problems.
tech_cat = '''def tech_category(title,rows,key,offset=0):\n    items=rows["etf_name"].tolist()\n    selected=ensure_selected(key,items)\n    with st.expander(title,expanded=False):\n        all_active=len(selected)==len(items)\n        _,bulk=st.columns([.86,.14])\n        with bulk:\n            if st.button("✓" if all_active else "+",key=f"techbulk_{key}",help="Kategorie vollständig auswählen/abwählen",use_container_width=True):\n                st.session_state[key]=[] if all_active else items.copy()\n                st.rerun()\n        for j,(_,row) in enumerate(rows.iterrows()):\n            name=row["etf_name"]\n            active=name in selected\n            proxy=MARKET_PROXY_BY_SIGNATURE.get(parse_share_classes_v8(row["share_classes"]),"–")\n            with st.container(border=True):\n                label=f"{'✓  ' if active else ''}{name}"\n                if st.button(label,key=f"techbtn_{key}_{name}",type="secondary",use_container_width=True):\n                    toggle_selected(key,name,items)\n                details=(\n                    f"• **Index:** {row['index_name']}  " + chr(10)\n                    + f"• **Aktienklassen:** {row['share_classes']}  " + chr(10)\n                    + f"• **Mitglieder:** {row['members']}  " + chr(10)\n                    + f"• **Market Proxy (Benchmark für IR/TE):** {proxy}  " + chr(10)\n                    + f"• **TER:** {row['ter']:.2f}%"\n                )\n                st.markdown(details)\n                st.link_button("ETF-Link",row["source_url"],use_container_width=True)\n    return list(ensure_selected(key,items))\n'''
source = re.sub(r'def tech_category\(title,rows,key,offset=0\):.*?\n\ndef render_tech', tech_cat + '\n\ndef render_tech', source, flags=re.S)

# Reuse session data in ETF dialog, tech page and market page.
source = source.replace(
    'rr,ww=resolve_rows_cached(index_name,(row["etf_name"],)); resolved+=rr; warnings+=ww',
    'rr,ww=session_etf(index_name,row["etf_name"]); resolved+=rr; warnings+=ww'
)
source = source.replace(
    'rr,ww=resolve_tech_cached((name,)); resolved+=rr; warnings+=ww; bar.progress(int(i/n*100))',
    'rr,ww=session_tech(name); resolved+=rr; warnings+=ww; bar.progress(int(i/n*100))'
)
source = source.replace(
    'try: resolved.append(resolve_index_cached(name))\n        except Exception as exc: warnings.append(f"{name}: {exc}")',
    'item,err=session_index(name)\n        if item is not None: resolved.append(item)\n        if err: warnings.append(f"{name}: {err}")'
)

# Cleaner final load status and no separate v8 caption.
source = source.replace('txt.caption(f"Marktdaten geladen · {n} von {n} · 100 %")', 'status_block(txt,n,n)')
source = source.replace('st.caption("Version v8")', '')
source = source.replace('hovermode="x unified"', 'hovermode="closest"')

# Compile transformed source before execution.
code = compile(source, str(Path(__file__).with_name("app_v8_runtime.py")), "exec")
exec(code, globals(), globals())
