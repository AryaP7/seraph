# C10 — FR35 / decision D5: pins on the pre-registered ablation design.
"""Workstream D triage of `docs/evidence/FR35-CONFIG-COUNT-CONFLICT.md`.
Reasoning and the approval question: `docs/evidence/BLOCKER-TRIAGE.md` §D-2.

**Nothing in `seraph/validation/` is changed by this file.** C10 belongs to
another owner and the design is pre-registration-hashed (D5(d)); these are
read-only assertions over `configuration_list()`.

---

## What SPEC settles, and it settles the headline conflict

`FR35-CONFIG-COUNT-CONFLICT.md` recommends restricting Table A to
Hawkes-containing subsets, taking the total from 20 to 14. **That
recommendation is wrong against SPEC, and must not be applied.** SPEC v3.1
line 243, which is authoritative over ARCHITECTURE (AGENTS.md §1: ARCHITECTURE
is "derived from SPEC, adds nothing new"):

> **FR35 `[v2]`** | The system shall produce **Table A** (7 subsets × 2
> reconciliation modes, on the 4 Hawkes-covered epochs) and **Table B** (3
> subsets × 2 modes, on the 2 pre-2015 epochs), each reporting AUC and mean
> lead time. | O7

That is explicit arithmetic with only one reading: Table A = 7 × 2 = **14**,
Table B = 3 × 2 = **6**, total **20**. `configuration_list()`'s 20 is
SPEC-correct, and ARCHITECTURE D5's repeated "14" is Table A's count — the
reading the conflict note stated fairly in its §3 and then rejected.

There is also a methodological reason the 7 subsets are right rather than
sloppy: `(rmt)` must appear in Table A **on the same 4 folds** as
`(hawkes,rmt)`, or there is nothing to difference against to isolate Hawkes's
marginal contribution. Dropping the non-Hawkes subsets from Table A would
destroy the within-table comparison D5(c) exists to report. Table B then
extends RMT/Hamilton coverage to the epochs Table A cannot reach — so the
3-subset overlap between tables is by design, with the fold set as the
distinguishing axis, which is exactly why D5(b) forbids pooling them into one
ranking.

`test_fr35_table_shape_is_spec_literal` pins that. It passes today.

## What SPEC does NOT settle — the real open question

SPEC FR35 puts Table B "**on the 2 pre-2015 epochs**" (→ 2 folds).
ARCHITECTURE D5(b) says "Table B subsets (RMT, Hamilton, RMT+Hamilton) use
**all 6** → **6 folds**". These genuinely conflict, and
`configuration_list()` implements D5(b)'s 6.

Corroborating that this is an unresolved authoring question rather than a
settled choice: `preregistration.py` defines

    #: Pre-2015 epochs — Table B, RMT/Hamilton subsets only.
    PRE_HAWKES_EPOCHS = ("gfc_2008", "taper_2013")

…documents it as Table B's epoch set, exports it from
`seraph/validation/__init__.py`, and then **never uses it** — Table B is built
from `EPOCHS` (all six). So the module contains both readings, one in code and
one in a docstring'd constant that no code path reaches.

`test_fr35_table_b_fold_count_is_the_open_question` is `xfail(strict=True)` and
pins it. It asserts SPEC FR35's literal reading (2 folds), which fails today.

**Either resolution retires this test, and that is the point:**

* **D5(b) wins (folds stay 6)** → delete this test and delete
  `PRE_HAWKES_EPOCHS`, whose docstring then states something false.
* **SPEC FR35 literal wins (folds become 2)** → this test XPASSes, which
  `strict=True` turns into a suite failure, forcing the marker off deliberately
  rather than by accident.

D5(d) requires this settled **before the first AUC is computed**, because the
fold count is inside the hashed design and "a result whose hash does not match
the committed file is not reportable".
"""
from __future__ import annotations

import pytest

from seraph.validation.preregistration import (
    EPOCHS,
    HAWKES_EPOCHS,
    PRE_HAWKES_EPOCHS,
    configuration_list,
)


def test_fr35_table_shape_is_spec_literal():
    """SPEC FR35 [v2]: Table A = 7 subsets × 2 modes; Table B = 3 × 2.

    Guards against `FR35-CONFIG-COUNT-CONFLICT.md` §5's recommendation, which
    would restrict Table A to Hawkes-containing subsets (8 configurations) and
    contradict SPEC's explicit "7 subsets".
    """
    cfgs = configuration_list(table_b_scope="two_epoch")
    a = [c for c in cfgs if c["table"] == "A"]
    b = [c for c in cfgs if c["table"] == "B"]

    subsets_a = {tuple(c["pillarSubset"]) for c in a}
    subsets_b = {tuple(c["pillarSubset"]) for c in b}
    modes = {c["reconciliationMode"] for c in cfgs}

    assert modes == {"kalman", "forward_fill"}, "FR36: exactly two modes"
    assert len(subsets_a) == 7, (
        f"SPEC FR35 says Table A is 7 subsets; got {len(subsets_a)}: "
        f"{sorted(subsets_a)}"
    )
    assert len(subsets_b) == 3, (
        f"SPEC FR35 says Table B is 3 subsets; got {len(subsets_b)}"
    )
    assert len(a) == 14 and len(b) == 6
    # Table C (DR-05) is the six-epoch RMT/Hamilton run that Table B stopped
    # being: 3 subsets x 2 modes again, so 26 rows in all. SPEC FR35's
    # "20 configurations" counted A and B, and A and B still total 20.
    c = [cfg for cfg in cfgs if cfg["table"] == "C"]
    assert len(c) == 6
    assert len(a) + len(b) == 20 and len(cfgs) == 26

    # Table A must retain the non-Hawkes subsets: they are the within-table
    # baseline that makes Hawkes's marginal contribution differenceable.
    assert ("rmt",) in subsets_a and ("hamilton",) in subsets_a
    assert ("rmt", "hamilton") in subsets_a
    # Table B is the non-Hawkes subsets only.
    assert all("hawkes" not in s for s in subsets_b)
    # Table A is scored on the Hawkes-covered epochs (SPEC FR35, D5(b)).
    assert {c["folds"] for c in a} == {len(HAWKES_EPOCHS)} == {4}


def test_fr35_table_b_is_the_two_pre_hawkes_epochs():
    """**Was an `xfail(strict=True)` pinning an open question.** The owner
    decided it on 2026-10-16 (DR-05): Table B is SPEC FR35's literal reading,
    the 2 pre-2015 epochs, and the six-epoch RMT/Hamilton run is retained as
    Table C.

    DR-05 was explicit that the *shape* of this retirement matters, because
    making the xfail pass meant editing either the code or the test, and
    either one would have resolved a scientific question in favour of
    whichever was easier to change. It is retired here because the question
    was answered, not because the marker was inconvenient.
    """
    assert PRE_HAWKES_EPOCHS == ("gfc_2008", "taper_2013")
    assert len(PRE_HAWKES_EPOCHS) == 2 and len(EPOCHS) == 6

    b = [c for c in configuration_list(table_b_scope="two_epoch")
         if c["table"] == "B"]
    assert b, "Table B must exist"
    assert {c["folds"] for c in b} == {len(PRE_HAWKES_EPOCHS)} == {2}
    assert {tuple(c["epochs"]) for c in b} == {PRE_HAWKES_EPOCHS}


def test_the_scope_has_no_default_so_every_caller_states_it():
    """DR-05 step 1. The fold count is inside the pre-registration hash, so a
    caller that inherits the scope can produce a result under one reading
    that is later read as the other."""
    with pytest.raises(TypeError):
        configuration_list()                        # type: ignore[call-arg]
    with pytest.raises(ValueError, match="no default"):
        configuration_list(table_b_scope="whatever_is_convenient")


def test_the_two_readings_hash_differently():
    """DR-05 step 2. If both readings hashed the same, a result produced under
    one could be verified against a design committed under the other, and
    `verify()`'s whole guarantee would be vacuous."""
    from seraph.validation.preregistration import build, content_hash
    two = content_hash(build(table_b_scope="two_epoch"))
    six = content_hash(build(table_b_scope="six_epoch"))
    assert two != six


def test_table_c_exists_under_the_decision_and_is_the_six_epoch_run():
    """DR-05 step 3: nothing is lost by narrowing Table B. The six-epoch
    RMT/Hamilton run is a legitimate full-period ablation — it just is not the
    pre-Hawkes table, so it gets its own identity."""
    cfgs = configuration_list(table_b_scope="two_epoch")
    c = [cfg for cfg in cfgs if cfg["table"] == "C"]
    assert c, "Table C must exist under the two-epoch decision"
    assert {tuple(cfg["epochs"]) for cfg in c} == {EPOCHS}
    assert {cfg["folds"] for cfg in c} == {6}
    assert all("hawkes" not in cfg["pillarSubset"] for cfg in c)


def test_table_c_is_absent_under_the_six_epoch_reading():
    """Under D5(b)'s reading Table B already *is* the six-epoch run, so a
    Table C would be the same rows twice under two names."""
    cfgs = configuration_list(table_b_scope="six_epoch")
    assert not [cfg for cfg in cfgs if cfg["table"] == "C"]
    b = [cfg for cfg in cfgs if cfg["table"] == "B"]
    assert {cfg["folds"] for cfg in b} == {6}


def test_the_three_tables_are_disjoint_questions():
    """A and B must not overlap at all — that overlap was the whole argument
    against the six-epoch reading. C overlaps A by design, and the design body
    has to say so."""
    cfgs = configuration_list(table_b_scope="two_epoch")
    epochs_of = lambda t: {e for cfg in cfgs if cfg["table"] == t
                           for e in cfg["epochs"]}
    assert epochs_of("A").isdisjoint(epochs_of("B"))
    assert epochs_of("A") < epochs_of("C")        # C strictly contains A's

    from seraph.validation.preregistration import build
    note = build(table_b_scope="two_epoch")["tableComparability"]
    assert "must not" in note and "three different questions" in note


def test_pre_hawkes_epochs_is_now_reached_by_a_code_path():
    """The historical contradiction, kept as a record rather than deleted.

    For as long as Table B was built from `EPOCHS`, this module held **both**
    readings of FR35 at once: `PRE_HAWKES_EPOCHS` was documented as Table B's
    epoch set, exported from the package, and never used by any code path. A
    constant saying one thing while the code did another is how the conflict
    survived unnoticed long enough to need a decision record.

    This test used to assert the contradiction still existed. It now asserts
    it is gone, which is the same guard pointing the other way: if Table B
    ever stops being built from `PRE_HAWKES_EPOCHS` without DR-05 being
    revisited, this fails.
    """
    b = [c for c in configuration_list(table_b_scope="two_epoch")
         if c["table"] == "B"]
    assert {tuple(c["epochs"]) for c in b} == {PRE_HAWKES_EPOCHS}, (
        "Table B must be built from PRE_HAWKES_EPOCHS under DR-05; if this "
        "fails, either the decision was reversed without updating DR-05 or "
        "the constant drifted out of the code path again")
    assert set(PRE_HAWKES_EPOCHS).issubset(set(EPOCHS))
    assert set(PRE_HAWKES_EPOCHS).isdisjoint(set(HAWKES_EPOCHS)), (
        "the six epochs must partition into Hawkes-covered and pre-2015"
    )
    assert len(HAWKES_EPOCHS) + len(PRE_HAWKES_EPOCHS) == len(EPOCHS) == 6
