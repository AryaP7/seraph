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
    cfgs = configuration_list()
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
    assert len(a) == 14 and len(b) == 6 and len(cfgs) == 20

    # Table A must retain the non-Hawkes subsets: they are the within-table
    # baseline that makes Hawkes's marginal contribution differenceable.
    assert ("rmt",) in subsets_a and ("hamilton",) in subsets_a
    assert ("rmt", "hamilton") in subsets_a
    # Table B is the non-Hawkes subsets only.
    assert all("hawkes" not in s for s in subsets_b)
    # Table A is scored on the Hawkes-covered epochs (SPEC FR35, D5(b)).
    assert {c["folds"] for c in a} == {len(HAWKES_EPOCHS)} == {4}


@pytest.mark.xfail(
    strict=True,
    reason=(
        "PINS AN OPEN QUESTION — see BLOCKER-TRIAGE.md §D-2. SPEC FR35 [v2] "
        "puts Table B 'on the 2 pre-2015 epochs' (2 folds); ARCHITECTURE D5(b) "
        "says Table B 'use all 6 -> 6 folds'. configuration_list() implements "
        "D5(b)'s 6, while preregistration.PRE_HAWKES_EPOCHS encodes SPEC's "
        "reading and is never used. This needs an explicit owner decision "
        "BEFORE preregistration.json is committed and hashed (D5(d)): the "
        "fold count is inside the hash and a mismatched hash is not "
        "reportable. Not decided by Workstream D - C10 is another owner's "
        "component."
    ),
)
def test_fr35_table_b_fold_count_is_the_open_question():
    """SPEC FR35's literal Table B scope: the 2 pre-2015 epochs, 2 folds."""
    assert PRE_HAWKES_EPOCHS == ("gfc_2008", "taper_2013")
    assert len(PRE_HAWKES_EPOCHS) == 2 and len(EPOCHS) == 6

    b = [c for c in configuration_list() if c["table"] == "B"]
    assert b, "Table B must exist"
    assert {c["folds"] for c in b} == {len(PRE_HAWKES_EPOCHS)}, (
        "SPEC FR35 [v2] scopes Table B to the 2 pre-2015 epochs; "
        f"configuration_list() uses {sorted({c['folds'] for c in b})} folds "
        f"per ARCHITECTURE D5(b)"
    )
    assert {tuple(c["epochs"]) for c in b} == {PRE_HAWKES_EPOCHS}


def test_fr35_pre_hawkes_epochs_is_documented_as_table_b_but_unused():
    """A read-only diagnostic: the two readings coexist in one module.

    `PRE_HAWKES_EPOCHS` is documented as Table B's epoch set and exported, but
    `configuration_list()` builds Table B from `EPOCHS`. This test does not
    judge which is right — it records that the contradiction is in the code,
    so the §D-2 decision cannot be mistaken for a docs-only quibble.
    """
    b = [c for c in configuration_list() if c["table"] == "B"]
    epoch_sets = {tuple(c["epochs"]) for c in b}
    assert epoch_sets == {EPOCHS}, (
        "if this flips to PRE_HAWKES_EPOCHS the §D-2 decision has been taken; "
        "retire this test and the xfail above together"
    )
    assert set(PRE_HAWKES_EPOCHS).issubset(set(EPOCHS))
    assert set(PRE_HAWKES_EPOCHS).isdisjoint(set(HAWKES_EPOCHS)), (
        "the six epochs must partition into Hawkes-covered and pre-2015"
    )
    assert len(HAWKES_EPOCHS) + len(PRE_HAWKES_EPOCHS) == len(EPOCHS) == 6
