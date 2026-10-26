"""C5 — durable native-bar producer for the live C8 seam (FR10–15).

Uses the existing detector, discrete estimator and DR-08 basket policy.
The window is explicitly configured, never fitted to a desired output. Late
fits retain their actual availability and cannot satisfy an earlier cutoff.
The separate F07 network diagnostic is not invoked here.
"""
from datetime import date, datetime, timedelta
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sqlite3

import numpy as np

from seraph.shared_types import IST
from seraph.live.inference import ModelBundle, Vintage
from seraph.pillars.hawkes.basket_stream import PooledStream, basket_digest, verify_manifest
from seraph.pillars.hawkes.engine import fit_discrete_hawkes, asymmetry_significance


def timestamp(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError('Native inputs require explicit timestamps')
    return moment.astimezone(IST).isoformat()


def read_worker_status(config_path):
    """Read configuration/status without opening a native database or a feed."""
    if config_path is None:
        return dict(configured=False, worker=None)
    path = Path(config_path)
    config = json.loads(path.read_text(encoding='utf-8'))
    status_path = path.with_suffix('.status.json')
    return dict(configured=True, members=len(config['members']),
                window_sessions=config['window_sessions'],
                rebalance_date=config['rebalance_date'],
                session_schedule_file=config.get('session_schedule_file'),
                worker=(json.loads(status_path.read_text(encoding='utf-8'))
                        if status_path.exists() else None))


class NativeHistory:
    """Append-only closes; revisions are refused, arrivals never backdated."""
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS native_closes ('
                       'symbol TEXT NOT NULL, end TEXT NOT NULL, close REAL NOT NULL, '
                       'received_at TEXT NOT NULL, source TEXT NOT NULL, '
                       'PRIMARY KEY(symbol,end))')

    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        return db

    def append(self, bars, *, received_at, source='live_closed_bar'):
        received = timestamp(received_at)
        with self.connect() as db:
            for bar in bars:
                end = timestamp(bar.end)
                if (not bar.complete or datetime.fromisoformat(end) > datetime.fromisoformat(received)
                        or datetime.fromisoformat(end)-datetime.fromisoformat(bar.start) != timedelta(minutes=5)):
                    raise ValueError('Native input must be a complete five-minute bar received after its end')
                if not math.isfinite(bar.close) or bar.close <= 0:
                    raise ValueError('Native close must be finite and positive')
                old = db.execute('SELECT close FROM native_closes WHERE symbol=? AND end=?',
                                 (bar.symbol, end)).fetchone()
                if old is not None and old['close'] != bar.close:
                    raise ValueError('Native close revision requires a separate input archive')
                db.execute('INSERT OR IGNORE INTO native_closes VALUES (?,?,?,?,?)',
                           (bar.symbol, end, bar.close, received, source))

    def rows(self, members, cutoff, *, session_schedule=None, basket=None,
             arrival=None):
        if not members:
            return []
        mark = timestamp(cutoff)
        reach = timestamp(arrival) if arrival else mark
        condition, extra = (session_schedule.sql_filter(basket or members, reach)
                            if session_schedule else ('', ()))
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                'SELECT * FROM native_closes WHERE symbol IN (' + ','.join('?' for _ in members)
                + ') AND end<=? AND received_at<=?'+condition+' ORDER BY end,symbol',
                (*members, mark, reach, *extra))]

    def sessions(self, members, cutoff, *, arrival=None):
        if not members:
            return []
        mark = timestamp(cutoff)
        reach = timestamp(arrival) if arrival else mark
        with self.connect() as db:
            return [row[0] for row in db.execute(
                'SELECT DISTINCT substr(end,1,10) FROM native_closes WHERE symbol IN ('
                + ','.join('?' for _ in members)
                + ') AND end<=? AND received_at<=? ORDER BY 1', (*members, mark, reach))]

    def eligible_count(self, members, cutoff, *, arrival=None):
        """An append-only input generation, including newly eligible late rows."""
        mark = timestamp(cutoff)
        reach = timestamp(arrival) if arrival else mark
        with self.connect() as db:
            return db.execute('SELECT COUNT(*) FROM native_closes WHERE symbol IN ('
                + ','.join('?' for _ in members) + ') AND end<=? AND received_at<=?',
                (*members, mark, reach)).fetchone()[0]

    def coverage(self, members, cutoff, *, window_start, session_schedule=None,
                 arrival=None):
        """Check the observed common grid before extracting millions of jumps.

        Counts describe actual rows; missing session-edge bars are not inferred
        from a weekday calendar, and no missing contributor is filled with zero.
        """
        members = tuple(sorted(set(members)))
        mark = timestamp(cutoff)
        reach = timestamp(arrival) if arrival else mark
        where = (' FROM native_closes WHERE symbol IN ('
                 + ','.join('?' for _ in members)
                 + ') AND end>=? AND end<=? AND received_at<=?')
        args = (*members, window_start+'T00:00:00+05:30', mark, reach)
        condition, extra = (session_schedule.sql_filter(members, reach)
                            if session_schedule else ('', ()))
        with self.connect() as db:
            grid = db.execute('SELECT end,COUNT(*)'+where+condition+' GROUP BY end ORDER BY end',
                              (*args, *extra)).fetchall()
            counts = dict(db.execute('SELECT symbol,COUNT(*)'+where+condition+' GROUP BY symbol',
                                     (*args, *extra)))
            excluded = (db.execute('SELECT COUNT(*)'+where, args).fetchone()[0]-sum(counts.values())
                        if condition else 0)
        times = [datetime.fromisoformat(row[0]) for row in grid]
        missing = {symbol: len(grid)-counts.get(symbol, 0)
                   for symbol in members if counts.get(symbol, 0) < len(grid)}
        return dict(observed_sessions=len({t.date() for t in times}),
                    observed_bins=len(grid), required_members=len(members),
                    complete_members=[s for s in members if s not in missing],
                    incomplete_members=list(missing), missing_bars_by_member=missing,
                    incomplete_bins=sum(row[1] < len(members) for row in grid),
                    missing_symbol_bars=sum(missing.values()),
                    excluded_noncommon_rows=excluded,
                    session_schedule_sha256=session_schedule.sha256 if session_schedule else None,
                    grid_gaps=sum(a.date() == b.date() and b-a != timedelta(minutes=5)
                                  for a, b in zip(times, times[1:])),
                    input_end=grid[-1][0] if grid else None, window_start=window_start)


class NativeHawkesProducer:
    """Persist each closed batch and emit only supported, registered estimates.

Missing native inputs are transient once this producer is configured, keeping
Hawkes in the D2 mask and preventing an RMT-only score from claiming readiness.
"""
    def __init__(self, history, daily, *, members, rebalance_date, window_sessions,
                 refit_sessions=5, now=None, session_schedule=None):
        if not members or not isinstance(window_sessions, int) or window_sessions < 1:
            raise ValueError('Declare members and a positive window_sessions')
        date.fromisoformat(rebalance_date)
        if not isinstance(refit_sessions, int) or refit_sessions < 1:
            raise ValueError('Declare a positive refit_sessions')
        self.history, self.daily = history, daily
        self.session_schedule = session_schedule
        self.members = tuple(sorted(set(members)))
        self.rebalance_date = rebalance_date
        self.window_sessions = window_sessions
        # Same five-session cadence as the existing production writer. The
        # latest estimate retains its original observation time between fits.
        self.refit_sessions = refit_sessions
        self.now = now or (lambda: datetime.now(IST))
        self.status = dict(kind='native_hawkes', observed_sessions=0,
                           reason='native history has not yet been inspected')
        self._last_input_count = None
        self._last_result = None

    def describe(self):
        return dict(self.status, window_sessions=self.window_sessions,
                    refit_sessions=self.refit_sessions,
                    members=list(self.members), rebalance_date=self.rebalance_date,
                    membership_policy='fixed_at_fit_cutoff',
                    session_schedule_sha256=self.session_schedule.sha256 if self.session_schedule else None,
                    note='Contemporaneous diagnostic; prospective predictive skill unestablished')

    def vintages_for(self, bars, as_of):
        received = self.now()
        self.history.append(bars, received_at=received.isoformat())
        other = [v for v in self.daily.vintages_for(bars, as_of) if v.producer != 'hawkes']
        end = max((b.end for b in bars), default=as_of.isoformat())
        reason = 'insufficient_history'
        cutoff = min(received, as_of).isoformat()
        days = self.history.sessions(self.members, cutoff)
        self.status.update(observed_sessions=len(days))
        self.status['reason'] = 'Insufficient native sessions for the explicitly configured window'
        manifests = {row['bundle_id']: row for row in self.daily.store.deployments()}
        compatible = [row for row in manifests.values() if self._compatible(row)]
        previous = max((row['trained_through'] for row in compatible), default=None)
        due = previous is None or sum(day > previous[:10] for day in days) >= self.refit_sessions
        if self.rebalance_date > end[:10]:
            self.status['reason'] = 'Basket snapshot is after the requested input time'
        elif not due:
            self.status['reason'] = 'Retaining the existing fit and its observation time until the declared refit cadence'
        elif len(days) >= self.window_sessions:
            self.status['reason'] = 'Native fit is due; the separate producer worker performs estimation'
        # Only read completed fits; numerical estimation never blocks this bar-close callback.
        candidates = self.daily.vintages_for(bars, as_of)
        manifests = {row['bundle_id']: row for row in self.daily.store.deployments()}
        for value in candidates:
            if value.producer == 'hawkes' and value.bundle_id.startswith('native-hawkes:'):
                if self._compatible(manifests.get(value.bundle_id, {})):
                    return [value, *other]
        return [Vintage(producer='hawkes', input_end=end,
                        emission_available_at=received.isoformat(), absence='transient',
                        absence_reason=reason), *other]

    def fit_pending(self, *, data_cutoff=None):
        """Called by the separate C5 process, never the live bar-close callback.

        `data_cutoff` fits a PAST window: bars are selected by when they
        happened, while the arrival guard stays on the real clock, so a
        historical replay cannot see a bar that had not arrived. Omitted, the
        cutoff is `now()` and this behaves exactly as the live worker does.
        """
        arrival = self.now().isoformat()
        cutoff = data_cutoff or arrival
        count = self.history.eligible_count(self.members, cutoff, arrival=arrival)
        # Dated rule sets are keyed on ARRIVAL: a replay run today knows the
        # exchange evidence published today, and says so in the vintage's
        # actual availability rather than backdating it.
        calendar_key = ((tuple(self.session_schedule.cutoffs(self.members, arrival).items()),
                         tuple(self.session_schedule.openings(self.members, arrival).items()))
                        if self.session_schedule else ())
        version = (count, calendar_key, cutoff)
        if self._last_result is not None and version == self._last_input_count:
            return dict(deepcopy(self._last_result), reused_result=True)
        # Exceptions are deliberately not cached: a temporary store failure is
        # retryable without a new market bar. Supported/unavailable evaluations
        # are stable until append-only inputs change or a late arrival is eligible.
        result = self._fit_pending(cutoff, arrival=arrival)
        result['evaluated_at'] = self.now().isoformat()
        result['reused_result'] = False
        self._last_input_count, self._last_result = version, deepcopy(result)
        return result

    def _fit_pending(self, cutoff, *, arrival=None):
        self.status['reason'] = 'No common current native input'
        self.status.pop('coverage', None)
        days = self.history.sessions(self.members, cutoff, arrival=arrival)
        if len(days) < self.window_sessions:
            return dict(fitted=False, reason='insufficient_history', observed_sessions=len(days))
        previous = self._previous_fit(cutoff, arrival)
        if previous is not None and sum(day > previous[:10] for day in days) < self.refit_sessions:
            return dict(fitted=False, reason='refit_not_due')
        coverage = self.history.coverage(self.members, cutoff,
                                         window_start=days[-self.window_sessions],
                                         session_schedule=self.session_schedule,
                                         arrival=arrival)
        self.status['coverage'] = coverage
        end = coverage['input_end']
        if end is None or self.rebalance_date > end[:10]:
            return dict(fitted=False, reason='no_eligible_basket')
        if coverage['observed_sessions'] < self.window_sessions:
            self.status['reason'] = 'Insufficient common-session history'
            return dict(fitted=False, reason=self.status['reason'], coverage=coverage)
        if coverage['incomplete_members'] or coverage['grid_gaps']:
            self.status['reason'] = 'Incomplete common native-bar coverage'
            return dict(fitted=False, reason=self.status['reason'], coverage=coverage)
        # Keep detector prehistory, but pool only the trailing declared window.
        # Read/release one symbol at a time, rather than materialising the
        # entire native corpus as Python rows or scanning it per symbol.
        def symbol_rows():
            for symbol in self.members:
                rows = self.history.rows((symbol,), cutoff,
                    session_schedule=self.session_schedule, basket=self.members,
                    arrival=arrival)
                yield (symbol, [datetime.fromisoformat(r['end']) for r in rows],
                       [r['close'] for r in rows])
        stream = PooledStream.build(symbol_rows(), requested=self.members)
        lo = int(np.searchsorted(np.asarray(stream.day, dtype=str), days[-self.window_sessions]))
        hi = len(stream.bars)-1
        if hi >= lo and stream.bars[-1].isoformat() == end:
            inputs, manifest = stream.window(lo, hi, segments=[(lo, hi, self.members)],
                policy='fixed_at_fit_cutoff', declared=self.members,
                basket_id=basket_digest(self.members), basket_basis='point_in_time',
                rebalance_date=self.rebalance_date)
            # No missing contributor is converted to a zero-event observation.
            supported = np.all(inputs['active'] == len(self.members))
            grid = inputs['bars']
            gaps = sum(left.date() == right.date() and right-left != timedelta(minutes=5)
                       for left, right in zip(grid, grid[1:]))
            supported = supported and not gaps and manifest.n_sessions >= self.window_sessions
            complete = [symbol for symbol in self.members if symbol in stream.series
                        and stream.series[symbol].bars_in(lo, hi) == hi-lo+1]
            self.status['coverage'].update(
                observed_sessions=manifest.n_sessions, observed_bins=manifest.n_bars,
                required_members=len(self.members), complete_members=complete,
                incomplete_members=sorted(set(self.members)-set(complete)), grid_gaps=gaps,
                input_end=end, window_start=manifest.training_start)
            self.status['reason'] = 'Incomplete common native-bar coverage'
            if supported and not verify_manifest(manifest, n_neg=inputs['n_neg'],
                    n_pos=inputs['n_pos'], active=inputs['active']):
                counts, slots = inputs['n_neg'], inputs['tod_index']
                totals = np.bincount(slots, weights=counts, minlength=inputs['n_slots'])
                profile = totals / np.maximum(np.bincount(slots, minlength=len(totals)), 1)
                profile = profile / max(profile.mean(), 1e-12)
                fit = fit_discrete_hawkes(counts, inputs['session_starts'], profile, slots)
                self.status['reason'] = 'Native fit unavailable or unconverged'
                if fit is not None and fit.converged and 0 < fit.branching_ratio < 1:
                    self._persist(fit, profile, manifest, end)
                    self.status['reason'] = 'Native fit persisted with actual availability'
        return dict(fitted=self.status.get('reason') == 'Native fit persisted with actual availability',
                    reason=self.status.get('reason', 'No common current native input'),
                    coverage=self.status.get('coverage'))

    def _previous_fit(self, cutoff, arrival=None):
        """`trained_through` of the newest compatible fit KNOWABLE at `cutoff`.

        A replay must not be handed a model trained after the moment it is
        reconstructing, nor one that had not been published yet. For the live
        worker, where cutoff is now, this is every compatible fit as before.
        """
        reach = arrival or cutoff
        usable = [row for row in self.daily.store.deployments()
                  if self._compatible(row)
                  and (row.get('trained_through') or '') <= cutoff
                  and (row.get('available_at') or '') <= reach]
        return max((row['trained_through'] for row in usable), default=None)

    def _compatible(self, row):
        notes = json.loads(row.get('notes') or '{}')
        return (tuple(notes.get('members', ())) == self.members
                and notes.get('window_sessions') == self.window_sessions
                and notes.get('refit_sessions') == self.refit_sessions
                and notes.get('raw_statistic') == 'ungated_n_over_one_minus_n'
                and notes.get('session_schedule_sha256') == (self.session_schedule.sha256
                    if self.session_schedule else None)
                and notes.get('manifest', {}).get('membership', {}).get('rebalance_date') == self.rebalance_date)

    def _persist(self, fit, profile, manifest, end):
        completed = self.now().isoformat()
        gate, _, _ = asymmetry_significance(manifest.n_neg, manifest.n_pos)
        # Match the adopted C5 -> C8 contagion adapter; FR13 gating remains
        # provenance rather than destroying the rank signal with repeated zeros.
        value = fit.branching_ratio / (1-fit.branching_ratio)
        body = dict(schema='native-hawkes/1', window_sessions=self.window_sessions,
                    refit_sessions=self.refit_sessions,
                    manifest=manifest.describe(), members=self.members,
                    parameters=vars(fit), tod_profile=profile.tolist(), value=value,
                    fr13_gate_open=bool(gate), mts=value if gate else 0.0,
                    raw_statistic='ungated_n_over_one_minus_n')
        body['session_schedule_sha256'] = self.session_schedule.sha256 if self.session_schedule else None
        body['observation_policy'] = ('common_continuous_session' if self.session_schedule else 'strict_observed_grid')
        body['implementation_sha256'] = hashlib.sha256(
            Path(__file__).read_bytes() + Path(__file__).with_name('engine.py').read_bytes()
            + Path(__file__).with_name('basket_stream.py').read_bytes()
            + (Path(__file__).parents[2]/'market_calendar'/'native_sessions.py').read_bytes()).hexdigest()
        payload = json.dumps(body, sort_keys=True, allow_nan=False)
        digest = hashlib.sha256(payload.encode()).hexdigest()
        bundle = 'native-hawkes:' + digest
        store = self.daily.store
        # Preserve the first availability on a replay of the identical input.
        existing = next((row for row in store.deployments() if row['bundle_id'] == bundle), None)
        if existing is not None:
            completed = existing['available_at']
        store.register_deployment(ModelBundle(bundle, 'hawkes', end, completed,
                                              digest, payload))
        store.record_daily_vintage(producer='hawkes', input_end=end,
            emission_available_at=completed, value=value, bundle_id=bundle,
            origin='computed', detail=body)
