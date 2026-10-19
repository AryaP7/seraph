# DR-12 — the FR35 experiment runner: five contracts, one open gate

**Date:** 2026-10-20
**Backlog:** `T10` (closes C12's "complete original evaluation experiment runner")
**Status:** implemented, except §6 which is the owner's.

`EvaluationRow` — C10's declared output type, specified in ARCHITECTURE §2 as
S9's return — was constructed **nowhere in the repository**. Every primitive
the FR35 ablation needs already existed and had no caller: `score_subset`,
`calibrate`, `auc`, `mean_lead_time`, `precision_at_recall`, `leakage_check`,
`configuration_list`, the epoch labels. T10 is the assembly.

Assembling them forced five decisions and surfaced one thing that needs the
owner. Each is here because it changes what a number means, not because it
changes how the code is arranged.

---

## 1. The unit of aggregation is the configuration, never the table

**Decided:** `ExperimentReport.configurations()` returns one summary per
`(table, subset, reconciliation_mode, xi_mode)`, each a mean over **its own**
folds. There is no table-level mean, and the first version's `mean_auc(table)`
and `fold_spread(table)` were removed.

**Why.** The first implementation reported, for Table B,
`declared_folds: 2, measured_folds: 24`. Both numbers were true and the pair
was meaningless: it had pooled six configurations across two xi modes and
called the result a fold count. D5 asks for "mean AUC reported **with
per-fold spread**", and a configuration's folds are the only set a mean is
defined over. Averaging a table mixes subsets, modes and xi modes — it answers
no question anyone asked, and a single number per table reads as a ranking,
which D5 forbids in the same sentence.

`declared_folds` and `measured_folds` are both carried, because they differ:
a configuration can declare four folds and measure three, and reporting only
the mean hides that while reporting only the count hides which absence caused
it. `unavailable_folds` names the reasons.

## 2. An unavailable cell is a result, with a closed reason

**Decided:** eight reasons, as a closed `Literal`:
`structural_pillar_absence`, `reconciliation_mode_absent`,
`insufficient_training_sample`, `insufficient_test_sample`,
`calibration_failed`, `train_test_overlap`, `scoring_failed`,
`single_class_fold`.

**Why closed.** An open string is how a runner acquires twelve spellings of
"no data" and a reader loses the ability to tell which absences are the same
absence. This repository has already paid for that lesson twice:
`UnavailableEmission.reason` is a closed `Literal` and three invented values
passed twenty-two unit tests before raising on the first real decision.

**Why a result and not an error.** It is what FR35's table honestly contains
at that cell. The alternative is 0.5, which is what gets written when a schema
requires a number — see §4.

One distinction worth stating: a **NaN lead time stays a measurement**. It
means the amber threshold was never crossed before onset, which is a missed
warning and a real finding about the configuration. Only an undefined AUC
empties the cell.

## 3. The optimiser budget belongs inside the hashed design

**Decided:** `build()` writes `calibrationMaxIter`; `calibrate()` takes
`max_iterations`; the runner reads it from the design and the report carries
it.

**Why.** The budget changes the weights and therefore changes the result. A
cheap plumbing run and a full evaluation are now **two declared designs with
two hashes**, not one design run two ways — so a cheap run cannot be read as
the expensive one. The same argument applies to the amber threshold, which was
previously recoverable only by parsing the prose of `amberThresholdRule`; it
is now also a number in the design body, and the runner refuses a design that
lacks it rather than choosing its own.

**Consequence, recorded rather than hidden.** These two additions changed the
design hashes. DR-05's implementation table records `d12ed87f…` and
`68cea514…` for the two readings; they are now:

| reading | configurations | hash |
|---|---|---|
| `two_epoch` | 26 (A 14, B 6, C 6) | `c2d71ea22ef30ffa…` |
| `six_epoch` | 20 (A 14, B 6) | `43443ec57f006963…` |

This is safe **only** because `preregistration.json` has never been committed,
so no result exists under the old hashes. DR-05 is a historical record and is
left unedited; this table supersedes its hash column. The property DR-05's
test pins — that the two readings hash differently — still holds.

## 4. The archive must be able to hold what the runner measures

**Decided:** `migration 002_experiment_rows.sql` and the matching
`schema.sql` change. `table_id` widens to `('A','B','C')`; the three metric
columns, `weights_artefact_id` and `leakage_check` become nullable;
`availability` plus its reason are added; a CHECK keeps each state whole so
`measured` always means a number is present.

**Why.** Two defects, both latent since DR-05:

* DR-05 step 3 added Table C and its implementation table marks it **done**.
  It was done in `configuration_list()`, which emits `table: "C"` under the
  `two_epoch` scope — the *default*. It was not done in the store, where
  `CHECK (table_id IN ('A','B'))` still stood. So six of the twenty-six
  configurations the committed design asks for could not be archived at all,
  against FR38's requirement to archive every ablation result. A run would
  compute Table C and then fail to insert it.
* Every metric column was `NOT NULL`. An ablation cell legitimately has no
  measurement, so the only way to store one was to invent a number — and the
  number people invent is 0.5. The schema was quietly requiring the
  fabrication that §2's explicit absences exist to prevent.

**Not verified here:** applying 002 needs a real Postgres. Its SQL is asserted
statically and the application is gated like FIX06's. The test for it skips on
this machine and says so.

## 5. A single-pillar row is invariant to the weights and the xi mode

**Found, not decided** — but it changes how Table B and C are read, so it is
recorded as a contract.

Under a one-pillar mask every regime row of the weight matrix renormalises to
the same indicator vector, so C9's `a = xi @ effective` collapses to that
indicator and `CSRS = x_hat[k]` **exactly**, whatever the weights are and
whichever xi mode ran. Two consequences:

* The R5 control is **structurally incapable of diverging** on a
  single-pillar subset. ARCHITECTURE R5 aims it at "Hamilton-standalone" —
  precisely the case where it can say nothing. It is informative only for the
  multi-pillar subsets, where `rmt+hamilton` does move. Identical columns
  there are the arithmetic, not agreement between two ways of weighting, and a
  report that does not say so invites a false reassurance that the coupling is
  not doing the work.
* A single-pillar AUC is that pillar's own discriminative power and carries no
  information about fusion. Those rows are still calibrated and still
  reported: blanking a cell because it is uninformative is how a descriptive
  ablation stops being descriptive.

The fixture had to be corrected twice for this family of reasons. It emitted a
uniform xi everywhere, which made the R5 control report agreement by
construction across *every* subset; and its signal produced AUCs of 0.996,
which at a glance is indistinguishable from a spectacular real result.

---

## 6. OPEN — widening `EvaluationRow` is the owner's call

**The gap.** The archive can now hold a Table C row (§4). The published
contract cannot:

```python
class EvaluationRow(FrozenModel):
    table: Literal["A", "B"]       # FR35
```

There is also no field for an unavailable cell, so the twenty-six-row design
produces rows that `EvaluationRow` has no shape for.

**Why it is not done here.** `CLAUDE.md` gates `seraph/shared_types/` on the
human — "confirm with the human before editing it, since every component
imports from there" — and `.claude/settings.json` lists it as ask-before-edit.
All twelve components import from that package, so widening the type is not a
C10-local change.

**What the runner does instead.** It produces `ExperimentRow`, a C10-owned
superset, and `as_evaluation_row()` converts the rows the published contract
does cover. Table C rows and unavailable rows return `None`, and
`ExperimentReport.unpublishable_rows` **counts** them. Nothing is dropped
silently: the gap between what was measured and what the declared contract can
carry is a number on the report.

**What the owner decides.** Whether `EvaluationRow` becomes

```python
    table: Literal["A", "B", "C"]
```

with an availability discriminator, or whether Table C stays archive-only and
`ExperimentRow` is the published shape for ablation results. The first is a
two-line edit to a file everything imports; the second leaves two row types in
play. DR-05's own step 3 said Table C gets "its own `table_id`", which points
at the first — but that decision was about the design, not the contract, so it
is not taken as authority here.

---

## What T10 does not claim

`preregistration.json` is still uncommitted, and DR-05 step 5 leaves it to the
owner for the reason pre-registration exists: a design is fixed by a person
before any result is seen, and a script writing it as a build step defeats the
mechanism. **So no real AUC has been computed.** Every number produced so far
comes from `fixtures/experiment_dataset.py`, which declares itself synthetic
in a field that travels with the data.

What is demonstrated is the plumbing T10's acceptance asks for — "a small
supplied valid dataset exercises runner/configuration/report plumbing; full
expensive scientific evaluation is separate" — plus the refusals: no design,
an edited design, a design without a threshold, a leaking fold, a
single-class fold, a subset that outruns its epoch's coverage, a transfer that
would be in-sample, and a sensitivity sweep whose designs do not differ.

FR37's transfer runs against a fixture epoch standing in for a second market,
and says so in its own output. A real O9 result needs daily data for one of
IDX / Ibovespa / JSE, which SPEC O9 states is free via `yfinance` and which is
not wired up. SPEC OQ14 — which of the three — is still open.
