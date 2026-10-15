"""C9 experimental contextual watch: sourced public events, never probabilities.

This rule is evaluated separately from the predictive fusion. It is a declared
scenario policy, not a trained model or a causal claim about asset prices.
Date-only sources enter strictly after the publication date as an explicit
availability approximation; precise publication/archive timestamps are better.
"""
from __future__ import annotations
import numpy as np


def public_event_watch(dates, events, duration=20):
    dates = np.asarray(dates, dtype='datetime64[D]')
    if (dates.ndim != 1 or np.isnat(dates).any()
            or (np.diff(dates).astype(int) <= 0).any()):
        raise ValueError('dates must be increasing and unique')
    if (isinstance(duration, bool) or not np.isfinite(duration)
            or int(duration) != duration or duration < 1):
        raise ValueError('duration must be a positive integer')
    active = [[] for _ in dates]
    audit, seen = [], set()
    for event in events:
        identity = event['event']
        if identity in seen:
            raise ValueError('duplicate event identifier')
        seen.add(identity)
        publication = np.datetime64(event['published_date'], 'D')
        if np.isnat(publication) or not event['source_url'].startswith('https://'):
            raise ValueError('require publication date and HTTPS source')
        start = int(np.searchsorted(dates, publication, side='right'))
        # A truncated panel cannot reconstruct expiry of a watch that began
        # before its first session. Fail explicitly instead of rejuvenating it.
        if len(dates) and publication < dates[0]:
            raise ValueError('include session history before the first supplied event')
        end = min(len(dates), start+duration)
        for t in range(start, end):
            active[t].append(identity)
        audit.append(dict(**event, first_session=str(dates[start]) if start < len(dates) else None,
                          last_session=str(dates[end-1]) if end > start else None,
                          observed_sessions=end-start, expired_in_sample=start+duration <= len(dates)))
    return dict(watch=np.array([bool(ids) for ids in active]),
                active_events=np.array([';'.join(ids) for ids in active], dtype=object), events=audit)
