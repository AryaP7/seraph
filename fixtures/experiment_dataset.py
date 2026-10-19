# T0 — supplied dataset for the C10 experiment runner (T10).
"""A small, deterministic labelled dataset that exercises the runner.

T10's acceptance is explicit: "A small supplied valid dataset exercises
runner/configuration/report plumbing; full expensive scientific evaluation is
separate." This is that dataset. It is **synthetic and labelled as such** — no
number produced from it is a finding about Indian equities, and
`PROVENANCE` says so in a field that travels with the data rather than in a
comment a report generator can forget to read.

What it is built to exercise, specifically:

* **Structural absence, as a guard.** Hawkes coverage is withheld from the two
  pre-2015 epochs, exactly as the real corpus withholds it. Running the
  committed design against this produces **no** `structural_pillar_absence`
  row, and that is the correct outcome, not a gap in the fixture: FR35 splits
  the tables precisely so that no configuration ever asks for a pillar its
  epochs lack — Table A is the Hawkes-covered epochs, Tables B and C are
  RMT/Hamilton only. The withheld coverage is what makes that split
  *checkable* rather than asserted, and the runner's guard is exercised
  directly by a test that hands it a configuration the design would never
  emit.
* **Both reconciliation modes.** FR36 runs each protocol twice, so each epoch
  carries `kalman` and `forward_fill` states.
* **A fold that cannot be scored.** `degenerate_epoch` has one label class, so
  AUC is undefined there and the runner must say so rather than report 0.5.
* **A mildly informative signal**, so a measured AUC is neither 0.5 nor 1.0
  and the plumbing is visibly carrying numbers rather than constants.

The signal is a logistic function of the label plus seeded noise. That makes
AUC comfortably above chance by construction — which is the point for a
plumbing test and is precisely why this dataset must never be presented as
evidence. It demonstrates that the runner computes, not that SERAPH predicts.
"""
from __future__ import annotations

import numpy as np

from seraph.shared_types import PillarId, ReconciledState
from seraph.validation.epochs import EPOCH_BREAKS, HAWKES_COVERED
from seraph.validation.experiment import LabelledEpoch, Observation

PROVENANCE = (
    "SYNTHETIC fixture (fixtures/experiment_dataset.py). Generated from a "
    "seeded RNG to exercise the experiment runner's plumbing. Not market data; "
    "no result computed from it is evidence about any market."
)

#: Pillars available before 2015. Hawkes needs intraday bars that do not exist
#: for those epochs (SPEC §4), which is why Table B exists at all.
PRE_2015_COVERAGE: frozenset[PillarId] = frozenset({"rmt", "hamilton"})
FULL_COVERAGE: frozenset[PillarId] = frozenset({"hawkes", "rmt", "hamilton"})

_MODES = ("kalman", "forward_fill")


#: Mean shift applied to a positive observation, against SIGMA below. Kept
#: small on purpose: at 0.35/0.09 the fixture produced AUCs of 0.996, which is
#: indistinguishable at a glance from a spectacular real result. A plumbing
#: fixture should be obviously mid-range, so that nobody reading a runner
#: smoke test mistakes it for evidence.
LIFT = 0.10
SIGMA = 0.13


def _xi(label: int, informative: bool) -> tuple[float, float, float]:
    """The regime mixture at one instant, shifting toward the crisis regime.

    This has to be NON-UNIFORM or the R5 control is vacuous. Every Table B
    configuration is run twice, `xi_mode="hamilton"` against
    `xi_mode="uniform"`, because ARCHITECTURE R5 warns that Hamilton is both a
    signal and the weighting over signals: if the two diverge sharply, the
    coupling is doing the work and the report must say so.

    An earlier version of this fixture emitted `(1/3, 1/3, 1/3)` everywhere.
    The two xi modes then produced byte-identical AUCs by construction — so
    the control ran, reported agreement, and proved nothing. Worse than
    useless: a reader would have taken matching columns as evidence that the
    coupling was not doing the work.
    """
    if not informative:
        return (1 / 3, 1 / 3, 1 / 3)
    # Sums to exactly 1.0 at both label values, within Simplex3's tolerance.
    return (0.70 - 0.45 * label, 0.20, 0.10 + 0.45 * label)


def _states(rng: np.random.Generator, labels: np.ndarray, mode: str,
            epoch: str, informative: bool) -> tuple[Observation, ...]:
    """One mode's observations for one epoch.

    `x_hat` is clipped into [0, 1] because that is C9's own domain for the
    pillar vector; letting the fixture emit values outside it would test the
    clip in `score()` rather than the runner.

    Timestamps run up to the epoch's own labelled break date, so the positive
    block sits where the FR32 crisis window actually is. The metrics index by
    position rather than by date, so this changes no number — it means a row
    can be read against the epoch it claims to come from.
    """
    out = []
    positives = int((labels == 1).sum())
    start = (np.datetime64(EPOCH_BREAKS[epoch][0])
             - np.timedelta64(int(labels.size) - positives, "D"))
    for i, label in enumerate(labels):
        lift = LIFT * float(label) if informative else 0.0
        draw = rng.normal(0.35 + lift, SIGMA, size=3)
        x_hat = tuple(float(v) for v in np.clip(draw, 0.0, 1.0))
        ts = (start + np.timedelta64(i, "D")).item()
        stamp = f"{ts.isoformat()}T09:15:00+05:30"
        out.append(Observation(
            state=ReconciledState(
                ts=stamp, x_hat=x_hat,
                P=((0.01, 0.0, 0.0), (0.0, 0.01, 0.0), (0.0, 0.0, 0.01)),
                tau_last_update=(stamp, stamp, stamp),
                mask=(True, True, True), mode=mode),
            xi=_xi(label, informative),
            label=int(label)))
    return tuple(out)


def build(
    *,
    seed: int = 20261020,
    per_epoch: int = 48,
    positive_fraction: float = 0.25,
    degenerate_epoch: str | None = None,
    informative: bool = True,
) -> dict[str, LabelledEpoch]:
    """A `Dataset` covering all six labelled epochs.

    `degenerate_epoch` is given a single label class on purpose, so a caller can
    exercise the `single_class_fold` path without hand-building a dataset.
    """
    rng = np.random.default_rng(seed)
    dataset: dict[str, LabelledEpoch] = {}
    positives = max(1, int(per_epoch * positive_fraction))

    for epoch in EPOCH_BREAKS:
        labels = np.zeros(per_epoch, dtype=int)
        if epoch == degenerate_epoch:
            pass  # all zeros: AUC is undefined, which is the thing being tested
        else:
            # The positives sit at the END of the window, so a score that rises
            # before them produces a real lead time rather than an artefact of
            # positives being scattered through the series.
            labels[-positives:] = 1
        dataset[epoch] = LabelledEpoch(
            epoch=epoch,
            pillar_coverage=(FULL_COVERAGE if epoch in HAWKES_COVERED
                             else PRE_2015_COVERAGE),
            observations={m: _states(rng, labels, m, epoch, informative)
                          for m in _MODES})
    return dataset


def without_epoch(dataset: dict[str, LabelledEpoch], epoch: str
                  ) -> dict[str, LabelledEpoch]:
    """The same dataset with one epoch dropped entirely.

    `EpochId` is a closed `Literal` over the six labelled breaks, so a row can
    never name an epoch outside them — which means the runner's "no such
    epoch" path is reachable only for a VALID epoch the dataset does not
    cover. That is the real case: a corpus that has not been loaded far enough
    back, not a typo.
    """
    return {e: b for e, b in dataset.items() if e != epoch}


def without_mode(dataset: dict[str, LabelledEpoch], epoch: str, mode: str
                 ) -> dict[str, LabelledEpoch]:
    """The same dataset with one epoch's mode removed (FR36 absence path)."""
    block = dataset[epoch]
    kept = {m: o for m, o in block.observations.items() if m != mode}
    out = dict(dataset)
    out[epoch] = LabelledEpoch(epoch=block.epoch,
                               pillar_coverage=block.pillar_coverage,
                               observations=kept)
    return out
