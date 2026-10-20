# C15 / O03 — ordinary startup brings up the market side too
"""One launcher, both halves.

Before this, `launch_prototype.ps1` started the console and a supervised
news worker and nothing else: the daily pillar vintages and the prospective
forecasts needed a second terminal, and the console could not say whether
anyone had run them. The news half was already solved by a concurrent
session (unified startup, single-worker OS lock, owner-pid shutdown); this
is the market half.

The design claim being tested is that the market steps are a SEQUENCE OF
IDEMPOTENT WRITES rather than a daemon, per `AGENTS.md` §2's choice of cron
plus idempotent scripts over a workflow engine. That is what makes it safe
for the launcher to run them on every start, a scheduler to run them hourly,
and an operator to run them by hand, without any of the three coordinating.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

import run_market_jobs                                           # noqa: E402

LAUNCHER = (ROOT / "launch_prototype.ps1").read_text(encoding="utf-8")


class TestTheLauncherStartsBothHalves:
    def test_it_starts_the_news_worker(self):
        assert "news_supervisor.py" in LAUNCHER

    def test_it_starts_the_market_jobs(self):
        """The C15 gap: this line did not exist."""
        assert "run_market_jobs.py" in LAUNCHER

    def test_both_can_be_disabled_independently(self):
        assert "-NoNewsWorker" in LAUNCHER or "NoNewsWorker" in LAUNCHER
        assert "NoMarketJobs" in LAUNCHER

    def test_it_stops_only_what_it_started(self):
        """Shutdown must not reach a worker another launch owns."""
        assert LAUNCHER.count("taskkill") >= 2
        assert "Only the processes this script started" in LAUNCHER

    def test_the_market_jobs_run_in_the_background(self):
        """A two-minute RMT estimate must not hold the page hostage."""
        assert "market-jobs.log" in LAUNCHER

    def test_it_does_not_start_the_live_tick_loop(self):
        """Opening a broker feed is an operator decision, not a side effect
        of opening a dashboard."""
        assert "is NOT started" in LAUNCHER
        assert "run_live.py --status" in LAUNCHER

    def test_no_separate_news_command_is_required(self):
        """The concurrent session's unified-startup claim, re-asserted here
        so a launcher change cannot quietly reintroduce the second terminal."""
        assert "launch_news" not in LAUNCHER


class TestMarketJobsStatus:
    def test_an_unrun_installation_says_so_rather_than_looking_healthy(self,
                                                                       tmp_path,
                                                                       monkeypatch):
        monkeypatch.setenv("SERAPH_MARKET_JOBS_STATUS",
                           str(tmp_path / "absent.json"))
        state = run_market_jobs.status()
        assert state["ran"] is False
        assert "have not run" in state["note"]

    def test_an_unreadable_status_file_is_reported_not_swallowed(self, tmp_path,
                                                                 monkeypatch):
        broken = tmp_path / "broken.json"
        broken.write_text("{not json", encoding="utf-8")
        monkeypatch.setenv("SERAPH_MARKET_JOBS_STATUS", str(broken))
        state = run_market_jobs.status()
        assert state["ran"] is False
        assert "unreadable" in state["note"]

    def test_a_real_run_records_each_step(self, tmp_path, monkeypatch):
        written = tmp_path / "status.json"
        monkeypatch.setenv("SERAPH_MARKET_JOBS_STATUS", str(written))
        run_market_jobs._write(dict(
            generated="2026-10-20T02:00:00+05:30", ok=True,
            session="2026-08-21", corpus="7,385,306 daily rows",
            steps=[dict(step="daily vintages", ok=True)]))
        state = run_market_jobs.status()
        assert state["ran"] is True
        assert state["session"] == "2026-08-21"
        assert state["steps"][0]["step"] == "daily vintages"

    def test_a_failed_step_does_not_hide_the_ones_that_landed(self, tmp_path,
                                                              monkeypatch):
        """A failed forecast must not erase the vintages that succeeded."""
        written = tmp_path / "status.json"
        monkeypatch.setenv("SERAPH_MARKET_JOBS_STATUS", str(written))
        run_market_jobs._write(dict(
            generated="x", ok=False, session="2026-08-21", corpus="rows",
            steps=[dict(step="daily vintages", ok=True),
                   dict(step="prospective forecast", ok=False,
                        error="boom")]))
        state = run_market_jobs.status()
        assert state["ok"] is False
        assert [s["ok"] for s in state["steps"]] == [True, False]


class TestTheStepsAreIdempotent:
    """The property the whole design rests on. Each step is keyed so a
    second run writes nothing, which is what lets three different callers
    run it without coordinating."""

    def test_a_daily_vintage_is_keyed_by_producer_window_and_bundle(self):
        from seraph.live.store import LiveStore
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            store = LiveStore(Path(scratch) / "r.sqlite")
            args = dict(producer="rmt", input_end="2026-08-21T15:30:00+05:30",
                        emission_available_at="2026-08-21T16:00:00+05:30",
                        origin="computed", value=0.23, bundle_id="original rmt")
            assert store.record_daily_vintage(**args)["stored"] is True
            assert store.record_daily_vintage(**args)["stored"] is False

    def test_a_forecast_is_keyed_by_target_model_cutoff_and_artefact(self):
        from seraph.live.store import LiveStore
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            store = LiveStore(Path(scratch) / "r.sqlite")
            args = dict(target="loss10_15", model="m", as_of="2026-08-21",
                        artefact_id="fit:a", horizon=15,
                        matures_after="2026-09-14", fit_status="forecast",
                        probability=0.2)
            assert store.record_forecast(**args)["stored"] is True
            assert store.record_forecast(**args)["stored"] is False

    def test_settling_is_safe_to_repeat(self):
        """The store refuses an immature outcome, so `--settle` can run on
        every launch without the caller tracking what is due."""
        from seraph.live.store import LiveStore, StoreError
        import tempfile

        with tempfile.TemporaryDirectory() as scratch:
            store = LiveStore(Path(scratch) / "r.sqlite")
            store.record_forecast(
                target="t", model="m", as_of="2026-08-21", artefact_id="f",
                horizon=15, matures_after="2026-09-14",
                fit_status="forecast", probability=0.2)
            with pytest.raises(StoreError, match="has not finished producing"):
                store.attach_outcome(target="t", model="m", as_of="2026-08-21",
                                     artefact_id="f", outcome=1.0,
                                     now="2026-08-22")


class TestTheConsoleReportsIt:
    def test_the_panel_is_wired_into_the_page(self):
        body = (ROOT / "seraph/dashboard/prototype_app.py").read_text(
            encoding="utf-8")
        assert "MARKET JOBS" in body
        assert "market_jobs_panel()" in body

    def test_the_panel_reads_status_rather_than_computing(self):
        """Rendering must not trigger a two-minute RMT estimate."""
        body = (ROOT / "seraph/dashboard/prototype_app.py").read_text(
            encoding="utf-8")
        panel = body.split("def market_jobs_panel", 1)[1].split("def ", 1)[0]
        # The seam moved into the package so an installed wheel, which has
        # no `scripts/`, can still draw this panel. Same requirement: read a
        # status file, never start a two-minute estimate.
        assert "read_status()" in panel
        assert "run_all" not in panel
        assert "import run_market_jobs" not in panel

    def test_the_panel_says_the_live_loop_is_not_started(self):
        body = (ROOT / "seraph/dashboard/prototype_app.py").read_text(
            encoding="utf-8")
        panel = body.split("def market_jobs_panel", 1)[1].split("def ", 1)[0]
        assert "operator decision" in panel
