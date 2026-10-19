-- T07 / audit finding R04: the runtime transaction boundary.
--
-- One database, one transaction per decision. The head row is the
-- concurrency control: a writer states the version it expected to find, and
-- a mismatch aborts the whole commit rather than interleaving two writers'
-- decisions. A crash before COMMIT leaves no published decision at all.

CREATE TABLE IF NOT EXISTS input_batches (
    batch_id     TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    received_at  TEXT NOT NULL,
    payload_hash TEXT NOT NULL,
    payload_ref  TEXT,
    quality_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS closed_bars (
    symbol          TEXT NOT NULL,
    session_id      TEXT NOT NULL,
    bar_end         TEXT NOT NULL,
    revision        INTEGER NOT NULL DEFAULT 0,
    input_batch_id  TEXT,
    payload_json    TEXT NOT NULL,
    recorded_at     TEXT NOT NULL,
    PRIMARY KEY (symbol, session_id, bar_end, revision)
);

CREATE TABLE IF NOT EXISTS deployments (
    bundle_id      TEXT PRIMARY KEY,
    producer       TEXT NOT NULL,
    trained_through TEXT NOT NULL,
    available_at   TEXT NOT NULL,
    manifest_json  TEXT NOT NULL DEFAULT '{}',
    manifest_hash  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS inference_checkpoints (
    checkpoint_id    TEXT PRIMARY KEY,
    pipeline_version TEXT NOT NULL,
    bundle_id        TEXT,
    last_decision_id TEXT,
    input_cursor_json TEXT NOT NULL DEFAULT '{}',
    state_ref        TEXT NOT NULL,
    state_hash       TEXT NOT NULL,
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS live_decisions (
    decision_id       TEXT PRIMARY KEY,
    as_of             TEXT NOT NULL,
    computed_at       TEXT NOT NULL,
    input_hash        TEXT NOT NULL,
    checkpoint_id     TEXT,
    payload_json      TEXT NOT NULL,
    payload_hash      TEXT NOT NULL,
    publication_state TEXT NOT NULL,
    FOREIGN KEY (checkpoint_id) REFERENCES inference_checkpoints(checkpoint_id)
);

CREATE INDEX IF NOT EXISTS live_decisions_by_as_of
    ON live_decisions(as_of DESC);

CREATE TABLE IF NOT EXISTS runtime_head (
    stream_id     TEXT PRIMARY KEY,
    checkpoint_id TEXT,
    decision_id   TEXT,
    version       INTEGER NOT NULL DEFAULT 0,
    updated_at    TEXT NOT NULL
);

-- At-least-once delivery. `idempotency_key` is what the RECEIVER deduplicates
-- on; this side never claims exactly-once, because it cannot.
CREATE TABLE IF NOT EXISTS outbox (
    outbox_id       TEXT PRIMARY KEY,
    event_kind      TEXT NOT NULL,
    aggregate_id    TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    payload_json    TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    delivered_at    TEXT,
    attempts        INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    last_error      TEXT
);

CREATE INDEX IF NOT EXISTS outbox_undelivered
    ON outbox(delivered_at, next_attempt_at);
