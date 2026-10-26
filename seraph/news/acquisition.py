# C13 — Source registry, acquisition and deduplication (NEWS01, NEWS02)
"""Fetch registered sources idempotently, and collapse what comes back.

Two properties this module exists to guarantee:

* **A restart or a double poll produces one logical observation.** The
  observation id is derived from `(source, reference, content_hash)`, so
  re-fetching unchanged content writes nothing new. An item whose content
  changed becomes a new observation and a *correcting* story, never an
  overwrite of what earlier users saw.
* **A source outage is missing coverage, not quiet.** Failures are recorded
  against the source's health with a bounded retry count; downstream asks
  `coverage_at()` and gets back which sources were actually reachable, so an
  empty map can be distinguished from a calm one.

Fetching is injected (`fetcher`), never hard-wired. Tests drive it with
fixtures; an operator supplies a real HTTP client. Nothing here reaches the
network on import.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from seraph.news.model import (
    RawObservation,
    Source,
    SourceHealth,
    Story,
    syndication_key,
)
from seraph.product_types import Coverage, Timing
from seraph.shared_types import IST, ist_timestamp


def _now() -> str:
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


class SourceNotRegistered(KeyError):
    """An unregistered source tried to put something into the pipeline."""


@dataclass(frozen=True)
class FetchedItem:
    """One item as a fetcher hands it over, before any SERAPH semantics."""

    reference: str
    title: str
    url: str
    raw: bytes
    published_at: str | None = None
    body: str | None = None
    cursor: str | None = None
    language: str | None = None
    metadata: dict | None = None

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.raw).hexdigest()


@dataclass(frozen=True)
class FetchResult:
    items: tuple[FetchedItem, ...] = ()
    cursor: str | None = None
    http_status: int | None = 200


@dataclass(frozen=True)
class IngestReport:
    source_id: str
    attempted_at: str
    ok: bool
    new_observations: int = 0
    unchanged: int = 0
    new_stories: int = 0
    corrections: int = 0
    syndications: int = 0
    attempts: int = 1
    error: str | None = None
    #: Documents that returned to bytes this source served before. Counted
    #: apart from `new_observations` because the observation is genuinely
    #: not new -- the OBSERVED STATE is.
    reversions: int = 0

    def describe(self) -> dict:
        return dict(source_id=self.source_id, attempted_at=self.attempted_at,
                    ok=self.ok, new_observations=self.new_observations,
                    unchanged=self.unchanged, new_stories=self.new_stories,
                    corrections=self.corrections, syndications=self.syndications,
                    reversions=self.reversions,
                    attempts=self.attempts, error=self.error)


class NewsStore:
    """Sources, observations, stories and source health."""

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS observation_metadata (
                    observation_id TEXT PRIMARY KEY REFERENCES observations(observation_id),
                    payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS source_versions (
                    source_id TEXT NOT NULL, known_at TEXT NOT NULL, payload TEXT NOT NULL,
                    PRIMARY KEY(source_id,known_at));
                CREATE TABLE IF NOT EXISTS http_validators (
                    source_id TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS document_attempts (
                    source_id TEXT NOT NULL, url TEXT NOT NULL,
                    attempted_at TEXT NOT NULL, retry_at TEXT NOT NULL,
                    status TEXT NOT NULL, PRIMARY KEY(source_id,url));
                CREATE TABLE IF NOT EXISTS news_snapshots (
                    snapshot_id TEXT PRIMARY KEY, available_at TEXT NOT NULL,
                    method TEXT NOT NULL, payload TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS snapshots_no_update BEFORE UPDATE ON news_snapshots
                    BEGIN SELECT RAISE(ABORT,'snapshots are immutable'); END;

                CREATE TABLE IF NOT EXISTS sources (
                    source_id TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    registered_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS source_health (
                    source_id TEXT PRIMARY KEY REFERENCES sources(source_id),
                    last_attempt_at TEXT, last_success_at TEXT,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT, cursor TEXT);
                CREATE TABLE IF NOT EXISTS observations (
                    observation_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    reference TEXT NOT NULL, content_hash TEXT NOT NULL,
                    fetched_at TEXT NOT NULL, http_status INTEGER,
                    parse_status TEXT NOT NULL, cursor TEXT, raw BLOB);
                CREATE INDEX IF NOT EXISTS obs_by_ref
                    ON observations(source_id, reference);
                CREATE TABLE IF NOT EXISTS stories (
                    story_id TEXT PRIMARY KEY,
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    observation_id TEXT NOT NULL REFERENCES observations(observation_id),
                    title TEXT NOT NULL, url TEXT NOT NULL, body TEXT,
                    first_seen_at TEXT NOT NULL, published_at TEXT,
                    syndication_group TEXT, corrects TEXT, retracts TEXT,
                    language TEXT NOT NULL DEFAULT 'en',
                    -- Decided at acquisition, where first_seen_at is the
                    -- current instant, so a later published_at can only be a
                    -- future date. At read time the two cases are
                    -- indistinguishable, so this is stored, not re-derived.
                    publication_scheduled INTEGER NOT NULL DEFAULT 0);
                CREATE INDEX IF NOT EXISTS stories_by_group
                    ON stories(syndication_group);
                CREATE INDEX IF NOT EXISTS stories_by_seen ON stories(first_seen_at);
                -- A syndication group is DERIVED, and the rule that derives
                -- it has been wrong (an ASCII-only tokeniser filed every
                -- Hindi headline of a day as one story). `stories` is
                -- immutable by trigger and must stay so, because the group
                -- a user was shown is part of what the system actually
                -- said. The corrected grouping therefore lives here, beside
                -- the record rather than over it, with the rule version
                -- that produced it.
                CREATE TABLE IF NOT EXISTS syndication_rebuilds (
                    story_id TEXT PRIMARY KEY REFERENCES stories(story_id),
                    syndication_group TEXT NOT NULL,
                    previous_group TEXT,
                    key_version TEXT NOT NULL,
                    rebuilt_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS rebuilds_by_group
                    ON syndication_rebuilds(syndication_group);
                -- The OBSERVED STATE TIMELINE of one document reference.
                -- `observations` are keyed by content, so re-fetching bytes
                -- the source served before collapses onto the earlier row
                -- and the document looked unchanged. A document that goes
                -- A -> B -> A has three states and two transitions, and the
                -- third is what is current.
                CREATE TABLE IF NOT EXISTS document_states (
                    state_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    reference TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    content_hash TEXT NOT NULL,
                    observation_id TEXT NOT NULL REFERENCES observations(observation_id),
                    story_id TEXT,
                    observed_at TEXT NOT NULL,
                    reverted INTEGER NOT NULL DEFAULT 0);
                CREATE UNIQUE INDEX IF NOT EXISTS document_states_seq
                    ON document_states(source_id, reference, sequence);
                CREATE TRIGGER IF NOT EXISTS document_states_no_update
                    BEFORE UPDATE ON document_states
                    BEGIN SELECT RAISE(ABORT,'document states are immutable'); END;
                -- Text retrieved for a permitted document, kept so a later
                -- pass does not spend its whole budget re-fetching what it
                -- already has while another document never gets a body.
                CREATE TABLE IF NOT EXISTS documents (
                    source_id TEXT NOT NULL, url TEXT NOT NULL,
                    text TEXT NOT NULL, document_hash TEXT NOT NULL,
                    format TEXT NOT NULL, truncated INTEGER NOT NULL DEFAULT 0,
                    acquired_at TEXT NOT NULL, refresh_after TEXT NOT NULL,
                    PRIMARY KEY(source_id, url));
                -- Written by the acquisition worker on every pass. One row
                -- per worker name, overwritten: this is liveness, not
                -- history, and the append-only record is `ingest_log`.
                CREATE TABLE IF NOT EXISTS worker_heartbeat (
                    worker TEXT PRIMARY KEY,
                    beat_at TEXT NOT NULL,
                    pid INTEGER,
                    status TEXT NOT NULL DEFAULT 'running',
                    detail TEXT,
                    -- Advances once per completed pass. A beat alone proves
                    -- the process is alive; only this proves it is getting
                    -- anywhere.
                    sequence INTEGER NOT NULL DEFAULT 0,
                    activity TEXT,
                    -- When the current operation should have finished. A
                    -- long operation that declares its deadline is
                    -- distinguishable from a deadlock; one that does not is
                    -- indistinguishable.
                    deadline TEXT);
                -- A REQUEST for acquisition, not an acquisition. One row
                -- per request; a pending request absorbs further asks, which
                -- is what stops N browser tabs producing N fetch storms.
                -- A period during which a source was NOT collected,
                -- recorded independently of source_health because the first
                -- successful poll after an outage overwrites that and would
                -- destroy the evidence of the gap.
                CREATE TABLE IF NOT EXISTS collection_gaps (
                    gap_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL REFERENCES sources(source_id),
                    since TEXT, until TEXT NOT NULL,
                    observed_at TEXT NOT NULL,
                    recoverable INTEGER NOT NULL DEFAULT 0,
                    state TEXT NOT NULL DEFAULT 'open',
                    -- Where a truncated backfill should resume. Stopping at a
                    -- page cap and reporting success would claim an interval
                    -- was covered when it was not.
                    next_page INTEGER,
                    covered_until TEXT,
                    recovered_stories INTEGER NOT NULL DEFAULT 0,
                    note TEXT,
                    closed_at TEXT);
                CREATE INDEX IF NOT EXISTS gaps_open
                    ON collection_gaps(source_id, state);
                CREATE TABLE IF NOT EXISTS acquisition_requests (
                    request_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_at TEXT NOT NULL,
                    requested_by TEXT,
                    reason TEXT,
                    state TEXT NOT NULL DEFAULT 'pending',
                    claimed_at TEXT, claimed_by TEXT,
                    finished_at TEXT,
                    progress TEXT);
                CREATE INDEX IF NOT EXISTS acq_by_state
                    ON acquisition_requests(state, requested_at);
                -- A reviewer's decision about whether one instrument
                -- replaces another. Appended, never overwritten: a link
                -- that was acted on must stay readable after it is
                -- reversed, and `decided_at` is what makes a replay of
                -- last week see last week's decision.
                CREATE TABLE IF NOT EXISTS supersession_reviews (
                    review_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    later_event_id TEXT NOT NULL,
                    earlier_event_id TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reviewer TEXT NOT NULL,
                    reason TEXT,
                    instrument_id TEXT,
                    decided_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS supersession_by_pair
                    ON supersession_reviews(later_event_id, earlier_event_id);
                CREATE TRIGGER IF NOT EXISTS supersession_no_update
                    BEFORE UPDATE ON supersession_reviews
                    BEGIN SELECT RAISE(ABORT,'reviews are append-only; record a new decision'); END;
                -- What retention removed, and from where. `retention_days`
                -- had no enforcement path at all: it was recorded on the
                -- source and nothing ever acted on it. Enforcement deletes
                -- the TEXT and keeps the record that the text existed --
                -- the observation row, its content hash and this entry --
                -- so a retention policy cannot be used to quietly rewrite
                -- what the system once held.
                CREATE TABLE IF NOT EXISTS retention_redactions (
                    redaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL,
                    observation_id TEXT NOT NULL,
                    reference TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    fetched_at TEXT NOT NULL,
                    retention_days INTEGER NOT NULL,
                    raw_bytes_removed INTEGER NOT NULL DEFAULT 0,
                    body_removed INTEGER NOT NULL DEFAULT 0,
                    redacted_at TEXT NOT NULL);
                CREATE INDEX IF NOT EXISTS redactions_by_obs
                    ON retention_redactions(observation_id);
                CREATE TRIGGER IF NOT EXISTS redactions_no_update
                    BEFORE UPDATE ON retention_redactions
                    BEGIN SELECT RAISE(ABORT,'redaction records are immutable'); END;
                CREATE TABLE IF NOT EXISTS ingest_log (
                    rowid_ INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id TEXT NOT NULL, attempted_at TEXT NOT NULL,
                    payload TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS observations_no_update
                    BEFORE UPDATE ON observations
                    BEGIN SELECT RAISE(ABORT,'observations are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS stories_no_update BEFORE UPDATE ON stories
                    BEGIN SELECT RAISE(ABORT,'stories are immutable; publish a correction'); END;
            ''')
            # `CREATE TABLE IF NOT EXISTS` never adds a column to a table that
            # already exists, so a store created before a column was
            # introduced silently lacks it -- and the read degraded to
            # `unknown` rather than failing loudly. Additive migration is
            # applied here, on every open, for exactly the columns added
            # after a table shipped.
            self._add_missing_columns(db, {
                'stories': {
                    'publication_scheduled': 'INTEGER NOT NULL DEFAULT 0',
                },
                'worker_heartbeat': {
                    'sequence': 'INTEGER NOT NULL DEFAULT 0',
                    'activity': 'TEXT',
                    'deadline': 'TEXT',
                },
                'acquisition_requests': {
                    'lease_until': 'TEXT',
                    'claim_token': 'TEXT',
                    'attempts': 'INTEGER NOT NULL DEFAULT 0',
                },
            })

    @staticmethod
    def _add_missing_columns(db, wanted: dict) -> list:
        """Add columns a table is missing. Additive only: never drops, never
        rewrites, never changes a type -- so it cannot lose data, and it is
        safe to run on every open."""
        added = []
        for table, columns in wanted.items():
            existing = {row[1] for row in
                        db.execute(f'PRAGMA table_info({table})')}
            if not existing:
                continue                      # the table itself is new
            for name, decl in columns.items():
                if name not in existing:
                    db.execute(f'ALTER TABLE {table} ADD COLUMN {name} {decl}')
                    added.append(f'{table}.{name}')
        return added

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

    # ------------------------------------------------------- registry

    def register(self, source: Source) -> Source:
        with self.connect() as db:
            stamp = _now()
            payload = json.dumps(source.describe())
            db.execute('INSERT INTO sources VALUES (?,?,?) ON CONFLICT(source_id) '
                       'DO UPDATE SET payload=excluded.payload',
                       (source.source_id, payload, stamp))
            # Versioned on CHANGE, not on every call. `INSERT OR IGNORE`
            # keyed on (source_id, known_at) silently dropped a revised
            # registration that landed in the same second as the previous
            # one, so a manifest could pin a source definition that was no
            # longer the one in use.
            latest = db.execute(
                'SELECT payload FROM source_versions WHERE source_id=? '
                'ORDER BY known_at DESC LIMIT 1',
                (source.source_id,)).fetchone()
            if latest is None or latest[0] != payload:
                db.execute('INSERT OR REPLACE INTO source_versions VALUES (?,?,?)',
                           (source.source_id, stamp, payload))
            db.execute('INSERT OR IGNORE INTO source_health '
                       '(source_id, consecutive_failures) VALUES (?,0)',
                       (source.source_id,))
        return source

    def source(self, source_id: str) -> Source:
        with self.connect() as db:
            row = db.execute('SELECT payload FROM sources WHERE source_id=?',
                             (source_id,)).fetchone()
        if not row:
            raise SourceNotRegistered(
                f'{source_id} is not a registered source. Unregistered content '
                f'cannot enter the pipeline')
        payload = json.loads(row[0])
        return Source(source_id=payload['source_id'], provider=payload['provider'],
                      kind=payload['kind'], url=payload['url'],
                      topic_coverage=tuple(payload['topic_coverage']),
                      language=payload['language'], rights=payload['rights'],
                      may_store_full_text=payload['may_store_full_text'],
                      retention_days=payload['retention_days'],
                      poll_interval_minutes=payload['poll_interval_minutes'],
                      failure_behaviour=payload['failure_behaviour'],
                      max_retries=payload.get('max_retries', 3),
                      accessibility_verified=payload['accessibility_verified'],
                      permissions=(tuple(payload['permissions'])
                                   if payload.get('permissions') else None),
                      rights_reviewed_by=payload.get('rights_reviewed_by'),
                      rights_reviewed_at=payload.get('rights_reviewed_at'),
                      rights_version=payload.get('rights_version'),
                      notes=payload.get('notes'))

    def sources(self) -> list[Source]:
        with self.connect() as db:
            ids = [r[0] for r in db.execute('SELECT source_id FROM sources ORDER BY source_id')]
        return [self.source(i) for i in ids]

    def sources_at(self, timestamp: str) -> list[Source]:
        """Historical source roster/configuration, without today's additions."""
        with self.connect() as db:
            rows = db.execute(
                'SELECT v.payload FROM source_versions v JOIN '
                '(SELECT source_id,MAX(known_at) AS known_at FROM source_versions '
                'WHERE known_at<=? GROUP BY source_id) latest '
                'ON latest.source_id=v.source_id AND latest.known_at=v.known_at '
                'ORDER BY v.source_id', (timestamp,)).fetchall()
        import dataclasses
        # A stored version may carry fields this build does not know:
        # `permitted_uses` was added by the rights work and is not a `Source`
        # field, so splatting the whole payload made every roster stored from
        # 2026-10-19 unreadable -- and this is the strict-replay path the
        # historical console uses. `source()` has always built field by field
        # and so tolerated it. Unknown keys are ignored, never guessed at.
        known = {field.name for field in dataclasses.fields(Source)}
        result = []
        for (raw,) in rows:
            payload = json.loads(raw)
            payload['topic_coverage'] = tuple(payload['topic_coverage'])
            if payload.get('permissions') is not None:
                payload['permissions'] = tuple(payload['permissions'])
            result.append(Source(**{name: value for name, value in payload.items()
                                    if name in known}))
        return result

    def health(self, source_id: str) -> SourceHealth:
        with self.connect() as db:
            row = db.execute(
                'SELECT source_id,last_attempt_at,last_success_at,'
                'consecutive_failures,last_error,cursor FROM source_health '
                'WHERE source_id=?', (source_id,)).fetchone()
        if not row:
            raise SourceNotRegistered(source_id)
        return SourceHealth(*row)

    # ------------------------------------------------------ acquisition

    def document_attempt(self, source_id, url):
        """Operational retrieval state; never modifies immutable evidence."""
        with self.connect() as db:
            row = db.execute('SELECT attempted_at,retry_at,status FROM document_attempts '
                             'WHERE source_id=? AND url=?', (source_id, url)).fetchone()
        return dict(zip(('attempted_at', 'retry_at', 'status'), row)) if row else None

    def record_document_attempt(self, source_id, url, status, *, retry_seconds=3600):
        stamp = _now()
        retry = ist_timestamp(datetime.fromisoformat(stamp) + timedelta(seconds=retry_seconds))
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO document_attempts VALUES (?,?,?,?,?)',
                       (source_id, url, stamp, retry, status))

    #: How long a successfully retrieved document is reused before it is
    #: fetched again. DECLARED, not implicit: the full text of an official
    #: document does change (a correction, a re-issued annex), so "never
    #: refresh" would be wrong, and the previous behaviour -- no persistence
    #: at all -- re-fetched it on every single pass and starved every other
    #: document of the budget.
    DOCUMENT_REFRESH_DAYS = 7

    def save_document(self, source_id, url, *, text, document_hash, format,
                      truncated=False, acquired_at=None,
                      refresh_days: "int | None" = None):
        """Persist retrieved document text so a later pass need not re-fetch it.

        Without this, a restart (or an expired per-process cache) meant the
        first permitted URL consumed the whole document budget on every
        pass, forever, and the second document never got a body at all.
        """
        acquired = acquired_at or _now()
        days = self.DOCUMENT_REFRESH_DAYS if refresh_days is None else refresh_days
        refresh = ist_timestamp(datetime.fromisoformat(acquired)
                                + timedelta(days=days))
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO documents VALUES (?,?,?,?,?,?,?,?)',
                       (source_id, url, text, document_hash, format,
                        int(bool(truncated)), acquired, refresh))
        return dict(source_id=source_id, url=url, acquired_at=acquired,
                    refresh_after=refresh)

    def document(self, source_id, url, *, now: "str | None" = None):
        """The stored text for a permitted document, if it is still current.

        Returns the row with `due_for_refresh` set, so a caller can reuse it
        (no network, identical bytes, therefore an idempotent observation)
        and still know when a refresh is owed.
        """
        with self.connect() as db:
            row = db.execute(
                'SELECT text,document_hash,format,truncated,acquired_at,'
                'refresh_after FROM documents WHERE source_id=? AND url=?',
                (source_id, url)).fetchone()
        if row is None:
            return None
        return dict(text=row[0], document_hash=row[1], format=row[2],
                    truncated=bool(row[3]), acquired_at=row[4],
                    refresh_after=row[5],
                    due_for_refresh=(now or _now()) >= row[5])

    def document_progress(self, source_id: "str | None" = None) -> dict:
        """How many permitted documents have text, and how many are owed one."""
        # A document is counted when it was retrieved for this story, from
        # EITHER the citation url or the separate retrieval url the adapter
        # supplied. Joining on the citation alone reported zero documents
        # for every source whose text is published somewhere other than the
        # link a reader follows -- which is every Federal Register source,
        # whose text comes from the GPO.
        sql = ('SELECT s.source_id, COUNT(*), '
               'SUM(CASE WHEN d.url IS NULL THEN 0 ELSE 1 END) '
               'FROM stories s '
               'LEFT JOIN observation_metadata m '
               'ON m.observation_id=s.observation_id '
               'LEFT JOIN documents d '
               'ON d.source_id=s.source_id AND d.url IN '
               '(s.url, COALESCE(json_extract(m.payload, \'$.document_url\'), s.url))')
        args = []
        if source_id:
            sql += ' WHERE s.source_id=?'
            args.append(source_id)
        sql += ' GROUP BY s.source_id'
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
        return {r[0]: dict(stories=r[1], with_document=r[2] or 0,
                           outstanding=r[1] - (r[2] or 0)) for r in rows}

    def pending_documents(self, source_id, *, limit=100):
        """Recover deferred article fetches even after restart or feed HTTP 304.

        Select current revisions only. Old corrections must never replace a
        newer story just because their document was fetched later.
        """
        with self.connect() as db:
            rows = db.execute('''SELECT o.reference,s.title,s.url,o.raw,s.published_at,
                s.body,s.language,m.payload,o.observation_id,o.content_hash FROM stories s
                JOIN observations o ON o.observation_id=s.observation_id
                LEFT JOIN observation_metadata m ON m.observation_id=s.observation_id
                LEFT JOIN document_attempts d ON d.source_id=s.source_id AND d.url=s.url
                WHERE s.source_id=? AND s.retracts IS NULL
                AND NOT EXISTS (SELECT 1 FROM stories newer
                    WHERE newer.corrects=s.story_id OR newer.retracts=s.story_id)
                -- Text this store has deliberately let go of under a
                -- retention window is not a deferred fetch waiting to be
                -- recovered.
                AND NOT EXISTS (SELECT 1 FROM retention_redactions r
                    WHERE r.observation_id=s.observation_id)
                AND COALESCE(json_extract(m.payload,'$.document_status'),'') != 'retrieved'
                AND (d.retry_at IS NULL OR d.retry_at<=?)
                ORDER BY COALESCE(d.attempted_at,''),s.first_seen_at,s.story_id LIMIT ?''',
                (source_id, _now(), limit)).fetchall()
        items = []
        for r in rows:
            metadata = json.loads(r[7] or '{}')
            raw = r[3]
            if raw is None:
                # Earlier rights rules may have allowed metadata only. A
                # newly permitted document can still be retrieved by URL;
                # never pretend to reconstruct the discarded feed bytes.
                raw = json.dumps(dict(stored_title=r[1], stored_url=r[2],
                                      predecessor_hash=r[9]), sort_keys=True).encode()
                metadata.update(reconstructed_from_observation=r[8],
                                document_recovery_only=True)
            items.append(FetchedItem(reference=r[0], title=r[1], url=r[2], raw=raw,
                                     published_at=r[4], body=r[5], language=r[6], metadata=metadata))
        return items

    @staticmethod
    def _backfill_document_states(db, source_id: str, reference: str) -> int:
        """Derive the state timeline for one reference from its observations.

        Stores written before the timeline existed have the observations
        but not the sequence, and without it the first pass after an
        upgrade cannot tell a repeat from a reversion. Derived from
        immutable rows, in their recorded order, so it reconstructs exactly
        one timeline and is safe to run on every ingest.
        """
        if db.execute('SELECT 1 FROM document_states WHERE source_id=? AND '
                      'reference=? LIMIT 1', (source_id, reference)).fetchone():
            return 0
        rows = db.execute(
            'SELECT o.observation_id,o.content_hash,o.fetched_at,'
            '(SELECT story_id FROM stories s WHERE s.observation_id='
            'o.observation_id) FROM observations o WHERE o.source_id=? AND '
            'o.reference=? ORDER BY o.fetched_at, o.rowid',
            (source_id, reference)).fetchall()
        seen = set()
        for sequence, (observation_id, content_hash, fetched_at, story_id) in \
                enumerate(rows, start=1):
            db.execute(
                'INSERT INTO document_states (source_id,reference,sequence,'
                'content_hash,observation_id,story_id,observed_at,reverted) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (source_id, reference, sequence, content_hash, observation_id,
                 story_id, fetched_at, int(content_hash in seen)))
            seen.add(content_hash)
        return len(rows)

    def record_supersession_review(self, *, later_event_id: str,
                                   earlier_event_id: str, decision: str,
                                   reviewer: str, reason: str = "",
                                   instrument_id: "str | None" = None,
                                   now: "str | None" = None) -> dict:
        """Record a human decision that one instrument replaces another.

        The documents themselves often carry no shared identifier — a
        revocation published on its own cites nothing that names the order
        it revokes — and guessing from a similar title is exactly what must
        not happen. This is the other way a link can legitimately exist.
        """
        if decision not in ("confirmed", "rejected"):
            raise ValueError("a supersession decision is 'confirmed' or "
                             "'rejected'; there is no third answer that can "
                             "be acted on")
        if later_event_id == earlier_event_id:
            raise ValueError("an instrument cannot supersede itself")
        stamp = now or _now()
        with self.connect() as db:
            cursor = db.execute(
                'INSERT INTO supersession_reviews (later_event_id,'
                'earlier_event_id,decision,reviewer,reason,instrument_id,'
                'decided_at) VALUES (?,?,?,?,?,?,?)',
                (later_event_id, earlier_event_id, decision, reviewer,
                 reason, instrument_id, stamp))
        return dict(review_id=cursor.lastrowid, decided_at=stamp,
                    decision=decision)

    def supersession_decisions(self, *, visible_at: "str | None" = None) -> dict:
        """The decision in force for each pair at a decision time.

        Latest decision wins, bounded by `visible_at` so a replay sees what
        had been decided then rather than what is decided now.
        """
        sql = ('SELECT later_event_id,earlier_event_id,decision,reviewer,'
               'reason,decided_at FROM supersession_reviews')
        args = []
        if visible_at:
            sql += ' WHERE decided_at<=?'
            args.append(visible_at)
        sql += ' ORDER BY decided_at, review_id'
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
        latest = {}
        for later, earlier, decision, reviewer, reason, decided_at in rows:
            latest[(later, earlier)] = dict(decision=decision, reviewer=reviewer,
                                            reason=reason, decided_at=decided_at)
        return dict(
            confirmed=tuple(pair for pair, row in latest.items()
                            if row['decision'] == 'confirmed'),
            rejected=tuple(pair for pair, row in latest.items()
                           if row['decision'] == 'rejected'),
            decisions=[dict(later=p[0], earlier=p[1], **row)
                       for p, row in latest.items()])

    def document_states(self, source_id: str, reference: str) -> list[dict]:
        """Every observed state of one document reference, in order."""
        with self.connect() as db:
            self._backfill_document_states(db, source_id, reference)
            rows = db.execute(
                'SELECT sequence,content_hash,observation_id,story_id,'
                'observed_at,reverted FROM document_states WHERE source_id=? '
                'AND reference=? ORDER BY sequence', (source_id, reference)
            ).fetchall()
        return [dict(sequence=r[0], content_hash=r[1], observation_id=r[2],
                     story_id=r[3], observed_at=r[4], reverted=bool(r[5]))
                for r in rows]

    def ingest(self, source_id: str, fetcher, *, now: str | None = None,
               sleep=time.sleep) -> IngestReport:
        """Fetch a source once, with bounded retries, and store what is new.

        `fetcher(source, cursor) -> FetchResult`. Raising is a failure; the
        retry budget comes from the source's own registration, and exhausting
        it records missing coverage rather than raising at the caller.
        """
        source = self.source(source_id)
        attempted = now or _now()
        # Cursor validators only advance in the same transaction as accepted items.
        http = getattr(fetcher, '_http', fetcher)
        if hasattr(http, 'validators'):
            with self.connect() as db:
                row = db.execute('SELECT payload FROM http_validators WHERE source_id=?', (source_id,)).fetchone()
            if row: http.validators[source_id] = json.loads(row[0])
        health = self.health(source_id)
        attempts, error, result = 0, None, None
        budget = source.max_retries if source.failure_behaviour == 'retry_then_report' else 1
        # A caller working to a deadline passes one. Without it, retrying a
        # timing-out source three times with backoff spent more than twice the
        # whole refresh budget on one feed -- the socket timeout bit, and then
        # the retry loop ignored it.
        deadline = getattr(fetcher, 'deadline_timeout', None)
        spent = 0.0
        while attempts < max(1, budget):
            attempts += 1
            started = time.monotonic()
            try:
                result = fetcher(source, health.cursor)
                error = None
                break
            except Exception as exc:                       # noqa: BLE001
                error = f'{type(exc).__name__}: {exc}'
                spent += time.monotonic() - started
                if deadline is not None and spent >= deadline:
                    error = (f'{error} (deadline {deadline:.1f}s exhausted '
                             f'after {attempts} attempt(s); not retrying)')
                    break
                if attempts < budget:
                    backoff = min(2 ** (attempts - 1), 30)
                    if deadline is not None:
                        backoff = min(backoff, max(0.0, deadline - spent))
                    sleep(backoff)
                    spent += backoff
        if result is None:
            with self.connect() as db:
                db.execute(
                    'UPDATE source_health SET last_attempt_at=?, '
                    'consecutive_failures=consecutive_failures+1, last_error=? '
                    'WHERE source_id=?', (attempted, error, source_id))
            report = IngestReport(source_id=source_id, attempted_at=attempted,
                                  ok=False, attempts=attempts, error=error)
            self._log(report)
            return report

        new_obs = unchanged = new_stories = corrections = syndications = 0
        reversions = 0
        with self.connect() as db:
            for item in result.items:
                observation_id = RawObservation.identity(source_id, item.reference,
                                                         item.content_hash)
                exists = db.execute('SELECT 1 FROM observations WHERE observation_id=?',
                                    (observation_id,)).fetchone()
                # CONTENT identity and the OBSERVED STATE TIMELINE are two
                # different things, and conflating them lost a real change.
                # An observation id is derived from the bytes, so a document
                # that goes A -> B -> A produced an id that already existed
                # on the third fetch and was dismissed as a duplicate, which
                # left B standing as current forever. Repeated CURRENT bytes
                # are idempotent; returning to EARLIER bytes is a new state.
                self._backfill_document_states(db, source_id, item.reference)
                state = db.execute(
                    'SELECT sequence,content_hash,story_id FROM document_states '
                    'WHERE source_id=? AND reference=? ORDER BY sequence DESC '
                    'LIMIT 1', (source_id, item.reference)).fetchone()
                if state and state[1] == item.content_hash:
                    unchanged += 1
                    continue
                if state is None and exists:
                    # Nothing in the timeline and the bytes are already on
                    # file: a pre-timeline store with no story for this
                    # reference. Record the state and treat it as unchanged
                    # rather than publishing a correction of nothing.
                    db.execute(
                        'INSERT INTO document_states (source_id,reference,sequence,'
                        'content_hash,observation_id,story_id,observed_at,reverted) '
                        'VALUES (?,?,?,?,?,?,?,0)',
                        (source_id, item.reference, 1, item.content_hash,
                         observation_id, None, attempted))
                    unchanged += 1
                    continue
                sequence = (state[0] + 1) if state else 1
                seen_before = bool(db.execute(
                    'SELECT 1 FROM document_states WHERE source_id=? AND '
                    'reference=? AND content_hash=?',
                    (source_id, item.reference, item.content_hash)).fetchone())
                prior = db.execute(
                    'SELECT observation_id FROM observations WHERE source_id=? '
                    'AND reference=? ORDER BY fetched_at DESC, rowid DESC LIMIT 1',
                    (source_id, item.reference)).fetchone()
                received_at = max(attempted, (item.metadata or {}).get('document_acquired_at') or attempted)
                if not exists:
                    db.execute(
                        'INSERT INTO observations VALUES (?,?,?,?,?,?,?,?,?)',
                        (observation_id, source_id, item.reference, item.content_hash,
                         received_at, result.http_status, 'ok', item.cursor or result.cursor,
                         item.raw if source.permits('store') else None))
                    if item.metadata:
                        db.execute('INSERT INTO observation_metadata VALUES (?,?)',
                                   (observation_id, json.dumps(item.metadata)))
                    new_obs += 1
                else:
                    reversions += 1
                group = syndication_key(item.title, published_at=item.published_at,
                                        source_id=source_id,
                                        reference=item.reference)
                story_id = 'sty_' + hashlib.sha256(
                    f'{observation_id}'.encode()).hexdigest()[:20]
                if db.execute('SELECT 1 FROM stories WHERE story_id=?',
                              (story_id,)).fetchone():
                    # Only reachable on a reversion, where the bytes -- and
                    # therefore the observation id -- are the ones an earlier
                    # story already used. The state sequence disambiguates;
                    # every other story id keeps its historical derivation.
                    story_id = 'sty_' + hashlib.sha256(
                        f'{observation_id}|state:{sequence}'.encode()).hexdigest()[:20]
                corrects = state[2] if state else None
                if corrects is None and prior:
                    corrects = db.execute(
                        'SELECT story_id FROM stories WHERE observation_id=?',
                        (prior[0],)).fetchone()
                    corrects = corrects[0] if corrects else None
                same_group = db.execute(
                    'SELECT COUNT(*) FROM stories WHERE syndication_group=?',
                    (group,)).fetchone()[0]
                # `attempted` IS the current instant, so a published_at
                # after it is a scheduled future publication -- the Federal
                # Register routinely assigns one a few days out. Recorded
                # here because this is the only point at which the scheduled
                # case can be told apart from a back-filled first_seen_at.
                scheduled = bool(item.published_at
                                 and item.published_at > attempted)
                db.execute(
                    'INSERT INTO stories VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (story_id, source_id, observation_id, item.title, item.url,
                     item.body if source.permits('store') else None,
                     received_at, item.published_at, group, corrects, None,
                     item.language or ('hi' if any('\u0900' <= c <= '\u097f' for c in item.title) else source.language),
                     int(scheduled)))
                db.execute(
                    'INSERT INTO document_states (source_id,reference,sequence,'
                    'content_hash,observation_id,story_id,observed_at,reverted) '
                    'VALUES (?,?,?,?,?,?,?,?)',
                    (source_id, item.reference, sequence, item.content_hash,
                     observation_id, story_id, received_at, int(seen_before)))
                new_stories += 1
                if corrects:
                    corrections += 1
                if same_group:
                    syndications += 1

            db.execute(
                'UPDATE source_health SET last_attempt_at=?, last_success_at=?, '
                'consecutive_failures=0, last_error=NULL, cursor=COALESCE(?,cursor) '
                'WHERE source_id=?',
                (attempted, attempted, result.cursor, source_id))
            if hasattr(http, 'validators') and source_id in http.validators:
                db.execute('INSERT OR REPLACE INTO http_validators VALUES (?,?)',
                           (source_id, json.dumps(http.validators[source_id])))
            report = IngestReport(source_id=source_id, attempted_at=attempted, ok=True,
                                  new_observations=new_obs, unchanged=unchanged,
                                  new_stories=new_stories, corrections=corrections,
                                  syndications=syndications, reversions=reversions,
                                  attempts=attempts)
            db.execute('INSERT INTO ingest_log (source_id,attempted_at,payload) VALUES (?,?,?)',
                       (source_id, attempted, json.dumps(report.describe())))
        return report

    def _log(self, report: IngestReport) -> None:
        with self.connect() as db:
            db.execute('INSERT INTO ingest_log (source_id,attempted_at,payload) '
                       'VALUES (?,?,?)',
                       (report.source_id, report.attempted_at,
                        json.dumps(report.describe())))

    # ----------------------------------------------------------- reads

    def stories(self, *, visible_at: str | None = None,
                source_id: str | None = None) -> list[Story]:
        """Stories knowable at a decision time.

        `visible_at` filters on `first_seen_at`, never on `published_at`. A
        replay that filtered on publication would read items the system had
        not yet received.
        """
        sql = ('SELECT story_id,source_id,observation_id,title,url,body,'
               'first_seen_at,published_at,syndication_group,corrects,retracts,'
               'language,publication_scheduled FROM stories')
        clauses, args = [], []
        if visible_at:
            clauses.append('first_seen_at<=?')
            args.append(visible_at)
        if source_id:
            clauses.append('source_id=?')
            args.append(source_id)
        if clauses:
            sql += ' WHERE ' + ' AND '.join(clauses)
        sql += ' ORDER BY first_seen_at, story_id'
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
            metadata = dict(db.execute('SELECT observation_id,payload FROM observation_metadata'))
            # A corrected grouping overrides the one stored on the
            # immutable row; the original stays readable in `stories` and
            # the reason is in `syndication_rebuilds`.
            regrouped = dict(db.execute(
                'SELECT story_id,syndication_group FROM syndication_rebuilds'))
        return [Story(story_id=r[0], source_id=r[1], observation_id=r[2], title=r[3],
                      url=r[4], body=r[5],
                      timing=Timing(first_seen_at=r[6], published_at=r[7],
                                    publication_scheduled=bool(r[12])),
                      syndication_group=regrouped.get(r[0], r[8]),
                      corrects=r[9], retracts=r[10],
                      language=r[11], metadata=json.loads(metadata.get(r[2], "{}"))) for r in rows]

    def rebuild_syndication_groups(self, *, now: str | None = None,
                                   dry_run: bool = False) -> dict:
        """Recompute derived syndication groups under the current rule.

        Derived, so it may be rebuilt; the ORIGINAL rows are not touched.
        `stories` is immutable by trigger and stays that way, because the
        group a reader was shown is part of what the system said at the
        time. The corrected mapping is written beside it, versioned, and
        read in preference by `stories()`.
        """
        from seraph.news.model import SYNDICATION_KEY_VERSION
        stamp = now or _now()
        changed, unchanged = [], 0
        with self.connect() as db:
            rows = db.execute(
                'SELECT s.story_id,s.source_id,s.title,s.published_at,'
                's.syndication_group,o.reference FROM stories s '
                'JOIN observations o ON o.observation_id=s.observation_id'
            ).fetchall()
            existing = dict(db.execute(
                'SELECT story_id,syndication_group FROM syndication_rebuilds'))
            for story_id, source_id, title, published_at, group, reference in rows:
                wanted = syndication_key(title, published_at=published_at,
                                         source_id=source_id, reference=reference)
                current = existing.get(story_id, group)
                if wanted == current:
                    unchanged += 1
                    continue
                changed.append(dict(story_id=story_id, was=current, now=wanted))
                if not dry_run:
                    db.execute(
                        'INSERT OR REPLACE INTO syndication_rebuilds VALUES '
                        '(?,?,?,?,?)',
                        (story_id, wanted, group, SYNDICATION_KEY_VERSION, stamp))
        return dict(key_version=SYNDICATION_KEY_VERSION, rebuilt_at=stamp,
                    dry_run=dry_run, stories=len(changed) + unchanged,
                    regrouped=len(changed), unchanged=unchanged,
                    changes=changed[:200],
                    note=('original story rows and every observation are '
                          'untouched; this is a derived mapping with the '
                          'rule version that produced it'))

    def syndication_groups(self, *, visible_at: str | None = None
                           ) -> dict[str, list[Story]]:
        groups: dict[str, list[Story]] = {}
        stories = self.stories(visible_at=visible_at)
        replaced = {s.corrects for s in stories if s.corrects} | {s.retracts for s in stories if s.retracts}
        for story in stories:
            if story.story_id in replaced or story.retracts:
                continue
            groups.setdefault(story.syndication_group or story.story_id, []).append(story)
        return groups

    def observation(self, observation_id: str) -> RawObservation | None:
        with self.connect() as db:
            row = db.execute(
                'SELECT observation_id,source_id,reference,content_hash,fetched_at,'
                'http_status,parse_status,cursor,raw FROM observations '
                'WHERE observation_id=?', (observation_id,)).fetchone()
        if not row:
            return None
        return RawObservation(observation_id=row[0], source_id=row[1], reference=row[2],
                              content_hash=row[3], fetched_at=row[4], http_status=row[5],
                              parse_status=row[6], cursor=row[7], raw=row[8])

    def open_gap(self, *, source_id: str, since: "str | None", until: str,
                 recoverable: bool, note: str = "",
                 now: "str | None" = None) -> "dict | None":
        """Record a gap, unless an equivalent one is already open.

        Re-observing the same outage every thirty seconds must not produce a
        row every thirty seconds, so an open gap for the same source simply
        has its `until` extended.
        """
        stamp = now or _now()
        with self.connect() as db:
            existing = db.execute(
                "SELECT gap_id,since FROM collection_gaps "
                "WHERE source_id=? AND state='open' ORDER BY gap_id DESC "
                "LIMIT 1", (source_id,)).fetchone()
            if existing:
                db.execute("UPDATE collection_gaps SET until=? WHERE gap_id=?",
                           (until, existing[0]))
                return None
            cursor = db.execute(
                "INSERT INTO collection_gaps (source_id,since,until,"
                "observed_at,recoverable,note) VALUES (?,?,?,?,?,?)",
                (source_id, since, until, stamp, int(recoverable), note))
            return dict(gap_id=cursor.lastrowid, source_id=source_id,
                        since=since, until=until, recoverable=recoverable)

    def open_gaps(self, source_id: "str | None" = None, *,
                  visible_at: "str | None" = None) -> list:
        """Gaps open now, or open AT a decision time.

        Without `visible_at` a strict 08:00 replay listed a gap first
        observed at 10:00 — the system reporting, as of eight o'clock,
        something it did not learn until ten. A gap closed after the
        decision time was still open then, so the filter is on when the
        gap was observed and when it was closed, not on today's `state`.
        """
        sql = ("SELECT gap_id,source_id,since,until,observed_at,recoverable,"
               "next_page,covered_until,recovered_stories,note "
               "FROM collection_gaps WHERE ")
        args = []
        if visible_at:
            sql += "observed_at<=? AND (closed_at IS NULL OR closed_at>?)"
            args.extend((visible_at, visible_at))
        else:
            sql += "state='open'"
        if source_id:
            sql += " AND source_id=?"
            args.append(source_id)
        with self.connect() as db:
            rows = db.execute(sql + " ORDER BY gap_id", args).fetchall()
        return [dict(gap_id=r[0], source_id=r[1], since=r[2], until=r[3],
                     observed_at=r[4], recoverable=bool(r[5]), next_page=r[6],
                     covered_until=r[7], recovered_stories=r[8], note=r[9])
                for r in rows]

    def advance_gap(self, gap_id: int, *, next_page: "int | None" = None,
                    covered_until: "str | None" = None,
                    recovered: int = 0) -> None:
        """Persist progress through a gap so a truncated run can resume."""
        with self.connect() as db:
            db.execute(
                "UPDATE collection_gaps SET next_page=COALESCE(?,next_page),"
                "covered_until=COALESCE(?,covered_until),"
                "recovered_stories=recovered_stories+? WHERE gap_id=?",
                (next_page, covered_until, recovered, gap_id))

    def close_gap(self, gap_id: int, *, state: str = "recovered",
                  note: "str | None" = None, now: "str | None" = None) -> None:
        """Close a gap. `state` distinguishes how it ended.

        `recovered` means the interval was actually covered. `unrecoverable`
        means the feed cannot reach back that far -- the gap is settled, not
        filled, and the corpus has a known hole.
        """
        with self.connect() as db:
            db.execute(
                "UPDATE collection_gaps SET state=?,closed_at=?,"
                "note=COALESCE(?,note) WHERE gap_id=?",
                (state, now or _now(), note, gap_id))

    def claim_worker_ownership(self, worker: str, pid: int, *,
                               now: "str | None" = None,
                               stale_after_minutes: int = 5) -> dict:
        """Take ownership of this worker name, or refuse.

        A second worker against the same store doubles every fetch and races
        on the same acquisition requests. One refuses to start while
        another's heartbeat is fresh under a different pid; a stale heartbeat
        is a handover, because the previous owner is gone.
        """
        stamp = now or _now()
        state = self.worker_state(stamp, worker,
                                  dead_after_minutes=stale_after_minutes)
        holder = state.get("pid")
        if (state["state"] in self.ALIVE_STATUSES and holder is not None
                and holder != pid):
            return dict(granted=False, held_by=holder,
                        reason=(f"worker {worker!r} is already owned by pid "
                                f"{holder}, last beat {state['age_minutes']} "
                                f"min ago. Two workers on one store double "
                                f"every fetch and race on the same requests"))
        self.beat(worker, status="running", pid=pid, now=stamp,
                  activity="starting", detail="ownership claimed")
        return dict(granted=True, held_by=pid,
                    reason=("ownership claimed"
                            if holder in (None, pid)
                            else f"previous owner {holder} is gone; handover"))

    def request_acquisition(self, *, reason: str = "manual",
                            requested_by: str = "console",
                            now: "str | None" = None,
                            min_seconds_between: float = 60.0) -> dict:
        """Ask for acquisition. Coalesced and rate-limited.

        Returns the request that will serve this ask -- which may be one
        already pending. Two tabs pressing refresh together produce ONE
        acquisition, because the coalescing happens in the store rather than
        in any one session.
        """
        stamp = now or _now()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._recover_requests(db, stamp)
            pending = db.execute(
                "SELECT request_id,requested_at,state FROM acquisition_requests "
                "WHERE state IN ('pending','running') "
                "ORDER BY request_id DESC LIMIT 1").fetchone()
            if pending:
                return dict(request_id=pending[0], requested_at=pending[1],
                            state=pending[2], coalesced=True,
                            note="an acquisition is already pending or running; "
                                 "this ask joined it rather than starting a second")
            recent = db.execute(
                "SELECT request_id,finished_at FROM acquisition_requests "
                "WHERE finished_at IS NOT NULL "
                "ORDER BY request_id DESC LIMIT 1").fetchone()
            if recent and recent[1]:
                try:
                    gap = (datetime.fromisoformat(stamp)
                           - datetime.fromisoformat(recent[1])).total_seconds()
                except (ValueError, TypeError):
                    gap = min_seconds_between
                if gap < min_seconds_between:
                    return dict(request_id=recent[0], requested_at=recent[1],
                                state="rate_limited", coalesced=False,
                                retry_after_seconds=round(min_seconds_between - gap, 1),
                                note=(f"an acquisition finished {gap:.0f}s ago; "
                                      f"refusing another for "
                                      f"{min_seconds_between - gap:.0f}s. The "
                                      f"sources have not changed in that time"))
            cursor = db.execute(
                "INSERT INTO acquisition_requests (requested_at,requested_by,"
                "reason,state) VALUES (?,?,?,'pending')",
                (stamp, requested_by, reason))
            return dict(request_id=cursor.lastrowid, requested_at=stamp,
                        state="pending", coalesced=False,
                        note="queued; the worker will serve it on its next pass")

    @staticmethod
    def _recover_requests(db, stamp):
        """Requeue expired leases, including pre-migration abandoned requests.

        A fresh legacy claim gets three minutes to finish. Tokens fence late
        completion by an old owner after reassignment. Acquisitions themselves
        remain idempotent through observation/content identities.
        """
        legacy_cutoff = (datetime.fromisoformat(stamp) - timedelta(seconds=180)).isoformat()
        db.execute(
            "UPDATE acquisition_requests SET state='pending',claimed_at=NULL,"
            "claimed_by=NULL,claim_token=NULL,lease_until=NULL,progress=? "
            "WHERE state='running' AND ((lease_until IS NOT NULL AND lease_until<=?) "
            "OR (lease_until IS NULL AND (claimed_at IS NULL OR claimed_at<=?)))",
            (json.dumps({'recovery': 'previous acquisition lease expired; requeued'}),
             stamp, legacy_cutoff))

    def claim_acquisition(self, *, worker: str, now: "str | None" = None,
                          lease_seconds: float = 180
                          ) -> "dict | None":
        """Take ownership of the oldest pending request, or None.

        Claiming is a conditional UPDATE, so two workers racing cannot both
        serve the same request.
        """
        stamp = now or _now()
        token = uuid.uuid4().hex
        lease_until = (datetime.fromisoformat(stamp) + timedelta(seconds=lease_seconds)).isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self._recover_requests(db, stamp)
            row = db.execute(
                "SELECT request_id,requested_at,reason FROM acquisition_requests "
                "WHERE state='pending' ORDER BY request_id LIMIT 1").fetchone()
            if row is None:
                return None
            changed = db.execute(
                "UPDATE acquisition_requests SET state='running',claimed_at=?,"
                "claimed_by=?,claim_token=?,lease_until=?,attempts=attempts+1 "
                "WHERE request_id=? AND state='pending'",
                (stamp, worker, token, lease_until, row[0])).rowcount
            if not changed:
                return None
            return dict(request_id=row[0], requested_at=row[1], reason=row[2],
                        claim_token=token, lease_until=lease_until)

    def finish_acquisition(self, request_id: int, *, progress: dict,
                           claim_token: str, state: str = "done",
                           now: "str | None" = None) -> bool:
        if state not in ('done', 'failed'):
            raise ValueError('acquisition completion must be done or failed')
        with self.connect() as db:
            return bool(db.execute(
                "UPDATE acquisition_requests SET state=?,finished_at=?,"
                "progress=?,lease_until=NULL WHERE request_id=? "
                "AND state='running' AND claim_token=? AND lease_until>?",
                (state, now or _now(), json.dumps(progress), request_id,
                 claim_token, now or _now())).rowcount)

    def acquisition_progress(self, request_id: "int | None" = None) -> dict:
        """What the current or most recent acquisition request is doing."""
        with self.connect() as db:
            if request_id is None:
                row = db.execute(
                    "SELECT request_id,requested_at,state,claimed_at,claimed_by,"
                    "finished_at,progress FROM acquisition_requests "
                    "ORDER BY request_id DESC LIMIT 1").fetchone()
            else:
                row = db.execute(
                    "SELECT request_id,requested_at,state,claimed_at,claimed_by,"
                    "finished_at,progress FROM acquisition_requests "
                    "WHERE request_id=?", (request_id,)).fetchone()
        if row is None:
            return dict(state="none",
                        note="no acquisition has been requested in this store")
        return dict(request_id=row[0], requested_at=row[1], state=row[2],
                    claimed_at=row[3], claimed_by=row[4], finished_at=row[5],
                    progress=json.loads(row[6]) if row[6] else None)

    def beat(self, worker: str = 'news.poll', *, status: str = 'running',
             pid: "int | None" = None, detail: "str | None" = None,
             now: "str | None" = None, sequence: "int | None" = None,
             activity: "str | None" = None,
             deadline: "str | None" = None) -> str:
        """Record that the worker is alive, as of now.

        Overwrites rather than appends: this answers "is it running?", and the
        append-only account of what it did is `ingest_log`.
        """
        stamp = now or _now()
        with self.connect() as db:
            # `sequence` is bound TWICE on purpose. On insert it becomes 0
            # (the column is NOT NULL); on conflict it keeps the existing
            # value when the caller passed None. Coercing None to 0 in the
            # values instead made `excluded.sequence` always 0, so COALESCE
            # chose it and every beat reset the counter to zero -- which
            # would make a progressing worker look permanently stalled.
            db.execute(
                'INSERT INTO worker_heartbeat '
                '(worker,beat_at,pid,status,detail,sequence,activity,deadline) '
                'VALUES (?,?,?,?,?,COALESCE(?,0),?,?) '
                'ON CONFLICT(worker) DO UPDATE SET '
                'beat_at=excluded.beat_at, pid=excluded.pid, '
                'status=excluded.status, detail=excluded.detail, '
                'sequence=COALESCE(?, worker_heartbeat.sequence), '
                'activity=excluded.activity, deadline=excluded.deadline',
                (worker, stamp, pid, status, detail, sequence, activity,
                 deadline, sequence))
        return stamp

    #: Statuses that CLAIM to be alive, and are therefore subject to the age
    #: and stall checks. `stopped` and `failed` are terminal.
    #:
    #: `degraded` is alive. A worker whose pass completed while one publisher
    #: returned 503 is working correctly: the outage belongs to that source's
    #: health, not to the process. Writing `failed` for it made the
    #: supervisor -- which restarts anything not in this tuple -- terminate a
    #: healthy worker, and a recurring publisher error could exhaust the
    #: restart budget and stop every good feed with it.
    ALIVE_STATUSES = ('running', 'catching_up', 'degraded')

    #: Consecutive JOB-level failures (the pass machinery itself raising,
    #: not a source returning an error) before the worker declares itself
    #: failed and invites a restart. One is a blip; three in a row is a
    #: worker that cannot do its job, which is what a supervisor is for.
    MAX_CONSECUTIVE_JOB_FAILURES = 3

    def worker_state(self, decision_ts: str, worker: str = 'news.poll', *,
                     dead_after_minutes: int = 5,
                     strict_replay: bool = False) -> dict:
        """Is the acquisition worker running, and how do we know?

        `dead_after_minutes` is deliberately short and independent of any
        source's polling interval. The worker beats every pass regardless of
        whether a source was due, so silence means the WORKER stopped -- which
        is a different fact from a source being slow, and the one that was
        previously unobservable.
        """
        with self.connect() as db:
            row = db.execute(
                'SELECT beat_at,pid,status,detail,sequence,activity,deadline '
                'FROM worker_heartbeat WHERE worker=?', (worker,)).fetchone()
        if row is None:
            return dict(worker=worker, state='never_started', last_beat_at=None,
                        age_minutes=None, pid=None,
                        note=('no acquisition worker has ever recorded a '
                              'heartbeat in this store. Stories here were '
                              'written by a one-off run, and nothing is '
                              'fetching now'))
        beat_at, pid, status, detail, sequence, activity, deadline = row
        ahead = beat_at > decision_ts
        if ahead and strict_replay:
            # The heartbeat is LIVENESS, overwritten on every beat: there
            # is no history of it to replay. A decision time before the
            # only beat we hold therefore has no operational state, and
            # the honest answer is to say so. Reporting the row anyway
            # gave a strict 08:00 replay a worker beating at 10:00, with
            # an age of MINUS 120 minutes -- information from two hours
            # after the moment being reconstructed.
            return dict(worker=worker, state='unavailable_at_decision_time',
                        last_beat_at=None, age_minutes=None, pid=None,
                        detail=None, sequence=None, activity=None,
                        deadline=None, dead_after_minutes=dead_after_minutes,
                        omitted_future_beat_at=beat_at,
                        note=('the only heartbeat held was recorded AFTER '
                              'this decision time. Worker liveness is not '
                              'versioned -- the row is overwritten every '
                              'beat -- so what was running then cannot be '
                              'reconstructed and is omitted rather than '
                              'back-dated'))
        age = None
        try:
            age = (datetime.fromisoformat(decision_ts)
                   - datetime.fromisoformat(beat_at)).total_seconds() / 60
        except (ValueError, TypeError):
            pass
        if age is not None and age < 0:
            # A beat from after the question. Outside a strict replay this
            # is a clock skew or a fixed decision stamp, not a reason to
            # hide the status -- but a negative AGE is not a measurement
            # and must not be published as one.
            age = None
        # `stopped` and `failed` are terminal: the worker said so itself and
        # no amount of elapsed time changes that. Every other status is a
        # claim to be ALIVE, so it is subject to the age check -- otherwise a
        # worker that hung inside a long catch-up would advertise
        # `catching_up` forever and never be reported dead, which is the hole
        # this whole heartbeat exists to close.
        ALIVE = self.ALIVE_STATUSES
        if status not in ALIVE:
            state = status
        elif age is None:
            state = 'unknown'
        elif age > dead_after_minutes:
            state = 'stopped'
        else:
            state = status
        # Alive but getting nowhere. A process wedged inside a socket read
        # still beats and still says `running`; only an operation that blew
        # through its own declared deadline reveals it.
        if state in ALIVE and deadline and decision_ts > deadline:
            state = 'stalled'

        return dict(worker=worker, state=state, last_beat_at=beat_at,
                    age_minutes=None if age is None else round(age, 1),
                    pid=pid, detail=detail, sequence=sequence,
                    activity=activity, deadline=deadline,
                    dead_after_minutes=dead_after_minutes,
                    beat_after_decision_time=ahead or None,
                    note=('a stopped worker and a quiet market look identical '
                          'on every other surface. This is the fact that '
                          'separates them'
                          + ('. This beat was recorded AFTER the time asked '
                             'about, so its age is not a measurement and is '
                             'withheld' if ahead else '')))

    def coverage_at(self, decision_ts: str, *, stale_after_minutes: int | None = None,
                    strict_replay: bool = False
                    ) -> Coverage:
        """Which registered sources were actually reachable.

        This is what makes an empty map readable: `uncovered` names the
        sources that failed or were never fetched, so nobody reads silence as
        calm.
        """
        sources = self.sources_at(decision_ts) if strict_replay else self.sources()
        uncovered = []
        for source in sources:
            health = self.health_at(source.source_id, decision_ts)
            limit = stale_after_minutes or source.poll_interval_minutes * 3
            if health.consecutive_failures:
                uncovered.append(f'{source.source_id}: last acquisition failed: {health.last_error}')
                continue
            if health.last_success_at is None:
                uncovered.append(f'{source.source_id}: never fetched')
                continue
            if health.last_success_at > decision_ts:
                uncovered.append(f'{source.source_id}: no fetch before this decision')
                continue
            age = (datetime.fromisoformat(decision_ts)
                   - datetime.fromisoformat(health.last_success_at))
            if age > timedelta(minutes=limit):
                uncovered.append(
                    f'{source.source_id}: last success {int(age.total_seconds() // 60)}'
                    f'min before, past its {limit}min freshness policy')
        return Coverage(population='registered news sources',
                        covered=len(sources) - len(uncovered), total=len(sources),
                        uncovered=tuple(uncovered),
                        basis=('per-source fetch health at the decision time: '
                               'a source counts as covered when its last '
                               'successful fetch is within THREE TIMES the '
                               'polling interval it declared. This is not '
                               'worker liveness (see worker_state) and not '
                               'editorial or economic coverage of the news '
                               'itself'))

    def apply_retention(self, *, now: "str | None" = None,
                        dry_run: bool = False) -> dict:
        """Enforce each source's declared retention window on stored text.

        `retention_days` was recorded on every source and enforced nowhere,
        so a declared 30-day window meant nothing: the text stayed until
        the file was deleted. This removes the TEXT — the observation's raw
        bytes and the story body — and keeps everything that makes the
        removal auditable: the observation row, its content hash, the
        story's title and URL, and an immutable redaction record saying
        what went and under which policy.

        That split is the whole design. A retention policy that deleted
        rows would also delete the evidence of what the system once said,
        which is the thing an audit most needs and the thing a retention
        rule has no business touching.
        """
        stamp = now or _now()
        cutoffs = {}
        for source in self.sources():
            if source.retention_days:
                cutoffs[source.source_id] = ist_timestamp(
                    datetime.fromisoformat(stamp)
                    - timedelta(days=source.retention_days))
        if not cutoffs:
            return dict(checked_at=stamp, dry_run=dry_run, sources=0,
                        redacted=0, bytes_removed=0, rows=[],
                        note='no source declares a retention window')

        rows, removed_bytes = [], 0
        with self.connect() as db:
            for source_id, cutoff in sorted(cutoffs.items()):
                expired = db.execute(
                    'SELECT o.observation_id,o.reference,o.content_hash,'
                    'o.fetched_at,LENGTH(o.raw) FROM observations o '
                    'LEFT JOIN retention_redactions r '
                    'ON r.observation_id=o.observation_id '
                    'WHERE o.source_id=? AND o.fetched_at<? AND r.redaction_id '
                    'IS NULL AND (o.raw IS NOT NULL OR EXISTS ('
                    'SELECT 1 FROM stories s WHERE s.observation_id='
                    'o.observation_id AND s.body IS NOT NULL))',
                    (source_id, cutoff)).fetchall()
                for observation_id, reference, content_hash, fetched_at, size in expired:
                    rows.append(dict(source_id=source_id,
                                     observation_id=observation_id,
                                     reference=reference, fetched_at=fetched_at,
                                     cutoff=cutoff, bytes=size or 0))
                    removed_bytes += size or 0
                if dry_run or not expired:
                    continue
                ids = [row[0] for row in expired]
                days = next(s.retention_days for s in self.sources()
                            if s.source_id == source_id)
                for observation_id, reference, content_hash, fetched_at, size in expired:
                    db.execute(
                        'INSERT INTO retention_redactions (source_id,'
                        'observation_id,reference,content_hash,fetched_at,'
                        'retention_days,raw_bytes_removed,body_removed,'
                        'redacted_at) VALUES (?,?,?,?,?,?,?,?,?)',
                        (source_id, observation_id, reference, content_hash,
                         fetched_at, days, size or 0, 1, stamp))
                # Both tables are immutable by trigger, and rightly so: this
                # is the ONE operation permitted to change them, it is
                # recorded above before it runs, and the triggers go back on
                # inside the same transaction.
                db.execute('DROP TRIGGER IF EXISTS observations_no_update')
                db.execute('DROP TRIGGER IF EXISTS stories_no_update')
                try:
                    marks = ','.join('?' * len(ids))
                    db.execute(f'UPDATE observations SET raw=NULL WHERE '
                               f'observation_id IN ({marks})', ids)
                    db.execute(f'UPDATE stories SET body=NULL WHERE '
                               f'observation_id IN ({marks})', ids)
                    urls = [r[0] for r in db.execute(
                        f'SELECT DISTINCT url FROM stories WHERE '
                        f'observation_id IN ({marks})', ids).fetchall()]
                    db.execute(
                        f'DELETE FROM documents WHERE source_id=? AND url IN '
                        f'(SELECT url FROM stories WHERE observation_id IN '
                        f'({marks}))', [source_id, *ids])
                    # Without this the enrichment queue would see a story
                    # with no body and no stored document, call it
                    # outstanding, re-fetch it every pass and starve the
                    # documents that have never been retrieved -- the
                    # defect A08 closed, reintroduced by the retention
                    # policy. A retention window is a decision not to hold
                    # the text, not an instruction to keep fetching it.
                    expiry = ist_timestamp(
                        datetime.fromisoformat(stamp) + timedelta(days=3650))
                    for url in urls:
                        db.execute(
                            'INSERT OR REPLACE INTO document_attempts '
                            'VALUES (?,?,?,?,?)',
                            (source_id, url, stamp, expiry, 'retention_expired'))
                finally:
                    db.execute(
                        "CREATE TRIGGER IF NOT EXISTS observations_no_update "
                        "BEFORE UPDATE ON observations BEGIN SELECT "
                        "RAISE(ABORT,'observations are immutable'); END")
                    db.execute(
                        "CREATE TRIGGER IF NOT EXISTS stories_no_update "
                        "BEFORE UPDATE ON stories BEGIN SELECT RAISE(ABORT,"
                        "'stories are immutable; publish a correction'); END")
        return dict(checked_at=stamp, dry_run=dry_run, sources=len(cutoffs),
                    redacted=len(rows), bytes_removed=removed_bytes,
                    rows=rows[:200],
                    note=('text removed; the observation, its content hash, '
                          'the story title/URL and an immutable redaction '
                          'record are kept, so the audit trail survives the '
                          'retention policy'))

    def redactions(self, source_id: "str | None" = None) -> list[dict]:
        sql = ('SELECT source_id,observation_id,reference,content_hash,'
               'fetched_at,retention_days,raw_bytes_removed,redacted_at '
               'FROM retention_redactions')
        args = []
        if source_id:
            sql += ' WHERE source_id=?'
            args.append(source_id)
        with self.connect() as db:
            rows = db.execute(sql + ' ORDER BY redaction_id', args).fetchall()
        return [dict(zip(('source_id', 'observation_id', 'reference',
                          'content_hash', 'fetched_at', 'retention_days',
                          'raw_bytes_removed', 'redacted_at'), r)) for r in rows]

    def source_version_hashes(self, timestamp: "str | None" = None) -> dict:
        """A content hash per source registration, as it stood at `timestamp`.

        A reconstruction is only reproducible if the source definitions it
        ran against are pinned too — the rights flag, the polling interval
        and the notes all shape what was collected and what may be shown.
        """
        sql = 'SELECT source_id,known_at,payload FROM source_versions'
        args = []
        if timestamp:
            sql += ' WHERE known_at<=?'
            args.append(timestamp)
        sql += ' ORDER BY source_id,known_at'
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
        latest = {}
        for source_id, known_at, payload in rows:
            latest[source_id] = dict(
                known_at=known_at,
                payload_hash=hashlib.sha256(payload.encode()).hexdigest()[:16])
        return latest

    def health_at(self, source_id: str, timestamp: str) -> SourceHealth:
        """Reconstruct health from the append-only acquisition log, as known then."""
        with self.connect() as db:
            rows = db.execute('SELECT payload FROM ingest_log WHERE source_id=? AND attempted_at<=? '
                              'ORDER BY attempted_at,rowid_', (source_id,timestamp)).fetchall()
        last_success = last_attempt = error = None
        failures = 0
        for (raw,) in rows:
            report = json.loads(raw)
            last_attempt = report['attempted_at']
            if report['ok']:
                last_success, failures, error = last_attempt, 0, None
            else:
                failures += 1
                error = report.get('error')
        return SourceHealth(source_id,last_attempt,last_success,failures,error)

    def due_sources(self, now: str) -> list[Source]:
        current = datetime.fromisoformat(now)
        return [s for s in self.sources() if (self.health(s.source_id).last_attempt_at is None
            or current - datetime.fromisoformat(self.health(s.source_id).last_attempt_at)
            >= timedelta(minutes=s.poll_interval_minutes))]

    def save_snapshot(self, payload: dict, *, available_at: str, method: str) -> str:
        raw = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
        identity = 'news_' + hashlib.sha256(raw.encode()).hexdigest()
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO news_snapshots VALUES (?,?,?,?)',
                       (identity, available_at, method, raw))
        return identity
