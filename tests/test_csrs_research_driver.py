# C9/C10 research driver — the guards that stop evidence being overwritten
"""`weights_artefact_id` is part of the `csrs` primary key, which makes artefact
identity a data-safety concern rather than bookkeeping.

This project has already hit that hazard twice:

1. `baseline_weights()` originally returned **one** id for both the 2-pillar and
   3-pillar line-ups. Since the id is in the PK, the second run would have
   silently overwritten the first. Fixed by binding `mask_profile` into the hash.
2. `--full-span` runs the whole Pillar 2 history (2005+) instead of clamping the
   grid to the Hawkes span (2017+). Nothing in `CalibrationConfig` encodes the
   span, so it hashes to the **same** id as the 2017+ run — and the values
   genuinely differ, because `KalmanReconciler` is recursive and a 2017 tick
   reached after twelve years of updates is not the same tick reached from a cold
   start. Writing it would have destroyed evidence, not deduplicated it.

Both guards are invisible in normal use and would fail silently if removed, so
they are pinned here. Neither test touches the database: the `--write
--full-span` refusal is the first statement in `main()` and returns before a pool
is opened, which is itself part of the contract.
"""
from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parent.parent


def _driver():
    spec = importlib.util.spec_from_file_location(
        "run_csrs_research", _ROOT / "scripts" / "run_csrs_research.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_write_with_full_span_is_refused_before_any_db_access():
    """Must return non-zero without opening a connection.

    If this ever returns 0, a full-span run would upsert over the 2017+ rows
    under the same `weights_artefact_id`.
    """
    mod = _driver()
    rc = asyncio.run(mod.main(write=True, limit=None, stress_slot=False,
                              full_span=True))
    assert rc != 0, "--write --full-span must be refused"


def test_the_two_pillar_line_ups_have_distinct_artefact_ids():
    """`mask_profile` must stay bound into the weights hash."""
    mod = _driver()
    two = mod.baseline_weights(stress_slot=False)
    three = mod.baseline_weights(stress_slot=True)
    assert two.artefact_id != three.artefact_id, (
        "one id for two pillar line-ups would make the csrs PK collide and "
        "silently overwrite a run")
    # and the ids must be stable across calls, or reruns stop being idempotent
    assert mod.baseline_weights(stress_slot=False).artefact_id == two.artefact_id
    assert mod.baseline_weights(stress_slot=True).artefact_id == three.artefact_id


def test_the_research_weights_declare_they_were_trained_on_nothing():
    """Equal weights are the explicitly uncalibrated baseline D5(c) prescribes.

    Empty `epochs` is the audit trail saying so. If something ever calibrates
    these weights, `epochs` must become non-empty — and this test should then be
    updated deliberately, not deleted.
    """
    mod = _driver()
    for stress in (False, True):
        cfg = mod.baseline_weights(stress_slot=stress).calibrated_on
        assert cfg.epochs == (), "equal weights must not claim to be calibrated"
        assert cfg.kappa_miss == 1.0 and cfg.kappa_fa == 1.0, (
            "a symmetric loss asserts no asymmetric cost; FR30 has not been run")


def test_mask_profile_matches_the_pillar_line_up_it_names():
    mod = _driver()
    assert mod.baseline_weights(stress_slot=False).calibrated_on.mask_profile == (
        True, True, False), "slot 3 is a structural absence without --stress-slot"
    assert mod.baseline_weights(stress_slot=True).calibrated_on.mask_profile == (
        True, True, True), "--stress-slot occupies slot 3"


@pytest.mark.parametrize("w", [5, 20])
def test_downside_semivariance_is_causal_and_ignores_upside(w):
    """Only negative returns contribute, and out[i] never reads past i."""
    import numpy as np
    mod = _driver()
    lr = np.zeros(80)
    lr[60] = +0.10                       # a large UP move
    sv = mod.downside_semivariance(lr, w=w)
    assert np.nanmax(sv) == pytest.approx(0.0), (
        "an upside move must not register as downside stress")

    lr2 = np.zeros(80)
    lr2[40] = -0.10                      # a large DOWN move
    sv2 = mod.downside_semivariance(lr2, w=w)
    # Index the ORIGINAL positions, not the finite-filtered array: the leading
    # entries are NaN while the window fills, so sv2[isfinite(sv2)][:40] reaches
    # past position 40 and would make this assertion test the wrong days.
    before = sv2[:40]
    assert np.all(before[np.isfinite(before)] == pytest.approx(0.0)), (
        "a shock at t=40 must not affect any value before it — that is a leak")
    assert sv2[40] > 0.0
    # and it must decay out of the trailing window, not persist forever
    assert sv2[40 + w] == pytest.approx(0.0)
