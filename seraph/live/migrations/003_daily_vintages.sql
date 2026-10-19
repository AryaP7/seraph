-- 003 — persisted daily pillar vintages (T03 / audit R01, R12)
--
-- `engine_adapter.NullProducers` says why it exists, and it is right: "a live
-- Hawkes estimate needs the warm-started count window from the durable store,
-- and RMT/Hamilton are daily products read from the store, not derived from a
-- five-minute bar." That store is this table.
--
-- The shape is `Vintage`'s, deliberately, because the whole point is that a
-- producer reads a row and hands back a `Vintage` without reinterpreting it:
--
--   producer                which pillar
--   input_end               the last observation the estimate consumed
--   emission_available_at   when SERAPH could first read it
--   value / variance        the sub-score, or NULL with a declared absence
--   absence/absence_reason  NEVER inferred; structural drops the pillar from
--                           the D2 mask and transient does not
--   bundle_id               which model produced it
--   origin                  how it was obtained -- see below
--
-- `origin` is the honesty column. Three values are legitimate and they must
-- not be conflated on screen:
--
--   'computed'   this installation ran the estimator on corpus data at
--                `computed_at`. RMT and Hamilton reach this from the daily
--                EOD2 corpus.
--   'archived'   read from a prior research artefact rather than recomputed
--                here. Carries its own as-of and is a real measurement, but
--                of an earlier run, not of today.
--   'absent'     no estimate. The absence kind says whether that is
--                structural (no estimator/coverage at all) or transient.
--
-- Hawkes is the case that forces this distinction to exist: its FRESH
-- computation needs 5-minute intraday bars, `intraday_bars` is empty, and
-- filling it needs a paid Kite subscription and a daily interactive login.
-- So Hawkes is either 'archived' from the persisted research snapshot or
-- 'absent' -- and a screen that showed an archived 2026-08 Hawkes value as a
-- current reading would be exactly the substitution this project's mode
-- discipline exists to prevent.
--
-- One row per (producer, input_end, bundle_id): a re-run of the same estimator
-- over the same window is the same vintage, so the daily job is idempotent.
-- A genuinely new emission has a later `input_end`.

CREATE TABLE IF NOT EXISTS daily_vintages (
    producer              TEXT NOT NULL,
    input_end             TEXT NOT NULL,
    bundle_id             TEXT NOT NULL DEFAULT '',
    emission_available_at TEXT NOT NULL,
    value                 REAL,
    variance              REAL,
    absence               TEXT,
    absence_reason        TEXT,
    quality               TEXT NOT NULL DEFAULT 'ok',
    coverage              REAL,
    origin                TEXT NOT NULL,
    computed_at           TEXT NOT NULL,
    detail_json           TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (producer, input_end, bundle_id)
);

-- The producer's read is "the newest usable vintage for this pillar at or
-- before a cutoff", which is this index exactly.
CREATE INDEX IF NOT EXISTS daily_vintages_by_producer
    ON daily_vintages(producer, input_end DESC);

-- A vintage is a record of what an estimator said at a moment. Correcting it
-- in place would destroy the only evidence of what the system actually read,
-- which is the same reason `scenario_assumptions` and `case_events` are
-- append-only. A revision is a new row with a later `emission_available_at`.
CREATE TRIGGER IF NOT EXISTS daily_vintages_no_update
    BEFORE UPDATE ON daily_vintages
    BEGIN SELECT RAISE(ABORT,'a daily vintage is a record of what an estimator said; add a revision rather than editing it'); END;
