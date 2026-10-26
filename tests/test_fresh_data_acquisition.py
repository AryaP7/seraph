# Fresh EOD acquisition: NSE bhavcopy -> corpus -> snapshot -> prediction
"""The pipeline ran correctly on a snapshot that ended 2026-08-21 and
produced a two-month-old forecast. Every step succeeded, the scheduler fired,
and no new observation ever entered the system -- a working pipeline on stale
inputs, which is the failure a green dashboard hides.

These tests cover the acquisition layer's refusals, the incremental
bookkeeping it has to get right, and the integration points where acquiring
data and *using* it come apart. They do not re-test `parse_bhavcopy`, which
`test_bhavcopy_reader.py` owns, nor the engine, which
`test_prediction_integration.py` owns.

Almost everything here runs offline against a synthesised bhavcopy. The one
live test is marked and skipped unless `SERAPH_LIVE_NSE=1`, because a suite
that silently depends on an exchange being reachable fails for reasons that
have nothing to do with the code.
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

from seraph.ingestion import bhavcopy_client as client
from seraph.ingestion.bhavcopy_reader import parse_bhavcopy
from seraph.prediction import operational

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

UDIFF_HEADER = ('TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,'
                'SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,'
                'OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,'
                'UndrlygPric,SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,'
                'TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,'
                'Rsvd2,Rsvd3,Rsvd4')


def udiff_row(symbol, day, *, open_=100.0, high=110.0, low=95.0, close=105.0,
              volume=1000, value=105000.0):
    return (f'{day},{day},CM,NSE,STK,1,INE000A01001,{symbol},EQ,,,,,'
            f'{symbol} LTD,{open_},{high},{low},{close},{close},{open_},'
            f',,,,{volume},{value},10,F1,1,,,,,')


def udiff_csv(day='2026-10-19', rows=600, **overrides):
    body = [UDIFF_HEADER]
    for index in range(rows):
        body.append(udiff_row(f'SYM{index:04d}', day, **overrides))
    return '\n'.join(body).encode('utf-8')


def parsed(day='2026-10-19', rows=600, **overrides):
    return parse_bhavcopy(udiff_csv(day=day, rows=rows, **overrides))


class TestWhichSessionsAreMissing:
    @staticmethod
    def declared_clock():
        from seraph.live.clock import MarketClock
        from seraph.market_calendar import SessionCalendar
        return MarketClock(calendar=SessionCalendar(session_dates={'2026-10-19', '2026-10-21'}))

    def test_it_lists_only_trading_days(self):
        days = client.sessions_to_acquire(latest_stored='2026-10-16',
                    expected='2026-10-21', clock=self.declared_clock())
        assert days == ['2026-10-19', '2026-10-21']

    def test_it_starts_after_the_last_stored_session(self):
        days = client.sessions_to_acquire(latest_stored='2026-10-19',
                    expected='2026-10-21', clock=self.declared_clock())
        assert days == ['2026-10-21']

    def test_nothing_is_missing_when_the_corpus_is_current(self):
        assert client.sessions_to_acquire(latest_stored='2026-10-20',
                                          expected='2026-10-20') == []

    def test_the_limit_bounds_a_backfill(self):
        days = client.sessions_to_acquire(latest_stored='2026-08-21',
                                          expected='2026-10-19', limit=5)
        assert len(days) == 5
        assert days[0] == '2026-08-24'

    def test_an_empty_corpus_asks_only_for_the_expected_session(self):
        """Not 2005 to today: a first run must not try to fetch five
        thousand files one at a time."""
        assert client.sessions_to_acquire(latest_stored=None,
                                          expected='2026-10-19') \
            == ['2026-10-19']

    def test_both_archive_layouts_are_tried(self):
        """NSE replaced the legacy layout with UDiFF in July 2024, so a
        session near the changeover may exist under only one."""
        urls = client.candidate_urls('2026-10-19')
        assert len(urls) == 2
        assert 'BhavCopy_NSE_CM_0_0_0_20261019_F_0000.csv.zip' in urls[0][0]
        assert 'cm19OCT2026bhav.csv.zip' in urls[1][0]


class TestTheRefusals:
    """Each of these is a file that parses cleanly and must not be stored."""

    def test_a_file_dated_differently_from_the_request_is_refused(self):
        """The worst failure an acquisition layer can have: writing one
        session's prices under another session's date."""
        refusal = client.validate(parsed(day='2026-10-16'), day='2026-10-19')
        assert refusal and 'trade date' in refusal
        assert 'another session' in refusal

    def test_an_empty_file_is_refused(self):
        refusal = client.validate(parsed(rows=0), day='2026-10-19')
        assert refusal and 'no rows' in refusal

    def test_an_implausibly_small_file_is_refused(self):
        """A truncated or placeholder file would quietly shrink the
        cross-section every downstream estimator computes on."""
        refusal = client.validate(parsed(rows=10), day='2026-10-19')
        assert refusal and 'below the' in refusal
        assert '2,700' in refusal

    def test_a_high_below_the_low_is_caught_by_the_parser(self):
        """Two layers, and this one was already there: `parse_bhavcopy`
        rejects the row itself with a reason, so the file arrives empty and
        is refused for having no rows rather than for the OHLC."""
        result = parsed(high=90.0, low=95.0, open_=92.0, close=93.0)
        assert result.rows == []
        assert result.rejected
        assert 'is below low' in result.rejected[0]['reason']
        assert client.validate(result, day='2026-10-19') is not None

    def test_a_close_outside_the_range_is_caught_here(self):
        """What the parser does NOT check: the four numbers against each
        other. high >= low holds, every value parses, and the close is still
        impossible."""
        refusal = client.validate(parsed(low=95.0, high=110.0, open_=100.0,
                                         close=150.0),
                                  day='2026-10-19')
        assert refusal and 'cannot be true' in refusal

    def test_an_open_outside_the_range_is_caught_here(self):
        refusal = client.validate(parsed(low=95.0, high=110.0, open_=5.0,
                                         close=100.0),
                                  day='2026-10-19')
        assert refusal and 'cannot be true' in refusal

    def test_one_bad_row_among_good_ones_still_refuses_the_file(self):
        """A single impossible bar poisons that symbol's return, so the day
        is refused rather than stored with it."""
        body = [UDIFF_HEADER]
        for index in range(600):
            body.append(udiff_row(f'SYM{index:04d}', '2026-10-19'))
        body.append(udiff_row('POISON', '2026-10-19', low=95.0, high=110.0,
                              open_=100.0, close=150.0))
        result = parse_bhavcopy('\n'.join(body).encode('utf-8'))
        assert len(result.rows) == 601
        refusal = client.validate(result, day='2026-10-19')
        assert refusal and 'POISON' in refusal

    def test_a_non_positive_price_is_refused(self):
        refusal = client.validate(parsed(low=0.0, open_=0.0, close=0.0,
                                         high=0.0),
                                  day='2026-10-19')
        assert refusal is not None

    def test_a_good_file_is_accepted(self):
        assert client.validate(parsed(), day='2026-10-19') is None

    def test_the_floor_is_below_a_real_thin_day(self):
        """2,698 rows on 2026-10-19. The floor must refuse a placeholder
        without refusing an ordinary session."""
        assert 0 < client.MIN_PLAUSIBLE_ROWS < 1000


class TestIncrementalBookkeeping:
    def test_the_listing_counter_continues_from_the_corpus(self):
        """FR52 filters on `listing_days_to_date >= 1000`. A fresh row
        written with 0 would drop that symbol out of the eligible set."""
        state = client._ListingState(last_date={'RELIANCE': '2026-10-16'},
                                     days={'RELIANCE': 5000})
        assert state.next_for('RELIANCE', '2026-10-19') == 5001

    def test_a_symbol_new_to_the_corpus_starts_at_one(self):
        state = client._ListingState()
        assert state.next_for('NEWLISTING', '2026-10-19') == 1

    def test_re_acquiring_a_counted_day_does_not_double_count(self):
        """Re-running a day is expected -- the write is an upsert -- so the
        counter must not advance twice for the same session."""
        state = client._ListingState(last_date={'X': '2026-10-19'},
                                     days={'X': 100})
        assert state.next_for('X', '2026-10-19') == 100
        assert state.next_for('X', '2026-10-19') == 100

    def test_consecutive_days_advance_once_each(self):
        state = client._ListingState()
        assert [state.next_for('X', d) for d in
                ('2026-10-19', '2026-10-20', '2026-10-21')] == [1, 2, 3]


class TestTheStoredRows:
    def test_adj_close_is_the_close_and_not_invented(self):
        """A bhavcopy is unadjusted. For the session it describes the
        adjusted and unadjusted close are the same number, so this is not an
        approximation -- but a later corporate action will not retroactively
        adjust these rows until D04 does."""
        bars = client.to_daily_bars(parsed(rows=600), day='2026-10-19',
                                    listing=client._ListingState())
        assert bars
        for bar in bars[:5]:
            assert bar.adj_close == bar.close

    def test_the_exact_traded_value_is_carried_not_the_proxy(self):
        """`eod2_client` approximates tottrdval as close x volume and warns
        on every batch. FR52 ranks the universe on it."""
        result = parsed(rows=600, close=105.0, volume=1000, value=99999.0)
        assert result.traded_value_basis == 'exact_TOTTRDVAL'
        bars = client.to_daily_bars(result, day='2026-10-19',
                                    listing=client._ListingState())
        assert bars[0].tottrdval == pytest.approx(99999.0)
        assert bars[0].tottrdval != pytest.approx(105.0 * 1000)

    def test_the_date_written_is_the_requested_session(self):
        bars = client.to_daily_bars(parsed(day='2026-10-19'),
                                    day='2026-10-19',
                                    listing=client._ListingState())
        assert {bar.date for bar in bars} == {'2026-10-19'}

    def test_the_source_is_the_existing_closed_vocabulary_value(self):
        """`IngestBatch.source` is a closed Literal and `bhavcopy` is
        already one of its values. Inventing `nse-bhavcopy` failed
        validation -- the right value already existed."""
        from typing import get_args

        from seraph.shared_types import IngestBatch

        permitted = get_args(
            IngestBatch.model_fields['source'].annotation)
        assert 'bhavcopy' in permitted
        source = Path(client.__file__).read_text(encoding='utf-8')
        assert 'source="bhavcopy"' in source
        assert 'nse-bhavcopy' not in source


class TestTheStatusVocabulary:
    """Four outcomes with four different operator actions, so they cannot
    share one."""

    def test_the_statuses_are_distinct(self):
        from typing import get_args

        assert set(get_args(client.SessionStatus)) == {
            'stored', 'not_published', 'blocked', 'unavailable', 'invalid'}

    def test_an_unzip_handles_a_bare_csv_too(self):
        raw = udiff_csv(rows=5)
        assert client._unzip(raw) == raw

    def test_an_unzip_reads_the_csv_from_an_archive(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('BhavCopy_x.csv', udiff_csv(rows=5))
        extracted = client._unzip(buffer.getvalue())
        assert extracted.startswith(b'TradDt')

    def test_an_archive_without_a_csv_is_an_error(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, 'w') as archive:
            archive.writestr('readme.txt', b'nope')
        with pytest.raises(ValueError, match='no CSV'):
            client._unzip(buffer.getvalue())


class TestItReusesRatherThanReimplements:
    def test_it_uses_the_shared_fetcher_and_parser(self):
        import ast

        source = Path(client.__file__).read_text(encoding='utf-8')
        imported = set()
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.update(a.name for a in node.names)
        assert '_Fetcher' in imported, 'the retry/backoff/cache is reimplemented'
        assert 'parse_bhavcopy' in imported, 'the schema parsing is reimplemented'

    def test_it_writes_through_the_idempotent_bulk_path(self):
        """Upsert on (symbol, date), so re-acquiring a day converges to
        inserted: 0 (CT-1)."""
        source = Path(client.__file__).read_text(encoding='utf-8')
        assert 'write_batch_bulk' in source

    def test_the_archive_gap_is_justified_and_polite(self):
        """The shared 20s default is for FRED's adaptive throttle. A static
        ZIP archive does not need it, and this is not a bypass."""
        assert 1.0 <= client.ARCHIVE_GAP_S < 20.0


class TestTheSnapshotSelection:
    def test_the_rebuilt_snapshot_is_preferred(self, tmp_path, monkeypatch):
        monkeypatch.delenv('SERAPH_MARKET_SNAPSHOT', raising=False)
        import hashlib
        current = tmp_path / 'market_snapshot.parquet'
        monkeypatch.setattr(operational, 'CURRENT_SNAPSHOT', current)
        current.write_bytes(b'legacy snapshot fixture')
        assert operational.snapshot_path() == current
        version = tmp_path / 'versions' / 'test-version'
        version.mkdir(parents=True)
        candidate = version / 'market_snapshot.parquet'
        candidate.write_bytes(b'versioned snapshot fixture')
        manifest = version / 'manifest.json'
        manifest.write_text('{}')
        (tmp_path / 'active.json').write_text(json.dumps(dict(
            version='test-version', sha256=hashlib.sha256(candidate.read_bytes()).hexdigest(),
            manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest())))
        assert operational.snapshot_path() == candidate
        candidate.write_bytes(b'corrupted snapshot')
        with pytest.raises(ValueError, match='identity mismatch'):
            operational.snapshot_path()

    def test_the_frozen_experiment_input_is_not_overwritten(self):
        """`research_data/market_snapshot.parquet` is the input
        `research_results/v1` was produced from and its sha256 is in that
        run's manifest. Rebuilding it in place would make the frozen
        experiment unreproducible.

        Asserted on the `--out` value the step actually passes, not on the
        file's text: the module docstring names the frozen path in order to
        explain that it is NOT written, so a substring search finds exactly
        the string it is trying to forbid. The fifth time this session.
        """
        source = (SCRIPTS / 'run_acquisition.py').read_text(encoding='utf-8')
        assert 'Path("research_data/current/versions")' in source
        assert '"--out", str(version)' in source

    def test_the_environment_override_wins(self, tmp_path, monkeypatch):
        monkeypatch.setenv('SERAPH_MARKET_SNAPSHOT', str(tmp_path / 's.parquet'))
        assert operational.snapshot_path() == tmp_path / 's.parquet'

    def test_provenance_distinguishes_rebuilt_from_frozen(self):
        root = Path(operational.__file__).resolve().parents[2]
        rebuilt = operational.snapshot_provenance(
            root / operational.CURRENT_SNAPSHOT)
        frozen = operational.snapshot_provenance(
            root / operational.FROZEN_SNAPSHOT)
        assert rebuilt['kind'] == 'rebuilt'
        assert frozen['kind'] == 'frozen_experiment_input'
        assert 'not today' in frozen['note']

    def test_the_state_records_which_snapshot_it_used(self):
        saved = operational.load_state()
        if saved.get('ran'):
            assert 'kind' in saved['state']['snapshot']


class TestSchedulerIntegration:
    def test_acquisition_is_the_first_daily_step(self):
        source = (SCRIPTS / 'run_market_jobs.py').read_text(encoding='utf-8')
        assert 'scripts/run_acquisition.py' in source
        assert 'fresh market data' in source

    def test_the_corpus_is_read_after_acquisition_not_before(self):
        """The session read used to happen before any step. With acquisition
        added in front, the vintages and the forecast would have been
        computed for the pre-acquisition date -- a run that fetched today's
        prices and then scored yesterday."""
        source = (SCRIPTS / 'run_market_jobs.py').read_text(encoding='utf-8')
        body = source.split('def run_all', 1)[1].split('\ndef ', 1)[0]
        acquire_at = body.index('run_acquisition.py')
        read_at = body.index('_latest_session()')
        assert acquire_at < read_at, (
            'the corpus is read before acquisition, so every downstream step '
            'would use the pre-acquisition date')

    def test_re_derivation_only_happens_when_something_was_stored(self):
        source = (SCRIPTS / 'run_acquisition.py').read_text(encoding='utf-8')
        body = source.split('def run(', 1)[1].split('\ndef ', 1)[0]
        assert 'if not pending:' in body
        assert 'identical files' in body

    def test_only_the_affected_years_are_re_flagged(self):
        """A full 2005-2026 rebuild re-reads every rebalance for no reason."""
        source = (SCRIPTS / 'run_acquisition.py').read_text(encoding='utf-8')
        assert 'day[:4] for day in stored' in source

    def test_it_does_not_introduce_a_second_scheduler(self):
        source = (SCRIPTS / 'run_acquisition.py').read_text(encoding='utf-8')
        for forbidden in ('schtasks', 'crontab', 'Register-ScheduledTask'):
            assert forbidden not in source

    def test_the_status_separates_execution_from_acquisition(self):
        import run_acquisition

        saved = run_acquisition.status()
        if saved.get('ran'):
            assert 'ok' in saved and 'acquired' in saved


class TestFailedAcquisitionDoesNotLookCurrent:
    """Requirement: failed acquisition must not silently produce a
    misleading current prediction."""

    def test_an_unreachable_store_is_reported_not_raised(self):
        import asyncio

        report = asyncio.run(client.acquire(
            dsn='postgresql://nobody:nobody@127.0.0.1:1/none'))
        assert report['ok'] is False
        assert report['acquired'] is False
        assert 'unreachable' in report['blocked']

    def test_a_stale_forecast_is_marked_rather_than_discarded(self):
        from seraph.operations.schedule import prediction_staleness

        marked = prediction_staleness('2026-08-21', expected='2026-10-19')
        assert marked['stale'] is True
        assert marked['days_behind'] > 0
        assert 'last valid forecast' in marked['detail']

    def test_a_current_forecast_is_not_marked_stale(self):
        from seraph.operations.schedule import prediction_staleness

        assert prediction_staleness('2026-10-19',
                                    expected='2026-10-19')['stale'] is False

    def test_the_panel_shows_the_acquisition_verdict(self):
        body = (Path('seraph/dashboard/prototype_app.py')
                .read_text(encoding='utf-8'))
        panel = body.split('def health_panel', 1)[1].split('\ndef ', 1)[0]
        assert 'Acquisition FAILED' in panel
        assert 'acquired nothing' in panel
        assert 'never run' in panel


@pytest.mark.skipif(os.environ.get('SERAPH_LIVE_NSE') != '1',
                    reason=('hits NSE. Set SERAPH_LIVE_NSE=1 to run. A suite '
                            'that silently depends on an exchange being '
                            'reachable fails for reasons unrelated to the '
                            'code.'))
class TestAgainstTheLiveSource:
    def test_a_real_session_is_fetched_parsed_and_validated(self):
        from seraph.ingestion.macro_client import _Fetcher

        fetcher = _Fetcher(client.DEFAULT_CACHE_DIR,
                           gap_s=client.ARCHIVE_GAP_S)
        raw, url, digest = client.fetch_session(fetcher, '2026-10-19')
        result = parse_bhavcopy(raw)
        assert client.validate(result, day='2026-10-19') is None
        assert len(result.rows) > client.MIN_PLAUSIBLE_ROWS
        assert result.traded_value_basis == 'exact_TOTTRDVAL'
        assert len(digest) == 64


class TestTheDailyVintagesReachTheCurrentRiskPath:
    """`run_live.py` built `InferenceService` with no deployments, so the
    registry was empty and `reason_unusable` refused every real vintage with
    `bundle original rmt is not registered`. The producer handed over a
    stored, available vintage and the service then withheld it -- the daily
    pillars could not reach the current-risk path at all.

    Found by a concurrent session's engineering audit, which named the exact
    line numbers. The fix registers from the store, so a bundle exists
    because a vintage was produced by it.
    """

    @staticmethod
    def _store(tmp_path):
        from seraph.live.store import LiveStore

        store = LiveStore(tmp_path / 'live.sqlite')
        for producer, bundle, input_end, available in (
                ('rmt', 'original rmt', '2026-10-16T15:30:00+05:30',
                 '2026-10-16T16:00:00+05:30'),
                ('rmt', 'original rmt', '2026-10-19T15:30:00+05:30',
                 '2026-10-19T16:00:00+05:30'),
                ('hamilton', 'original hamilton', '2026-10-19T15:30:00+05:30',
                 '2026-10-19T16:00:00+05:30')):
            store.record_daily_vintage(
                producer=producer, bundle_id=bundle, input_end=input_end,
                emission_available_at=available, value=0.3, variance=0.01,
                quality='ok', coverage=1.0, origin='computed')
        return store

    def test_an_empty_registry_refuses_a_real_vintage(self, tmp_path):
        """The defect, reproduced, so the fix is not asserted against
        nothing."""
        from datetime import datetime

        from seraph.live.inference import DeploymentRegistry

        self._store(tmp_path)
        reason = DeploymentRegistry().reason_unusable(
            'original rmt', datetime.fromisoformat('2026-10-19T16:00:00+05:30'))
        assert reason == 'bundle original rmt is not registered'

    def test_a_registry_from_the_store_admits_it(self, tmp_path):
        from datetime import datetime

        from seraph.live.engine_adapter import registry_from_store

        registry = registry_from_store(self._store(tmp_path))
        moment = datetime.fromisoformat('2026-10-19T16:00:00+05:30')
        assert registry.reason_unusable('original rmt', moment) is None
        assert registry.reason_unusable('original hamilton', moment) is None

    def test_a_bundle_nobody_produced_is_still_refused(self, tmp_path):
        """Registering from the store must not become registering
        everything: the refusal is the point."""
        from datetime import datetime

        from seraph.live.engine_adapter import registry_from_store

        registry = registry_from_store(self._store(tmp_path))
        reason = registry.reason_unusable(
            'invented bundle',
            datetime.fromisoformat('2026-10-19T16:00:00+05:30'))
        assert reason == 'bundle invented bundle is not registered'

    def test_availability_is_the_earliest_emission_not_the_latest(self,
                                                                  tmp_path):
        """Using the latest would make a bundle unusable for every decision
        before its most recent emission -- refusing exactly the historical
        decisions it was available for."""
        from datetime import datetime

        from seraph.live.engine_adapter import registry_from_store

        registry = registry_from_store(self._store(tmp_path))
        earlier = datetime.fromisoformat('2026-10-16T16:00:00+05:30')
        assert registry.reason_unusable('original rmt', earlier) is None

    def test_a_bundle_is_still_refused_before_it_existed(self, tmp_path):
        from datetime import datetime

        from seraph.live.engine_adapter import registry_from_store

        registry = registry_from_store(self._store(tmp_path))
        before = datetime.fromisoformat('2026-10-15T16:00:00+05:30')
        reason = registry.reason_unusable('original rmt', before)
        assert reason and 'becomes available at' in reason

    def test_the_store_query_groups_by_bundle(self, tmp_path):
        rows = self._store(tmp_path).daily_vintage_bundles()
        by_id = {row['bundle_id']: row for row in rows}
        assert set(by_id) == {'original rmt', 'original hamilton'}
        assert by_id['original rmt']['vintages'] == 2
        assert by_id['original rmt']['available_at'] \
            == '2026-10-16T16:00:00+05:30'
        assert by_id['original rmt']['trained_through'] \
            == '2026-10-19T15:30:00+05:30'

    def test_an_unstamped_vintage_needs_no_registration(self, tmp_path):
        """A vintage with no bundle id is admitted by `reason_unusable`
        already; it must not create a nameless bundle."""
        from seraph.live.store import LiveStore

        store = LiveStore(tmp_path / 'live.sqlite')
        store.record_daily_vintage(
            producer='rmt', bundle_id='',
            input_end='2026-10-19T15:30:00+05:30',
            emission_available_at='2026-10-19T16:00:00+05:30', value=0.3,
            variance=0.01, quality='ok', coverage=1.0, origin='computed')
        assert store.daily_vintage_bundles() == []

    def test_run_live_passes_the_registry(self):
        source = (SCRIPTS / 'run_live.py').read_text(encoding='utf-8')
        assert 'registry_from_store(store, allow_legacy=replay)' in source
        assert 'deployments=deployments' in source
