"""C2/F02/F04: bounded recovery must not skip a longer or failed request."""
import asyncio
from datetime import datetime
from types import SimpleNamespace

import pytest

from scripts import backfill_intraday as job


@pytest.fixture
def rig(monkeypatch, tmp_path):
    calls, batches = [], []
    candle = ['2020-02-20T09:15:00+05:30', 100, 102, 99, 101, 500]
    state = SimpleNamespace(candles=[candle], fail=False, closed=False)

    class Client:
        def instruments_nse(self): return {'TEST': 123}
        def historical(self, token, interval, start, end):
            calls.append((token, interval, start, end))
            return state.candles

    class Writer:
        async def write_batch_bulk(self, batch):
            batches.append(batch)
            return SimpleNamespace(status='error' if state.fail else 'ok', error='test failure')
        async def close(self): state.closed = True

    async def connect(): return Writer()
    monkeypatch.setattr(job, 'KiteClient', Client)
    monkeypatch.setattr(job.StoreWriter, 'connect', connect)
    path = tmp_path/'checkpoint.json'

    def run(end='2020-02-21', dry=False):
        return asyncio.run(job.main('2020-02-20', dry, end=end,
                                    symbols=('TEST',), checkpoint=path))
    return state, calls, batches, path, run


def test_resume_skips_before_fetch_but_extended_window_is_fetched(rig):
    state, calls, batches, path, run = rig
    # Preserve legacy evidence; a start date alone is insufficient to skip.
    job.save_checkpoint({'TEST|2020-02-20'}, path)
    assert run() == 0
    assert calls[0][3].isoformat() == '2020-02-21T15:30:00+05:30'
    assert run() == 0 and len(calls) == 1
    assert run('2020-02-24') == 0 and len(calls) == 2
    assert len(batches) == 2 and state.closed
    assert 'TEST|2020-02-20' in job.load_checkpoint(path)
    assert len(job.load_checkpoint(path)) == 3


@pytest.mark.parametrize('failure', ['write', 'empty', 'all_rejected', 'part_rejected'])
def test_incomplete_window_stays_retriable(rig, failure):
    state, calls, batches, path, run = rig
    valid = list(state.candles)
    if failure == 'write': state.fail = True
    if failure == 'empty': state.candles = []
    if failure == 'all_rejected': state.candles = [['2020-02-20', 'bad', 1, 1, 1, 1]]
    if failure == 'part_rejected': state.candles += [['2020-02-20', 'bad', 1, 1, 1, 1]]
    assert run() == 2
    assert not job.load_checkpoint(path) and state.closed
    state.fail, state.candles = False, valid
    assert run() == 0 and len(calls) == 2


def test_explicit_dry_run_never_opens_broker_or_writer(rig, monkeypatch):
    *_, path, run = rig
    def forbidden(): raise AssertionError('dry run touched broker')
    monkeypatch.setattr(job, 'KiteClient', forbidden)
    assert run(dry=True) == 0 and not path.exists()
    with pytest.raises(ValueError, match='start before end'):
        run('2020-02-19')


def test_window_plan_is_bounded_and_exact():
    start = datetime.fromisoformat('2020-01-01T09:00:00+05:30')
    end = datetime.fromisoformat('2020-08-01T15:30:00+05:30')
    windows = list(job.request_windows(start, end))
    assert windows[0][0] == start and windows[-1][1] == end
    assert all((b-a).total_seconds() <= 100*86400 for a,b in windows)
    assert all(a[1] == b[0] for a,b in zip(windows, windows[1:]))

class TestTheDefaultWindowNeverEndsMidSession:
    """F02: the 14,616-bar truncation, and why it was not the broker.

    With no `--to`, the window used to end at `now - 5 minutes`. A daily job
    runs during market hours, so that asked Kite for a window ending
    mid-session; Kite answered correctly with the bars up to that point.
    Repeated once per session it removed the last three 5-minute bars of 56
    consecutive sessions for 87 of 95 members -- 14,616 of the 14,630
    missing symbol-bars in the trailing 500-session window (99.90%). The
    remaining 14 are genuine no-trade intervals in four liquid names and are
    NOT recoverable by asking again.
    """

    def test_a_mid_session_run_stops_at_the_previous_close(self):
        """15:20 on a Thursday must not ask for Thursday at all."""
        now = datetime.fromisoformat('2026-10-22T15:20:00+05:30')
        got = job._last_completed_session_close(now)
        assert got == datetime.fromisoformat('2026-10-21T15:30:00+05:30')
        assert got < now.replace(hour=9, minute=15)

    def test_after_the_close_the_whole_session_is_requested(self):
        now = datetime.fromisoformat('2026-10-22T15:31:00+05:30')
        assert job._last_completed_session_close(now) == \
            datetime.fromisoformat('2026-10-22T15:30:00+05:30')

    def test_a_non_session_day_walks_back_to_a_real_close(self):
        """Saturday resolves to Friday, not to Saturday minus five minutes."""
        now = datetime.fromisoformat('2026-10-24T17:50:00+05:30')
        assert job._last_completed_session_close(now) == \
            datetime.fromisoformat('2026-10-23T15:30:00+05:30')

    def test_the_close_comes_from_the_calendar_not_a_fixed_1530(self):
        """A short session must end at its OWN close.

        Diwali Muhurat trading is an evening session. A hardcoded 15:30
        would claim bars that never existed for it.
        """
        from seraph.market_calendar.sessions import SessionCalendar
        calendar = SessionCalendar()
        for registered in calendar.registered():
            if registered.close != '15:30:00':
                now = datetime.fromisoformat(
                    f'{registered.date}T23:59:00+05:30')
                got = job._last_completed_session_close(now)
                assert got.date().isoformat() == registered.date
                assert got.strftime('%H:%M:%S') == registered.close
                break
