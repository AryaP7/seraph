"""C12 — regulator submission preview, persistence, decomposition and export (FR42)."""
import json

import streamlit as st

from seraph.dashboard import workspace_service as svc
from seraph.decision_support.institutions import InstitutionStore, _stamp


def panel(role, *, flags=None):
    if role != 'regulator':
        return None
    registry = svc.registry()
    principal = svc.demo_principal(role, reg=registry)
    store = InstitutionStore(svc._runs_dir()/'institutions.sqlite', registry)
    with st.expander('INSTITUTION EXPOSURES — regulator submissions'):
        st.caption(svc.DEMO_NOTE)
        st.caption('INR long-only holdings. Values are submitted exposures, not predicted losses.')
        with st.form('institution_submit'):
            institution_id = st.text_input('Institution ID')
            name = st.text_input('Institution display name')
            source = st.selectbox('Submission source', ['demo', 'user_supplied'])
            effective = st.text_input('Submission effective at (IST)', value=_stamp())
            upload = st.file_uploader('Institution holdings CSV or JSON', type=['csv', 'json'])
            pasted = st.text_area('Or paste holdings CSV', value='symbol,quantity,value,sector\n')
            preview_clicked = st.form_submit_button('Preview institution submission')
            submit_clicked = st.form_submit_button('Accept institution submission')
        body = upload.getvalue().decode('utf-8') if upload else pasted
        source_name = upload.name if upload else 'submission.csv'
        if preview_clicked or submit_clicked:
            try:
                st.json(store.preview(principal, body, source_name=source_name))
                if submit_clicked:
                    saved = store.submit(principal, institution_id=institution_id,
                        name=name, source=source, effective_at=effective,
                        body=body, source_name=source_name)
                    st.success(f"Saved revision {saved['revision']} · {saved['content_hash']}")
            except (ValueError, PermissionError) as exc:
                st.warning(str(exc))
        cutoff = st.text_input('Submission cutoff (IST)', value=_stamp())
        try:
            result = store.decomposition(principal, cutoff=cutoff, flags=flags)
        except (ValueError, PermissionError) as exc:
            st.warning(str(exc))
            return None
        st.metric('Known submitted value (INR)', result['total_known_value'])
        st.caption(result['note'])
        st.caption(f"Unsized positions: {result['unsized_positions']} · "
                   f"unmapped value: {result['unmapped_value']} · "
                   f"measured flag coverage: {result['covered_value']}")
        st.dataframe(result['sectors'])
        for book in result['institutions']:
            with st.expander(f"{book['name']} · {book['source']} · revision {book['revision']}"):
                st.json(book)
        st.download_button('Export institution decomposition',
            json.dumps(result, indent=2), file_name='seraph-institution-decomposition-v1.json',
            mime='application/json')
        return result
