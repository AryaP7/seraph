"""Chronological alert calibration and honest pre-onset evaluation.

All decisions are after close. Calibration admits a label only when its entire
future horizon has elapsed. A frozen alert threshold is a policy, not a proof
that the future false-alarm budget will be met.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import numpy as np
from scipy.stats import rankdata


@dataclass(frozen=True)
class AlertConfig:
    horizon: int = 15
    min_calibration: int = 252
    lookback: int = 1260
    refit_every: int = 63
    false_episodes_per_year: float = 2.0
    max_alarm_fraction: float = .10
    sessions_per_year: int = 252

    def __post_init__(self):
        for name in ('horizon', 'min_calibration', 'lookback', 'refit_every', 'sessions_per_year'):
            value = getattr(self, name)
            if isinstance(value, bool) or int(value) != value or value < 1:
                raise ValueError(f'{name} must be a positive integer')
        if self.lookback < self.min_calibration:
            raise ValueError('lookback must cover min_calibration')
        if (not 0 < self.max_alarm_fraction < 1
                or not np.isfinite(self.false_episodes_per_year) or self.false_episodes_per_year < 0):
            raise ValueError('invalid alarm budgets')


def _vectors(scores, labels):
    p, y = np.asarray(scores, float), np.asarray(labels, float)
    if p.ndim != 1 or p.shape != y.shape:
        raise ValueError('scores and labels must be equal-length vectors')
    if np.any(np.isfinite(y) & ~np.isin(y, (0, 1))):
        raise ValueError('finite labels must be binary')
    return p, y


def onset_labels(dates, event_dates, horizon=15):
    """All stated event dates retained; non-session dates map to next session.

    No pre-onset positive is emitted for an event beyond the data boundary.
    Last horizon rows are unknown, not negative.
    """
    dates = np.asarray(dates, dtype='datetime64[D]')
    if (dates.ndim != 1 or np.isnat(dates).any()
            or isinstance(horizon, bool) or not np.isfinite(horizon)
            or int(horizon) != horizon or horizon < 1 or (np.diff(dates).astype(int) <= 0).any()):
        raise ValueError('require positive horizon and increasing unique dates')
    y = np.zeros(len(dates), float)
    for event in event_dates:
        i = int(np.searchsorted(dates, np.datetime64(event, 'D')))
        if i < len(dates):
            y[max(0, i-horizon):i] = 1
    y[max(0, len(dates)-horizon):] = np.nan
    return y


def episode_spans(alarm):
    a = np.asarray(alarm, bool)
    edges = np.diff(np.r_[False, a, False].astype(int))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def alarm_stats(scores, labels, thresholds, sessions_per_year=252):
    p, y = _vectors(scores, labels)
    th = np.broadcast_to(np.asarray(thresholds, float), p.shape)
    valid = np.isfinite(p) & np.isfinite(y) & ~np.isnan(th)
    alarm = valid & (p >= th)
    spans = episode_spans(alarm)
    false_count = sum(not np.any(y[start:end] == 1) for start, end in spans)
    count = int(valid.sum())
    return dict(evaluated_sessions=count, alarm_sessions=int(alarm.sum()),
                alarm_fraction=float(alarm.sum()/count) if count else None,
                episodes=len(spans), false_episodes=false_count,
                false_episodes_per_year=float(false_count*sessions_per_year/count) if count else None)


def calibrate_alerts(scores, labels, config=None):
    """Threshold chosen from PAST OOS scores and matured outcomes only.

    Lowest candidate satisfying both budgets wins. Infinity means explicit
    abstention when no finite candidate works; NaN means unassessable warmup.
    Missing dates split episodes instead of compressing the time grid.
    """
    cfg = config or AlertConfig()
    p, y = _vectors(scores, labels)
    thresholds = np.full(len(p), np.nan)
    audits = []
    threshold, last_fit = np.nan, -cfg.refit_every
    for t in range(len(p)):
        end = t-cfg.horizon+1
        start = max(0, end-cfg.lookback)
        valid = np.isfinite(p[start:max(end, 0)]) & np.isfinite(y[start:max(end, 0)])
        if valid.sum() < cfg.min_calibration:
            # A threshold calibrated under adequate historical coverage must
            # not remain silently usable after that history ages out.
            threshold, last_fit = np.nan, -cfg.refit_every
        elif end > 0 and t-last_fit >= cfg.refit_every:
            hist_p, hist_y = p[start:end], y[start:end]
            candidates = np.unique(np.r_[np.quantile(hist_p[valid], np.linspace(.5, 1, 101)), np.inf])
            for candidate in candidates:
                stats = alarm_stats(hist_p, hist_y, candidate, cfg.sessions_per_year)
                if (stats['alarm_fraction'] <= cfg.max_alarm_fraction
                        and stats['false_episodes_per_year'] <= cfg.false_episodes_per_year):
                    threshold = float(candidate)
                    break
            last_fit = t
            audits.append(dict(decision_index=t, calibration_start=start,
                               calibration_end_exclusive=end, threshold=threshold,
                               calibration=stats))
        thresholds[t] = threshold
    return dict(threshold=thresholds, alarm=np.isfinite(p) & ~np.isnan(thresholds) & (p >= thresholds),
                fits=audits, config=asdict(cfg))


def probability_metrics(scores, labels, mask=None):
    p, y = _vectors(scores, labels)
    valid = np.isfinite(p) & np.isfinite(y)
    if mask is not None:
        mask = np.asarray(mask, bool)
        if mask.shape != p.shape:
            raise ValueError('mask must match scores')
        valid &= mask
    p, y = p[valid], y[valid]
    if np.any((p < 0) | (p > 1)):
        raise ValueError('probabilities outside [0,1]')
    if not len(p):
        return dict(n=0, positives=0, brier=None, log_loss=None, auc=None)
    positive = y == 1
    n1, n0 = int(positive.sum()), int((~positive).sum())
    ranks = rankdata(p)
    auc = float((ranks[positive].sum()-n1*(n1+1)/2)/(n1*n0)) if n1 and n0 else None
    clipped = np.clip(p, 1e-10, 1-1e-10)
    return dict(n=len(p), positives=n1, base_rate=float(y.mean()),
                brier=float(np.mean((p-y)**2)),
                log_loss=float(-np.mean(y*np.log(clipped)+(1-y)*np.log1p(-clipped))), auc=auc)


def event_warnings(dates, scores, thresholds, events, horizon=15):
    dates = np.asarray(dates, dtype='datetime64[D]')
    p, th = np.asarray(scores, float), np.asarray(thresholds, float)
    if (dates.ndim != 1 or p.shape != dates.shape or th.shape != dates.shape
            or np.isnat(dates).any() or (np.diff(dates).astype(int) <= 0).any()
            or isinstance(horizon, bool) or not np.isfinite(horizon) or int(horizon) != horizon or horizon < 1):
        raise ValueError('require aligned vectors, ordered dates and positive integer horizon')
    rows = []
    for name, (date, provenance) in events.items():
        onset = int(np.searchsorted(dates, np.datetime64(date, 'D')))
        start = max(0, onset-horizon)
        valid = np.isfinite(p[start:onset]) & ~np.isnan(th[start:onset])
        assessable = onset < len(dates) and onset-start == horizon and bool(valid.all())
        alarm = valid & (p[start:onset] >= th[start:onset])
        indices = np.flatnonzero(alarm) + start
        first = int(indices[0]) if len(indices) else None
        provisional = 'PROVISIONAL' in provenance or 'OQ' in provenance
        rows.append(dict(event=name, label_date=date, session_date=str(dates[onset]) if onset < len(dates) else None,
                         label_status='explicitly_unresolved' if provisional else 'provisional_project_label',
                         provenance=provenance, available_sessions=int(valid.sum()),
                         status=('unassessable' if not assessable else 'warned' if first is not None else 'missed'),
                         first_warning=str(dates[first]) if first is not None and assessable else None,
                         lead_sessions=onset-first if first is not None and assessable else None))
    return rows


def paired_brier_block_interval(candidate, baseline, labels, block=63, draws=1000, seed=381):
    """Descriptive paired circular-block bootstrap; not selection-adjusted proof.

    Retains gaps in the chronology. Negative difference favors candidate.
    """
    p, y = _vectors(candidate, labels)
    b = np.asarray(baseline, float)
    if b.shape != p.shape:
        raise ValueError('baseline must match candidate')
    for value in (block, draws):
        if isinstance(value, bool) or not np.isfinite(value) or int(value) != value or value < 1:
            raise ValueError('block and draws must be positive integers')
    valid = np.isfinite(p) & np.isfinite(b) & np.isfinite(y)
    d = np.where(valid, (p-y)**2-(b-y)**2, np.nan)
    indices = np.flatnonzero(valid)
    if len(indices) < 2*block:
        return dict(n=int(len(indices)), mean=None, lower=None, upper=None)
    d = d[indices[0]:indices[-1]+1]
    rng = np.random.default_rng(seed)
    offsets = np.arange(block)
    estimates = []
    for _ in range(draws):
        starts = rng.integers(0, len(d), size=int(np.ceil(len(d)/block)))
        sample = d[((starts[:, None]+offsets) % len(d)).ravel()[:len(d)]]
        if np.isfinite(sample).any():
            estimates.append(float(np.nanmean(sample)))
    return dict(n=int(valid.sum()), mean=float(np.nanmean(d)),
                lower=float(np.quantile(estimates, .025)), upper=float(np.quantile(estimates, .975)),
                block=block, draws=draws, caveat='descriptive; not adjusted for model/research selection or nonstationarity')
