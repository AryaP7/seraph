# T04 — the prospective forecast ledger (audit R12, feature C10)
"""Incremental forecast publication with an immutable dated record.

The historical experiment already produces 75,054 walk-forward rows WITH
their realised labels. That is retrospective: every row knows its outcome
because the outcome had happened before the file was written. C10's gap is
the other object -- a record of what was predicted BEFORE the outcome was
known.

The distinction is the whole feature, so most of these tests are about the
maturity rule rather than about arithmetic. A ledger that let a writer fill
in the label at issue time would be backfilled from the same features the
forecast was made from within a week, and the evaluation would silently
become in-sample.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from seraph.live.store import LiveStore, StoreError                # noqa: E402


@pytest.fixture
def store(tmp_path):
    return LiveStore(tmp_path / "runtime.sqlite")


def issue(store, *, as_of="2026-08-21", matures="2026-09-14",
          target="loss10_15", model="csrs_logit", artefact="fit:abc",
          probability=0.23, **extra):
    return store.record_forecast(
        target=target, model=model, as_of=as_of, artefact_id=artefact,
        horizon=15, matures_after=matures, fit_status="forecast",
        probability=probability, threshold=0.4, alarm=False, **extra)


class TestIssuingAForecast:
    def test_a_forecast_is_recorded_without_an_outcome(self, store):
        issue(store)
        (row,) = store.forecasts()
        assert row["probability"] == 0.23
        assert row["outcome"] is None, "a label was written at issue time"
        assert row["outcome_at"] is None

    def test_reissuing_the_same_forecast_stores_once(self, store):
        assert issue(store)["stored"] is True
        assert issue(store)["stored"] is False
        assert len(store.forecasts()) == 1

    def test_a_different_fit_over_the_same_cutoff_is_a_separate_forecast(self, store):
        """A re-fitted model is genuinely a different forecast and both
        deserve to exist."""
        issue(store, artefact="fit:abc")
        issue(store, artefact="fit:def")
        assert len(store.forecasts()) == 2

    def test_an_abstention_is_recorded_rather_than_omitted(self, store):
        """Silently dropping a model that could not fit would make the ledger
        look more confident than the system was."""
        issue(store, probability=None, model="gjr_garch_t")
        (row,) = [r for r in store.forecasts() if r["model"] == "gjr_garch_t"]
        assert row["probability"] is None
        assert row["fit_status"] == "forecast"

    def test_a_probability_outside_zero_one_is_refused(self, store):
        for bad in (-0.1, 1.5):
            with pytest.raises(StoreError, match="outside"):
                issue(store, probability=bad)

    def test_a_forecast_maturing_at_its_own_cutoff_is_refused(self, store):
        """A forecast with no horizon is not a forecast."""
        with pytest.raises(StoreError, match="no horizon"):
            issue(store, as_of="2026-08-21", matures="2026-08-21")


class TestTheMaturityRule:
    def test_an_outcome_before_maturity_is_refused(self, store):
        issue(store)
        with pytest.raises(StoreError, match="has not finished producing"):
            store.attach_outcome(target="loss10_15", model="csrs_logit",
                                 as_of="2026-08-21", artefact_id="fit:abc",
                                 outcome=1.0, now="2026-08-25")

    def test_an_outcome_after_maturity_is_accepted(self, store):
        issue(store)
        settled = store.attach_outcome(
            target="loss10_15", model="csrs_logit", as_of="2026-08-21",
            artefact_id="fit:abc", outcome=1.0, now="2026-09-15")
        assert settled["outcome"] == 1.0
        (row,) = store.forecasts()
        assert row["outcome"] == 1.0 and row["outcome_at"] == "2026-09-15"

    def test_an_outcome_cannot_be_rewritten(self, store):
        issue(store)
        store.attach_outcome(target="loss10_15", model="csrs_logit",
                             as_of="2026-08-21", artefact_id="fit:abc",
                             outcome=1.0, now="2026-09-15")
        with pytest.raises(StoreError, match="already has an outcome"):
            store.attach_outcome(target="loss10_15", model="csrs_logit",
                                 as_of="2026-08-21", artefact_id="fit:abc",
                                 outcome=0.0, now="2026-09-16")

    def test_an_outcome_needs_a_forecast_to_attach_to(self, store):
        with pytest.raises(StoreError, match="never issued"):
            store.attach_outcome(target="loss10_15", model="nope",
                                 as_of="2026-08-21", artefact_id="fit:abc",
                                 outcome=1.0, now="2026-09-15")

    def test_pending_forecasts_are_queryable(self, store):
        issue(store, model="a")
        issue(store, model="b")
        store.attach_outcome(target="loss10_15", model="a", as_of="2026-08-21",
                             artefact_id="fit:abc", outcome=1.0,
                             now="2026-09-15")
        pending = store.forecasts(pending_only=True)
        assert [p["model"] for p in pending] == ["b"]


class TestThePredictionIsFinalOnceIssued:
    def test_the_probability_cannot_be_edited(self, store):
        import sqlite3
        issue(store)
        with pytest.raises(sqlite3.IntegrityError, match="final once issued"):
            with store.connect() as db:
                db.execute("UPDATE prospective_forecasts SET probability=0.99")

    def test_the_maturity_date_cannot_be_moved_forward(self, store):
        """Otherwise an outcome could be matured into existence early."""
        import sqlite3
        issue(store)
        with pytest.raises(sqlite3.IntegrityError, match="final once issued"):
            with store.connect() as db:
                db.execute("UPDATE prospective_forecasts "
                           "SET matures_after='2026-08-22'")

    def test_a_forecast_cannot_be_deleted(self, store):
        import sqlite3
        issue(store)
        with pytest.raises(sqlite3.IntegrityError, match="still evidence"):
            with store.connect() as db:
                db.execute("DELETE FROM prospective_forecasts")


class TestTheIncrementalJob:
    """`scripts/run_forecast.py` publishes what the walk-forward produced; it
    does not fit independently, so there is one idea of what the model said
    on a date."""

    @pytest.fixture
    def results(self):
        path = ROOT / "research_results" / "v1_verified"
        if not (path / "predictions.parquet").is_file():
            pytest.skip("no saved walk-forward output in this checkout")
        return path

    def test_the_horizon_is_the_last_number_in_the_target_name(self):
        """`onset15` has no underscore before its horizon, so splitting on
        '_' returns the name whole and int() raises on it -- which is how the
        first run of this job died."""
        import run_forecast

        assert run_forecast._horizon_of("loss10_15") == 15
        assert run_forecast._horizon_of("onset15") == 15
        assert run_forecast._horizon_of("no_digits_here") == 15

    def test_issuing_a_real_cutoff_writes_the_whole_slate(self, store, results):
        import run_forecast

        out = run_forecast.issue(store, "2026-08-21", results=results)
        assert out["issued"], out.get("reason")
        assert all(i["stored"] for i in out["issued"])
        assert all(r["outcome"] is None for r in store.forecasts(limit=100))

    def test_reissuing_is_idempotent(self, store, results):
        import run_forecast

        run_forecast.issue(store, "2026-08-21", results=results)
        again = run_forecast.issue(store, "2026-08-21", results=results)
        assert not any(i["stored"] for i in again["issued"])

    def test_a_cutoff_the_experiment_has_not_reached_is_reported(self, store,
                                                                 results):
        """Not papered over with an ad-hoc fit: that would create a second,
        divergeable idea of what the model said."""
        import run_forecast

        out = run_forecast.issue(store, "2099-01-01", results=results)
        assert out["issued"] == []
        assert "has no row for 2099-01-01" in out["reason"]
        assert "experiment re-run" in out["reason"]

    #: A cutoff whose 15-session label HAS been realised in the artefact.
    #: 2026-08-21 is the corpus edge, so its own label cannot exist there --
    #: which `settle` correctly reports as `unlabelled` rather than inventing
    #: one (see the test below).
    SETTLEABLE = "2026-07-31"

    def test_settling_before_maturity_leaves_the_forecast_pending(self, store,
                                                                  results):
        import run_forecast

        run_forecast.issue(store, self.SETTLEABLE, results=results)
        out = run_forecast.settle(store, results=results, now="2026-08-01")
        assert out["settled"] == 0
        assert out["waiting"] > 0, out

    def test_settling_after_maturity_attaches_outcomes(self, store, results):
        import run_forecast

        run_forecast.issue(store, self.SETTLEABLE, results=results)
        out = run_forecast.settle(store, results=results, now="2026-10-01")
        assert out["settled"] > 0, out
        settled = [r for r in store.forecasts(limit=100)
                   if r["outcome"] is not None]
        assert settled

    def test_a_cutoff_at_the_corpus_edge_has_no_label_to_attach(self, store,
                                                               results):
        """The honest case, and the reason `unlabelled` exists as a separate
        count: the newest forecast's own 15-session window has not finished,
        so no realised label exists anywhere -- not in the ledger and not in
        the artefact. `settle` reports it rather than inventing a label."""
        import run_forecast

        run_forecast.issue(store, "2026-08-21", results=results)
        out = run_forecast.settle(store, results=results, now="2026-12-01")
        assert out["settled"] == 0
        assert out["unlabelled"] > 0
        assert all(r["outcome"] is None for r in store.forecasts(limit=100))

    def test_the_artefact_id_is_content_not_a_label(self, results):
        """Two different fits must not collide in the ledger."""
        import run_forecast

        assert run_forecast.artefact_id(results).startswith("fit:")
        assert len(run_forecast.artefact_id(results)) > 10
