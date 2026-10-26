"""C11 — versioned institution exposure submissions and decomposition (FR42–43).

Market-value shares are holdings arithmetic, never CSRS or loss contributions.
"""
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3

from seraph.identity import AuthorizationError
from seraph.shared_types import IST, ist_timestamp
from seraph.decision_support.workspace import parse_holdings


def _stamp(value=None):
    moment = datetime.fromisoformat(value) if value else datetime.now(IST)
    if moment.tzinfo is None:
        raise ValueError('Submission timestamps require an explicit offset')
    return ist_timestamp(moment.astimezone(IST).replace(microsecond=0))


class InstitutionStore:
    def __init__(self, path, registry):
        self.path, self.registry = Path(path), registry
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS submissions(
                    resource_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    effective_at TEXT NOT NULL, received_at TEXT NOT NULL,
                    content_hash TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(resource_id,revision));
                CREATE TRIGGER IF NOT EXISTS submissions_no_update BEFORE UPDATE ON submissions
                    BEGIN SELECT RAISE(ABORT,'submission revisions are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS submissions_no_delete BEFORE DELETE ON submissions
                    BEGIN SELECT RAISE(ABORT,'submission revisions are immutable'); END;
                CREATE TABLE IF NOT EXISTS rejections(
                    received_at TEXT NOT NULL, submitter TEXT NOT NULL, detail TEXT NOT NULL);
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def principal(self, principal):
        fresh = self.registry.revalidate(principal)
        if fresh.role != 'regulator':
            raise AuthorizationError('Institution submissions are regulator-only')
        return fresh

    def preview(self, principal, body, *, source_name):
        self.principal(principal)
        preview = parse_holdings(body, source_name=source_name, base_currency='INR')
        result = preview.describe()
        result['acceptable'] = bool(preview.accepted) and not preview.rejected and not preview.duplicates_merged
        result['note'] = 'INR long-only valued or explicitly unsized positions; duplicates must be resolved before acceptance.'
        return result

    def submit(self, principal, *, institution_id, name, effective_at, body,
               source_name, source, received_at=None):
        principal = self.principal(principal)
        received = _stamp(received_at)
        try:
            if not str(institution_id).strip() or not str(name).strip():
                raise ValueError('Institution ID and name are required')
            if source not in ('demo', 'user_supplied'):
                raise ValueError('Source must be demo or user_supplied')
            effective = _stamp(effective_at)
            preview = parse_holdings(body, source_name=source_name, base_currency='INR')
            if preview.rejected or preview.duplicates_merged or not preview.accepted:
                raise ValueError('Resolve rejected/duplicate positions before submitting: ' +
                                 json.dumps(preview.describe(), default=str))
        except ValueError as exc:
            with self.connect() as db:
                db.execute('INSERT INTO rejections VALUES (?,?,?)',
                           (received, principal.user_id, str(exc)))
            raise
        resource_id = 'inst_' + hashlib.sha256(
            f'{principal.org_id}:{institution_id}'.encode()).hexdigest()
        payload = dict(schema='institution-submission/1', institution_id=institution_id,
                       name=name, source=source, currency='INR',
                       valuation_basis='caller-supplied position values; no FX conversion',
                       effective_at=effective, submitter=principal.user_id,
                       owner_scope=principal.org_id, positions=[asdict(r) for r in preview.accepted],
                       source_sha256=hashlib.sha256(body.encode()).hexdigest())
        raw = json.dumps(payload, sort_keys=True, allow_nan=False)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        self.registry.register_resource('institution_submission', resource_id,
                                        org_id=principal.org_id,
                                        owner_user_id=principal.user_id, visibility='org')
        self.registry.require(principal, 'write', 'institution_submission', resource_id)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            previous = db.execute('SELECT revision,content_hash FROM submissions WHERE resource_id=? ORDER BY revision DESC LIMIT 1',
                                  (resource_id,)).fetchone()
            if previous and previous['content_hash'] == digest:
                return dict(resource_id=resource_id, revision=previous['revision'],
                            content_hash=digest, stored=False)
            revision = previous['revision'] + 1 if previous else 1
            db.execute('INSERT INTO submissions VALUES (?,?,?,?,?,?)',
                       (resource_id, revision, effective, received, digest, raw))
        return dict(resource_id=resource_id, revision=revision, content_hash=digest, stored=True)

    def decomposition(self, principal, *, cutoff, flags=None):
        principal = self.principal(principal)
        cutoff = _stamp(cutoff)
        with self.connect() as db:
            rows = db.execute(
                'SELECT * FROM submissions WHERE effective_at<=? AND received_at<=? '
                'ORDER BY effective_at DESC,revision DESC', (cutoff, cutoff)).fetchall()
        visible = set(self.registry.visible(principal, 'institution_submission',
                                            {r['resource_id'] for r in rows}))
        chosen = {}
        for row in rows:
            if row['resource_id'] in visible:
                chosen.setdefault(row['resource_id'], row)
        institutions, sectors = [], {}
        for row in chosen.values():
            book = json.loads(row['payload'])
            totals, unsized = {}, 0
            for position in book['positions']:
                sector = position.get('sector') or 'unclassified'
                value = position.get('value')
                if value is None:
                    unsized += 1
                    continue
                totals[sector] = totals.get(sector, 0.) + value
                sectors[sector] = sectors.get(sector, 0.) + value
            institutions.append(dict(
                **book, revision=row['revision'], received_at=row['received_at'],
                content_hash=row['content_hash'], total_value=sum(totals.values()),
                unsized_positions=unsized, sectors=totals))
        total = sum(r['total_value'] for r in institutions)
        for institution in institutions:
            institution['share_pct'] = (
                100 * institution['total_value'] / total if total else None)
        sector_rows = [dict(sector=k, value=v, share_pct=100*v/total if total else None,
                            flag=(flags or {}).get(k),
                            covered=k in (flags or {})) for k, v in sorted(sectors.items())]
        return dict(schema='institution-decomposition/1', cutoff=cutoff, currency='INR',
                    total_known_value=total, institutions=institutions, sectors=sector_rows,
                    unsized_positions=sum(r['unsized_positions'] for r in institutions),
                    unmapped_value=sectors.get('unclassified', 0.),
                    covered_value=sum(r['value'] for r in sector_rows if r['covered']),
                    note='Market-value exposure shares, not loss or CSRS contributions. Demo/user-supplied positions retain their source labels.')
