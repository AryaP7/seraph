"""Local prototype persistence. Separate from PostgreSQL E1-E14 contracts.

SQLite transactions protect run rows and the C11 action journal. This is a
single-user demonstration store, not authenticated regulatory infrastructure.

Run lifecycle (FIX03)
---------------------
    running -> inference_complete -> complete

`finish()` SEALS a run: it verifies the exact expected date set (not just a row
count) and every point's schema, records the sealed date set and a content
digest, and then refuses further writes under that identity. A byte-identical
retry of an already-sealed point still succeeds, so deterministic replay
recovery keeps working; anything else is rejected, including a date outside the
manifest's declared range.

A run that declares `requires_report=True` stops at `inference_complete`. It
becomes `complete` only once its report exists, so a crash between the last
point and the report can never present itself as a finished run (audit finding
A04). Reports are immutable revisions: writing a different report appends a new
revision and preserves the previous one rather than overwriting it (A04).

Action journal (FIX08)
----------------------
Commands and journal events are separate (audit finding A13). C11 deliberately
creates NO journal event when an update leaves an action unchanged; the store
used to reinsert the previous event and hit
`UNIQUE constraint failed: action_events.run_id, action_events.seq`. Every
command is now recorded once in `action_commands`, keyed by request id, and
points at the event it produced — or at no event at all for a no-op. The
journal itself stays append-only and trigger-protected.
"""
from __future__ import annotations
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

#: Keys every persisted inference point must carry. The schema of a sealed run
#: is verified, not assumed.
POINT_SCHEMA = ('run_id','date','evaluation_timestamp','data_cutoff',
                'original_pillars','reconciled','composite','coverage','limitations')

RUN_STATES = ('running','inference_complete','complete')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def _now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


class RunStore:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY, manifest TEXT NOT NULL, status TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS points (
                    run_id TEXT NOT NULL REFERENCES runs(id), day TEXT NOT NULL,
                    payload TEXT NOT NULL, PRIMARY KEY(run_id,day));
                CREATE TABLE IF NOT EXISTS action_events (
                    run_id TEXT NOT NULL REFERENCES runs(id), seq INTEGER NOT NULL,
                    request_id TEXT NOT NULL, request TEXT NOT NULL, event TEXT NOT NULL,
                    PRIMARY KEY(run_id,seq), UNIQUE(run_id,request_id));
                CREATE TRIGGER IF NOT EXISTS journal_no_update BEFORE UPDATE ON action_events
                    BEGIN SELECT RAISE(ABORT,'append-only journal'); END;
                CREATE TRIGGER IF NOT EXISTS journal_no_delete BEFORE DELETE ON action_events
                    BEGIN SELECT RAISE(ABORT,'append-only journal'); END;
            ''')
            self._migrate(db)

    # ------------------------------------------------------------ migration

    @staticmethod
    def _columns(db, table):
        return [row[1] for row in db.execute(f'PRAGMA table_info({table})')]

    def _migrate(self, db):
        """Additive migrations. Existing rows are preserved, never rewritten."""
        run_columns = self._columns(db, 'runs')
        if 'sealed_dates' not in run_columns:
            db.execute('ALTER TABLE runs ADD COLUMN sealed_dates TEXT')
        if 'content_hash' not in run_columns:
            db.execute('ALTER TABLE runs ADD COLUMN content_hash TEXT')
        if 'sealed_at' not in run_columns:
            db.execute('ALTER TABLE runs ADD COLUMN sealed_at TEXT')

        # FIX03: immutable report revisions. The legacy single-row `reports`
        # table is copied in as revision 1 and kept as `reports_legacy`.
        db.execute('''CREATE TABLE IF NOT EXISTS report_revisions (
            run_id TEXT NOT NULL REFERENCES runs(id), revision INTEGER NOT NULL,
            payload TEXT NOT NULL, content_hash TEXT NOT NULL, created_at TEXT NOT NULL,
            PRIMARY KEY(run_id,revision))''')
        db.executescript('''
            CREATE TRIGGER IF NOT EXISTS report_no_update BEFORE UPDATE ON report_revisions
                BEGIN SELECT RAISE(ABORT,'reports are immutable revisions'); END;
            CREATE TRIGGER IF NOT EXISTS report_no_delete BEFORE DELETE ON report_revisions
                BEGIN SELECT RAISE(ABORT,'reports are immutable revisions'); END;
        ''')
        # Legacy single-row `reports` table: copy its rows in as revision 1 and
        # keep the original under `reports_legacy`. New stores never create it.
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        if 'reports' in tables:
            for run_id, payload in db.execute('SELECT run_id,payload FROM reports'):
                db.execute('INSERT OR IGNORE INTO report_revisions VALUES (?,?,?,?,?)',
                           (run_id, 1, payload,
                            hashlib.sha256(payload.encode()).hexdigest(), _now()))
            if 'reports_legacy' in tables:
                db.execute('DROP TABLE reports')
            else:
                db.execute('ALTER TABLE reports RENAME TO reports_legacy')

        # FIX08: commands are distinct from journal events.
        db.execute('''CREATE TABLE IF NOT EXISTS action_commands (
            run_id TEXT NOT NULL REFERENCES runs(id), request_id TEXT NOT NULL,
            request TEXT NOT NULL, result TEXT NOT NULL, event_seq INTEGER,
            created_at TEXT NOT NULL, PRIMARY KEY(run_id,request_id))''')
        for run_id, seq, request_id, request, event in db.execute(
                'SELECT run_id,seq,request_id,request,event FROM action_events'):
            db.execute('INSERT OR IGNORE INTO action_commands VALUES (?,?,?,?,?,?)',
                       (run_id, request_id, request, event, seq, _now()))

    # ------------------------------------------------------------ plumbing

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _status(db, run_id):
        row = db.execute('SELECT status FROM runs WHERE id=?', (run_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown run')
        return row[0]

    @staticmethod
    def _manifest(db, run_id):
        row = db.execute('SELECT manifest FROM runs WHERE id=?', (run_id,)).fetchone()
        return json.loads(row[0]) if row else {}

    # ------------------------------------------------------------- lifecycle

    def begin(self, manifest):
        run_id = digest(manifest)
        text = canonical(manifest)
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO runs (id,manifest,status) VALUES (?,?,?)',
                       (run_id, text, 'running'))
            if db.execute('SELECT manifest FROM runs WHERE id=?', (run_id,)).fetchone()[0] != text:
                raise ValueError('Run identity collision')
        return run_id

    def put(self, run_id, point):
        if point['run_id'] != run_id:
            raise ValueError('Cross-run point rejected')
        missing = [k for k in POINT_SCHEMA if k not in point]
        if missing:
            raise ValueError(f'Point is missing required fields: {missing}')
        text = canonical(point)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            status = self._status(db, run_id)
            old = db.execute('SELECT payload FROM points WHERE run_id=? AND day=?',
                             (run_id, point['date'])).fetchone()
            if old:
                if old[0] != text:
                    raise ValueError('Retry changed an already persisted point')
                return   # verified identical retry: always allowed
            if status != 'running':
                raise ValueError(
                    f'Run {run_id[:12]} is sealed ({status}); a new point for '
                    f'{point["date"]} cannot be added')
            manifest = self._manifest(db, run_id)
            start, end = manifest.get('start'), manifest.get('end')
            if start and end and not (start <= point['date'] <= end):
                raise ValueError(
                    f'Point {point["date"]} lies outside this run\'s declared '
                    f'range {start}..{end}')
            db.execute('INSERT INTO points VALUES (?,?,?)', (run_id, point['date'], text))

    def finish(self, run_id, expected, *, requires_report=False):
        """Seal a run.

        `expected` is the exact set of dates the run must contain, or an
        integer row count for store-level callers that do not model dates.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            status = self._status(db, run_id)
            rows = db.execute('SELECT day,payload FROM points WHERE run_id=? ORDER BY day',
                              (run_id,)).fetchall()
            actual = [day for day, _ in rows]
            if isinstance(expected, int):
                if len(actual) != expected:
                    raise ValueError('Incomplete run cannot be marked complete')
            else:
                wanted = sorted(expected)
                if actual != wanted:
                    missing = sorted(set(wanted) - set(actual))
                    extra = sorted(set(actual) - set(wanted))
                    raise ValueError(
                        f'Run contents do not match the expected date set '
                        f'(missing {missing[:5]}, unexpected {extra[:5]})')
            content_hash = hashlib.sha256(
                '\n'.join(payload for _, payload in rows).encode()).hexdigest()
            sealed_dates = canonical(actual)
            if status != 'running':
                # Deterministic retry of a completed run must be a no-op, and
                # must verify that the sealed contents did not change.
                previous = db.execute(
                    'SELECT sealed_dates,content_hash FROM runs WHERE id=?',
                    (run_id,)).fetchone()
                if previous[0] is not None and (previous[0], previous[1]) != (
                        sealed_dates, content_hash):
                    raise ValueError('Sealed run contents changed on retry')
                return status
            new_status = 'inference_complete' if requires_report else 'complete'
            if db.execute('SELECT 1 FROM report_revisions WHERE run_id=?',
                          (run_id,)).fetchone():
                new_status = 'complete'
            db.execute('UPDATE runs SET status=?, sealed_dates=?, content_hash=?, '
                       'sealed_at=? WHERE id=?',
                       (new_status, sealed_dates, content_hash, _now(), run_id))
            return new_status

    def runs(self):
        with self.connect() as db:
            return [dict(id=r[0], manifest=json.loads(r[1]), status=r[2],
                         sealed_dates=json.loads(r[3]) if r[3] else None,
                         content_hash=r[4], sealed_at=r[5])
                    for r in db.execute('SELECT id,manifest,status,sealed_dates,'
                                        'content_hash,sealed_at FROM runs ORDER BY rowid DESC')]

    def points(self, run_id):
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                'SELECT payload FROM points WHERE run_id=? ORDER BY day', (run_id,))]

    # --------------------------------------------------------------- reports

    def report(self, run_id, value=None):
        """Read the latest report revision, or append a new one.

        An identical re-write is an idempotent no-op. A DIFFERENT report
        appends a new revision; the previous revision is preserved.
        """
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if value is not None:
                self._status(db, run_id)
                text = canonical(value)
                content_hash = hashlib.sha256(text.encode()).hexdigest()
                latest = db.execute(
                    'SELECT revision,content_hash FROM report_revisions WHERE run_id=? '
                    'ORDER BY revision DESC LIMIT 1', (run_id,)).fetchone()
                if latest is None or latest[1] != content_hash:
                    revision = 1 if latest is None else latest[0] + 1
                    db.execute('INSERT INTO report_revisions VALUES (?,?,?,?,?)',
                               (run_id, revision, text, content_hash, _now()))
                # FIX03: the report is what completes an inference-sealed run.
                db.execute("UPDATE runs SET status='complete' WHERE id=? "
                           "AND status='inference_complete'", (run_id,))
            row = db.execute('SELECT payload FROM report_revisions WHERE run_id=? '
                             'ORDER BY revision DESC LIMIT 1', (run_id,)).fetchone()
            return json.loads(row[0]) if row else None

    def report_revisions(self, run_id):
        with self.connect() as db:
            return [dict(revision=r[0], payload=json.loads(r[1]), content_hash=r[2],
                         created_at=r[3])
                    for r in db.execute(
                        'SELECT revision,payload,content_hash,created_at FROM '
                        'report_revisions WHERE run_id=? ORDER BY revision', (run_id,))]

    # --------------------------------------------------------------- journal

    @staticmethod
    def _restore(events):
        from seraph.decision_support.action_log import RegulatoryActionLog, ActionLogJournalRecord
        log = RegulatoryActionLog()
        # C11's immutable journal is the authority; restore the exact entries,
        # timestamps and revisions, including tombstones, without re-issuing actions.
        for text in events:
            event = ActionLogJournalRecord.model_validate_json(text)
            log._journal.append(event)
            if event.after is not None:
                log._entries[event.alert_id] = event.after
        return log

    def action_log(self, run_id):
        with self.connect() as db:
            return self._restore([r[0] for r in db.execute(
                'SELECT event FROM action_events WHERE run_id=? ORDER BY seq', (run_id,))])

    def action_commands(self, run_id):
        with self.connect() as db:
            return [dict(request_id=r[0], request=json.loads(r[1]),
                         result=json.loads(r[2]), event_seq=r[3], created_at=r[4])
                    for r in db.execute(
                        'SELECT request_id,request,result,event_seq,created_at FROM '
                        'action_commands WHERE run_id=? ORDER BY created_at,request_id',
                        (run_id,))]

    def action(self, run_id, request_id, role, operation, **kwargs):
        from seraph.dashboard.gateway import action_log_request
        request = canonical(dict(role=role, operation=operation, arguments=kwargs))
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM runs WHERE id=?', (run_id,)).fetchone():
                raise ValueError('Unknown run')
            old = db.execute('SELECT request,result FROM action_commands '
                             'WHERE run_id=? AND request_id=?',
                             (run_id, request_id)).fetchone()
            if old:
                if old[0] != request:
                    raise ValueError('Idempotency key reused with different action')
                return json.loads(old[1])
            existing = [r[0] for r in db.execute(
                'SELECT event FROM action_events WHERE run_id=? ORDER BY seq', (run_id,))]
            log = self._restore(existing)
            before = len(log.journal())
            result = action_log_request(role, operation, log, **kwargs)
            if result.status != 'ok':
                raise ValueError(str(result.error))
            if operation == 'read':
                return result.value
            appended = log.journal()[before:]
            if appended:
                # One command, one new journal event.
                event = appended[-1]
                payload = event.model_dump_json()
                db.execute('INSERT INTO action_events VALUES (?,?,?,?,?)',
                           (run_id, event.seq, request_id, request, payload))
                db.execute('INSERT INTO action_commands VALUES (?,?,?,?,?,?)',
                           (run_id, request_id, request, payload, event.seq, _now()))
                return json.loads(payload)
            # FIX08: a no-op command. C11 correctly appended no journal event,
            # so no sequence number is consumed and nothing is reinserted. The
            # command result is still recorded, so a retry is idempotent.
            noop = dict(noop=True, operation=operation,
                        reason='the command left the action unchanged; no journal '
                               'event was created',
                        journal_length=before,
                        last_seq=json.loads(existing[-1])['seq'] if existing else None)
            db.execute('INSERT INTO action_commands VALUES (?,?,?,?,?,?)',
                       (run_id, request_id, request, canonical(noop), None, _now()))
            return noop
