"""C2/C12 — bounded exchange-calendar input for current operation (FR39).

The default historical registry stays partial. A supplied calendar must enumerate
every day of its covered interval and pin the exchange notices behind it.
"""
from datetime import date, timedelta
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse

from .sessions import SessionCalendar, TradingSession, SPECIAL_SESSIONS


class ExchangeCalendar(SessionCalendar):
    def __init__(self, document, *, source_dir):
        if document.get('schema') != 'nse-cash-calendar/1':
            raise ValueError('Expected nse-cash-calendar/1')
        self.start = date.fromisoformat(document['start'])
        self.end = date.fromisoformat(document['end'])
        if self.end < self.start:
            raise ValueError('Invalid calendar interval')
        evidence = document['evidence']
        if not evidence:
            raise ValueError('Exchange notice evidence is required')
        for item in evidence:
            if urlparse(item['url']).hostname not in ('www.nseindia.com','nseindia.com','nsearchives.nseindia.com'):
                raise ValueError('Calendar evidence must identify the exchange source')
            path = (Path(source_dir)/item['file']).resolve()
            if not path.is_relative_to(Path(source_dir).resolve()):
                raise ValueError('Evidence path must stay within the calendar directory')
            if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
                raise ValueError('Exchange calendar evidence hash mismatch')
        expected = {(self.start+timedelta(days=i)).isoformat()
                    for i in range((self.end-self.start).days+1)}
        rows = document['days']
        if len(rows) != len(expected) or {r['date'] for r in rows} != expected:
            raise ValueError('Calendar must enumerate every covered day exactly once')
        # The bounded live input does not replace historical special-session
        # evidence. Retain it outside this interval, still unverified for live.
        sessions = [s for s in SPECIAL_SESSIONS if s.date not in expected]
        self._open_days = set()
        for row in rows:
            refs = row.get('evidence_indices', [])
            if not refs or any(type(i) is not int or not 0 <= i < len(evidence) for i in refs):
                raise ValueError('Every day needs valid exchange evidence references')
            if row['status'] == 'closed':
                if row.get('windows'):
                    raise ValueError('A closed day cannot have trading windows')
                continue
            if row['status'] != 'open':
                raise ValueError('Day status must be open or closed')
            self._open_days.add(row['date'])
            sessions.append(TradingSession(date=row['date'], kind=row['kind'],
                windows=tuple(tuple(w) for w in row['windows']),
                evidence='; '.join(evidence[i]['url'] for i in refs),
                evidence_status='verified_against_exchange_notice'))
        super().__init__(sessions=tuple(sessions), session_dates=self._open_days)
        self.identity = hashlib.sha256(json.dumps(document,sort_keys=True).encode()).hexdigest()
        self.evidence = evidence

    def verified_for(self, day):
        return self.start <= date.fromisoformat(day) <= self.end

    def is_session(self, day):
        if self.verified_for(day):
            return day in self._open_days
        # Outside the supplied interval, the clock may schedule a probe, but
        # publication stays unverified. Do not extend evidence by assumption.
        return self.is_special(day) or date.fromisoformat(day).weekday() < 5

    def completeness(self):
        return dict(completeness='PARTIAL globally; exchange-verified only within the declared interval',
            start=self.start.isoformat(), end=self.end.isoformat(), artifact_id=self.identity,
            evidence=self.evidence)


def load(path):
    path = Path(path)
    return ExchangeCalendar(json.loads(path.read_text(encoding='utf-8')), source_dir=path.parent)


def configured():
    """Use the installation's declared calendar, or retain the partial registry."""
    override = os.environ.get('SERAPH_EXCHANGE_CALENDAR')
    path = Path(override) if override else Path(__file__).resolve().parents[2]/'prototype_runs/exchange_calendar/current.json'
    if override or path.exists():
        return load(path)
    return SessionCalendar()
