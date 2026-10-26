"""C2/C5 — collect dated NSE CAS evidence for native-bar coverage (FR1, FR10).

Archives downloaded here identify securities in each dated auction. They do
not supply continuous-session prices or justify filling an unobserved candle.
The raw reports, retrieval times and hashes are retained beside the output.
"""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit, urlunsplit

import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seraph.market_calendar.native_sessions import (
    CIRCULAR_ROOT, PREOPEN_NOTICES, RENAME_NOTICE,
    NativeSessionSchedule, report_date, report_members,
)

ARCHIVE_URL = 'https://www.nseindia.com/static/reports/closing-auction-session-historical-data'
RULE_URL = 'https://www.sebi.gov.in/sebi_data/attachdocs/jan-2026/1768576287344.pdf'
REVISION_URL = 'https://www.sebi.gov.in/sebi_data/attachdocs/oct-2026/1792079571420.pdf'


def report_links(html):
    """Use only archive links published on the exchange page, never guessed URLs."""
    out = {}
    for value in re.findall(r'https://nsearchives\.nseindia\.com/[^\"<>\s]+Closing-Auction-Session[^\"<>\s]+\.csv', html):
        parts = urlsplit(value)
        url = urlunsplit(parts._replace(path=re.sub('/+', '/', parts.path)))
        day = report_date(url)
        if day in out and out[day] != url:
            raise ValueError('Multiple report versions for '+day+'; select evidence explicitly')
        out[day] = url
    return out


def collect(args):
    from seraph.shared_types import IST
    if datetime.strptime(args.through, '%Y-%m-%d').date().isoformat() != args.through:
        raise ValueError('Use a YYYY-MM-DD through date')
    if not '2026-08-03' <= args.through < '2026-12-07':
        raise ValueError('This collector covers only the evidenced August CAS timetable')
    if args.through > datetime.now(IST).date().isoformat():
        raise ValueError('Cannot collect future dated evidence')
    args.out.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update({'User-Agent':'Mozilla/5.0', 'Referer':'https://www.nseindia.com/'})
    page = session.get(ARCHIVE_URL, timeout=25)
    page.raise_for_status()
    page_time = datetime.now(IST).isoformat()
    (args.out/'nse-archive.html').write_bytes(page.content)
    links = report_links(page.text)
    if not links:
        raise ValueError('No dated exchange reports were found')
    sources = []
    failures = []
    days = {}
    for day, url in sorted(links.items()):
        if not '2026-08-03' <= day <= args.through:
            continue
        path = args.out/url.rsplit('/', 1)[-1]
        receipt = path.with_suffix('.retrieval.json')
        try:
            if path.exists() and receipt.exists():
                raw = path.read_bytes()
                source = json.loads(receipt.read_text(encoding='utf-8'))
                if source['url'] != url or source['sha256'] != hashlib.sha256(raw).hexdigest():
                    raise ValueError('Cached source identity mismatch')
            else:
                response = session.get(url, timeout=15)
                response.raise_for_status()
                raw = response.content
                source = dict(url=url, received_at=datetime.now(IST).isoformat(),
                              sha256=hashlib.sha256(raw).hexdigest(), file=path.name)
                report_members(raw)  # Never cache an HTML error as a valid report.
                path.write_bytes(raw)
                receipt.write_text(json.dumps(source, indent=2), encoding='utf-8')
            members = report_members(raw)
            sources.append(source)
            days[day] = dict(cas_members=members, continuous_close='15:15:00',
                            received_at=source['received_at'], source_sha256=source['sha256'])
        except (requests.RequestException, ValueError, KeyError) as exc:
            failures.append(dict(day=day, url=url, error_type=type(exc).__name__))
        if len(days) % 10 == 0:
            print(json.dumps(dict(reports=len(days), failed=len(failures))), flush=True)
    selected_notices = []
    if getattr(args, 'include_special_preopen', False):
        selected_notices = [name for name, (day, _) in PREOPEN_NOTICES.items() if day <= args.through]
        files = selected_notices + ([RENAME_NOTICE] if 'CMTR70614.pdf' in selected_notices else [])
        for filename in files:
            url = CIRCULAR_ROOT+filename
            path = args.out/filename
            receipt = path.with_suffix('.retrieval.json')
            if path.exists() and receipt.exists():
                raw = path.read_bytes()
                source = json.loads(receipt.read_text(encoding='utf-8'))
                if source['url'] != url or source['sha256'] != hashlib.sha256(raw).hexdigest():
                    raise ValueError('Cached circular identity mismatch')
            else:
                response = session.get(url, timeout=25)
                response.raise_for_status()
                raw = response.content
                if not raw.startswith(b'%PDF-'):
                    raise ValueError('Exchange circular is not a PDF')
                source = dict(url=url, received_at=datetime.now(IST).isoformat(),
                              sha256=hashlib.sha256(raw).hexdigest(), file=filename)
                path.write_bytes(raw)
                receipt.write_text(json.dumps(source, indent=2), encoding='utf-8')
            sources.append(source)
    result = dict(schema='native-session-schedule/1', generated_at=datetime.now(IST).isoformat(),
        rule_sources=[RULE_URL, REVISION_URL], archive=dict(url=ARCHIVE_URL,
        received_at=page_time, sha256=hashlib.sha256(page.content).hexdigest()),
        dates=days, sources=sources, failures=failures,
        special_preopen_notices=selected_notices,
        policy='common_continuous_session', through=args.through,
        note='Dated evidence only. No forward extrapolation; special sessions need their own schedule. '
             'The December 7 revision must not be applied early. No prices are fabricated.')
    target = args.out/'schedule.json'
    temporary = target.with_suffix('.tmp')
    temporary.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    NativeSessionSchedule.load(temporary)
    os.replace(temporary, target)
    print(json.dumps(dict(schedule=str(target), reports=len(days), failed=len(failures))))
    return 2 if failures else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--through', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--include-special-preopen', action='store_true',
                        help='Include the four individually reviewed, dated NSE auction notices')
    raise SystemExit(collect(parser.parse_args()))
