# C8/C9 — D4 staleness scale, D2 eligibility and the Hawkes cadence (FR26, FR28).
"""Regression checks for pillar eligibility as a function of CADENCE.

These pin the *mechanism* by which a pillar enters or leaves the D2 mask, and
the measured relationship between each pillar's configured D4 staleness scale
and that pillar's actual update cadence. They assert what the code does today,
including two places where the configured scale and the real cadence disagree,
so that neither can change without a test changing with it.

They are information-accounting checks. Nothing here claims predictive skill.
"""
from datetime import date, datetime, timedelta
from math import exp, log

import numpy as np
import pytest

from seraph.fusion.score import score
from seraph.reconciliation.kalman import DEFAULT_H_BARS, KalmanReconciler
from seraph.reconciliation.noise_model import SaturatingNoise
from seraph.shared_types import (
    IST,
    CalibrationConfig,
    FusionWeights,
    ObservedEmission,
    PillarObservation,
    UnavailableEmission,
    ist_timestamp,
)

#: Bars of open trading time in one regular NSE session, 09:15–15:30.
BARS_PER_SESSION = 75.0

#: The Hawkes pillar's measured update cadence. `refit_sessions = 5` in every
#: native config, and the archived original series holds 473 observations over
#: 2017-02-09..2026-08-20 (~49.7/year, consecutive gaps of 7 or 8 calendar
#: days), i.e. one emission per five trading sessions. The pillar value is a
#: function of the fitted parameters, so it cannot change between fits.
HAWKES_NATIVE_CADENCE_BARS = 5 * BARS_PER_SESSION   # 375.0

SESSIONS = [date(2026, 10, 19) + timedelta(days=i) for i in range(40)]


def _weights():
    cfg = CalibrationConfig(epochs=[], splitPolicy="leave_one_epoch_out",
                            foldHeldOut=None, kappaMiss=1.0, kappaFa=1.0,
                            maskProfile=[True, True, False])
    third = 1.0 / 3.0
    rows = ((third, third, third),) * 3
    return FusionWeights(artefactId="0" * 64, calibratedOn=cfg, w=rows,
                         ecdfWindowYears=5)


def observed(pillar, when, *, tau=None, value=0.5, variance=None):
    return ObservedEmission(obs=PillarObservation(
        pillar=pillar, ts=ist_timestamp(when),
        tau=ist_timestamp(tau or when), value=value,
        estimation_variance=variance))


def absent(pillar, when, *, absence):
    return UnavailableEmission(
        pillar=pillar, ts=ist_timestamp(when), absence=absence,
        reason="estimation_failed" if absence == "transient"
        else "no_data_coverage")


def ok(result):
    assert result.status == "ok", result
    return result.value


# --------------------------------------------------------- D4 geometry


def test_saturation_threshold_is_a_fixed_multiple_of_the_staleness_scale():
    """Δ_sat = h·ln((R_max/R₀ − 1)/(R_max/R₀ − sf·R_max/R₀)) — scale-free.

    With R_max = 100·R₀ and saturation at 0.95·R_max the threshold is
    2.9857·h for every pillar, independent of R₀. So a pillar's eligibility
    lifetime is set entirely by its own `h_bars`.
    """
    ratio, frac = 100.0, 0.95
    expected = -log(1.0 - (frac * ratio - 1.0) / (ratio - 1.0))
    assert expected == pytest.approx(2.9856819377, abs=1e-9)

    for h in (1.0, 7.5, 75.0, 375.0):
        curve = SaturatingNoise(h_bars=h)
        for r0 in (0.002, 0.02, 0.2):
            below = expected * h * (1 - 1e-9)
            above = expected * h * (1 + 1e-9)
            assert not curve.saturated(curve.r(below, r0), r0)
            assert curve.saturated(curve.r(above, r0), r0)


def test_configured_hawkes_scale_is_a_fraction_of_its_own_update_cadence():
    """The configured scale and the measured cadence disagree, by 375×.

    D4 (SPEC OQ10) initialises `h_p` to "each pillar's native update cadence",
    and ARCHITECTURE §D4 reads that as "Hawkes 5 min, RMT 1 trading day,
    Hamilton 1 trading day". RMT and Hamilton are configured at one session,
    which is their cadence. Hawkes is configured at ONE BAR while its pillar
    value changes once every five sessions, so its eligibility lifetime is
    0.8% of one of its own update cycles — against RMT's 299%.

    This test asserts the present state, not the intended one. Changing
    `DEFAULT_H_BARS` is an owner decision; see
    docs/DECISION-REGISTER-2026-10-26.md.
    """
    h_hawkes, h_rmt, h_hamilton = DEFAULT_H_BARS
    assert (h_hawkes, h_rmt, h_hamilton) == (1.0, 75.0, 75.0)

    sat = 2.9856819377
    # RMT and Hamilton: eligible for about three of their own cycles.
    assert sat * h_rmt / BARS_PER_SESSION == pytest.approx(2.986, abs=1e-3)
    assert sat * h_hamilton / BARS_PER_SESSION == pytest.approx(2.986, abs=1e-3)
    # Hawkes: eligible for 0.8% of one of its own cycles.
    hawkes_cycles = sat * h_hawkes / HAWKES_NATIVE_CADENCE_BARS
    assert hawkes_cycles == pytest.approx(0.00796, abs=1e-5)
    assert hawkes_cycles < 0.01


# ------------------------------------------- the 15:15 → 15:30 crossing


def test_freshest_possible_hawkes_vintage_is_saturated_at_the_nominal_close():
    """A fit observing through 15:15 is stale at a 15:30 decision.

    The native Hawkes grid is the COMMON CONTINUOUS session, which ends at
    15:15; 15:15–15:30 is the closing auction and carries no bin the model
    uses. So 15:15 is the freshest observation that can exist. The decision is
    taken at the nominal close, 15:30 — exactly 3.0 bars of open trading time
    later, against a 2.9857-bar ceiling. The margin is 4.3 seconds.
    """
    fit_end = datetime(2026, 10, 23, 15, 15, tzinfo=IST)
    decide = datetime(2026, 10, 23, 15, 30, tzinfo=IST)

    rec = KalmanReconciler(session_dates=SESSIONS)
    ok(rec.update([observed("hawkes", fit_end, value=0.5)]))
    state = ok(rec.state_at(ist_timestamp(decide)))

    assert state.noise_saturated[0] is True
    assert state.mask[0] is False, "hawkes excluded at the nominal close"

    # and the crossing really is at three bars, not two
    rec = KalmanReconciler(session_dates=SESSIONS)
    ok(rec.update([observed("hawkes", fit_end, value=0.5)]))
    two_bars = ok(rec.state_at(ist_timestamp(
        datetime(2026, 10, 23, 15, 25, tzinfo=IST))))
    assert two_bars.mask[0] is True, "still eligible two bars after the fit"


def test_one_native_cycle_scale_makes_the_same_vintage_eligible_and_moves_csrs():
    """Sensitivity: with h = one Hawkes cycle the pillar enters and matters.

    Nothing but the staleness scale changes. The same vintage, the same
    decision timestamp, the same weights and the same pure `score()`.
    """
    fit_end = datetime(2026, 10, 23, 15, 15, tzinfo=IST)
    rmt_end = datetime(2026, 10, 22, 15, 30, tzinfo=IST)
    decide = ist_timestamp(datetime(2026, 10, 23, 15, 30, tzinfo=IST))
    weights = _weights()

    def composite(h_hawkes, hawkes_value):
        rec = KalmanReconciler(session_dates=SESSIONS,
                               h_bars=(h_hawkes, 75.0, 75.0))
        ok(rec.update([observed("rmt", rmt_end, value=0.1)]))
        ok(rec.update([observed("hawkes", fit_end, value=hawkes_value)]))
        state = ok(rec.state_at(decide))
        return state, ok(score(reconciled=state, xi=(1 / 3, 1 / 3, 1 / 3),
                               weights=weights, xi_mode="uniform"))

    excluded, rmt_only = composite(1.0, 0.5)
    included, two_pillar = composite(HAWKES_NATIVE_CADENCE_BARS, 0.5)

    assert excluded.mask == (False, True, False)
    assert included.mask == (True, True, False)
    # the renormalised row gives an included Hawkes half the composite
    assert rmt_only.effective_weights[0] == (0.0, 1.0, 0.0)
    assert included is not None
    assert two_pillar.effective_weights[0] == (0.5, 0.5, 0.0)
    assert two_pillar.csrs != rmt_only.csrs

    # monotone and strictly responsive in the Hawkes reading
    seen = [composite(HAWKES_NATIVE_CADENCE_BARS, v)[1].csrs
            for v in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert seen == sorted(seen)
    assert seen[-1] - seen[0] > 0.1, "an eligible Hawkes genuinely moves CSRS"
    # and the excluded pillar contributes nothing at all
    assert rmt_only.shapley[0] == 0.0
    assert rmt_only.csrs == pytest.approx(
        composite(1.0, 0.0)[1].csrs, abs=0.0), \
        "while excluded, the Hawkes value cannot affect the composite"


# ------------------------------------------------ D2 absence semantics


def test_structural_absence_and_unseen_both_excluded_regardless_of_staleness():
    decide = ist_timestamp(datetime(2026, 10, 23, 15, 30, tzinfo=IST))
    rec = KalmanReconciler(session_dates=SESSIONS)
    ok(rec.update([observed("rmt", datetime(2026, 10, 23, 15, 30, tzinfo=IST),
                            value=0.1)]))
    state = ok(rec.state_at(decide))
    assert state.mask[0] is False, "never observed -> unseen -> excluded"
    assert state.mask[2] is False

    rec = KalmanReconciler(session_dates=SESSIONS)
    ok(rec.update([observed("hawkes", datetime(2026, 10, 19, 10, 0, tzinfo=IST),
                            value=0.9),
                   observed("rmt", datetime(2026, 10, 19, 10, 0, tzinfo=IST),
                            value=0.1)]))
    ok(rec.update([absent("hawkes", datetime(2026, 10, 23, 15, 30, tzinfo=IST),
                          absence="structural"),
                   observed("rmt", datetime(2026, 10, 23, 15, 30, tzinfo=IST),
                            value=0.1)]))
    state = ok(rec.state_at(decide))
    assert state.mask[0] is False, "structural absence excludes (D2 row 4)"


def test_transient_absence_is_more_favourable_than_carrying_forward():
    """Identical information, opposite mask, depending on how absence is said.

    A pillar observed once and then simply omitted from later batches keeps
    status `observed`, ages past the D4 ceiling and is masked OUT. The same
    pillar, with the same single observation and the same elapsed time, is
    masked IN if its producer emits an explicit TRANSIENT absence — because
    D2 row 3 ("transient -> mask true, D4 inflation handles it") carries no
    age limit, so `noise_saturated` and `mask` can both be true at once.

    This is the documented D2 table applied literally. It is asserted here
    because it is a live inconsistency, not because it is desirable; see
    docs/DECISION-REGISTER-2026-10-26.md.
    """
    first = datetime(2026, 10, 19, 10, 0, tzinfo=IST)
    late = datetime(2026, 11, 5, 10, 0, tzinfo=IST)
    decide = ist_timestamp(late)

    def seeded():
        rec = KalmanReconciler(session_dates=SESSIONS)
        ok(rec.update([observed("hawkes", first, value=0.9),
                       observed("rmt", first, value=0.1)]))
        return rec

    carried = ok(seeded().state_at(decide))

    rec = seeded()
    ok(rec.update([absent("hawkes", late, absence="transient"),
                   observed("rmt", late, value=0.1)]))
    declared = ok(rec.state_at(decide))

    assert carried.noise_saturated[0] is True
    assert declared.noise_saturated[0] is True
    assert carried.mask[0] is False
    assert declared.mask[0] is True, (
        "a declared transient absence keeps a saturated pillar in the mask")
    # the two disagree on identical information
    assert carried.mask[0] != declared.mask[0]


# ----------------------------------------- the archived/native statistic


def test_archived_hawkes_emits_the_ungated_branching_ratio_statistic():
    """FR13 v4: "the branching ratio is reported regardless" of the gate.

    `mts` is the GATED column and is 0.0 on 352 of the archive's 473 rows.
    The native producer persists `n/(1-n)` ungated for exactly this reason
    (`pillars/hawkes/runtime.py:_persist`), so the archived path must agree or
    one pillar's ECDF reference window mixes two different statistics.
    """
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import scripts.run_daily as run_daily

    if not run_daily.ARCHIVED_HAWKES.exists():
        pytest.skip("archived Hawkes snapshot not present")

    import polars as pl
    frame = pl.read_parquet(run_daily.ARCHIVED_HAWKES)
    rows = list(frame.iter_rows(named=True))
    gated_off = [r for r in rows if float(r["mts"]) == 0.0]
    assert gated_off, "expected gated-off rows in the archived series"

    row = max(gated_off, key=lambda r: r["ts"])
    day = row["ts"].astimezone(run_daily.IST).strftime("%Y-%m-%d")
    emitted = run_daily.archived_hawkes(day)

    assert emitted is not None
    n = float(row["branching_ratio_n"])
    assert emitted["value"] == pytest.approx(n / (1.0 - n), rel=1e-12)
    assert emitted["value"] > 0.0, "a gated-off reading is not a zero reading"
    assert emitted["detail"]["fr13_gate_open"] is False
    assert emitted["detail"]["raw_statistic"] == "ungated_n_over_one_minus_n"
    assert emitted["detail"]["mts"] == 0.0, "the gate survives as provenance"


def test_native_and_archived_hawkes_values_are_not_on_one_scale():
    """The two Hawkes series are different measurements, not one history.

    The archived pillar pooled the market-wide stream; the native fit pools a
    95-member point-in-time basket over a 500-session window under the common
    continuous-session policy. Every native value sits above the archive's
    whole range, so an ECDF built by concatenating them ranks every native
    reading at 1.0 and carries no information.
    """
    from pathlib import Path

    archive = (Path(__file__).resolve().parents[1]
               / "research_data" / "original_hawkes.parquet")
    if not archive.exists():
        pytest.skip("archived Hawkes snapshot not present")

    import polars as pl
    from seraph.fusion import ecdf_transform

    frame = pl.read_parquet(archive)
    n = frame["branching_ratio_n"].to_numpy()
    ungated = n / (1.0 - n)

    # the native fits registered on this installation
    native = np.array([0.1996530154113905, 0.20008944992338842,
                       0.20116972899471558])
    assert native.min() > ungated.max(), (
        "native branching ratios exceed the entire archived range "
        f"({ungated.min():.4f}..{ungated.max():.4f})")
    for value in native:
        assert ecdf_transform(float(value), ungated) == 1.0

# ------------------------------------- the absence KIND is the real gate


def test_structural_absence_overrides_a_fresh_unsaturated_observation():
    """The binding exclusion is the absence KIND, not D4 staleness.

    Measured on the real archive: 251 of 254 replayed sessions carry a stored
    Hawkes absence of kind `structural` (written by `scripts/run_daily.py`
    whenever that job supplies no fresh fit), and only 3 carry a fit at all.
    A structural absence clears the mask bit UNCONDITIONALLY -- even when the
    pillar holds a recent observation that is nowhere near its D4 ceiling.

    Here Hawkes is observed at 2026-10-22 15:15 and the decision is taken at
    2026-10-23 15:30, 78 bars later. Against a one-native-cycle scale the
    ceiling is 1,119.6 bars, so the observation is NOT saturated -- yet the
    structural absence still removes it, while a transient one does not.
    """
    fit = datetime(2026, 10, 22, 15, 15, tzinfo=IST)
    later = datetime(2026, 10, 23, 15, 30, tzinfo=IST)
    decide = ist_timestamp(later)

    def seeded():
        rec = KalmanReconciler(session_dates=SESSIONS,
                               h_bars=(HAWKES_NATIVE_CADENCE_BARS, 75.0, 75.0))
        ok(rec.update([observed("hawkes", fit, value=0.5)]))
        return rec

    # the observation really is fresh on this scale
    fresh = ok(seeded().state_at(decide))
    assert fresh.noise_saturated[0] is False, "78 bars is inside the ceiling"

    seen = {}
    for kind in ("structural", "transient"):
        rec = seeded()
        ok(rec.update([absent("hawkes", later, absence=kind),
                       observed("rmt", later, value=0.1)]))
        state = ok(rec.state_at(decide))
        assert state.noise_saturated[0] is False
        seen[kind] = state.mask[0]

    assert seen["structural"] is False
    assert seen["transient"] is True, (
        "a between-fit session declared transient keeps the fresh fit in the "
        "mask; declared structural it does not -- and `run_daily.py` declares "
        "structural")


# ------------------------------- the rank's own uncertainty is not carried


def test_ecdf_rank_from_an_empty_window_is_assimilated_at_full_confidence():
    """An absence of reference history becomes a confident observation of 0.5.

    `standardise` returns the documented uninformative midpoint 0.5 when the
    pillar's ECDF reference window is empty, and flags PARTIAL_COVERAGE. But
    no pillar supplies a per-observation estimation variance -- 0 of the 777
    stored vintages carry one -- so that 0.5 reaches the Kalman with
    `estimation_variance=None` and is assimilated at `r0_default`, the SAME
    observation noise as a rank backed by a full five-year window.

    Consequence, measured on the real archive: admitting Hawkes to the D2
    mask today puts this 0.5 into the composite at half the weight and moves
    the published CSRS from 0.0900 to 0.2950 on no information at all. That
    is why the warm-up gate must not be relaxed ahead of the reference
    history -- see docs/DECISION-REGISTER-2026-10-26.md.
    """
    from seraph.orchestration.standardize import standardise

    empty_rank, empty_var, empty_warnings = standardise(
        0.2001, window=[], raw_variance=None, pillar="hawkes")
    full_rank, full_var, full_warnings = standardise(
        0.2001, window=list(range(1260)), raw_variance=None, pillar="hawkes")

    assert empty_rank == 0.5, "no reference distribution -> midpoint"
    assert [w.code for w in empty_warnings] == ["PARTIAL_COVERAGE"]
    assert full_warnings == ()
    # neither carries an estimation variance, so neither is down-weighted
    assert empty_var is None and full_var is None

    curve = SaturatingNoise()
    assert curve.r(0.0, empty_var) == curve.r(0.0, full_var), (
        "a rank from zero observations is given the same observation noise "
        "as a rank from a full window")

    # and the composite consequence, with the official pure score()
    weights = _weights()
    rmt_end = datetime(2026, 10, 22, 15, 30, tzinfo=IST)
    decide = ist_timestamp(datetime(2026, 10, 22, 15, 30, tzinfo=IST))

    rec = KalmanReconciler(session_dates=SESSIONS,
                           h_bars=(HAWKES_NATIVE_CADENCE_BARS, 75.0, 75.0))
    ok(rec.update([observed("rmt", rmt_end, value=0.09523809523809523)]))
    rmt_only = ok(score(reconciled=ok(rec.state_at(decide)),
                        xi=(1 / 3, 1 / 3, 1 / 3), weights=weights,
                        xi_mode="uniform"))

    rec = KalmanReconciler(session_dates=SESSIONS,
                           h_bars=(HAWKES_NATIVE_CADENCE_BARS, 75.0, 75.0))
    ok(rec.update([observed("rmt", rmt_end, value=0.09523809523809523)]))
    ok(rec.update([observed("hawkes", rmt_end, value=empty_rank)]))
    with_hawkes = ok(score(reconciled=ok(rec.state_at(decide)),
                           xi=(1 / 3, 1 / 3, 1 / 3), weights=weights,
                           xi_mode="uniform"))

    assert with_hawkes.mask == (True, True, False)
    assert with_hawkes.csrs > rmt_only.csrs, (
        "an uninformative 0.5 RAISES the composite above the RMT-only value")
    # it drags the composite toward the 0.5 prior and away from the reading
    # RMT actually supplied. The MAGNITUDE depends on how far the filtered RMT
    # state has converged, so it is not asserted here: on the real 254-session
    # replay, where x_rmt has converged to 0.0900, the same mechanism moves the
    # composite to 0.2950 (+0.2050). This two-step filter still sits near its
    # own 0.5 prior, so only the direction is checkable.
    assert abs(with_hawkes.csrs - 0.5) < abs(rmt_only.csrs - 0.5)
