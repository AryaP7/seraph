# C10 — Validation Harness (FR34): sensitivity analyses.
"""FR34 names four axes. Exactly one of them is C10's to vary.

> "The system shall run sensitivity analyses varying rolling-window length,
> Hawkes kernel order K, Absorption-Ratio component count, and
> `kappa_miss/kappa_fa`."

Only `kappa_miss/kappa_fa` lives in the fusion/calibration layer. The other
three are pillar estimator parameters owned by C4, C5 and C6 — varying them
means re-running the estimators over the real corpus, which is a different and
much more expensive job than re-weighting an existing reconciled state. The
modules that own them already expose them as module constants precisely so
FR34's sweep can reach them (`jump_extraction.LOCAL_WINDOW_K`,
`hawkes.engine.SECTOR_AMBER_MULTIPLE`, the RMT component weights), and this
module reports them as **declared, unavailable axes with their owner** rather
than quietly presenting a one-axis sweep as the whole of FR34.

**A sweep is a set of designs, not one design run several ways.** The loss
ratio is inside the pre-registration hash, so varying it produces a different
design with a different hash — which is correct and is the whole point: a
result cannot be produced under one loss ratio and read as though it came from
another. `sweep()` therefore takes already-committed design files, one per
point, and refuses to synthesise them. If it built and hashed designs itself
after seeing a result, it would be a mechanism for choosing the loss ratio
that flatters a number, which is exactly what D5 exists to prevent.

Every row this produces is marked `is_sensitivity=True` and the primary metric
is reported separately. An ablation is descriptive (D5): no point on a sweep
is selected as best and reported as a headline.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np

from seraph.shared_types import ContractViolation, Err, FrozenModel, Ok, err, ok
from seraph.validation.experiment import Dataset, ExperimentReport
from seraph.validation.experiment import run as run_experiment


@dataclass(frozen=True)
class UnavailableAxis:
    """An FR34 axis this module cannot vary, and who owns it."""
    axis: str
    owner: str
    constant: str
    why: str


#: The three axes FR34 names that are not C10's. Stated rather than omitted:
#: a sweep over one of four axes that does not say so reads as a sweep over
#: FR34.
PILLAR_AXES: tuple[UnavailableAxis, ...] = (
    UnavailableAxis(
        axis="rolling-window length",
        owner="C4 (features) / C6 (RMT)",
        constant="jump_extraction local window K, RMT correlation window",
        why=("changing it re-derives every feature and re-estimates the "
             "pillar, so the reconciled states this runner consumes would "
             "have to be rebuilt from the corpus first"),
    ),
    UnavailableAxis(
        axis="Hawkes kernel order K",
        owner="C5 (Hawkes)",
        constant="seraph.pillars.hawkes.engine",
        why=("requires re-running the Hawkes MLE over 5-minute bars, which "
             "this installation does not have (FR1 needs a paid intraday "
             "subscription); the pillar is archived, not computed"),
    ),
    UnavailableAxis(
        axis="Absorption-Ratio component count",
        owner="C6 (RMT)",
        constant="seraph.pillars.rmt.engine component weights",
        why=("AR_t is derived in C4 and the component count changes the "
             "eigen-decomposition, so the RMT pillar must be recomputed "
             "rather than re-weighted"),
    ),
)


class SensitivityPoint(FrozenModel):
    """One design on the sweep, with the hash that identifies it."""
    label: str
    pre_registration_hash: str
    kappa_miss: float
    kappa_fa: float
    kappa_ratio: float
    amber_threshold: float
    calibration_max_iter: int
    measured_rows: int
    unavailable_rows: int
    #: Per-configuration means under this design, keyed by the configuration.
    mean_auc_by_configuration: dict[str, float]
    is_sensitivity: bool = True


class SensitivityReport(FrozenModel):
    points: tuple[SensitivityPoint, ...]
    unavailable_axes: tuple[dict, ...]
    note: str

    def swept_axes(self) -> dict[str, tuple[float, ...]]:
        """What actually varied across the committed designs."""
        return {
            "kappa_ratio": tuple(sorted({p.kappa_ratio for p in self.points})),
            "amber_threshold": tuple(
                sorted({p.amber_threshold for p in self.points})),
        }

    def spread(self, configuration: str) -> dict:
        """How one configuration's mean AUC moves across the sweep.

        The spread is the answer FR34 asks for. A single headline number would
        be a selection, and D5 forbids selecting a configuration and reporting
        it as the result.
        """
        vals = [p.mean_auc_by_configuration.get(configuration)
                for p in self.points]
        present = [v for v in vals if v is not None and np.isfinite(v)]
        if not present:
            return dict(points=len(self.points), measured=0, min=None,
                        max=None, range=None)
        return dict(points=len(self.points), measured=len(present),
                    min=min(present), max=max(present),
                    range=max(present) - min(present))

    def most_sensitive(self) -> tuple[str, ...]:
        """Configurations ordered by how far they move, widest first.

        This is a statement about STABILITY, not about quality: a
        configuration near the top moved a lot under a different loss ratio,
        which says its number is contingent. It is deliberately not a ranking
        of configurations by AUC, and nothing here picks a best point.
        """
        keys = {k for p in self.points for k in p.mean_auc_by_configuration}
        scored = []
        for key in keys:
            rng = self.spread(key)["range"]
            if rng is not None:
                scored.append((rng, key))
        return tuple(key for _, key in sorted(scored, reverse=True))


def _key(row) -> str:
    return (f"{row.table}:{'+'.join(row.pillar_subset)}:"
            f"{row.reconciliation_mode}:{row.xi_mode}")


def _summarise(label: str, report: ExperimentReport, design: dict
               ) -> SensitivityPoint:
    means = {}
    for summary in report.configurations():
        key = (f"{summary.table}:{'+'.join(summary.pillar_subset)}:"
               f"{summary.reconciliation_mode}:{summary.xi_mode}")
        means[key] = float(summary.mean_auc)
    kappa_miss = float(design.get("kappaMiss", 10.0))
    kappa_fa = float(design.get("kappaFa", 1.0))
    return SensitivityPoint(
        label=label,
        pre_registration_hash=report.pre_registration_hash,
        kappa_miss=kappa_miss, kappa_fa=kappa_fa,
        kappa_ratio=kappa_miss / kappa_fa if kappa_fa else float("inf"),
        amber_threshold=float(design.get("amberThreshold", float("nan"))),
        calibration_max_iter=report.calibration_max_iter,
        measured_rows=len(report.measured()),
        unavailable_rows=len(report.unavailable()),
        mean_auc_by_configuration=means)


def sweep(
    *,
    dataset: Dataset,
    designs: Sequence[tuple[str, Path]],
    tables: Sequence[str] = ("A", "B", "C"),
) -> Ok[SensitivityReport] | Err:
    """Run `dataset` under each committed design and report the spread.

    `designs` is `(label, path)` pairs, each path a pre-registration file
    already committed by a person. This function will not build one: see the
    module docstring — synthesising designs here would make the loss ratio
    something chosen after seeing a result.
    """
    import json

    if len(designs) < 2:
        return err(ContractViolation(
            field="designs",
            detail=("a sensitivity sweep needs at least two committed designs; "
                    "one design is a run, not a sweep")))

    seen: set[str] = set()
    points: list[SensitivityPoint] = []
    for label, path in designs:
        path = Path(path)
        result = run_experiment(dataset=dataset, preregistration=path,
                               tables=tables)
        if result.status == "error":
            return result
        report = result.value
        if report.pre_registration_hash in seen:
            return err(ContractViolation(
                field="designs",
                detail=(f"{label} has the same design hash as an earlier "
                        f"point, so nothing varied between them; a sweep over "
                        f"identical designs reports a spread of zero and "
                        f"looks like stability")))
        seen.add(report.pre_registration_hash)
        design = json.loads(path.read_text(encoding="utf-8")).get("design", {})
        points.append(_summarise(label, report, design))

    return ok(SensitivityReport(
        points=tuple(points),
        unavailable_axes=tuple(
            dict(axis=a.axis, owner=a.owner, constant=a.constant, why=a.why)
            for a in PILLAR_AXES),
        note=("FR34 names four axes; this sweep varies the one that lives in "
              "the fusion layer. The other three are pillar estimator "
              "parameters listed in `unavailable_axes` with their owners, and "
              "are not covered by these numbers. Every point is a separately "
              "hashed design, and no point is selected as best.")))
