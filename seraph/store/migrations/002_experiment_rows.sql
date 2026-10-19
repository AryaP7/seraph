-- 002 — let validation_results hold what the FR35 runner actually measures (T10)
--
-- THE DEFECT
-- DR-05 chose Reading 1 on 2026-10-16 and its step 3 added Table C: the
-- six-epoch RMT/Hamilton run, "with its own table_id". That landed in
-- configuration_list(), which emits `table: "C"` under the two_epoch scope and
-- is the DEFAULT. It did not land here. validation_results still declares
--
--     table_id text NOT NULL CHECK (table_id IN ('A', 'B'))
--
-- so six of the twenty-six configurations the committed design asks for cannot
-- be archived at all. FR38 requires every ablation result to be archived for
-- retrospective analysis; a run would compute Table C and then fail to insert
-- it, or worse, be written to drop it silently.
--
-- Second, every metric column is NOT NULL. An ablation cell legitimately has
-- no measurement -- a fold with one label class, a subset whose pillar has no
-- coverage in that epoch, a calibration that did not converge -- and under
-- NOT NULL the only way to store such a row is to invent a number for it.
-- 0.5 is the number people invent. That is precisely the fabrication the
-- runner's explicit unavailable rows exist to prevent, and the schema was
-- quietly requiring it.
--
-- THE CHANGE
--   * widen the table_id CHECK to ('A', 'B', 'C');
--   * make the three metric columns nullable;
--   * add `availability` with the reason, so an empty cell says WHY it is
--     empty rather than being indistinguishable from an unfinished run;
--   * add the provenance a reader needs to compare two rows honestly:
--     declared_folds (which differs by table), the training epochs the
--     artefact was fitted on, and the optimiser budget the design declared.
--
-- A CHECK keeps the two states whole: a measured row has an AUC, an
-- unavailable row has a reason. A half-filled row of either kind cannot be
-- inserted, so "measured" always means a number is present.
--
-- Existing rows predate the runner and are all measurements, so they migrate
-- to availability='measured'. Nothing is dropped or relabelled.
--
-- Idempotent: safe to apply repeatedly.
--
-- NOTE ON SCOPE: this widens what can be ARCHIVED (FR38). It does not widen
-- what can be PUBLISHED: shared_types.EvaluationRow still declares
-- `table: Literal["A", "B"]`, so a Table C row has no published shape. That
-- edit is gated on the owner (CLAUDE.md: shared_types is ask-before-edit,
-- since all twelve components import from it) and is deliberately not made
-- here. The runner reports such rows as unpublishable rather than dropping
-- them.

BEGIN;

-- Widen the table_id domain. The constraint name is generated, so find it
-- rather than assuming; re-adding an identical constraint would error.
DO $$
DECLARE
    constraint_name text;
BEGIN
    SELECT c.conname
      INTO constraint_name
      FROM pg_constraint c
     WHERE c.conrelid = 'validation_results'::regclass
       AND c.contype = 'c'
       AND pg_get_constraintdef(c.oid) LIKE '%table_id%'
       AND pg_get_constraintdef(c.oid) NOT LIKE '%''C''%';

    IF constraint_name IS NOT NULL THEN
        EXECUTE format('ALTER TABLE validation_results DROP CONSTRAINT %I',
                       constraint_name);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'validation_results'::regclass
           AND conname = 'validation_results_table_id_in_abc'
    ) THEN
        ALTER TABLE validation_results
            ADD CONSTRAINT validation_results_table_id_in_abc
            CHECK (table_id IN ('A', 'B', 'C'));
    END IF;
END $$;

-- An unavailable cell has no metrics. Under NOT NULL the only way to store one
-- is to invent a number.
ALTER TABLE validation_results ALTER COLUMN auc DROP NOT NULL;
ALTER TABLE validation_results ALTER COLUMN mean_lead_time_days DROP NOT NULL;
ALTER TABLE validation_results ALTER COLUMN precision_at_recall DROP NOT NULL;

ALTER TABLE validation_results
    ADD COLUMN IF NOT EXISTS availability text NOT NULL DEFAULT 'measured';
ALTER TABLE validation_results
    ADD COLUMN IF NOT EXISTS unavailable_reason text;
ALTER TABLE validation_results
    ADD COLUMN IF NOT EXISTS unavailable_detail text;
ALTER TABLE validation_results
    ADD COLUMN IF NOT EXISTS declared_folds integer;
ALTER TABLE validation_results
    ADD COLUMN IF NOT EXISTS train_epochs text[];
ALTER TABLE validation_results
    ADD COLUMN IF NOT EXISTS calibration_max_iter integer;

-- The weights artefact is absent on an unavailable row: there was nothing to
-- fit, or the fit is what failed.
ALTER TABLE validation_results ALTER COLUMN weights_artefact_id DROP NOT NULL;
ALTER TABLE validation_results ALTER COLUMN leakage_check DROP NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
         WHERE conrelid = 'validation_results'::regclass
           AND conname = 'validation_results_availability_is_whole'
    ) THEN
        ALTER TABLE validation_results
            ADD CONSTRAINT validation_results_availability_is_whole CHECK (
                (availability = 'measured'
                 AND auc IS NOT NULL
                 AND unavailable_reason IS NULL)
                OR
                (availability = 'unavailable'
                 AND auc IS NULL
                 AND unavailable_reason IS NOT NULL)
            );
    END IF;
END $$;

-- Reading the table by design and availability is what a report loader does.
CREATE INDEX IF NOT EXISTS validation_results_by_availability
    ON validation_results (pre_registration_hash, table_id, availability);

COMMIT;
