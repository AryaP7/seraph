# Regression tests — U01 (console startup shapes and scalar CSRS)
"""The four startup shapes, and the CSRS dict that raised in `st.metric`.

Audit U01, reproduced in `docs/evidence/engineering-audit-2026-10-18/application.json`:

* `live_only_canonical_app` -> 1 info message, 0 metrics, 0 radios. `main()`
  returned on a missing archive store before the live panel was built, so a
  machine running the live runtime showed one line telling the operator to run
  a historical script.
* `persisted_nested_csrs_panel` -> "Invalid `value` type. Expected one of:
  int, float, Decimal, NumPy number. Provided type: dict."

Every test here failed before the repair in the same commit.
"""
from __future__ import annotations

from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from seraph.dashboard.prototype_app import csrs_metric
from seraph.live.store import LiveStore

APP = Path(__file__).resolve().parents[1] / 'seraph/dashboard/prototype_app.py'
IST = '+05:30'


@pytest.fixture
def stores(tmp_path, monkeypatch):
    """Point all three store paths at a scratch directory, none existing."""
    paths = dict(archive=tmp_path / 'archive.sqlite',
                 live=tmp_path / 'live.sqlite',
                 news=tmp_path / 'news.sqlite')
    monkeypatch.setenv('SERAPH_PROTOTYPE_STORE', str(paths['archive']))
    monkeypatch.setenv('SERAPH_LIVE_STORE', str(paths['live']))
    monkeypatch.setenv('SERAPH_NEWS_STORE', str(paths['news']))
    return paths


def commit_live_decision(path: Path, *, csrs: dict | None, as_of: str):
    """One committed decision, in the shape `run_live.commit` actually writes:
    `payload=decision.describe()`, whose `csrs` key is `model_dump()`."""
    store = LiveStore(path)
    store.commit_decision(
        decision_id=f'live:{as_of}', as_of=as_of, computed_at=as_of,
        payload=dict(decision_ts=as_of, bar_end=as_of, publishable=True,
                     csrs=csrs, label='current market reading'),
        publication_state='current', state=dict(pipeline_version='test'),
        input_cursor=dict(batches=[]))
    return store


CSRS_POINT = dict(ts=f'2026-10-16T10:05:00{IST}', csrs=0.42, variance=0.01,
                  ci_lower=0.30, ci_upper=0.54, shapley=[0.2, 0.1, 0.12],
                  alert_level='elevated', mask=[True, True, False],
                  effective_weights=[0.5, 0.5, 0.0], xi_mode='causal',
                  weights_artefact_id='fw:test', reconciliation_mode='kalman')


# ------------------------------------------------- the scalar CSRS helper


class TestU01CsrsIsRenderedAsAScalar:
    def test_a_nested_csrs_point_yields_a_number(self):
        score, _ = csrs_metric(dict(csrs=CSRS_POINT))
        assert score == 0.42

    def test_the_detail_line_carries_the_interval_and_mask(self):
        _, detail = csrs_metric(dict(csrs=CSRS_POINT))
        assert 'FR29 interval [0.300, 0.540]' in detail
        assert 'hawkes' in detail and 'rmt' in detail
        assert 'hamilton' not in detail, 'a masked-out pillar must not be listed'

    def test_a_bare_float_is_also_accepted(self):
        assert csrs_metric(dict(csrs=0.5))[0] == 0.5

    def test_an_absent_csrs_is_unavailable_not_an_exception(self):
        assert csrs_metric(dict(csrs=None))[0] == 'Unavailable'
        assert csrs_metric({})[0] == 'Unavailable'
        assert csrs_metric(None)[0] == 'Unavailable'

    def test_a_withheld_decision_with_no_numeric_score_is_unavailable(self):
        score, detail = csrs_metric(dict(csrs=dict(CSRS_POINT, csrs=None)))
        assert score == 'Unavailable'
        assert 'no numeric CSRS' in detail

    def test_an_all_false_mask_says_none_rather_than_nothing(self):
        _, detail = csrs_metric(
            dict(csrs=dict(CSRS_POINT, mask=[False, False, False])))
        assert 'pillars NONE' in detail

    def test_a_bool_is_not_a_score(self):
        assert csrs_metric(dict(csrs=True))[0] == 'Unavailable'

    def test_an_unrecognised_shape_is_named_not_rendered(self):
        score, detail = csrs_metric(dict(csrs=['not', 'a', 'point']))
        assert score == 'Unavailable' and 'unrecognised' in detail


# ----------------------------------------------- the four startup shapes


class TestU01EmptyStoresStartupShape:
    def test_an_entirely_empty_environment_renders(self, stores):
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert not app.exception
        assert any('No archive store' in i.value for i in app.info)

    def test_each_absent_store_is_named_with_its_override(self, stores):
        app = AppTest.from_file(str(APP)).run(timeout=60)
        footer = ' '.join(c.value for c in app.caption)
        assert 'SERAPH_PROTOTYPE_STORE' in footer
        assert 'SERAPH_LIVE_STORE' in footer
        assert 'SERAPH_NEWS_STORE' in footer
        assert footer.count('ABSENT') == 3

    def test_no_store_file_is_created_by_merely_looking(self, stores):
        AppTest.from_file(str(APP)).run(timeout=60)
        assert not any(p.exists() for p in stores.values())


class TestU01LiveOnlyStartupShape:
    """The probed failure: 1 info, 0 metrics, 0 radios."""

    def test_the_live_panel_renders_without_an_archive_store(self, stores):
        commit_live_decision(stores['live'], csrs=CSRS_POINT,
                             as_of=f'2026-10-16T10:05:00{IST}')
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert not app.exception
        assert len(app.metric) > 0, 'the live panel did not render (U01)'
        assert len(app.radio) > 0, 'the view-mode radio did not render (U01)'

    def test_the_live_score_is_the_committed_one(self, stores):
        commit_live_decision(stores['live'], csrs=CSRS_POINT,
                             as_of=f'2026-10-16T10:05:00{IST}')
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert any(m.label == 'CSRS' and '0.42' in str(m.value)
                   for m in app.metric)

    def test_a_real_payload_shape_does_not_raise(self, stores):
        """`st.metric` raised on the nested dict `run_live.commit` writes."""
        commit_live_decision(stores['live'], csrs=CSRS_POINT,
                             as_of=f'2026-10-16T10:05:00{IST}')
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert not app.exception, f'U01 nested CSRS still raises: {app.exception}'

    def test_a_withheld_decision_renders_unavailable_not_an_exception(self, stores):
        commit_live_decision(stores['live'], csrs=None,
                             as_of=f'2026-10-16T10:05:00{IST}')
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert not app.exception
        assert any(m.label == 'CSRS' and 'Unavailable' in str(m.value)
                   for m in app.metric)

    def test_the_archive_message_is_about_the_archive_only(self, stores):
        commit_live_decision(stores['live'], csrs=CSRS_POINT,
                             as_of=f'2026-10-16T10:05:00{IST}')
        app = AppTest.from_file(str(APP)).run(timeout=60)
        archive_note = [i.value for i in app.info if 'No archive store' in i.value]
        assert archive_note, 'the empty state must name the archive surface'
        assert 'do not depend on it' in archive_note[0]


class TestU01NewsOnlyStartupShape:
    def test_the_news_channel_renders_without_an_archive_store(self, stores):
        from seraph.news import NewsStore
        NewsStore(stores['news'])                    # creates the schema
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert not app.exception
        assert any('CURRENT NEWS' in c.value for c in app.caption), \
            'the news-only surface was unreachable (U01)'

    def test_an_attached_but_empty_news_store_is_an_empty_result(self, stores):
        from seraph.news import NewsStore
        NewsStore(stores['news'])
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert any('empty result, not a failure' in i.value for i in app.info)

    def test_the_news_only_surface_is_labelled_as_the_live_clock(self, stores):
        from seraph.news import NewsStore
        NewsStore(stores['news'])
        app = AppTest.from_file(str(APP)).run(timeout=60)
        note = ' '.join(c.value for c in app.caption)
        assert 'not a reconstruction' in note, \
            'a news view with no market decision must not pass as one'

    def test_an_absent_news_store_names_the_launcher(self, stores):
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert any('launch_news' in i.value for i in app.info)


class TestU01ArchiveOnlyStartupShape:
    def test_an_archive_store_with_no_complete_run_says_so(self, stores):
        from seraph.orchestration.run_store import RunStore
        store = RunStore(stores['archive'])
        store.begin(dict(mode='synthetic test fixture',
                         data_available_through='2020-01-01'))
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert not app.exception
        assert any('no COMPLETE run' in i.value for i in app.info)

    def test_that_empty_state_is_about_the_archive_not_the_application(self, stores):
        from seraph.orchestration.run_store import RunStore
        RunStore(stores['archive']).begin(
            dict(mode='synthetic test fixture',
                 data_available_through='2020-01-01'))
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert any('sealed but awaiting its report' in i.value for i in app.info)

    def test_the_news_surface_is_still_reachable(self, stores):
        """The second early return (`if not runs`) hid news too."""
        from seraph.news import NewsStore
        from seraph.orchestration.run_store import RunStore
        RunStore(stores['archive']).begin(
            dict(mode='synthetic test fixture',
                 data_available_through='2020-01-01'))
        NewsStore(stores['news'])
        app = AppTest.from_file(str(APP)).run(timeout=60)
        assert any('CURRENT NEWS' in c.value for c in app.caption)
