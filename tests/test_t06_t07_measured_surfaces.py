# T06, T07 — replace fabricated panels with measured data or a named absence
"""The FR41 benchmark overlay, the FR45/FR51 flow panel, and the FR14 sector
flags.

Three surfaces the audit recorded as partial or absent, for three different
reasons, and the distinction is the point:

* **FR41 benchmark overlay** was absent because the history payload carried
  CSRS alone. The official series was already in the repository, so this is
  now real.
* **FR45/FR51 flow** showed three fabricated `(example)` values. NSE's public
  endpoint serves the real print, so this is now real too.
* **FR14 sector micro-flags** are genuinely blocked: they need per-sector
  jump counts from 5-minute bars, and `intraday_bars` cannot be filled
  without a Kite subscription. So the absence is NAMED and traceable to its
  cause, and nothing is substituted.

A test suite that could not tell those three apart would let a placeholder
pass as a measurement, which is the failure mode all of this exists to
prevent.
"""
from __future__ import annotations

import pytest

from seraph.dashboard.console_backend import dispatch, market_flow
from seraph.ingestion import benchmark_client
from seraph.orchestration.prototype import InferenceSession
from seraph.orchestration.run_store import RunStore


def saved(tmp_path):
    store = RunStore(tmp_path / "ui.sqlite")
    manifest = dict(mode="synthetic test fixture",
                    data_available_through="2020-01-01")
    run = store.begin(manifest)
    inputs = {p: dict(score_eligible=False, reason="test missing",
                      absence="structural", absence_reason="no_data_coverage")
              for p in ("hawkes", "rmt", "hamilton")}
    point = InferenceSession(["2020-01-01"]).step("2020-01-01", inputs, [],
                                                  run_id=run)
    store.put(run, point)
    store.finish(run, 1)
    return store, manifest, point


# --------------------------------------------------- T07 / FR41 overlay


class TestT07BenchmarkOverlayIsReal:
    def test_the_official_series_is_available(self):
        described = benchmark_client.describe()
        assert described["available"] is True
        assert "NIFTY 500" in described["label"]
        assert described["sessions"] > 3000

    def test_it_names_its_source_rather_than_claiming_an_index(self):
        described = benchmark_client.describe()
        assert described["source"].endswith("nifty 500.csv")

    def test_returns_are_close_to_close_and_not_forward_filled(self):
        described = benchmark_client.describe()
        assert "not forward-filled" in described["convention"]

    def test_a_csrs_date_with_an_index_print_gets_a_return(self):
        joined = benchmark_client.align([dict(date="2026-08-21", csrs=0.4)])
        row = joined["rows"][0]
        assert row["benchmark_available"] is True
        assert isinstance(row["benchmark_return"], float)
        assert row["benchmark_close"] > 0

    def test_a_csrs_date_before_the_index_begins_is_a_gap_not_a_guess(self):
        """The index starts 2012-02-21 and the CSRS archive starts 2005. That
        gap is real and must stay visible rather than being hidden by
        trimming the CSRS series."""
        joined = benchmark_client.align([dict(date="2005-01-03", csrs=0.5)])
        row = joined["rows"][0]
        assert row["benchmark_available"] is False
        assert row["benchmark_return"] is None
        assert joined["coverage"]["benchmark_missing"] == 1
        assert joined["coverage"]["first_missing"] == "2005-01-03"

    def test_the_csrs_series_is_never_trimmed_to_hide_a_gap(self):
        history = [dict(date="2005-01-03", csrs=0.5),
                   dict(date="2026-08-21", csrs=0.4)]
        joined = benchmark_client.align(history)
        assert len(joined["rows"]) == 2
        assert joined["coverage"]["csrs_dates"] == 2
        assert joined["coverage"]["matched"] == 1

    def test_both_series_declare_their_own_units(self):
        """A 0..1 score and a return must not land on one axis by accident."""
        joined = benchmark_client.align([dict(date="2026-08-21", csrs=0.4)])
        assert "0..1" in joined["units"]["csrs"]
        assert "return" in joined["units"]["benchmark"]

    def test_the_note_quantifies_the_coverage(self):
        joined = benchmark_client.align([dict(date="2005-01-03", csrs=0.5),
                                         dict(date="2026-08-21", csrs=0.4)])
        assert "1 of 2" in joined["note"]
        assert "forward-filled or substituted" in joined["note"]

    def test_fr54_reports_its_pair_count_beside_the_correlation(self):
        """With a short overlap a correlation means very little, so the pair
        count is reported rather than buried."""
        thin = benchmark_client.representativeness(
            [dict(date="2026-08-21", csrs=0.4)])
        assert thin["available"] is False
        assert thin["pairs"] == 1
        assert "noise" in thin["reason"]

    def test_the_overlay_reaches_the_console_payload(self, tmp_path):
        from seraph.dashboard.console_backend import project_run
        store, manifest, point = saved(tmp_path)
        payload = project_run(point, manifest, [point], "institutional")
        history = payload["history"]
        assert "rows" in history and "series" in history
        assert history["series"]["label"].startswith("NIFTY 500")
        assert "units" in history

    def test_a_missing_series_file_is_an_explicit_absence(self, tmp_path):
        absent = benchmark_client.describe(tmp_path / "nope.csv")
        assert absent["available"] is False
        assert "not substituted" in absent["reason"]

    def test_another_index_is_never_substituted(self, tmp_path):
        """FR41 names Nifty 500; Nifty 50 is a different population."""
        joined = benchmark_client.align([dict(date="2026-08-21", csrs=0.4)],
                                        path=tmp_path / "nope.csv")
        assert all(r["benchmark_available"] is False for r in joined["rows"])
        assert joined["series"]["available"] is False


# ------------------------------------------------ T06 / FR45 flow panel


class TestT06FlowPanelIsMeasuredOrAbsent:
    def test_a_date_before_any_print_is_an_explicit_absence(self):
        flow = market_flow("2005-01-01")
        assert flow["available"] is False
        assert "no free bulk history" in flow["reason"]
        for fabricated in ("-1200", "900", "0.72"):
            assert fabricated not in str(flow)

    def test_a_real_print_carries_its_units_and_scope(self):
        """Skips rather than passes when nothing has been ingested: an
        un-ingested store is an unverified claim, not a satisfied one."""
        flow = market_flow()
        if not flow["available"]:
            pytest.skip(f"no FII/DII print ingested: {flow['reason']}")
        assert flow["units"].startswith("INR crore")
        assert "never a per-instrument retail attribution" in flow["scope"]
        assert isinstance(flow["fiiNet"], float)
        assert isinstance(flow["diiNet"], float)

    def test_the_proxy_caveat_survives_to_the_screen(self):
        flow = market_flow()
        if not flow["available"]:
            pytest.skip("no FII/DII print ingested")
        assert any("not measured retail participation" in w
                   for w in flow["warnings"])

    def test_the_residual_share_is_not_clipped_into_plausibility(self):
        flow = market_flow()
        if not flow["available"]:
            pytest.skip("no FII/DII print ingested")
        assert flow["basis"].startswith("stored E14 proxy")


# ----------------------------------------- T06 / FR14 sector micro-flags


class TestT06SectorFlagsAreNamedAsBlocked:
    def test_the_portfolio_overlay_still_computes_without_them(self, tmp_path):
        store, _, point = saved(tmp_path)
        out = dispatch(store, point, "retail", dict(
            id="r1", run_id=point["run_id"], date=point["date"],
            op="portfolio",
            holdings=[dict(symbol="RELIANCE", quantity=10, price=1300,
                           value=13000.0, sector="Energy")]))
        assert out["kind"] == "portfolio"
        assert out["value"]

    def test_the_absence_names_what_it_needs_and_what_blocks_it(self, tmp_path):
        """An unexplained `{}` is indistinguishable from a bug. This turns it
        into a traceable blocker."""
        store, _, point = saved(tmp_path)
        out = dispatch(store, point, "retail", dict(
            id="r1", run_id=point["run_id"], date=point["date"],
            op="portfolio",
            holdings=[dict(symbol="RELIANCE", quantity=10, price=1300,
                           value=13000.0, sector="Energy")]))
        flags = out["sector_flags"]
        assert flags["available"] is False
        assert "jump counts" in flags["requires"]
        assert "Kite" in flags["blocked_by"]

    def test_no_substitute_is_used(self, tmp_path):
        store, _, point = saved(tmp_path)
        out = dispatch(store, point, "retail", dict(
            id="r1", run_id=point["run_id"], date=point["date"],
            op="portfolio",
            holdings=[dict(symbol="RELIANCE", quantity=10, price=1300,
                           value=13000.0, sector="Energy")]))
        assert "no substitute" in out["sector_flags"]["note"]
        assert "different subsystem" in out["sector_flags"]["note"]

    def test_the_estimator_still_accepts_sector_inputs_when_they_exist(self):
        """The capability is present and waiting on data, not missing: FR14's
        helper works when counts are supplied."""
        from seraph.pillars.hawkes.engine import sector_flags

        produced = sector_flags({"energy": 40, "it": 2},
                                {"energy": 1.0, "it": 1.0}, window_days=10.0)
        by_sector = {f.sector_id: f for f in produced}
        assert by_sector["energy"].flag == "amber"
        assert by_sector["it"].flag == "none"
