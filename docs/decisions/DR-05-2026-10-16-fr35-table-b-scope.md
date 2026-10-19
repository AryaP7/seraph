# DR-05 — FR35 Table B scope: two epochs or six

**Date:** 2026-10-16
**Backlog:** `FIX05` (audit finding A07), unblocks `FIX06`, `VAL03`
**Status:** **DECISION REQUIRED — not resolved by this document.**
This is the dated design the audit asked for. It states the conflict, works
out what each reading costs, and recommends one. It does **not** change
`configuration_list()`, and the expected-failure test still fails on purpose.

---

## The conflict, exactly

Two documents in this repository say different things, and the code implements
one of them while exporting a constant that encodes the other.

| Source | Table B scope | Folds |
|---|---|---|
| `docs/SPEC.md` FR35 `[v2]` | "the 2 pre-2015 epochs" | 2 |
| `docs/ARCHITECTURE.md` D5(b) | "use all 6 → 6 folds" | 6 |

In code (`seraph/validation/preregistration.py`):

- `PRE_HAWKES_EPOCHS = ("gfc_2008", "taper_2013")` is defined, documented as
  "Pre-2015 epochs — Table B", exported… **and never used**.
- `configuration_list()` builds Table B from `EPOCHS` (all six), implementing
  D5(b).

`tests/test_fr35_ablation_design_pins.py::test_fr35_table_b_fold_count_is_the_open_question`
is an `xfail` that pins SPEC's reading. It is still failing, deliberately.

This is not a documentation quibble. The fold count is **inside the
pre-registration hash** (D5(d)), and a result whose hash does not match the
committed design is not reportable. No `preregistration.json` has been
committed yet, so the design is still genuinely open — which is the only
reason this can still be decided cleanly rather than amended after the fact.

## What Table B is for

Table A covers the four Hawkes-capable epochs (`ilfs_2018`, `covid_2020`,
`tightening_2022`, `tariff_2026`) with all seven pillar subsets. Table B exists
because Hawkes has **no coverage before 2015**, so the two pre-2015 epochs
(`gfc_2008`, `taper_2013`) can only be evaluated on RMT/Hamilton subsets.

That is the whole motivation: *answer the question Table A cannot*.

## Reading 1 — two epochs (SPEC's literal text)

Table B = 3 subsets × 2 reconciliation modes × 2 xi modes over
`("gfc_2008", "taper_2013")`.

**For.** It matches the motivation exactly. Table B is the pre-Hawkes
evidence; mixing in the four epochs Table A already covers answers nothing new
and makes the two tables overlap on 4 of 6 folds, so their numbers move
together for reasons that have nothing to do with the pillar subset.

**Against.** Two folds. With `n = 2` a leave-one-epoch-out AUC has essentially
no resolving power: each fold is one positive event, and the spread across two
folds is not a distribution. The result would be a pair of numbers, honestly
reported as such.

## Reading 2 — six epochs (ARCHITECTURE D5(b), implemented)

Table B = 3 subsets × 2 modes × 2 xi modes over all six epochs.

**For.** Six folds give more comparisons, and the RMT/Hamilton subsets are
genuinely evaluable on all six, because neither pillar depends on Hawkes
coverage.

**Against.** It is no longer the pre-Hawkes table. Four of its six folds are
the same events Table A uses, so a Table A row and a Table B row for the same
subset and mode differ only in the two extra folds — and the existing design
note already has to warn that the two tables "are not directly comparable and
must not be placed in a single ranking". The overlap is what forces that
warning. It also loses the clean statement "this is what RMT and Hamilton can
do where Hawkes cannot exist".

## Recommendation

**Reading 1 — two epochs — with the six-epoch run retained as a separate,
clearly named table.**

Reasoning:

1. Table B's only reason to exist is the pre-Hawkes period. A table that
   mostly re-covers Table A's epochs is not that table.
2. The two-fold weakness is real but it is the *honest* weakness. It is a
   property of the data (two pre-2015 labelled epochs exist) and reporting
   two folds as two folds is correct. Six folds do not make the pre-2015
   evidence stronger; they dilute it with epochs that were never the question.
3. The comparability warning becomes true rather than mitigating: with
   disjoint epoch sets, Table A and Table B answer different questions and
   nobody is tempted to rank them together.
4. Nothing is lost. The six-epoch RMT/Hamilton run is a legitimate
   full-period ablation — it just is not Table B. Name it **Table C**, give it
   its own `table_id`, and both appear in the report. `FIX06`'s evaluation
   identity makes them coexist without collision, which is precisely why that
   migration had to come with this decision.

**What this recommendation is not.** It is a design judgement about which
question Table B should answer. It is not a finding about which produces a
better number — neither has been run, and the recommendation was written
before any Table B AUC exists, which is the point of pre-registration.

## What must happen when the decision is made

The owner picks a reading. Then, in one change:

1. Set the scope explicitly in `configuration_list()` — a named parameter with
   no default, so the choice is visible at every call site rather than
   inherited.
2. Record the chosen scope in the design body, so the pre-registration hash
   differs between the two readings and a result can never be mistaken for one
   produced under the other.
3. If Reading 1 is chosen, add Table C for the six-epoch RMT/Hamilton run with
   its own `table_id`, and state in the design that A, B and C are three
   different questions.
4. Replace the `xfail` with a real assertion of the chosen scope, and keep the
   diagnostic test that records the historical contradiction.
5. Commit `preregistration.json` — **before the first AUC is computed.**

Until step 1 happens, `FIX05` stays `scientifically unresolved` and `FIX06`'s
migration ships without presuming either answer: `evaluation_runs.table_b_scope`
accepts `two_epoch`, `six_epoch` or `legacy_unknown`, and existing rows are
preserved under `legacy_unknown` rather than relabelled.

## Why the expected failure was not removed

Making the xfail pass means editing either `configuration_list()` or the test.
Either one silently resolves a scientific question in favour of whichever was
easier to change, and the fold count would then be hashed into a
pre-registration that nobody decided. The failing test is the open question's
only mechanical representation; it stays until someone answers it.

---

## DECISION RECORDED — 2026-10-16

**The owner chose Reading 1: Table B is the two pre-Hawkes epochs
(`gfc_2008`, `taper_2013`), and the six-epoch RMT/Hamilton run is retained
separately as Table C.**

This matches the recommendation above. What it means for implementation, in
the order the plan requires:

1. `configuration_list()` takes an explicit `table_b_scope` with no default,
   so the choice is visible at every call site.
2. The chosen scope is recorded in the design body, so the pre-registration
   hash differs between the two readings and a result can never be mistaken
   for one produced under the other.
3. Table C is added for the six-epoch RMT/Hamilton run with its own
   `table_id`. A, B and C are three different questions and are never ranked
   together.
4. The `xfail` becomes a real assertion of the chosen scope; the diagnostic
   test recording the historical contradiction is kept.
5. `preregistration.json` is committed **before the first AUC is computed**.

`FIX05` moves from `scientifically unresolved` to a normal implementation
task. `evaluation_runs.table_b_scope` already accepts `two_epoch`, `six_epoch`
and `legacy_unknown`, so the `FIX06` migration needs no change — existing rows
stay `legacy_unknown` rather than being relabelled under a decision they were
not produced under.

---

## IMPLEMENTED — 2026-10-17

Steps 1–4 are done in one change, because they are only sound together: the
scope, the hash and the test have to move at the same time or a result can be
produced under one reading and read under the other.

| Step | Where | State |
|---|---|---|
| 1. explicit scope, no default | `configuration_list(*, table_b_scope)` | done — `TypeError` without it, `ValueError` naming DR-05 on an unknown value |
| 2. scope inside the hashed design | `build()` writes `tableBScope` + `tableBScopeDecision` | done — the two readings hash differently (`d12ed87f…` vs `68cea514…`) |
| 3. Table C | `configuration_list()` emits `table: "C"` under `two_epoch` only | done — 6 rows, all six epochs, RMT/Hamilton subsets, both xi modes |
| 4. xfail retired | `test_fr35_table_b_is_the_two_pre_hawkes_epochs` | done — real assertion; the diagnostic is kept, inverted to guard the resolution |
| 5. commit `preregistration.json` | — | **owner's to run, deliberately not done here** |

Shapes, verified:

```
two_epoch  rows=26  tables={'A': 14, 'B': 6, 'C': 6}  folds={'A': [4], 'B': [2], 'C': [6]}
six_epoch  rows=20  tables={'A': 14, 'B': 6}          folds={'A': [4], 'B': [6]}
```

SPEC FR35's "20 configurations" is preserved as A + B = 20; Table C is
additional and separately identified, not a renumbering.

`PRE_HAWKES_EPOCHS` is now reached by a code path for the first time. The test
that used to assert the contradiction still existed now asserts it is gone —
the same guard pointing the other way, so if Table B ever stops being built
from that constant without DR-05 being revisited, it fails.

**Step 5 was left for the owner on purpose.** Pre-registration exists so that
a design is fixed by a person before any result is seen; a script writing
`preregistration.json` unprompted would defeat the thing this record is for.
`commit()` already refuses to overwrite an existing file, so the sequence is
safe to run once ready:

```bash
python -c "from seraph.validation.preregistration import commit; print(commit())"
```

The six-epoch reading remains callable and tested, so a Table C run and a
historical `six_epoch` row can both still be described exactly.
