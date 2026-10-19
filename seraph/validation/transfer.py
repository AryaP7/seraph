# C10 — Validation Harness (FR37, O9): fixed-weight cross-market transfer.
"""Apply NSE-calibrated weights to another market **without retraining**.

> FR37: "apply NSE-calibrated fusion weights, without retraining, to >=1
> additional emerging-market index and report out-of-sample AUC, scoped to the
> RMT + Hamilton subset unless intraday data for that market proves free and
> available."

O9's acceptance is unusually mechanical, and each clause is enforced here
rather than asserted in a report:

* *"Weight vectors bit-identical between NSE and second-market runs (verified
  by parameter-file hash)"* — the artefact is an input. This module imports no
  calibrator, so there is no code path that could refit; `calibrated_on` and
  `artefact_id` are copied onto the result, and the NSE run's own hash is
  carried beside them for the comparison O9 asks for.
* *"execution log contains no refit step"* — `refit` is a `Literal[False]`.
  It cannot be set to anything else, so a result asserting no refit cannot be
  produced by a path that did one.
* *"out-of-sample AUC reported on >=1 of {IDX, Ibovespa, JSE}"* — the market
  is named on the result, and a market outside that set is refused unless the
  caller declares it explicitly, so the scope cannot drift silently.

**The scoping is reported, never silently omitted.** SPEC O9 says so in as
many words. A three-pillar transfer needs the second market's intraday
history; without it the test is the RMT+Hamilton subset, and the result says
that in a field (`scope_reason`) rather than by being short one pillar.

**NFR20 is an open `[GAP]`**: the paper anticipates "moderate" degradation and
sets no bound. So `degradation` is a measurement with `bound=None`, and this
module will not call a transfer result a pass or a failure. Inventing a
threshold here would turn an acknowledged gap into a fabricated criterion.
"""
from __future__ import annotations

from typing import Literal, Sequence

import numpy as np

from seraph.shared_types import (
    ContractViolation,
    Err,
    FrozenModel,
    FusionWeights,
    Ok,
    PillarId,
    Sha256,
    err,
    ok,
)
from seraph.validation.ablation import score_subset
from seraph.validation.experiment import Observation, XiMode
from seraph.validation.harness import (
    auc,
    leakage_check,
    mean_lead_time,
    precision_at_recall,
)

#: The three candidate markets SPEC O9 names. SPEC OQ14 ("IDX, Ibovespa or
#: JSE?") is still open, which is why all three are permitted and none is the
#: default.
CANDIDATE_MARKETS = ("IDX", "Ibovespa", "JSE")

#: FR37's default scope. Hawkes needs 5-minute bars for the target market; the
#: subset widens only when the caller declares that it has them.
DEFAULT_SUBSET: tuple[PillarId, ...] = ("rmt", "hamilton")


class TransferResult(FrozenModel):
    source_market: Literal["NSE"] = "NSE"
    target_market: str
    pillar_subset: tuple[PillarId, ...]
    xi_mode: XiMode
    #: Literal[False]: a result claiming no refit cannot come from a path that
    #: refitted, because there is no value this field can take that says it did.
    refit: Literal[False] = False
    weights_artefact_id: Sha256
    calibrated_on_epochs: tuple[str, ...]
    out_of_sample_auc: float
    mean_lead_time_days: float
    precision_at_fixed_recall: float
    observations: int
    scope_reason: str
    #: NFR20 is `[GAP]`. A measurement with no bound, and deliberately no verdict.
    nse_reference_auc: float | None = None
    degradation: float | None = None
    degradation_bound: None = None
    bound_note: str = (
        "NFR20 is an open [GAP] in SPEC: the paper anticipates 'moderate' "
        "degradation and sets no minimum acceptable bound. This result is "
        "therefore neither a pass nor a failure.")


def transfer(
    *,
    weights: FusionWeights,
    target_market: str,
    observations: Sequence[Observation],
    subset: tuple[PillarId, ...] = DEFAULT_SUBSET,
    xi_mode: XiMode = "hamilton",
    target_epochs: Sequence[str] = (),
    amber_threshold: float,
    target_recall: float = 0.8,
    nse_reference_auc: float | None = None,
    intraday_available: bool = False,
    allow_market_outside_spec: bool = False,
) -> Ok[TransferResult] | Err:
    """Score `observations` under weights calibrated elsewhere.

    `weights` arrives already fitted. Nothing in this module can change it:
    the calibrator is not imported, so "without retraining" is a property of
    the dependency graph rather than a promise in a docstring.
    """
    if target_market not in CANDIDATE_MARKETS and not allow_market_outside_spec:
        return err(ContractViolation(
            field="target_market",
            detail=(f"{target_market!r} is not one of {CANDIDATE_MARKETS}, "
                    f"which SPEC O9 names (OQ14 is still open between them). "
                    f"Pass allow_market_outside_spec=True to widen the scope "
                    f"deliberately rather than by accident.")))

    if "hawkes" in subset and not intraday_available:
        return err(ContractViolation(
            field="pillar_subset",
            detail=("FR37 scopes the transfer test to RMT+Hamilton unless "
                    "intraday data for the target market is free and "
                    "available. A three-pillar transfer without the target's "
                    "5-minute bars would carry a Hawkes coordinate that no "
                    "data for this market supports.")))

    if not observations:
        return err(ContractViolation(
            field="observations",
            detail=f"no observations supplied for {target_market}"))

    # "Out-of-sample" is the whole claim. When the caller can say which epochs
    # the target sample covers, the same D5 machine check the ablation uses
    # decides it — rather than the reader assuming a different market implies
    # a different sample. Caught exactly this in the CLI's own stand-in path,
    # where the donor weights were fitted on the epoch being scored.
    if target_epochs and leakage_check(weights, target_epochs) != "clean":
        shared = sorted(set(target_epochs)
                        & set(weights.calibrated_on.epochs))
        return err(ContractViolation(
            field="target_epochs",
            detail=(f"the artefact was calibrated on {', '.join(shared)}, "
                    f"which the {target_market} sample also covers. An AUC "
                    f"from this pairing is in-sample and FR37 asks for an "
                    f"out-of-sample one.")))

    labels = [o.label for o in observations]
    if len(set(labels)) < 2:
        return err(ContractViolation(
            field="observations",
            detail=(f"{target_market} has a single label class "
                    f"({sum(labels)} positive of {len(labels)}), so an "
                    f"out-of-sample AUC is undefined. FR37 asks for a "
                    f"reported AUC, and 0.5 would not be one.")))

    scores = []
    for obs in observations:
        scored = score_subset(reconciled=obs.state, xi=obs.xi, weights=weights,
                              subset=subset, xi_mode=xi_mode)
        if scored.status == "error":
            return err(ContractViolation(
                field="scoring",
                detail=(f"scoring {target_market} at {obs.state.ts} returned "
                        f"{scored.error.kind}")))
        scores.append(scored.value.csrs)

    measured = auc(scores, labels)
    if not np.isfinite(measured):
        return err(ContractViolation(
            field="out_of_sample_auc",
            detail=f"AUC is undefined on the {target_market} sample"))

    if intraday_available and "hawkes" in subset:
        reason = (f"three-pillar transfer: the caller declared free, available "
                  f"intraday data for {target_market}, which FR37 makes the "
                  f"condition for widening beyond RMT+Hamilton")
    else:
        reason = (f"RMT+Hamilton only. FR37's default scope: Hawkes needs "
                  f"5-minute bars for {target_market} and none are declared. "
                  f"Reported rather than omitted, per SPEC O9.")

    return ok(TransferResult(
        target_market=target_market,
        pillar_subset=subset,
        xi_mode=xi_mode,
        weights_artefact_id=weights.artefact_id,
        calibrated_on_epochs=tuple(weights.calibrated_on.epochs),
        out_of_sample_auc=float(measured),
        mean_lead_time_days=float(mean_lead_time(scores, labels,
                                                 amber_threshold)),
        precision_at_fixed_recall=float(precision_at_recall(scores, labels,
                                                            target_recall)),
        observations=len(observations),
        scope_reason=reason,
        nse_reference_auc=nse_reference_auc,
        degradation=(None if nse_reference_auc is None
                     else float(nse_reference_auc - measured))))


def weights_are_bit_identical(a: FusionWeights, b: FusionWeights) -> bool:
    """O9's acceptance check: the NSE and transfer runs used the same artefact.

    Compares the content hash **and** the weight rows. The hash alone would
    make this a test of the hash function; the rows alone would miss a
    differing calibration config that the hash is supposed to cover.
    """
    return a.artefact_id == b.artefact_id and a.w == b.w
