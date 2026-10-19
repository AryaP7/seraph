# Regression tests — X06 (the JS harnesses had no runner at all)
"""Run `tests/js/*.mjs` from pytest and assert what they report.

X06 (completion-audit verification, Part 3). `package-lock.json` existed at
the repository root with **no `package.json`**, so `npm ci` and `npm install`
both failed. The two harnesses were referenced by nothing -- no Python test,
no launcher, no CI job, no documentation -- despite `bridge_harness.mjs`
saying in its own header "Pytest reads that JSON, so the assertions live with
the other FIX11 tests". That wrapper was never written.

So the browser half of the console was unverified in two different senses:
the audit's V02 asked for JS flows in CI, and there was not even a manifest
to install from. These tests close the pytest half; `.github/workflows`
carries the CI half.

The harnesses themselves are good: both already run clean and emit a flat
JSON object of named claims. Nothing here reimplements them -- this runs the
real files and fails on any claim they report false, so a future regression
in `bridge.js` or `news_layer.js` fails the normal suite.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HARNESS_DIR = ROOT / "tests" / "js"

node = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is not on PATH; the JS harnesses need Node >= 20 "
           "(see package.json engines). Skipped, not passed: an absent "
           "runtime is an unverified claim, not a satisfied one")


def run_harness(name: str) -> dict:
    """Execute one harness and return the JSON object it prints."""
    path = HARNESS_DIR / name
    assert path.is_file(), f"{name} is missing"
    proc = subprocess.run(["node", str(path)], cwd=ROOT, capture_output=True,
                          text=True, timeout=120)
    assert proc.returncode == 0, (
        f"{name} exited {proc.returncode}\n"
        f"stdout:\n{proc.stdout[-2000:]}\nstderr:\n{proc.stderr[-2000:]}")
    # The harnesses print one JSON object, and `news_layer_harness` adds a
    # human summary line after it ("31 checks passed"). `raw_decode` takes
    # the object and ignores whatever surrounds it, so neither leading logs
    # nor a trailing summary breaks the bridge.
    start = proc.stdout.find("{")
    assert start != -1, f"{name} printed no JSON:\n{proc.stdout[-2000:]}"
    report, _ = json.JSONDecoder().raw_decode(proc.stdout[start:])
    return report


def failures(report: dict) -> list[str]:
    """Every claim the harness reported false. Non-boolean values are data
    (tables, counts) and are not pass/fail claims."""
    return sorted(k for k, v in report.items() if v is False)


# ------------------------------------------------------------- the manifest


class TestX06TheManifestExists:
    def test_package_json_is_present(self):
        assert (ROOT / "package.json").is_file(), \
            "package-lock.json with no package.json: npm ci cannot run (X06)"

    def test_the_lockfile_has_its_manifest(self):
        assert (ROOT / "package-lock.json").is_file()
        manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        assert manifest["private"] is True, \
            "these harnesses are not a published package"

    def test_the_manifest_can_run_both_harnesses(self):
        manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        script = manifest["scripts"]["test"]
        assert "bridge_harness.mjs" in script
        assert "news_layer_harness.mjs" in script

    def test_every_harness_in_the_directory_is_wired_up(self):
        """A harness nobody runs is the defect. If one is added, it must be
        added to the manifest and to this file."""
        present = {p.name for p in HARNESS_DIR.glob("*.mjs")}
        manifest = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        script = manifest["scripts"]["test"]
        unwired = sorted(n for n in present if n not in script)
        assert unwired == [], f"harnesses with no runner: {unwired}"


# --------------------------------------------------------- FIX11 the bridge


@node
class TestBridgeHarness:
    @pytest.fixture(scope="class")
    def report(self):
        return run_harness("bridge_harness.mjs")

    def test_every_claim_holds(self, report):
        assert failures(report) == []

    def test_the_request_lifecycle_is_exercised(self, report):
        """Guards against a harness that runs clean because it asserts
        nothing: these specific FIX11 claims must be present."""
        for claim in ("status_succeeded", "draft_preserved",
                      "context_change_discards", "no_stale_result_rendered"):
            assert claim in report, f"{claim} is no longer checked"

    def test_a_lost_response_can_be_retried(self, report):
        assert report.get("accepts_new_request_after_discard") is True

    def test_role_navigation_is_covered(self, report):
        assert report.get("role_change_sent_request") is True
        assert report.get("same_role_sends_no_request") is True

    def test_the_report_is_not_empty(self, report):
        assert len(report) >= 10


# ------------------------------------------------------- T13 the news layer


@node
class TestNewsLayerHarness:
    @pytest.fixture(scope="class")
    def report(self):
        return run_harness("news_layer_harness.mjs")

    def test_every_claim_holds(self, report):
        assert failures(report) == []

    def test_an_absent_channel_draws_nothing_and_says_so(self, report):
        for claim in ("absent_draws_nothing", "absent_keeps_preview",
                      "absent_banner_names_fabricated",
                      "absent_never_says_live"):
            assert report.get(claim) is True, f"{claim} regressed"

    def test_a_null_payload_cannot_crash_the_map(self, report):
        assert report.get("null_payload_is_safe") is True
        assert report.get("undefined_payload_is_safe") is True

    def test_coordinates_are_not_invented_in_the_browser(self, report):
        assert report.get("coordinates_come_from_the_server") is True
        assert report.get("a_node_without_coordinates_is_not_drawn_at_the_origin") \
            is True

    def test_the_news_palette_cannot_be_read_as_a_csrs_band(self, report):
        assert report.get("news_palette_is_disjoint_from_the_csrs_band") is True

    def test_the_report_is_not_empty(self, report):
        assert len(report) >= 20
