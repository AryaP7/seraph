"""C2/C5 — dated common continuous-session evidence (FR1, FR10–15).

The August 2026 CAS timetable ends continuous trading at 15:15 for eligible
securities. A pooled basket is jointly observable only until its first member
stops continuous trading. Dated NSE auction reports establish membership; they
are not an exchange holiday calendar and are never extrapolated to other days.
"""
import csv
from datetime import date, datetime
import hashlib
import io
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from seraph.shared_types import IST

# Individually reviewed NSE notices. These identify announced auction windows,
# not inferred gaps. TMPV is the broker's current historical-series label;
# CML70875 supplies the TATAMOTORS -> TMPV rename evidence, without changing
# the symbol that was actually in force on October 14.
PREOPEN_NOTICES = {
    'CMTR65845.pdf': ('2025-01-06', ('ITC',)),
    'CMTR70614.pdf': ('2025-10-14', ('TATAMOTORS', 'TMPV')),
    'CMTR71508.pdf': ('2025-12-05', ('HINDUNILVR',)),
    'CMTR73856.pdf': ('2026-04-30', ('VEDL',)),
}
CIRCULAR_ROOT = 'https://nsearchives.nseindia.com/content/circulars/'
RENAME_NOTICE = 'CML70875.pdf'


def report_date(url):
    """Bind each rule to the date in its actual exchange archive filename."""
    parts = urlsplit(url)
    match = re.search(r'Closing-Auction-Session-_?(\d{2}-[A-Za-z]{3}-\d{4})(?:_|\.csv)', parts.path)
    if parts.scheme != 'https' or parts.hostname != 'nsearchives.nseindia.com' or not match:
        raise ValueError('Invalid dated exchange report URL')
    return datetime.strptime(match[1], '%d-%b-%Y').date().isoformat()


def report_members(raw):
    rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
    if not rows or 'SYMBOL' not in rows[0] or 'FINAL PRICE' not in rows[0]:
        raise ValueError('NSE closing-auction report schema is missing')
    # One exchange report includes an entirely empty trailing CSV record.
    # A populated row with a missing symbol is still a schema failure.
    rows = [row for row in rows if any(str(value).strip() for value in row.values()
                                      if value is not None)]
    members = [row['SYMBOL'].strip().upper() for row in rows]
    if not members or any(not m for m in members) or len(members) != len(set(members)):
        raise ValueError('NSE closing-auction symbols must be nonempty and unique')
    return sorted(members)


class NativeSessionSchedule:
    def __init__(self, rules, digest, opening_rules=()):
        self._rules = tuple(rules)
        self._opening_rules = tuple(opening_rules)
        self.sha256 = digest

    @classmethod
    def load(cls, path):
        path = Path(path)
        raw = path.read_bytes()
        doc = json.loads(raw)
        if doc.get('schema') != 'native-session-schedule/1' or doc.get('policy') != 'common_continuous_session':
            raise ValueError('Unsupported native session schedule')
        sources = {}
        circulars = {}
        for source in doc['sources']:
            if (Path(source['file']).name != source['file']
                    or urlsplit(source['url']).path.rsplit('/', 1)[-1] != source['file']):
                raise ValueError('Invalid exchange source identity')
            data = (path.parent/source['file']).read_bytes()
            if hashlib.sha256(data).hexdigest() != source['sha256']:
                raise ValueError('Exchange report hash mismatch')
            if source['url'] == CIRCULAR_ROOT+source['file'] and source['file'] in {*PREOPEN_NOTICES, RENAME_NOTICE}:
                if not data.startswith(b'%PDF-'):
                    raise ValueError('Exchange circular is not a PDF')
                received = datetime.fromisoformat(source['received_at'])
                if received.tzinfo is None:
                    raise ValueError('Circular evidence requires an explicit receipt timestamp')
                circulars[source['file']] = received.astimezone(IST)
                continue
            day = report_date(source['url'])
            sources[(day, source['sha256'])] = (report_members(data), source['received_at'])
        rules = []
        for day, rule in sorted(doc['dates'].items()):
            if (date.fromisoformat(day).isoformat() != day
                    or not '2026-08-03' <= day < '2026-12-07'
                    or rule['continuous_close'] != '15:15:00'):
                raise ValueError('Date or close outside the evidenced August CAS timetable')
            if (day, rule['source_sha256']) not in sources:
                raise ValueError('Session date disagrees with the dated exchange report')
            members, receipt = sources[(day, rule['source_sha256'])]
            if sorted(rule['cas_members']) != members or rule['received_at'] != receipt:
                raise ValueError('Declared session members or receipt disagree with source')
            received = datetime.fromisoformat(receipt)
            if received.tzinfo is None:
                raise ValueError('Session evidence requires an explicit receipt timestamp')
            if received.astimezone(IST).date().isoformat() < day:
                raise ValueError('Session report receipt predates its session')
            rules.append((day, tuple(members), received.astimezone(IST)))
        opening_rules = []
        for filename in doc.get('special_preopen_notices', []):
            if filename not in PREOPEN_NOTICES or filename not in circulars:
                raise ValueError('Special pre-open selection requires a reviewed dated circular')
            day, members = PREOPEN_NOTICES[filename]
            received = circulars[filename]
            if 'TMPV' in members:
                if RENAME_NOTICE not in circulars:
                    raise ValueError('Broker historical alias requires exchange rename evidence')
                received = max(received, circulars[RENAME_NOTICE])
            if received.date().isoformat() < day:
                raise ValueError('Retrospective session evidence must not be backdated')
            opening_rules.append((day, members, received))
        return cls(rules, hashlib.sha256(raw).hexdigest(), opening_rules)

    def cutoffs(self, members, cutoff):
        from seraph.market_calendar.sessions import SessionCalendar
        when = datetime.fromisoformat(cutoff)
        if when.tzinfo is None:
            raise ValueError('Session selection requires an explicit cutoff')
        basket = set(members)
        calendar = SessionCalendar()
        return {day:'15:15:00' for day, symbols, received in self._rules
                if received <= when and day <= when.astimezone(IST).date().isoformat()
                and not calendar.is_special(day) and basket.intersection(symbols)}

    def sql_filter(self, members, cutoff):
        days = tuple(self.cutoffs(members, cutoff))
        opens = tuple(self.openings(members, cutoff))
        condition, args = '', ()
        if days:
            condition += (' AND NOT (substr(end,1,10) IN ('+','.join('?' for _ in days)
                          + ') AND substr(end,12,8)>?)')
            args += (*days, '15:15:00')
        if opens:
            # Native timestamps label five-minute bar ends. The first full
            # continuous-session candle after a 10:00 open ends at 10:05.
            condition += (' AND NOT (substr(end,1,10) IN ('+','.join('?' for _ in opens)
                          + ') AND substr(end,12,8)<=?)')
            args += (*opens, '10:00:00')
        return condition, args

    def openings(self, members, cutoff):
        when = datetime.fromisoformat(cutoff)
        if when.tzinfo is None:
            raise ValueError('Session selection requires an explicit cutoff')
        basket = set(members)
        return {day:'10:00:00' for day, symbols, received in self._opening_rules
                if received <= when and day <= when.astimezone(IST).date().isoformat()
                and basket.intersection(symbols)}


def schedule_from_config(config_path, config):
    name = config.get('session_schedule_file')
    return NativeSessionSchedule.load(Path(config_path).parent/name) if name else None
