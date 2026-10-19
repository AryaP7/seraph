# Live — the durable runtime store (T07, audit finding R04).
"""One transaction boundary for a decision, and nothing published before it.

**The defect (R04).** The live path held everything in memory. A restart lost
the bar accumulators, the volume baselines, the feature buffers, the filter
state and every decision made since start-up. There was no cursor, so a
restart could not know which inputs it had already consumed, and no record of
what had been published, so a replay could not tell whether a decision was
new or a repeat.

**The shape of the fix.** One SQLite database holds the runtime transaction
boundary. Within a single transaction `commit_decision()`:

1. compares the `runtime_head.version` the caller expected against the stored
   one and aborts on a mismatch, so two writers cannot interleave;
2. inserts the checkpoint reference;
3. inserts the decision;
4. advances the head;
5. inserts the outbox events.

A crash anywhere before `COMMIT` leaves none of it: no decision, no advanced
head, no outbox row. A crash after it leaves all of it, and a replay of the
same `decision_id` returns the stored decision instead of computing a second
one. That is the whole of the crash protocol, and it is why these five steps
are in one transaction rather than five convenient places.

**Delivery is at-least-once and says so.** The outbox carries an
`idempotency_key` for the *receiver* to deduplicate on. Nothing here claims
exactly-once network delivery, because a store and a network cannot jointly
promise it.

**Large checkpoints are content-addressed on disk.** The state blob is
written to a temporary file, fsynced, and atomically renamed into
`checkpoints/<sha>.json` *before* the row referencing it is inserted. So a
reference in the database always points at a complete file; the reverse
ordering would let a committed row name a file that a crash truncated.

**Schema changes are migrations, not start-up DDL.** The same rules C1 already
enforces: filename order, once each, recorded with the SHA of the file that
ran, and a changed file is an error rather than a silent re-run.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable, Sequence

from seraph.shared_types import IST

STORE_VERSION = "live.store/2026-10-17.1"
MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
DEFAULT_STREAM = "live"

#: Delivery backoff. Deliberately small and explicit: an outbox that retries
#: forever at one second is a denial of service against its own receiver.
RETRY_BACKOFF_SECONDS = (5, 30, 120, 600)
MAX_ATTEMPTS = len(RETRY_BACKOFF_SECONDS) + 1


class StoreError(RuntimeError):
    """The store refuses to do this."""


class HeadConflict(StoreError):
    """Another writer advanced the stream; this commit was not applied."""


class MigrationDrift(StoreError):
    """An applied migration's file has changed since it ran."""


#: Payload fields that are OPERATIONAL MEASUREMENT, not the decision.
#:
#: `LiveDecision.describe()` carries both: the decision (score, publishability,
#: which bars, which inputs) and how the run went (how many milliseconds from
#: bar close to decision, when the feed last spoke). The second kind is
#: legitimately different on every execution, so including it in the content
#: hash made R06's conflict detection fire on a LEGITIMATE recomputation --
#: re-deciding the same bar after a restart would raise `DecisionConflict`
#: purely because the stopwatch read differently.
#:
#: Found by `docs/evidence/engineering-audit-2026-10-18/r08_recovery_probe.py`,
#: which showed matching bars and matching decision counts but differing
#: payload hashes across a crash.
#:
#: The full payload is still STORED verbatim -- nothing is discarded. This
#: only decides what "the same decision" means.
OPERATIONAL_PAYLOAD_FIELDS = frozenset({
    "bar_close_to_decision_ms",     # a measured latency
    "feed",                         # includes last_message_at
    "recency",                      # age of the newest observation at decision
})


def decision_identity(payload: dict) -> dict:
    """The part of a decision payload that defines WHICH decision this is."""
    return {k: v for k, v in (payload or {}).items()
            if k not in OPERATIONAL_PAYLOAD_FIELDS}


class DecisionConflict(StoreError):
    """The same decision id is already stored with different content.

    R06: `commit_decision` used to return an existing row as a replay before
    comparing payloads, so a changed decision under a fixed id was silently
    discarded and reported as a successful replay.
    """


class CheckpointUnusable(StoreError):
    """The checkpoint cannot be trusted, so it will not be restored."""


def _now() -> datetime:
    return datetime.now(IST)


def _stamp(moment: datetime | None = None) -> str:
    return (moment or _now()).isoformat()


def digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


@dataclass(frozen=True)
class Head:
    stream_id: str
    checkpoint_id: str | None
    decision_id: str | None
    version: int
    updated_at: str | None

    def describe(self) -> dict:
        return dict(stream_id=self.stream_id, checkpoint_id=self.checkpoint_id,
                    decision_id=self.decision_id, version=self.version,
                    updated_at=self.updated_at)


@dataclass(frozen=True)
class OutboxEvent:
    outbox_id: str
    event_kind: str
    aggregate_id: str
    idempotency_key: str
    payload: dict
    attempts: int = 0
    created_at: str | None = None
    next_attempt_at: str | None = None
    last_error: str | None = None

    def describe(self) -> dict:
        return dict(outbox_id=self.outbox_id, event_kind=self.event_kind,
                    aggregate_id=self.aggregate_id,
                    idempotency_key=self.idempotency_key,
                    attempts=self.attempts, created_at=self.created_at,
                    next_attempt_at=self.next_attempt_at,
                    last_error=self.last_error)


class LiveStore:
    """The runtime's durable state. One database, one transaction boundary."""

    def __init__(self, path, *, stream_id: str = DEFAULT_STREAM,
                 migrations_dir: Path | None = None) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.stream_id = stream_id
        self.blobs = self.path.parent / f"{self.path.stem}_checkpoints"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.migrations_dir = Path(migrations_dir or MIGRATIONS_DIR)
        self.migrate()

    # ------------------------------------------------------------ plumbing

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30,
                             isolation_level="IMMEDIATE")
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        # A runtime whose durability claim is the point does not get to trade
        # it for speed: FULL means a committed decision survives the crash
        # that happens one instruction later.
        db.execute("PRAGMA synchronous=FULL")
        try:
            with db:
                yield db
        finally:
            db.close()

    def migrate(self) -> list[str]:
        """Apply pending migrations in filename order. Drift is an error."""
        applied: list[str] = []
        with self.connect() as db:
            db.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT PRIMARY KEY, content_sha TEXT NOT NULL,
                    applied_at TEXT NOT NULL)""")
            done = {r["name"]: r["content_sha"] for r in
                    db.execute("SELECT name, content_sha FROM schema_migrations")}
            for path in sorted(self.migrations_dir.glob("*.sql")):
                sql = path.read_text(encoding="utf-8")
                sha = hashlib.sha256(sql.encode()).hexdigest()
                if path.name in done:
                    if done[path.name] != sha:
                        raise MigrationDrift(
                            f"{path.name} was applied with content "
                            f"{done[path.name][:12]} and the file now hashes to "
                            f"{sha[:12]}; nobody knows what this database "
                            f"contains. Add a new migration instead of editing "
                            f"one that has run")
                    continue
                db.executescript(sql)
                db.execute("INSERT INTO schema_migrations(name, content_sha, "
                           "applied_at) VALUES (?,?,?)",
                           (path.name, sha, _stamp()))
                applied.append(path.name)
        return applied

    # -------------------------------------------------------------- inputs

    def record_input_batch(self, *, batch_id: str, source_id: str,
                           payload: dict, received_at: str | None = None,
                           quality: dict | None = None,
                           payload_ref: str | None = None) -> str:
        """Append an input batch. Re-recording the same batch is a no-op.

        Idempotent on `batch_id`, because a reconnecting feed replaying its
        buffer must not double-count an observation.
        """
        payload_hash = digest(payload)
        with self.connect() as db:
            existing = db.execute(
                "SELECT payload_hash FROM input_batches WHERE batch_id=?",
                (batch_id,)).fetchone()
            if existing is not None:
                if existing["payload_hash"] != payload_hash:
                    raise StoreError(
                        f"batch {batch_id} was already recorded with different "
                        f"content; a batch id identifies its payload")
                return payload_hash
            db.execute(
                "INSERT INTO input_batches(batch_id, source_id, received_at, "
                "payload_hash, payload_ref, quality_json) VALUES (?,?,?,?,?,?)",
                (batch_id, source_id, received_at or _stamp(), payload_hash,
                 payload_ref, json.dumps(quality or {}, sort_keys=True)))
        return payload_hash

    def record_closed_bar(self, bar, *, input_batch_id: str | None = None,
                          revision: int = 0) -> bool:
        """Persist a finalized bar. Returns whether it was newly written.

        A finalized window never reopens, so re-writing the same
        `(symbol, session, end, revision)` with different content is refused
        rather than silently accepted: a *corrected* bar is a new revision,
        which is what the revision column is for.
        """
        payload = bar.describe() if hasattr(bar, "describe") else dict(bar)
        session_id = payload.get("session_id") or payload["end"][:10]
        key = (payload["symbol"], session_id, payload["end"], revision)
        body = json.dumps(payload, sort_keys=True)
        with self.connect() as db:
            row = db.execute(
                "SELECT payload_json FROM closed_bars WHERE symbol=? AND "
                "session_id=? AND bar_end=? AND revision=?", key).fetchone()
            if row is not None:
                if row["payload_json"] != body:
                    raise StoreError(
                        f"{payload['symbol']} {payload['end']} revision "
                        f"{revision} is already stored with different content; "
                        f"a finalized bar does not change — record a new "
                        f"revision instead")
                return False
            db.execute(
                "INSERT INTO closed_bars(symbol, session_id, bar_end, revision,"
                " input_batch_id, payload_json, recorded_at) "
                "VALUES (?,?,?,?,?,?,?)", (*key, input_batch_id, body, _stamp()))
        return True

    def bars_for(self, session_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT payload_json FROM closed_bars WHERE session_id=? "
                "ORDER BY bar_end, symbol, revision", (session_id,)).fetchall()
        return [json.loads(r["payload_json"]) for r in rows]

    # --------------------------------------------------------- deployments

    def register_deployment(self, bundle) -> None:
        described = bundle.describe() if hasattr(bundle, "describe") else dict(bundle)
        manifest_hash = described.get("manifest_hash") or digest(described)
        with self.connect() as db:
            row = db.execute(
                "SELECT manifest_hash FROM deployments WHERE bundle_id=?",
                (described["bundle_id"],)).fetchone()
            if row is not None:
                if row["manifest_hash"] != manifest_hash:
                    raise StoreError(
                        f"bundle {described['bundle_id']} is already registered "
                        f"with a different manifest; a bundle id is immutable")
                return
            db.execute(
                "INSERT INTO deployments(bundle_id, producer, trained_through, "
                "available_at, manifest_json, manifest_hash) VALUES (?,?,?,?,?,?)",
                (described["bundle_id"], described["producer"],
                 described["trained_through"], described["available_at"],
                 json.dumps(described, sort_keys=True), manifest_hash))

    def deployments(self) -> list[dict]:
        with self.connect() as db:
            rows = db.execute("SELECT manifest_json FROM deployments "
                              "ORDER BY bundle_id").fetchall()
        return [json.loads(r["manifest_json"]) for r in rows]

    # --------------------------------------------------------- checkpoints

    def write_checkpoint_blob(self, state: dict) -> tuple[str, str]:
        """Content-address the state on disk. Returns `(ref, sha)`.

        Written to a temp file, fsynced and atomically renamed *before* any
        row references it, so a committed reference always names a complete
        file.
        """
        body = json.dumps(state, sort_keys=True, default=str).encode()
        sha = hashlib.sha256(body).hexdigest()
        target = self.blobs / f"{sha}.json"
        if not target.exists():
            fd, tmp = tempfile.mkstemp(dir=self.blobs, suffix=".part")
            try:
                with os.fdopen(fd, "wb") as handle:
                    handle.write(body)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, target)
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        return (f"{target.name}", sha)

    def read_checkpoint_blob(self, ref: str, expected_sha: str) -> dict:
        path = self.blobs / ref
        if not path.exists():
            raise CheckpointUnusable(
                f"checkpoint blob {ref} is referenced but missing; rebuild by "
                f"warm start rather than resuming from nothing")
        body = path.read_bytes()
        actual = hashlib.sha256(body).hexdigest()
        if actual != expected_sha:
            raise CheckpointUnusable(
                f"checkpoint blob {ref} hashes to {actual[:12]} and the record "
                f"says {expected_sha[:12]}; the state is corrupt and will not "
                f"be deserialized")
        return json.loads(body)

    def load_checkpoint(self, checkpoint_id: str, *,
                        pipeline_version: str | None = None) -> dict:
        """Fetch and validate a checkpoint. Refuses rather than guesses."""
        with self.connect() as db:
            row = db.execute(
                "SELECT * FROM inference_checkpoints WHERE checkpoint_id=?",
                (checkpoint_id,)).fetchone()
        if row is None:
            raise CheckpointUnusable(f"no checkpoint {checkpoint_id}")
        if pipeline_version and row["pipeline_version"] != pipeline_version:
            raise CheckpointUnusable(
                f"checkpoint {checkpoint_id} was written by "
                f"{row['pipeline_version']} and this build is "
                f"{pipeline_version}; rebuild by warm start rather than "
                f"resuming across a version change")
        state = self.read_checkpoint_blob(row["state_ref"], row["state_hash"])
        return dict(checkpoint_id=checkpoint_id,
                    pipeline_version=row["pipeline_version"],
                    bundle_id=row["bundle_id"],
                    last_decision_id=row["last_decision_id"],
                    input_cursor=json.loads(row["input_cursor_json"]),
                    state=state, state_hash=row["state_hash"],
                    created_at=row["created_at"])

    # ---------------------------------------------------------------- head

    def head(self) -> Head:
        with self.connect() as db:
            row = db.execute("SELECT * FROM runtime_head WHERE stream_id=?",
                             (self.stream_id,)).fetchone()
        if row is None:
            return Head(self.stream_id, None, None, 0, None)
        return Head(row["stream_id"], row["checkpoint_id"], row["decision_id"],
                    int(row["version"]), row["updated_at"])

    # ------------------------------------------------------------- commit

    def commit_decision(self, *, decision_id: str, as_of: str,
                        computed_at: str, payload: dict,
                        publication_state: str, state: dict,
                        expected_version: int | None = None,
                        input_cursor: dict | None = None,
                        input_hash: str | None = None,
                        bundle_id: str | None = None,
                        pipeline_version: str = STORE_VERSION,
                        at: datetime | None = None,
                        events: "Sequence[dict]" = ()) -> dict:
        """The one transaction. Everything, or nothing.

        A repeat of a `decision_id` already stored **with the same content**
        returns that decision without writing: after a crash between commit
        and acknowledgement, replay must return the same logical decision
        rather than a second one.

        R06: that check used to be `decision_id` alone, so the SAME id
        carrying DIFFERENT bytes was silently reported as a replay and the
        new content was thrown away. Idempotency is a property of content,
        not of a name. Same id and same bytes is a replay; same id and
        different bytes is a conflict, and the caller is told which.
        """
        # The payload hash is computed first, because it decides whether this
        # is a replay at all and nothing should be written to find that out.
        # It covers the DECISION, not the stopwatch -- see `decision_identity`.
        payload_body = json.dumps(payload, sort_keys=True, default=str)
        payload_hash = hashlib.sha256(
            json.dumps(decision_identity(payload), sort_keys=True,
                       default=str).encode()).hexdigest()

        existing = self.decision(decision_id)
        if existing is not None:
            if existing.get("payload_hash") == payload_hash:
                return dict(existing, replayed=True)
            raise DecisionConflict(
                f"decision {decision_id} is already stored with payload hash "
                f"{existing.get('payload_hash', '')[:16]} and this writer has "
                f"{payload_hash[:16]}. A decision id is immutable: the same "
                f"id with different content is a conflict, not a replay. "
                f"Either the id is being reused across streams or modes "
                f"(it carries both -- see engine_adapter.decision_id), or an "
                f"input changed under a fixed identity.")

        # The blob lands before the transaction opens, so the reference the
        # transaction inserts is already backed by a complete file.
        state_ref, state_hash = self.write_checkpoint_blob(state)
        checkpoint_id = f"ck:{state_hash[:24]}"
        # Injectable, like every other clock in this codebase: a test that
        # cannot control when a pass happened cannot test staleness.
        stamp = _stamp(at)

        with self.connect() as db:
            row = db.execute("SELECT version FROM runtime_head WHERE stream_id=?",
                             (self.stream_id,)).fetchone()
            current = int(row["version"]) if row else 0
            if expected_version is not None and expected_version != current:
                raise HeadConflict(
                    f"stream {self.stream_id} is at version {current} and this "
                    f"writer expected {expected_version}; the decision was NOT "
                    f"applied")

            db.execute(
                "INSERT OR IGNORE INTO inference_checkpoints(checkpoint_id, "
                "pipeline_version, bundle_id, last_decision_id, "
                "input_cursor_json, state_ref, state_hash, created_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (checkpoint_id, pipeline_version, bundle_id, decision_id,
                 json.dumps(input_cursor or {}, sort_keys=True), state_ref,
                 state_hash, stamp))
            db.execute(
                "INSERT INTO live_decisions(decision_id, as_of, computed_at, "
                "input_hash, checkpoint_id, payload_json, payload_hash, "
                "publication_state, stream_id) VALUES (?,?,?,?,?,?,?,?,?)",
                (decision_id, as_of, computed_at,
                 input_hash or payload_hash, checkpoint_id, payload_body,
                 payload_hash, publication_state, self.stream_id))
            db.execute(
                "INSERT INTO runtime_head(stream_id, checkpoint_id, decision_id,"
                " version, updated_at) VALUES (?,?,?,?,?) "
                "ON CONFLICT(stream_id) DO UPDATE SET checkpoint_id=excluded."
                "checkpoint_id, decision_id=excluded.decision_id, "
                "version=excluded.version, updated_at=excluded.updated_at",
                (self.stream_id, checkpoint_id, decision_id, current + 1, stamp))
            for i, event in enumerate(events):
                key = event.get("idempotency_key") or f"{decision_id}#{i}"
                db.execute(
                    "INSERT OR IGNORE INTO outbox(outbox_id, event_kind, "
                    "aggregate_id, idempotency_key, payload_json, created_at, "
                    "attempts, next_attempt_at, stream_id) "
                    "VALUES (?,?,?,?,?,?,0,?,?)",
                    (f"ob:{decision_id}:{i}", event["event_kind"],
                     event.get("aggregate_id", decision_id), key,
                     json.dumps(event.get("payload", {}), sort_keys=True,
                                default=str), stamp, stamp, self.stream_id))
        return dict(decision_id=decision_id, checkpoint_id=checkpoint_id,
                    version=current + 1, payload_hash=payload_hash,
                    replayed=False)

    # ----------------------------------------------------------- decisions

    def decision(self, decision_id: str) -> dict | None:
        with self.connect() as db:
            row = db.execute("SELECT * FROM live_decisions WHERE decision_id=?",
                             (decision_id,)).fetchone()
        if row is None:
            return None
        return _decision_row(row)

    def latest_decision(self, *, publishable_only: bool = False) -> dict | None:
        """The most recent decision ON THIS STREAM.

        R06: this used to query every row in the database and order by
        `as_of`, while `head()` beside it was stream-scoped. So a replay
        stream's decision -- or a demo's -- could be returned as the current
        live reading, which is the one substitution this codebase's whole
        mode discipline exists to prevent.
        """
        sql = "SELECT * FROM live_decisions WHERE stream_id=?"
        args: list = [self.stream_id]
        if publishable_only:
            sql += " AND publication_state='current'"
        sql += " ORDER BY as_of DESC, computed_at DESC LIMIT 1"
        with self.connect() as db:
            row = db.execute(sql, args).fetchone()
        return _decision_row(row) if row else None

    def decisions(self, *, limit: int = 50, since: str | None = None
                  ) -> list[dict]:
        """This stream's decisions, newest first (R06)."""
        sql = "SELECT * FROM live_decisions WHERE stream_id=?"
        args: list = [self.stream_id]
        if since:
            sql += " AND as_of > ?"
            args.append(since)
        sql += " ORDER BY as_of DESC LIMIT ?"
        args.append(limit)
        with self.connect() as db:
            rows = db.execute(sql, args).fetchall()
        return [_decision_row(r) for r in rows]

    # -------------------------------------------------------------- outbox

    def pending_events(self, *, at: datetime | None = None,
                       limit: int = 50) -> list[OutboxEvent]:
        """Undelivered events FOR THIS STREAM (R06).

        A delivery worker reading every stream's events would let a replay
        or a demo emit a production alert -- O04's first requirement is that
        this cannot happen, and it starts here.
        """
        moment = _stamp(at)
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM outbox WHERE stream_id=? AND "
                "delivered_at IS NULL AND "
                "attempts < ? AND (next_attempt_at IS NULL OR "
                "next_attempt_at <= ?) ORDER BY created_at LIMIT ?",
                (self.stream_id, MAX_ATTEMPTS, moment, limit)).fetchall()
        return [OutboxEvent(
            outbox_id=r["outbox_id"], event_kind=r["event_kind"],
            aggregate_id=r["aggregate_id"],
            idempotency_key=r["idempotency_key"],
            payload=json.loads(r["payload_json"]), attempts=int(r["attempts"]),
            created_at=r["created_at"], next_attempt_at=r["next_attempt_at"],
            last_error=r["last_error"]) for r in rows]

    def mark_delivered(self, outbox_id: str, *, at: datetime | None = None
                       ) -> None:
        with self.connect() as db:
            db.execute(
                "UPDATE outbox SET delivered_at=?, attempts=attempts+1, "
                "next_attempt_at=NULL WHERE outbox_id=? AND delivered_at IS NULL",
                (_stamp(at), outbox_id))

    def mark_failed(self, outbox_id: str, error: str, *,
                    at: datetime | None = None) -> dict:
        """Record a delivery failure and schedule the next attempt.

        Attempts are bounded. An event that exhausts them stays undelivered
        and visible in `dead_letters()` rather than retrying forever or being
        quietly dropped.
        """
        moment = at or _now()
        with self.connect() as db:
            row = db.execute("SELECT attempts FROM outbox WHERE outbox_id=?",
                             (outbox_id,)).fetchone()
            if row is None:
                raise StoreError(f"no outbox event {outbox_id}")
            attempts = int(row["attempts"]) + 1
            if attempts >= MAX_ATTEMPTS:
                nxt = None
            else:
                delay = RETRY_BACKOFF_SECONDS[min(attempts - 1,
                                                  len(RETRY_BACKOFF_SECONDS) - 1)]
                nxt = _stamp(moment + timedelta(seconds=delay))
            db.execute(
                "UPDATE outbox SET attempts=?, next_attempt_at=?, last_error=? "
                "WHERE outbox_id=?", (attempts, nxt, error[:500], outbox_id))
        return dict(outbox_id=outbox_id, attempts=attempts,
                    next_attempt_at=nxt, exhausted=attempts >= MAX_ATTEMPTS)

    def dead_letters(self) -> list[OutboxEvent]:
        with self.connect() as db:
            rows = db.execute(
                "SELECT * FROM outbox WHERE delivered_at IS NULL AND attempts>=?",
                (MAX_ATTEMPTS,)).fetchall()
        return [OutboxEvent(
            outbox_id=r["outbox_id"], event_kind=r["event_kind"],
            aggregate_id=r["aggregate_id"],
            idempotency_key=r["idempotency_key"],
            payload=json.loads(r["payload_json"]), attempts=int(r["attempts"]),
            created_at=r["created_at"], next_attempt_at=r["next_attempt_at"],
            last_error=r["last_error"]) for r in rows]

    # -------------------------------------------------------------- status

    def describe(self) -> dict:
        """What `--status` reports. Reads only; connects to nothing external."""
        with self.connect() as db:
            counts = {
                table: db.execute(f"SELECT count(*) AS n FROM {table}"
                                  ).fetchone()["n"]
                for table in ("input_batches", "closed_bars", "deployments",
                              "inference_checkpoints", "live_decisions",
                              "outbox")}
            undelivered = db.execute(
                "SELECT count(*) AS n FROM outbox WHERE delivered_at IS NULL"
            ).fetchone()["n"]
        head = self.head()
        latest = self.latest_decision()
        return dict(version=STORE_VERSION, path=str(self.path),
                    stream=head.describe(), counts=counts,
                    undelivered_events=undelivered,
                    dead_letters=len(self.dead_letters()),
                    latest_decision=(dict(decision_id=latest["decision_id"],
                                          as_of=latest["as_of"],
                                          publication_state=latest["publication_state"])
                                     if latest else None))


def _decision_row(row) -> dict:
    keys = row.keys()
    return dict(decision_id=row["decision_id"], as_of=row["as_of"],
                computed_at=row["computed_at"], input_hash=row["input_hash"],
                checkpoint_id=row["checkpoint_id"],
                payload=json.loads(row["payload_json"]),
                payload_hash=row["payload_hash"],
                publication_state=row["publication_state"],
                # Which stream this decision belongs to (R06). Read
                # defensively so a row from a database that predates
                # migration 002 still renders rather than raising.
                stream_id=(row["stream_id"] if "stream_id" in keys
                           else DEFAULT_STREAM))
