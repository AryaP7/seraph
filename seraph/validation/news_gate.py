"""NI17 — the news extraction release gate, with its thresholds frozen first.

The plan (§9A) sets these and is explicit that they are "proposed engineering
requirements, not measured achievements or universal statistical guarantees":

* >= 95% precision for promoted event/target links
* >= 90% recall on supported event classes
* >= 98% accuracy for numeric/unit/legal-stage fields
* zero known look-ahead / context breaches
* all adversarial regression cases fixed

They are defined **here, in code, before any evaluation runs** — the same
discipline D5(d) applies to the market-side pre-registration, and for the same
reason: a threshold chosen after seeing the number is not a threshold.

Several ways a gate like this passes when it should not, each closed below:

**An empty or missing slice.** A slice with no labelled examples has no
accuracy, and `None` is not `< threshold`, so an absent metric used to sail
through. Every required slice must now be present AND evaluated.

**Precision inflated by true negatives.** Counting "we correctly predicted no
link" as a success makes precision rise as the corpus fills with documents
that have nothing to link. Link precision is now computed over PREDICTED
links only, and every extra incorrect link counts against it.

**Recall that ignores abstentions.** A system that abstains on everything
scores perfectly on what it answered. Supported-class recall counts a missed
supported event as missed whether the cause was a wrong answer or no answer.

**Recall credited for correctly rejecting a negative** (audit A01,
2026-10-18). A corpus is deliberately full of hard negatives — documents that
are *not* a supported event. Agreeing that a negative is a negative is
specificity, not recall, and counting it in the recall numerator produced
*95% recall* on a run that found **none** of the five supported events
present. `class_recall` is now over SUPPORTED POSITIVE gold only; negatives
are scored separately as `negative_specificity`, whose `extra` counts the
false positives. `negative_specificity` is a gate added by that audit and
frozen here, before the evaluation that uses it, exactly like the others.

**Fields averaged together.** A 98% field gate met by numerics while legal
stage sits at 60% is not a 98% field gate. Each required field is scored and
gated separately.

**Breach counts taken on trust.** `lookahead_breaches=0` as an argument is a
claim, not a check. The gate requires evidence that the check RAN.

**Supplied corpus counts.** Reviewer independence and split membership are
asserted from the corpus itself, not from a number passed in.
"""
from __future__ import annotations

from dataclasses import dataclass, field

#: Frozen before evaluation. Changing one is a decision to be recorded.
GATES = {
    "link_precision": 0.95,
    # Over SUPPORTED POSITIVE gold events only — see `negative_specificity`.
    "class_recall": 0.90,
    # Added by the 2026-10-18 audit (A01) and frozen here before the
    # evaluation that reads it. The plan's §9A list has no specificity number
    # because it assumed recall was measured over positives; once the two are
    # separated, a channel that labels one hard negative in ten as a live
    # event is noise whatever its recall says. Declared at 0.95 for that
    # reason, not chosen after seeing a result.
    "negative_specificity": 0.95,
    # Each field is gated at the same level, separately. Averaging them lets a
    # strong field carry a weak one.
    "field_numeric": 0.98,
    "field_unit": 0.98,
    "field_action": 0.98,
    "field_legal_stage": 0.98,
    "lookahead_breaches": 0,
}

#: Every slice that must be present and evaluated. A gate that passes because
#: a metric is missing is worse than one that fails.
REQUIRED_SLICES = ("link_precision", "class_recall", "negative_specificity",
                   "field_numeric", "field_unit", "field_action",
                   "field_legal_stage")

#: Gold event classes that are NOT a supported event. A document labelled one
#: of these is a negative: getting it right is specificity, and it may never
#: appear in a recall numerator or denominator.
NEGATIVE_CLASSES = frozenset({"other", "unknown", "none", ""})


def is_supported_event(label) -> bool:
    """Is this gold label a supported event, rather than a hard negative?"""
    return bool(label) and str(label).strip().lower() not in NEGATIVE_CLASSES

#: The corpus the plan specifies.
REQUIRED_CORPUS = {
    "total": 600, "indian_policy": 120, "foreign_trade_regulation": 120,
    "company_operations": 120, "macro_monetary": 80, "logistics_hazards": 80,
    "hard_negatives": 80, "non_english": 100, "locked_test": 200,
    "reviewers": 2,
}

#: Below this many scored examples a slice reports `unevaluated` — which now
#: FAILS the gate rather than being quietly skipped.
MIN_SLICE = 20


@dataclass
class SliceResult:
    """One metric, with the counts that produced it.

    `predicted` and `relevant` are what make precision and recall honest:
    precision is over predictions, recall is over the things that should have
    been found, and neither is over "documents we looked at".
    """

    name: str
    correct: int = 0
    predicted: int = 0          # precision denominator
    relevant: int = 0           # recall denominator
    abstained: int = 0
    extra: int = 0              # predicted links that should not exist
    evaluated: bool = True
    note: str = ""

    @property
    def scored(self) -> int:
        if self.name.endswith("recall"):
            return self.relevant
        return self.predicted

    @property
    def accuracy(self) -> float | None:
        if not self.evaluated or self.scored <= 0:
            return None
        return self.correct / self.scored

    def describe(self) -> dict:
        return dict(
            name=self.name, correct=self.correct, predicted=self.predicted,
            relevant=self.relevant, abstained=self.abstained, extra=self.extra,
            scored=self.scored, evaluated=self.evaluated,
            accuracy=None if self.accuracy is None else round(self.accuracy, 4),
            abstention_rate=(round(self.abstained / self.relevant, 4)
                             if self.name.endswith("recall") and self.relevant
                             else None),
            # For `negative_specificity` this is the false-positive rate: how
            # often a hard negative was promoted to a supported event. It is
            # reported because a specificity of 0.95 and "5% of negatives
            # became live events" are the same number read two ways, and the
            # second is the one an operator acts on.
            false_positive_rate=(round(self.extra / self.scored, 4)
                                 if self.name == "negative_specificity"
                                 and self.scored else None),
            note=self.note)


@dataclass
class Checks:
    """Evidence that the non-metric checks actually RAN.

    `lookahead_breaches=0` passed as an argument is a claim. A gate that
    accepts it is trusting the caller about the thing most worth verifying.
    """

    lookahead_ran: bool = False
    lookahead_breaches: int = 0
    adversarial_ran: bool = False
    adversarial_total: int = 0
    adversarial_outstanding: int = 0

    def describe(self) -> dict:
        return dict(lookahead_ran=self.lookahead_ran,
                    lookahead_breaches=self.lookahead_breaches,
                    adversarial_ran=self.adversarial_ran,
                    adversarial_total=self.adversarial_total,
                    adversarial_outstanding=self.adversarial_outstanding)


@dataclass
class GateResult:
    corpus: dict = field(default_factory=dict)
    slices: list = field(default_factory=list)
    checks: Checks = field(default_factory=Checks)
    corpus_sufficient: bool = False
    thresholds_met: bool = False
    slices_complete: bool = False
    provisional: bool = True
    reasons: list = field(default_factory=list)
    #: {gold class: {found, missed, confused_with: {...}}}. Reported, not
    #: gated: an aggregate that hides which class is failing is the defect
    #: A01 describes, one level up.
    per_class: dict = field(default_factory=dict)

    @property
    def gate_passed(self) -> bool:
        """Every condition, never a subset."""
        return (self.corpus_sufficient and self.thresholds_met
                and self.slices_complete and not self.provisional)

    def describe(self) -> dict:
        return dict(
            gate_passed=self.gate_passed,
            corpus_sufficient=self.corpus_sufficient,
            thresholds_met=self.thresholds_met,
            slices_complete=self.slices_complete,
            provisional=self.provisional,
            reasons=list(self.reasons), thresholds=dict(GATES),
            required_corpus=dict(REQUIRED_CORPUS),
            required_slices=list(REQUIRED_SLICES),
            corpus=dict(self.corpus), checks=self.checks.describe(),
            slices=[s.describe() for s in self.slices],
            per_class=dict(self.per_class),
            note=("gate_passed requires a sufficient corpus AND every required "
                  "slice present and evaluated AND all thresholds met AND a "
                  "non-provisional labelling. A missing metric fails; it does "
                  "not pass by absence. `class_recall` is over supported "
                  "positive events only; correctly rejecting a hard negative "
                  "is `negative_specificity` and earns no recall credit"))


def check_corpus(counts: dict, reviewers: int) -> tuple[bool, list]:
    reasons = []
    for key, required in REQUIRED_CORPUS.items():
        if key == "reviewers":
            continue
        have = counts.get(key, 0)
        if have < required:
            reasons.append(f"{key}: {have} of {required} required")
    if reviewers < REQUIRED_CORPUS["reviewers"]:
        reasons.append(
            f"{reviewers} reviewer(s) of {REQUIRED_CORPUS['reviewers']} "
            f"required: inter-annotator reliability cannot be claimed and the "
            f"corpus is provisional")
    return (not reasons), reasons


def evaluate(slices: list, corpus_counts: dict, *, reviewers: int,
             checks: Checks | None = None,
             per_class: dict | None = None) -> GateResult:
    """Score the gate. Every condition is reported, never short-circuited."""
    checks = checks or Checks()
    sufficient, reasons = check_corpus(corpus_counts, reviewers)
    by_name = {item.name: item for item in slices}

    # --- every required slice must exist and be evaluated ---------------
    complete = True
    for name in REQUIRED_SLICES:
        item = by_name.get(name)
        if item is None:
            complete = False
            reasons.append(f"{name}: MISSING. A gate does not pass because a "
                           f"metric was absent")
            continue
        if item.scored < MIN_SLICE:
            item.evaluated = False
            item.note = (f"only {item.scored} scored example(s); below the "
                         f"{MIN_SLICE} minimum")
        if not item.evaluated:
            complete = False
            reasons.append(f"{name}: UNEVALUATED ({item.note or 'no reason'})")
        elif item.accuracy is None:
            complete = False
            reasons.append(f"{name}: no denominator, so no measurement")

    # --- thresholds ------------------------------------------------------
    met = True
    for name, threshold in GATES.items():
        if name == "lookahead_breaches":
            continue
        item = by_name.get(name)
        if item is None or item.accuracy is None:
            met = False
            continue
        if item.accuracy < threshold:
            met = False
            reasons.append(f"{name}: {item.accuracy:.1%} below the "
                           f"{threshold:.0%} gate (n={item.scored} scored)")
        if item.extra:
            reasons.append(f"{name}: {item.extra} incorrect extra prediction(s) "
                           f"counted against precision")

    # --- the checks must have RUN ---------------------------------------
    if not checks.lookahead_ran:
        met = False
        reasons.append("look-ahead check did not run: a zero that was never "
                       "measured is a claim, not a result")
    elif checks.lookahead_breaches > GATES["lookahead_breaches"]:
        met = False
        reasons.append(f"{checks.lookahead_breaches} look-ahead breach(es): "
                       f"the gate requires zero")
    if not checks.adversarial_ran:
        met = False
        reasons.append("adversarial regression cases did not run")
    elif checks.adversarial_outstanding:
        met = False
        reasons.append(f"{checks.adversarial_outstanding} of "
                       f"{checks.adversarial_total} adversarial case(s) "
                       f"outstanding")

    return GateResult(
        corpus=corpus_counts, slices=slices, checks=checks,
        corpus_sufficient=sufficient, thresholds_met=met,
        slices_complete=complete,
        provisional=reviewers < REQUIRED_CORPUS["reviewers"],
        reasons=reasons, per_class=dict(per_class or {}))
