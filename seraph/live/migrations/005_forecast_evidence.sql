-- C10 / F03: retain settlement window and protect issuance provenance.
ALTER TABLE prospective_forecasts ADD COLUMN outcome_evidence_json TEXT;
CREATE TRIGGER prospective_forecasts_identity_is_final
BEFORE UPDATE ON prospective_forecasts
WHEN OLD.detail_json IS NOT NEW.detail_json
  OR OLD.target IS NOT NEW.target OR OLD.model IS NOT NEW.model
  OR OLD.as_of IS NOT NEW.as_of OR OLD.artefact_id IS NOT NEW.artefact_id
BEGIN SELECT RAISE(ABORT,'forecast identity and provenance are immutable'); END;
