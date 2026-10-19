"""NI17 — the release gate, and the many ways one passes when it should not.

The plan (§9A) freezes these gates and says plainly that they are "proposed
engineering requirements, not measured achievements or universal statistical
guarantees". It also specifies the corpus: 600 documents, six groups, 100+
non-English, a 300/100/200 chronological split, and **two independent
reviewers**. This repository has ~280 documents and one labeller.

Most of this file is adversarial: each test is a way a gate can report success
on absent or inflated evidence, and every one of them is easy to write by
accident.

* a **missing** metric — `None` is not `< threshold`, so an absent slice used
  to sail through
* an **empty** metric — a rate over zero examples
* **precision inflated by true negatives** — counting "correctly predicted no
  link" as a success makes precision rise as irrelevant documents are added
* **extra predictions ignored** — a system that links everything to everything
  scores perfectly on the links it got right
* **recall that ignores abstentions** — abstain on everything, score 100% on
  what you answered
* **fields averaged together** — a 98% field gate met by numerics while legal
  stage sits at 60%
* **breach counts taken on trust** — `lookahead_breaches=0` as an argument is
  a claim, not a result
"""
from __future__ import annotations

import pathlib
import subprocess
import sys

import pytest

from seraph.validation.news_benchmark_labels import (
    GROUPS, LABELLED, LABELLER_COUNT, LABELLER_NOTE)
from seraph.validation.news_gate import (
    GATES, MIN_SLICE, REQUIRED_CORPUS, REQUIRED_SLICES, Checks, SliceResult,
    check_corpus, evaluate)

ROOT = pathlib.Path(__file__).resolve().parents[1]


def good_slices() -> list:
    """Every required slice, comfortably passing."""
    out = []
    for name in REQUIRED_SLICES:
        if name.endswith("recall"):
            out.append(SliceResult(name, correct=500, relevant=500))
        else:
            out.append(SliceResult(name, correct=500, predicted=500))
    return out


def full_corpus() -> dict:
    return {k: v for k, v in REQUIRED_CORPUS.items() if k != "reviewers"}


def ran_checks() -> Checks:
    return Checks(lookahead_ran=True, lookahead_breaches=0,
                  adversarial_ran=True, adversarial_total=8,
                  adversarial_outstanding=0)


def test_the_gate_is_passable():
    """Otherwise it is theatre rather than a threshold."""
    result = evaluate(good_slices(), full_corpus(), reviewers=2,
                      checks=ran_checks())
    assert result.gate_passed is True


# ------------------------- it cannot pass on absent evidence

@pytest.mark.parametrize("missing", sorted(REQUIRED_SLICES))
def test_a_missing_metric_fails_rather_than_passing_by_absence(missing):
    """`None` is not `< threshold`, so an absent slice used to sail through."""
    slices = [s for s in good_slices() if s.name != missing]
    result = evaluate(slices, full_corpus(), reviewers=2, checks=ran_checks())
    assert result.gate_passed is False
    assert result.slices_complete is False
    assert any(missing in r and "MISSING" in r for r in result.reasons)


def test_an_empty_metric_fails():
    slices = [s for s in good_slices() if s.name != "field_unit"]
    slices.append(SliceResult("field_unit", correct=0, predicted=0))
    result = evaluate(slices, full_corpus(), reviewers=2, checks=ran_checks())
    assert result.gate_passed is False


def test_a_slice_below_the_minimum_fails_rather_than_being_skipped():
    """A percentage over six examples cannot support a 95% threshold. It used
    to be reported `unevaluated` and then quietly not counted."""
    slices = [s for s in good_slices() if s.name != "link_precision"]
    slices.append(SliceResult("link_precision", correct=6, predicted=6))
    result = evaluate(slices, full_corpus(), reviewers=2, checks=ran_checks())
    assert result.gate_passed is False
    assert any("UNEVALUATED" in r for r in result.reasons)
    assert MIN_SLICE == 20


def test_an_unrun_lookahead_check_fails_the_gate():
    """A zero that was never measured is a claim, not a result."""
    result = evaluate(good_slices(), full_corpus(), reviewers=2,
                      checks=Checks(lookahead_ran=False, adversarial_ran=True))
    assert result.gate_passed is False
    assert any("did not run" in r for r in result.reasons)


def test_an_unrun_adversarial_check_fails_the_gate():
    result = evaluate(good_slices(), full_corpus(), reviewers=2,
                      checks=Checks(lookahead_ran=True, adversarial_ran=False))
    assert result.gate_passed is False


def test_a_lookahead_breach_fails_the_gate():
    result = evaluate(good_slices(), full_corpus(), reviewers=2,
                      checks=Checks(lookahead_ran=True, lookahead_breaches=1,
                                    adversarial_ran=True))
    assert result.gate_passed is False


def test_an_outstanding_adversarial_case_fails_the_gate():
    result = evaluate(good_slices(), full_corpus(), reviewers=2,
                      checks=Checks(lookahead_ran=True, adversarial_ran=True,
                                    adversarial_total=8,
                                    adversarial_outstanding=1))
    assert result.gate_passed is False


# -------------------------------- denominators cannot be gamed

def test_precision_is_over_predictions_not_documents():
    """Counting "correctly predicted no link" as a success makes precision
    rise as the corpus fills with documents that have nothing to link."""
    item = SliceResult("link_precision", correct=9, predicted=10)
    assert item.scored == 10
    assert item.accuracy == pytest.approx(0.9)


def test_recall_is_over_what_should_have_been_found():
    item = SliceResult("class_recall", correct=9, relevant=10, abstained=5)
    assert item.scored == 10, "abstentions stay in the recall denominator"
    assert item.accuracy == pytest.approx(0.9)


def test_abstaining_on_everything_does_not_score_well():
    """A system that answers nothing must not score 100% on what it
    answered."""
    item = SliceResult("class_recall", correct=0, relevant=50, abstained=50)
    assert item.accuracy == 0.0
    assert item.describe()["abstention_rate"] == 1.0


def test_extra_incorrect_links_are_recorded_against_precision():
    """A system that links everything to everything scores perfectly on the
    links it got right."""
    slices = [s for s in good_slices() if s.name != "link_precision"]
    slices.append(SliceResult("link_precision", correct=500, predicted=500,
                              extra=40))
    result = evaluate(slices, full_corpus(), reviewers=2, checks=ran_checks())
    assert any("extra prediction" in r for r in result.reasons)


def test_fields_are_gated_separately_not_averaged():
    """A 98% field gate met by numerics while legal stage sits at 60% is not
    a 98% field gate."""
    slices = [s for s in good_slices() if s.name != "field_legal_stage"]
    slices.append(SliceResult("field_legal_stage", correct=60, predicted=100))
    result = evaluate(slices, full_corpus(), reviewers=2, checks=ran_checks())
    assert result.thresholds_met is False
    assert any("field_legal_stage" in r and "below" in r for r in result.reasons)
    assert {"field_numeric", "field_unit", "field_action",
            "field_legal_stage"} <= set(GATES)


# ---------------------------------------- the corpus and its reviewers

def test_perfect_scores_do_not_pass_an_insufficient_corpus():
    result = evaluate(good_slices(), {"total": 34}, reviewers=1,
                      checks=ran_checks())
    assert result.thresholds_met is True
    assert result.corpus_sufficient is False
    assert result.gate_passed is False


def test_a_single_reviewer_keeps_the_corpus_provisional():
    result = evaluate(good_slices(), full_corpus(), reviewers=1,
                      checks=ran_checks())
    assert result.provisional is True
    assert result.gate_passed is False


def test_corpus_check_names_every_shortfall_not_just_the_first():
    sufficient, reasons = check_corpus({"total": 34}, reviewers=1)
    assert sufficient is False
    assert len(reasons) >= 8


# ----------------------------------------------- the runner's contract

def test_release_check_exits_nonzero_when_the_gate_fails():
    """A pipeline must be able to fail on this. The current corpus is short,
    so the gate fails and the command must say so in its exit status."""
    done = subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts/run_news_gate.py"),
         "--release-check"], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode != 0
    assert "RELEASE CHECK FAILED" in done.stdout


def test_report_only_mode_exits_zero():
    """Printing the numbers is useful even while the corpus is known short."""
    done = subprocess.run(
        [sys.executable, "-I", str(ROOT / "scripts/run_news_gate.py")],
        cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0


def test_the_checks_are_actually_executed_by_the_runner():
    runner = (ROOT / "scripts/run_news_gate.py").read_text(encoding="utf-8")
    assert "def run_lookahead_check" in runner
    assert "def run_adversarial_check" in runner
    assert "lookahead_breaches=breaches" in runner, (
        "the runner passes a literal instead of a measured result")


# ------------------------------------------------------- the benchmark

def test_the_benchmark_declares_a_single_provisional_labeller():
    assert LABELLER_COUNT == 1
    assert "PROVISIONAL" in LABELLER_NOTE
    assert "no inter-annotator reliability is claimed" in LABELLER_NOTE


def test_every_labelled_example_records_why():
    for headline, klass, stage, sector, group, why in LABELLED:
        assert why and len(why) > 10, f"{headline[:50]}: no reasoning"
        assert group in GROUPS, f"{headline[:50]}: unknown group {group!r}"


def test_the_adversarial_group_holds_the_defects_actually_found():
    adversarial = [h for h, _k, _s, _sec, g, _w in LABELLED if g == "adversarial"]
    joined = " ".join(adversarial).lower()
    for signature in ("postponement of final determination",
                      "scheduling of full five-year reviews",
                      "revocation of the antidumping duty order",
                      "final debarment order",
                      "advance traveler information for rail",
                      "previously approved collections", "polar bears"):
        assert signature in joined, f"missing regression case: {signature}"
