-- 001 — evaluation identity for E13 validation_results (FIX06; audit finding A06)
--
-- THE DEFECT
-- The key was (pillar_subset, reconciliation_mode, xi_mode, epoch). Three
-- things collide under it:
--
--   1. Table A and Table B. FR35's Table B includes RMT/Hamilton subsets, and
--      under ARCHITECTURE D5(b) it runs over all six epochs — so a Table B row
--      for ('rmt+hamilton', 'kalman', 'hamilton', 'covid_2020') has exactly the
--      same key as the Table A row for the same configuration. One silently
--      overwrites the other, and which survives depends on insert order.
--   2. Repeated experiments. Re-running an evaluation overwrites the previous
--      result in place, so the earlier evidence is simply gone.
--   3. Different pre-registered designs. The design hash was stored but not
--      keyed on, so results from two designs mix in one table.
--
-- THE CHANGE
-- Add `evaluation_run_id` and widen the key to include it, `table_id` and
-- `pre_registration_hash`. Existing rows are PRESERVED and migrated into a
-- named legacy evaluation run rather than dropped — the point of the fix is
-- that evidence stops being overwritten, so the migration must not overwrite
-- any either.
--
-- Idempotent: safe to apply repeatedly.

BEGIN;

CREATE TABLE IF NOT EXISTS evaluation_runs (
    evaluation_run_id      text        PRIMARY KEY,
    pre_registration_hash  text        NOT NULL,
    design_label           text        NOT NULL,
    table_b_scope          text        NOT NULL,   -- 'two_epoch' | 'six_epoch' | 'legacy_unknown'
    started_at             timestamptz NOT NULL DEFAULT now(),
    code_version           text,
    note                   text
);

INSERT INTO evaluation_runs (evaluation_run_id, pre_registration_hash,
                             design_label, table_b_scope, note)
VALUES ('legacy_pre_migration', 'unknown',
        'rows written before the evaluation-identity migration',
        'legacy_unknown',
        'the design these rows were produced under was not recorded; they are '
        'preserved as evidence and must not be compared with later runs')
ON CONFLICT (evaluation_run_id) DO NOTHING;

ALTER TABLE validation_results
    ADD COLUMN IF NOT EXISTS evaluation_run_id text
        NOT NULL DEFAULT 'legacy_pre_migration'
        REFERENCES evaluation_runs(evaluation_run_id);

-- Rebuild the primary key only when it is still the narrow one.
DO $$
DECLARE
    key_columns text;
BEGIN
    SELECT string_agg(a.attname, ',' ORDER BY k.ord)
      INTO key_columns
      FROM pg_constraint c
      JOIN LATERAL unnest(c.conkey) WITH ORDINALITY AS k(attnum, ord) ON true
      JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = k.attnum
     WHERE c.conrelid = 'validation_results'::regclass AND c.contype = 'p';

    IF key_columns IS NOT NULL AND position('evaluation_run_id' in key_columns) = 0 THEN
        EXECUTE 'ALTER TABLE validation_results DROP CONSTRAINT '
             || (SELECT conname FROM pg_constraint
                  WHERE conrelid = 'validation_results'::regclass AND contype = 'p');
        ALTER TABLE validation_results
            ADD PRIMARY KEY (evaluation_run_id, table_id, pillar_subset,
                             reconciliation_mode, xi_mode, epoch);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS validation_results_by_design
    ON validation_results (pre_registration_hash, table_id);

COMMIT;
