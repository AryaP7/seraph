"""C12 — regulator directed-sector graph, separate from the geographic news globe (FR42)."""
from datetime import datetime
import json

import pandas as pd
import streamlit as st

from seraph.pillars.hawkes.network import select
from seraph.shared_types import IST


def panel(role, decision_ts):
    if role != 'regulator':
        return None
    with st.expander('DIRECTED MARKET NETWORK — measured native sector counts'):
        mode = st.radio('Network artifact cutoff', ['Selected market decision', 'Current analytical archive'], horizontal=True)
        cutoff = decision_ts if mode=='Selected market decision' else datetime.now(IST).isoformat()
        try:
            result=select(cutoff)
        except (ValueError,OSError,KeyError) as exc:
            st.warning(str(exc));return None
        st.caption(f'{mode} · cutoff {cutoff}. News exposure arcs are a separate model.')
        if result['status']!='fitted':
            st.info(result['reason'])
        else:
            st.caption(f"Fitted {result['fitted_at']} · input {result['input_start']} to {result['input_end']}")
            st.dataframe(result['edges'],hide_index=True)
            dot=['digraph sectors {']
            dot.extend(json.dumps(node)+';' for node in result['node_ids'])
            dot.extend(f"{json.dumps(e['source'])} -> {json.dumps(e['target'])} [label=\"{e['weight']:.4f}\"];" for e in result['edges'])
            dot.append('}')
            st.graphviz_chart('\n'.join(dot))
            st.dataframe(pd.DataFrame(result['matrix'],index=result['node_ids'],columns=result['node_ids']))
            st.caption(f"Rows are targets, columns are sources. Hidden off-diagonal edges below declared display threshold: {result['hidden_edges']}.")
            for note in result['limitations']:
                st.caption(note)
        st.json(result)
        st.download_button('Export directed network artifact',json.dumps(result,indent=2),
                           file_name='seraph-directed-network.json',mime='application/json')
        return result
