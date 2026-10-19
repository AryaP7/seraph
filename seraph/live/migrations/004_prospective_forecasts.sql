-- 004 — the prospective forecast ledger (T03/T04, audit R12)
--
-- The historical experiment already produces 75,054 forecast rows with their
-- realised labels. That is a RETROSPECTIVE artefact: every row knows its own
-- outcome because the outcome had already happened when the file was written.
--
-- A prospective record is a different object and cannot be a copy of that
-- shape. A forecast made for date D over a 15-session horizon has no label
-- until D+15 sessions have elapsed. If the ledger carried a label column
-- that the writer could fill at issue time, the first mistake anyone makes
-- is to backfill it from the same features the forecast was made from, and
-- the evaluation silently becomes in-sample.
--
-- So the outcome lives in its own columns, written by a SEPARATE later
-- operation, and the table records what the forecast could not know:
--
--   issued_at           when this installation emitted the forecast
--   as_of               the information cutoff it was entitled to use
--   matures_after       the earliest date an outcome may be attached
--   outcome / outcome_at   NULL until maturity, then written once
--
-- `matures_after` is stored rather than derived so that changing the
-- horizon constant later cannot retroactively mature an existing row.
--
-- Identity is `(target, model, as_of, artefact_id)`. A re-run of the same
-- model over the same cutoff is the same forecast, so an incremental job
-- that fires twice writes once. `artefact_id` is in the key because a
-- different fitted model over the same cutoff is a genuinely different
-- forecast and both deserve to exist.

CREATE TABLE IF NOT EXISTS prospective_forecasts (
    target         TEXT NOT NULL,
    model          TEXT NOT NULL,
    as_of          TEXT NOT NULL,
    artefact_id    TEXT NOT NULL,
    issued_at      TEXT NOT NULL,
    horizon        INTEGER NOT NULL,
    matures_after  TEXT NOT NULL,
    probability    REAL,
    threshold      REAL,
    alarm          INTEGER,
    fit_status     TEXT NOT NULL,
    inputs_hash    TEXT NOT NULL DEFAULT '',
    detail_json    TEXT NOT NULL DEFAULT '{}',
    -- Written later, by `attach_outcome`, never at issue time.
    outcome        REAL,
    outcome_at     TEXT,
    PRIMARY KEY (target, model, as_of, artefact_id)
);

CREATE INDEX IF NOT EXISTS prospective_forecasts_by_as_of
    ON prospective_forecasts(as_of DESC, target, model);

-- Pending maturity is the query an operator actually runs.
CREATE INDEX IF NOT EXISTS prospective_forecasts_pending
    ON prospective_forecasts(matures_after)
    WHERE outcome IS NULL;

-- A forecast is a record of what was predicted BEFORE the outcome was known.
-- Editing the prediction after the fact destroys the only evidence that it
-- was made in advance, which is the entire value of a prospective ledger.
-- The outcome columns are the one permitted later write, so the trigger
-- allows a row whose prediction fields are unchanged and whose outcome goes
-- from NULL to a value, and refuses everything else -- including rewriting
-- an outcome once attached.
CREATE TRIGGER IF NOT EXISTS prospective_forecasts_prediction_is_final
    BEFORE UPDATE ON prospective_forecasts
    WHEN OLD.probability IS NOT NEW.probability
      OR OLD.threshold   IS NOT NEW.threshold
      OR OLD.alarm       IS NOT NEW.alarm
      OR OLD.fit_status  IS NOT NEW.fit_status
      OR OLD.issued_at   IS NOT NEW.issued_at
      OR OLD.horizon     IS NOT NEW.horizon
      OR OLD.matures_after IS NOT NEW.matures_after
      OR OLD.inputs_hash IS NOT NEW.inputs_hash
      OR OLD.outcome IS NOT NULL
    BEGIN SELECT RAISE(ABORT,'a prospective forecast is final once issued; only its outcome may be attached, once, after maturity'); END;

CREATE TRIGGER IF NOT EXISTS prospective_forecasts_no_delete
    BEFORE DELETE ON prospective_forecasts
    BEGIN SELECT RAISE(ABORT,'a prospective forecast cannot be deleted; a withdrawn forecast is still evidence of what was predicted'); END;
