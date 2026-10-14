# Blocker triage — Workstream D

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`.
Nothing committed. Database untouched: every query in this document is a
`SELECT`/`SHOW`. No production table was written, no schema changed.**

Classification scheme, one per issue: **(1)** routine implementation defect ·
**(2)** missing diagnostic / insufficient evidence · **(3)** test or
methodology issue requiring justification · **(4)** specification ambiguity
requiring explicit approval · **(5)** external dependency or unavailable data.

Documents cited by short name throughout: `docs/SPEC.md` ·
`docs/ARCHITECTURE.md` · `docs/AMENDMENT-03-jump-sparsity-R2.md` ("AMENDMENT-03") ·
`docs/SERAPH-BUILD-ROADMAP.md` ("ROADMAP") · `docs/PILLAR1-SELECTION-RULE.md` ·
and the peer evidence notes `docs/evidence/{HAMILTON-CAUSAL-POSTFIX,
HAMILTON-REGIME-SUPPORT, HAMILTON-UNAVAILABLE-DECISION, HAWKES-WINDOW-SELECTION,
FR35-CONFIG-COUNT-CONFLICT}.md`.

| § | Issue | Class | Verdict |
|---|---|---|---|
| D-1a | CT-3 jump-density failure | **(5)** | Genuine data limitation. R2 realised and already resolved by SPEC FR10 `[v4]`. Assertion **left failing, unmodified**. |
| D-1b | Lee–Mykland size calibration | **(4)** | Real defect, `1/c = 1.2533×` too strict. **Not fixed** — the fix re-bases a number SPEC FR10 quotes verbatim. Approval required. |
| D-2 | FR35 configuration count | **(4)** | The 20 configurations are **SPEC-correct**; `FR35-CONFIG-COUNT-CONFLICT.md`'s recommended fix is **wrong against SPEC FR35** and must not be applied. One genuinely open question remains: Table B's fold count. |
| D-3 | C7 converged-optimum | **(2)** | Diagnostic delivered, **no rule changed**. The two blocks **disagree**: on block 11 the discarded candidate IS a genuine local maximum (Hessian negative definite, 100× better conditioned) and the converged one is not; on block 10 neither is. Both proposed rule changes are contradicted; a **second-order check** is what the evidence supports. |
| D-4 | Data-integrity sweep | **(1)** + **(2)** | 5 of 5 mandated invariants verified correct. New finding: 17 non-standard session dates — 15 legitimate NSE calendar **(2)**, 4 genuine defects **(1)**. **No evaluation result invalidated.** |

New evidence artefacts (all new files; nothing overwritten):

| File | Contents |
|---|---|
| `20261013T124930Z-51-ct3-jump-density-and-lm-calibration.log` | Monte-Carlo size/power of the FR50 test; full-universe jump density under both thresholds |
| `20261013T125234Z-52-baseline-invariants-and-full-suite.log` | Pre-change `check_invariants.py` (exit 0). **Its pytest half was deliberately cancelled** — see the note appended inside it and §D-4 below |
| `20261013T130202Z-53-hamilton-converged-optimum-diagnostics.log` | D-3 gradient / Hessian / boundary diagnostics, causal blocks 10 and 11 |
| `20261013T130909Z-54-data-integrity-sweep.log` | D-4: timestamp audit, off-session bars, `writeBatch` idempotency verified read-only |
| `20261013T131336Z-55-fr35-keyspace-diagnostic.log` | D-2 read-only diagnostic: FR35 rows vs `validation_results`' primary key |
| `20261013T133418Z-56-offsession-session-calendar-impact.log` | D-4: all 17 non-standard session dates, FR32 window membership, pillar-output impact |
| `20261013T134259Z-57-post-change-invariants-and-full-suite.log` | Post-change `check_invariants.py` + full suite **including** Workstream D's new tests, with exit codes |

Plus, not Workstream D's but cited here: `20261013T072658Z-30-final-full-suite.log`
(session-start baseline, 1 failed / 170 passed) and
`20261013T135032Z-70-full-suite-FINAL.log` (coordinator's final run, which
reproduces `-57-` exactly).

---

## D-1. CT-3 jump-density sufficiency failure

### D-1a — the failure itself · classification (5), external/unavailable data

**Verdict: cause (b). Genuinely insufficient jump density in the real intraday
data — not a defect in `jump_extraction.py` and not a wrong threshold that may
be quietly relaxed. The assertion is left failing and unmodified.**

Measured read-only over the whole Hawkes universe (`build_symbol_list`, never a
raw `intraday_bars` scan), 95 symbols / 18,269,762 bars / 244,772 symbol-days:

| quantity | measured | CT-3 floor | shortfall |
|---|---|---|---|
| negative jump events | 21,180 | — | — |
| **negative jumps per symbol-day** | **0.0865** | 1.0 | **11.6×** |
| best single symbol (WEBELSOLAR) | 0.3512 | 1.0 | 2.8× |
| worst single symbol (SUNDRMFAST) | 0.0577 | 1.0 | 17.3× |
| positive jump events | 28,603 | — | — |
| negative share | 0.4254 | — | — |

The floor is missed by an order of magnitude **on every symbol in the
universe**, so this is structural, not an unlucky draw. The figure reproduces
`AMENDMENT-03` §1 independently and to the event (21,180 events; 0.0865 here vs
0.0869 there, the difference being a slightly different universe snapshot —
244,772 symbol-days vs 243,597).

**What density would be needed, and why it is not achievable.** The floor needs
~12× more events. `AMENDMENT-03` §1 already swept the whole Lee–Mykland grid
(`K ∈ {156, 78, 40}` × `α ∈ {0.01, 0.05, 0.10}`): density moves only between
0.079 and 0.147 — a **1.9× span against a ~12× shortfall**. Every rung of the
ROADMAP Phase-5 mitigation ladder is exhausted or inapplicable:

1. *1-minute bars* — not in the corpus; tick/1-min history is unobtainable at
   project budget (SPEC §7 item 12, OQ1 resolved "unobtainable").
2. *Coarsen `S_t` to 9 states* — does not help, because `S_t` was never the
   binding constraint: all 25 states are populated and 20 carry ≥100 events
   (`AMENDMENT-03` §1).
3. *Pool across symbols within a sector* — superseded; the project pooled
   **market-wide**, which goes further than the ladder.
4. *Lengthen the window* — adopted, and is exactly what FR10 `[v4]` now
   specifies.

The only remaining levers are sub-5-minute data (unavailable) or an `α` so
loose the jump test stops being a jump test. **Hence classification (5).**

**The requirement this floor guarded no longer exists.** SPEC v3.1 line 199:

> **FR10 `[v4]` AMENDED** | The system shall estimate a **discrete-time Hawkes
> process at the native 5-minute bar resolution** on the market-wide pooled
> stream of negative jump events, with a geometric excitation kernel
> `λ_t = μ·ToD(t) + α·Σ_k φ^(k−1)·N_(t−k)` … *Supersedes per-symbol
> one-trading-day continuous-time estimation, which AMENDMENT-03 §1–2 shows is
> unidentifiable with this data: density is 0.087 events/symbol-day, 75.8% of
> pooled events share a bar, and `β` pins to whatever bound is imposed.*

SPEC quotes **this test's own failing measurement** as its reason for retiring
the per-symbol one-day window. And the pooled design FR10 `[v4]` does specify
is well identified on the same data: `α ≈ 0.055`, `φ ≈ 0.50` **interior**,
`n ≈ 0.11` stable at ~5% parameter CV across chronological folds
(`AMENDMENT-03` §5d).

**Why the test was not changed.** It would have been defensible under the "(c)
specification demonstrably wrong" rule to mark it `xfail`, and that is probably
where it should end up. Workstream D did **not** do it, because:

* ARCHITECTURE §5 ① still states the assertion ("negative jumps per symbol-day
  ≥ agreed floor") and ROADMAP §4 records **no agreed number** — the 1.0 is the
  test author's own declared invention. AGENTS.md §9 is explicit that an
  unagreed constant is to be flagged, not guessed at, in either direction.
* The program's published baseline is "170 passed, 1 failed, the failure being
  CT-3". Silently turning that green is the concealment the mandate forbids.
* It unblocks nothing: Pillar 1 already ships under FR10 `[v4]`.

**Change made: documentation only, and that is mechanically checkable.**

```
$ git diff --numstat -- tests/contract/test_ct3_jump_sufficiency.py
71      0       tests/contract/test_ct3_jump_sufficiency.py
```

**71 insertions, 0 deletions** — so `MIN_NEG_JUMPS_PER_DAY = 1.0` and the
assertion are byte-identical and no line was removed. The module docstring and
the test docstring now carry the measured numbers, the FR10 `[v4]` quote, the
exhausted mitigation ladder, and a pointer here. CT-3 still reports **1 failed,
3 passed**, identically to before.

(The `git diff --stat` for this branch also lists
`seraph/pillars/hamilton/engine.py`, `seraph/orchestration/adapters.py` and
`seraph/orchestration/__init__.py` as modified. Those are **other workstreams'**
changes, already present in the working tree at the start of this session.
Workstream D touched no file under `seraph/`.)

**Approval required (small).** Retire the 1.0-per-symbol-day gate — replace it
with `xfail(strict=True)` citing FR10 `[v4]`, or delete it in favour of a
pooled-stream sufficiency assertion. Owner: C4/C5. Consequence of doing
nothing: a permanently red suite whose single red is explained here, which is
acceptable but trains readers to ignore red.

### D-1b — Lee–Mykland size calibration · classification (4), approval required

**Found while verifying (a) was not the cause. It is a real defect, it is NOT
the cause of the CT-3 failure, and it is NOT fixed.**

`extract_jumps` compares `L_i = |r_i| / σ̂_i` against
`lee_mykland_threshold(n)`. The two are on different scales:

* `bipower_volatility` divides the bipower sum by `_C_CONST**2 = μ₁² = 2/π`,
  i.e. it **applies** the `μ₁⁻²` correction. Measured: mean `σ̂ / σ = 1.0000`
  on 60k pure-Brownian returns. So `L_i` is in **true-σ units**, `L_i ≈ |Z|`.
* Lee & Mykland's `C_n`, `S_n` carry a factor `1/c` *because their own* `σ̂` is
  the **uncorrected** bipower estimate, which converges to `c·σ`. Their
  statistic is `≈ |Z|/c`. Multiplying their constants by `c` recovers the
  textbook extreme-value constants for the maximum of `n` i.i.d. `|N(0,1)|`:
  `c·C_n = √(2 ln n) − (ln ln n + ln π)/(2√(2 ln n)) = a_n` and
  `c·S_n = 1/√(2 ln n) = b_n`. That identity is the proof.

`μ₁` is therefore counted twice and the rejection threshold is
**`1/c = 1.2533×` too strict**. Monte-Carlo confirmation on a pure-Brownian
null (400 samples × 2,475 bars, seeded):

| | nominal α | P(≥1 rejection per sample) | power at 5σ | power at 6σ |
|---|---|---|---|---|
| **shipped** | 0.01 | **0.0000** | 0.250 | 0.505 |
| threshold × `c` | 0.01 | **0.0125** | 0.620 | 0.915 |

The shipped test never fires once in a million null bars at its own nominal
level. `tests/test_c4_lee_mykland_calibration.py` encodes the derivation: two
passing tests pin the premises, and `xfail(strict=True)` pins the defect.

**The severity is not 25%, it is ~3 orders of magnitude.** The Gumbel tail is
thin, so inflating the threshold by `1/c` collapses the realised *level*. Writing
the shipped threshold as a quantile of the statistic's own null max
distribution, `α_eff = 1 − exp(−exp(−x))` with `x = (thr_shipped − a_n)/b_n`:

| `n_obs` | `thr_shipped` | `thr_correct` | **effective α** | tighter than nominal |
|---|---|---|---|---|
| 2,319 — the CT-3 window | 5.8903 | 4.6998 | 9.26e-05 | **108×** |
| 200,000 — ≈ one symbol's full history | 6.8968 | 5.5029 | 1.03e-05 | **975×** |
| 18,781,302 — whole corpus | 7.8208 | 6.2401 | 1.07e-06 | 9,354× |

Nominal `α` is 0.01 in every row. The middle row is the production-relevant
one, because `extract_jumps` derives `n_obs` from the finite-`σ̂` count of the
single symbol it is handed — ~214,650 bars for a symbol with the full
2,862-session history, for which 200,000 is the round stand-in computed above. **FR50 therefore ships at an effective level near
`1e-5` while documenting `α = 0.01`.** That gap, rather than the density
shortfall, is the part a reviewer is most likely to ask about.

**The CT-3 conclusion is robust to it** — which is why the two are triaged
apart:

| | neg/symbol-day | events | vs CT-3 floor |
|---|---|---|---|
| shipped | 0.0865 | 21,180 | 11.6× short |
| threshold × `c` | **0.1478** | 36,173 | **6.8× short** |
| best single symbol, corrected | 0.5563 | — | 1.8× short |

**Why it was not fixed, though `seraph/features/` is Workstream D's to edit.**
The one-line correction changes `0.0865 → 0.1478`, and `0.087` is quoted
**verbatim in SPEC FR10 `[v4]`** as that requirement's own justification. It
would also invalidate `AMENDMENT-03` §1–§5d wholesale (21,180 events, the 75.8%
tie fraction, `ρ = 0.0552`, the six-family model selection, `n ≈ 0.11`), the 473
production rows in `hawkes_output`, and `HAWKES-WINDOW-SELECTION.md`. AGENTS.md
§1 governs: *"If code and docs disagree, the docs win. If you think a doc is
wrong, say so and ask — don't silently deviate."* `docs/SPEC.md` is outside
Workstream D's write scope, so applying the code fix would leave code and an
unamendable spec in contradiction. **This is an approval gate, not a routine
fix.**

**Approval question.** Correct the FR50 threshold scaling?

* **Alternative A — fix the code, amend the spec.** Multiply the threshold by
  `_C_CONST` in `extract_jumps` (one line; `bipower_volatility` stays an
  unbiased volatility estimator for its other consumers). Then: amend SPEC
  FR10 `[v4]`'s `0.087`, re-derive `AMENDMENT-03` §1–§5d, and re-run the
  `hawkes_output` backfill (~118 min per the E6 log). FR50 says "using the
  Lee–Mykland bipower-variation test", so faithfulness argues for this.
* **Alternative B — fix the parameterisation instead.** Drop the `/_C_CONST**2`
  from `bipower_volatility` so `σ̂` is L&M's own uncorrected estimate and the
  published constants apply unchanged. Identical detections to A, but `σ̂`
  stops being an unbiased volatility and any other consumer silently inherits a
  0.798× bias. **Not recommended.**
* **Alternative C — document and keep.** Record that FR50 runs at an effective
  level far tighter than its nominal `α = 0.01`, and that every Pillar 1 count
  is conservative. Costs nothing today; leaves a published "α = 0.01" that is
  not the realised size, which is the kind of thing a viva finds.
* **Recommendation: A**, scheduled deliberately rather than now. Nothing
  downstream is blocked on it — the R2 verdict, FR10 `[v4]` and `n ≈ 0.11` all
  survive the correction — so it should be taken as a planned spec amendment
  with the backfill, not folded into a triage pass. The `xfail(strict=True)`
  pin means whoever corrects the code trips a suite failure and is forced to do
  the spec half.

### Commands and exit codes

```
$ .venv/Scripts/python.exe -m pytest tests/contract/test_ct3_jump_sufficiency.py -v
  BEFORE : 1 failed, 3 passed   exit 1
  AFTER  : 1 failed, 3 passed   exit 1      (identical; docstrings only)

$ .venv/Scripts/python.exe -m pytest tests/test_c4_lee_mykland_calibration.py -v
           2 passed, 1 xfailed  exit 0      (new file)

$ .venv/Scripts/python.exe -m pytest tests/test_c4_lee_mykland_calibration.py \
      tests/test_fr35_ablation_design_pins.py -q
           4 passed, 2 xfailed in 3.89s     exit 0   (both new files together)

$ git diff --numstat -- tests/contract/test_ct3_jump_sufficiency.py
  71      0       tests/contract/test_ct3_jump_sufficiency.py   (additions only)
```

---

## D-2. FR35 configuration-count discrepancy · classification (4)

**Headline: `configuration_list()`'s 20 configurations are SPEC-correct.
`FR35-CONFIG-COUNT-CONFLICT.md` §5's recommended fix is wrong against SPEC
FR35 and must NOT be applied. Applying it would freeze an incorrect
pre-registration hash — the exact outcome that note was written to prevent.**

### What SPEC and ARCHITECTURE unambiguously require

`FR35-CONFIG-COUNT-CONFLICT.md` argues from ARCHITECTURE D5's prose ("14
configurations", five times) that the total must be 14, and recommends
restricting Table A to Hawkes-containing subsets. It never quotes SPEC FR35
itself. SPEC v3.1 line 243 — authoritative over ARCHITECTURE, which AGENTS.md
§1 describes as "derived from SPEC, adds nothing new":

> **FR35 `[v2]`** | The system shall produce **Table A** (7 subsets × 2
> reconciliation modes, on the 4 Hawkes-covered epochs) and **Table B** (3
> subsets × 2 modes, on the 2 pre-2015 epochs), each reporting AUC and mean
> lead time. | O7

That is explicit arithmetic with one reading: Table A = 7 × 2 = **14**, Table B
= 3 × 2 = **6**, total **20**. `configuration_list()` produces exactly that.
ARCHITECTURE D5's "14" is **Table A's count** — the reading the conflict note
stated fairly in its §3 and then rejected on the strength of D5(d)'s "full list
of 14". D5(d)'s phrasing is loose; FR35's arithmetic is not.

**There is also a methodological reason the 7 subsets are right, not sloppy.**
`(rmt)` must appear in Table A **on the same 4 folds** as `(hawkes,rmt)`, or
there is nothing to difference against to isolate Hawkes's marginal
contribution. The conflict note's §4 point 1 — "`(rmt)` scored on 4 folds
discards two of six epochs for no stated reason" — has a stated reason: holding
the fold set fixed is the only way the within-table comparison means anything.
Table B then extends RMT/Hamilton coverage to the epochs Table A cannot reach.
So the 3-subset overlap between tables is **by design**, with the fold set as
the distinguishing axis — which is precisely why D5(b) forbids pooling Table A
and Table B into one ranking. The note's §4 point 2 reads that overlap as the
bug; it is the mechanism.

Pinned, passing, in `tests/test_fr35_ablation_design_pins.py::test_fr35_table_shape_is_spec_literal`.

### What remains genuinely ambiguous

**One thing, and it is not the configuration count: Table B's fold count.**

| source | Table B scope |
|---|---|
| **SPEC FR35 `[v2]`** | "on the **2 pre-2015 epochs**" → **2 folds** |
| **ARCHITECTURE D5(b)** | "Table B subsets … use **all 6** → **6 folds**" |
| `configuration_list()` | `epochs=EPOCHS` (all 6), `folds=6` — follows D5(b) |
| `build()`'s `tableComparability` | "Table A (4 folds) and Table B (6 folds)" — follows D5(b) |

These genuinely conflict, and SPEC is the senior document. Corroborating that
this is unresolved authoring rather than a settled choice — a measurement, not
a reading:

```
seraph/validation/preregistration.py:28-29
    #: Pre-2015 epochs — Table B, RMT/Hamilton subsets only.
    PRE_HAWKES_EPOCHS = ("gfc_2008", "taper_2013")

$ grep -rn PRE_HAWKES_EPOCHS --include=*.py seraph/
  seraph/validation/preregistration.py:29   (definition)
  seraph/validation/__init__.py:17          (re-export)
  seraph/validation/__init__.py:27          (__all__)
  -> defined, documented as Table B's epoch set, exported, and NEVER USED.
```

The module contains **both readings**: D5(b)'s in executable code, SPEC's in a
documented constant no code path reaches. Pinned as
`xfail(strict=True)` in `tests/test_fr35_ablation_design_pins.py::test_fr35_table_b_fold_count_is_the_open_question`.

### An independent consequence that bears on the same decision

Found while triaging, and it converges on the same answer from a different
direction. `schema.sql:206`:

```sql
CREATE TABLE IF NOT EXISTS validation_results (
    pillar_subset, reconciliation_mode, xi_mode, epoch, table_id,
    auc, …, pre_registration_hash  text NOT NULL,          -- D5(d)
    PRIMARY KEY (pillar_subset, reconciliation_mode, xi_mode, epoch)
);
```

**`table_id` is not in the key, and neither is `pre_registration_hash`.**
Because SPEC FR35 puts `(rmt)`, `(hamilton)` and `(rmt,hamilton)` in *both*
tables, whether the Table A and Table B rows for those subsets collide depends
entirely on whether Table B's epoch set overlaps Table A's — i.e. on exactly the
open question above. Enumerated in
`20261013T131336Z-55-fr35-keyspace-diagnostic.log`:

| Table B scope | EvaluationRows | distinct PKs | **rows silently overwritten** |
|---|---|---|---|
| all 6 epochs — D5(b), **current code** | 128 | 104 | **24** (all cross-table) |
| the 2 pre-2015 epochs — SPEC FR35 literal | 80 | 80 | **0** |

e.g. `('hamilton', 'forward_fill', 'hamilton', 'covid_2020')` is a legitimate
Table A row *and* a legitimate Table B row under D5(b), and the second write
`ON CONFLICT DO UPDATE`s the first away.

Under SPEC FR35's literal reading the two epoch sets are disjoint and the
existing key is exactly sufficient — which is some evidence the schema was
authored against FR35's reading, alongside the unused `PRE_HAWKES_EPOCHS`.

**This is latent, not yet broken:** `grep -rn validation_results --include=*.py
seraph/ scripts/` returns **no hits** — no writer exists yet. So it is free to
fix now and expensive after the ablation is persisted. Independently of the
fold decision, the PK should carry `table_id`, and carrying
`pre_registration_hash` too would let two pre-registered designs coexist
instead of the second silently overwriting the first — which is the whole point
of D5(d). `schema.sql` is C1's file and `seraph/validation/` is C10's, so
nothing was changed here.

### The smallest explicit approval decision needed

One sentence from the C10 owner, before `preregistration.json` is written:

> **Table B is evaluated on ___ (a) the 2 pre-2015 epochs, 2 folds, per SPEC
> FR35 literal · (b) all 6 epochs, 6 folds, per ARCHITECTURE D5(b).**

* **If (b)** — no code change; delete `PRE_HAWKES_EPOCHS` (its docstring is
  then false) and delete the xfail test. Note that (b) is a *de facto*
  amendment of SPEC FR35's stated scope and should be recorded as one.
* **If (a)** — `configuration_list()`'s Table B branch takes
  `PRE_HAWKES_EPOCHS`; the xfail test XPASSes and `strict=True` fails the suite
  until the marker is removed deliberately. The 20 configurations are unchanged
  either way; only `folds` and `epochs` on the 6 Table B rows move.

**Consequence of not deciding:** D5(d) requires the design committed and hashed
*before the first AUC*, and `folds`/`epochs` are inside the hashed payload
(`build()` embeds `configuration_list()` wholesale). An ablation run now freezes
whichever reading happens to be in the code, and "a result whose hash does not
match the committed file is not reportable".

**Workstream D's recommendation, offered as a recommendation and not a
decision: (a).** Three reasons, in descending strength:

1. **SPEC is the senior document** (AGENTS.md §1) and FR35 `[v2]` says "on the
   2 pre-2015 epochs" in plain words.
2. **The schema only works under (a).** 24 of 128 `EvaluationRows` are silently
   overwritten under (b) and 0 under (a) — and `validation_results`' key was
   evidently authored against FR35's reading.
3. **`PRE_HAWKES_EPOCHS` exists, is documented as Table B's epoch set, and is
   dead code.** Someone wrote (a) and it was never wired up.

The counter-argument deserves stating: (b) uses more of the six positive events
on the subsets that do not need restricting, which at n=6 is a real statistical
gain. If (b) is chosen, it should be chosen **explicitly as an amendment to
FR35**, and the `validation_results` primary key must gain `table_id` first or
a third of Table B's rows will vanish.

**Not decided here. Nothing in `seraph/validation/` was changed** — C10 is
another owner's component and the design is pre-registration-hashed.

Secondary, non-blocking observation: `preregistration.py`'s module docstring
says "fourteen configurations" while `configuration_list()` returns 20. Under
the resolution above the docstring is the thing that is wrong (it should read
"fourteen in Table A, six in Table B"). A one-line docstring fix in another
owner's file, left to them.

### Commands and exit codes

```
$ .venv/Scripts/python.exe -m pytest tests/test_fr35_ablation_design_pins.py -v
  2 passed, 1 xfailed   exit 0      (new file)

$ .venv/Scripts/python.exe -m pytest tests/test_c10_harness.py -q
  (unchanged — see the post-change suite in the -54- log)
```

---

## D-3. C7 converged-optimum decision · classification (2)

**Diagnostic only. `seraph/pillars/hamilton/engine.py` was not touched and the
selection rule is unchanged.**

### The question, restated precisely

`HAMILTON-CAUSAL-POSTFIX.md` §5 establishes that on causal blocks 10 and 11 the
optimiser **found a point that satisfies nesting and then threw it away** for
failing BFGS's convergence test:

| blk | selected (converged) | discarded (non-converged) | `llf_restricted` | LR if discarded were kept |
|---|---|---|---|---|
| 10 | 38,518.59 | **39,392.03** | 39,378.13 | **+27.8** |
| 11 | 40,705.23 | **41,883.88** | 41,866.68 | **+34.4** |

(`LR = 2·Δllf`, the convention used throughout that document.) The selected fits
sit 859 and 1,162 llf *below* their own nested restrictions, which is impossible
at a true maximum — these are the surviving 2/14 nesting violations.

**"Converged" and "is a valid optimum" are different claims, and the engine
currently tests only the first.** `fit()` reads
`mle_retvals["converged"]`, which for `scipy.optimize.fmin_bfgs` is
`warnflag == 0` — i.e. "the gradient-norm tolerance was met within `maxiter`".
That flag fails for two very different reasons:

* `warnflag = 1` — **max iterations reached.** The point is simply unfinished;
  it says nothing about whether a valid optimum exists nearby.
* `warnflag = 2` — **precision loss / line-search failure.** Typical on a
  *ridge*: the likelihood is flat along some direction, so no step improves it
  to within tolerance even though the gradient never gets small.

Neither flag is evidence that the point is *not* a maximum. The evidence that
settles it is curvature, so this diagnostic measures, at **both** the selected
and the discarded parameter vector:

| quantity | what it decides |
|---|---|
| `scipy`'s own `gopt` norm, plus an independent numerical ∇ of the log-likelihood | is the gradient actually small, in the space BFGS optimises? |
| eigenvalues of the numerical Hessian | all `< 0` → genuine local **maximum**; mixed signs → **saddle** (ascent directions remain); some `≈ 0` → **ridge** |
| Hessian condition number, and the count of eigenvalues below `1e-6`/`1e-8` of the largest | distinguishes a flat ridge from a well-identified interior optimum |
| implied transition probabilities (min off-diagonal, max self-persistence) and `max abs` logit coefficient | **boundary proximity.** Under TVTP the logit block is *unconstrained*, so the only boundary is saturation at `p → 0/1`, which is a boundary at infinity |
| regime variances | the one genuine hard bound (`> 0`) |

### Method, and why it is read-only

The script re-runs `fit()`'s start enumeration verbatim — statsmodels' default,
the 4 seeded random restarts, `_tvtp_start_from_constant` and
`_tvtp_start_from_intercept_only` — and keeps the **parameters** of each
candidate, which `fit()` discards. `seraph/pillars/hamilton/engine.py` is
imported, never modified; one `SELECT` on `hamilton_output`; nothing persisted.

### Measured results

_Full output in `20261013T130202Z-53-hamilton-converged-optimum-diagnostics.log`._

#### Block 10 — all seven starts, `train_n = 4520`, `train_last = 2023-03-23`

```
start                        llf      converged  warnflag   |gopt|
statsmodels_default     38,518.59      True         0       1.1089e-05
random_0                38,518.59      True         0       7.4402e-06
random_1                38,518.59      True         0       9.2863e-06
random_2                39,367.84      False        1       4.7775e-01
random_3                38,518.59      True         0       1.0435e-05
warm_from_constant      39,392.03      False        1       8.4178e-04
warm_from_intercept_only 39,392.03     False        1       8.4178e-04
```

Three facts before any curvature analysis:

1. **Four independent starts converge to the identical 38,518.59** with
   gradient norms ~1e-5. That is a genuine, reproducible attractor, not a fluke
   of one seed.
2. **Both warm starts reach the identical 39,392.03** and both fail to
   converge. Also a reproducible attractor.
3. **`warnflag = 1` on every non-converged candidate — "maximum iterations
   reached", not `2` ("precision loss").** So the discarded points were not
   rejected because the optimiser broke down; they were rejected because
   `maxiter = 200` ran out. That is a budget, not a verdict on validity.
4. **There are at least three distinct attractors**, not two: 38,518.59 (×4
   starts, converged), 39,367.84 (`random_2`, `|gopt|` = 0.478) and 39,392.03
   (×2 warm starts). The likelihood surface is multi-modal *and* flat, and the
   two highest modes are both non-converged.

#### Block 10 — curvature and boundary at the two points

| quantity | SELECTED, converged, llf 38,518.59 | DISCARDED, non-conv., llf 39,392.03 |
|---|---|---|
| `n_params` | 30 | 30 |
| scipy `warnflag` | 0 | 1 (max iterations) |
| scipy `|gopt|` | **1.11e-05** | **8.42e-04** |
| Hessian λ_min | −1.169e+10 | −2.890e+10 |
| Hessian λ_max | **+1.393e-06** | **+4.731e-07** |
| # eigenvalues > 0 | **3** | **1** |
| # eigenvalues < 0 | 27 | 29 |
| condition number | **7.92e+16** | **6.11e+16** |
| # eigenvalues < 1e-6·λ_max | **12** | **12** |
| max abs logit coefficient | 29.94 | **434.32** |
| min off-diagonal transition prob | −3.55e-15 | −5.68e-14 |
| max self-persistence | 0.99999 | 0.999583 |
| **fraction of dates with an off-diagonal < 1e-6** | **1.000** | 0.992 |
| min regime variance (bound is 0) | 0.00264 | 0.00242 |

#### Block 11 — all seven starts, `train_n = 4772`, `train_last = 2024-04-01`

```
start                        llf      converged  warnflag   |gopt|
statsmodels_default     41,882.55      False        1       8.8652e-02
random_0                40,705.23      True         0       1.2810e-05
random_1                41,882.30      False        1       1.8829e-02
random_2                41,883.32      False        1       9.8724e-02
random_3                40,705.23      True         0       1.6216e-05
warm_from_constant      41,883.80      False        1       6.0348e-01
warm_from_intercept_only 41,883.88     False        1       2.6525e-01
```

**Five of seven starts land in the 41,882–41,884 region and all five fail the
convergence test. Only two converge, both to 40,705.23 — 1,179 llf lower.** So
the optimiser finds the better region from the *majority* of starting points
and can never certify it. Again `warnflag = 1` (max iterations) in every case,
never `2`.

#### Block 11 — curvature and boundary at the two points

| quantity | SELECTED, converged, llf 40,705.23 | DISCARDED, non-conv., llf 41,883.88 |
|---|---|---|
| scipy `warnflag` | 0 | 1 (max iterations) |
| scipy `|gopt|` | 1.28e-05 | 2.65e-01 |
| Hessian λ_min | −1.158e+10 | −2.343e+10 |
| Hessian λ_max | **+2.86e-06** | **−5.02e-05** |
| # eigenvalues > 0 | **3** | **0** |
| # eigenvalues < 0 | 27 | **30** |
| condition number | 3.19e+16 | **4.67e+14** (100× better) |
| # eigenvalues < 1e-6·λ_max | 12 | 12 |
| **second-order test** | indefinite | **negative definite → local MAXIMUM** |
| max abs logit coefficient | 26.37 | 95.21 |
| min off-diagonal transition prob | −3.55e-15 | −1.40e-14 |
| max self-persistence | 0.99999 | **1.000000** (absorbing) |
| fraction of dates, off-diagonal < 1e-6 | **1.000** | 0.9317 |
| min regime variance | 0.00299 | 0.00262 |

**Block 11 reverses block 10's verdict, and this is the single most important
result in §D-3.** The **discarded, non-converged** candidate has **all 30
Hessian eigenvalues negative** — it passes the textbook second-order test for a
local maximum — while the **selected, converged** candidate does not (3
positive). Its Hessian is also **two orders of magnitude better conditioned**
(4.7e+14 against 3.2e+16). On this block the convergence flag rejected a point
that is a local maximum and accepted one that is not, at a cost of 1,179 llf.

Two caveats kept in view: λ_max = −5.02e-05 against |λ|_max = 2.34e+10 is still
~1e-15 relative, so "negative definite" is itself near the numerical floor; and
the point has one **fully absorbing** regime (`p_ii = 1.000000`) with
`|coef| = 95`, which is a boundary hit in its own right.

#### What the evidence supports

#### Side by side

| | blk 10 SELECTED | blk 10 DISCARDED | blk 11 SELECTED | blk 11 DISCARDED |
|---|---|---|---|---|
| llf | 38,518.59 | 39,392.03 | 40,705.23 | 41,883.88 |
| converged | yes | no (warnflag 1) | yes | no (warnflag 1) |
| `|gopt|` | 1.11e-05 | 8.42e-04 | 1.28e-05 | 2.65e-01 |
| # positive Hessian eigenvalues | **3** | 1 | **3** | **0** |
| second-order test | fails | fails | fails | **PASSES** |
| condition number | 7.9e+16 | 6.1e+16 | 3.2e+16 | **4.7e+14** |
| # near-null directions (of 30) | 12 | 12 | 12 | 12 |
| max abs logit coefficient | 29.9 | **434.3** | 26.4 | 95.2 |
| frac. dates off-diag < 1e-6 | **1.000** | 0.992 | **1.000** | 0.932 |
| min variance (bound 0) | 0.00264 | 0.00242 | 0.00299 | 0.00262 |
| `llf_restricted` | 39,378.13 | — | 41,866.68 | — |
| LR if this point were kept | −1,719.1 | **+27.8** | −2,322.9 | **+34.4** |

#### Verdict on the question that decides it

The question is binary and the two readings imply opposite decisions:

> **(i)** the discarded higher-llf point is a **genuine interior optimum that
> the convergence test wrongly rejected** → the rule is costing real likelihood
> and should be relaxed; or
> **(ii)** it is a **boundary or ridge point where the higher likelihood is not
> evidence of a better optimum** → the rule is doing its job and the extra llf
> is an artefact of saturation.

**The two blocks do NOT agree. The answer is (i) on block 11 and (ii) on block
10.**

| | block 10 | block 11 |
|---|---|---|
| **verdict** | **(ii) ridge / boundary point** | **(i) genuine interior optimum, wrongly rejected** |
| decisive evidence | Hessian **indefinite** (1 positive eigenvalue); `|coef| = 434.3`, i.e. a transition probability saturated to `e^−434`; condition number 6.1e+16, no better than the selected point's 7.9e+16 | Hessian **negative definite, 30/30 eigenvalues < 0**; condition number **4.7e+14, 100× better** than the selected point's 3.2e+16; `|coef| = 95`, far less extreme than block 10's |
| so the extra llf is… | bought by pushing further out a boundary at infinity — not evidence of a better optimum | a real likelihood improvement at a point that satisfies the second-order condition |
| would accepting it fix nesting? | yes numerically (LR +27.8) but on an invalid point | yes (LR +34.4) **and** on a valid point |
| caveat | — | one regime is **fully absorbing** (`p_ii = 1.000000`), and λ_max = −5.0e-05 is itself near the numerical floor |

**Both answers come with the same background condition**, which is why neither
block gives a clean licence to change the rule: **12 of 30 Hessian eigenvalues
are near-null at all four points measured**, so the model is weakly identified
everywhere and the second-order verdicts rest on eigenvalues close to double
precision. Block 11's "negative definite" is credible mainly because its *whole
sign pattern* is consistent **and** its conditioning is two orders of magnitude
better — not because any single eigenvalue is comfortably negative.

**And on both blocks the currently-returned, "converged" fit fails the
second-order test** (3 positive eigenvalues each). So whichever reading applies
to the discarded candidate, the value the engine actually emits today is not a
local maximum in either block.

**1. The two blocks disagree, and that is the headline.** On **block 11** the
discarded candidate **passes** the second-order test (30/30 negative
eigenvalues) and is 100× better conditioned, while the selected one fails it.
On **block 10** *neither* passes, and the discarded one sits far further out on
the boundary (`|coef| = 434` against 30). So the answer is **block-dependent**,
and no blanket rule change is right.

**2. The one thing true at all four points: the selected fits are never
maxima.** Both "converged" fits have **3 positive Hessian eigenvalues**. The
convergence flag certifies a point with remaining ascent directions in both
blocks. Whatever is decided about the discarded candidates, the currently
*returned* values are not local maxima.

**3. Read the magnitudes before calling anything a saddle.** The positive
eigenvalues are `+1.4e-06`, `+4.7e-07`, `+2.9e-06` against largest-magnitude
eigenvalues of `1e+10`–`3e+10` — relative size ~`1e-16`, i.e. **machine
epsilon**. They are not ascent directions but **flat directions whose sign is
numerical noise**. The honest description of the three failing points is a
**plateau / ridge**, not a saddle; the script's own `verdict_curvature` string
says "SADDLE" and **is too strong**, and is reported corrected here. By the same
token block 11's "negative definite" verdict rests on λ_max = −5.0e-05, also
near the floor — but its *whole sign pattern* is consistent and its
conditioning is two orders of magnitude better, which the others' are not.

**4. The model is weakly identified at every point measured.** **12 of 30**
Hessian eigenvalues are below `1e-6` of the largest at all four points, with
condition numbers `1e+14`–`1e+17`. Twelve directions in the 30-dimensional
parameter space carry no measurable curvature. This is the stable, block-
independent finding, and it is a **specification** property, not an optimiser
one.

**5. The likelihood gain is bought partly with boundary saturation.** Under
TVTP the logit block is unconstrained, so the only boundary is saturation at
`p → 0` or `1`. The discarded points sit at `|coef| = 434` (block 10) and `95`
(block 11, with one regime **fully absorbing**, `p_ii = 1.000000`). All four
points report *negative* minimum off-diagonal transition probabilities
(−3.6e-15 … −1.4e-14) — floating-point underflow of a quantity that must be
≥ 0.

**6. A previously unreported number, worse than the published one.**
`HAMILTON-CAUSAL-POSTFIX.md` §5b reports 38.6% of dates with a minimum
off-diagonal transition below `1e-6` for the **full-sample** fit. At **both**
walk-forward blocks' selected points it is **100% of dates**
(`frac_dates_offdiag_below_1e6 = 1.000`). The walk-forward fits are
substantially more absorbing than the full-sample fit that was characterised,
and it is the *converged* fits that are the most absorbing of the four.

**7. The emission block is healthy at all four points.** Minimum regime
variance 0.0024–0.0030, far from its only hard bound of 0. The pathology is
entirely in the TVTP transition/logit block.

**A limitation of this diagnostic, stated rather than buried.** The `-53-` log
also reports `grad_norm_constrained` ≈ 2.7e+08 and `grad_norm_unconstrained`
≈ 5.8e+04 from my own `approx_fprime`. **Those two numbers should not be
used.** They were computed with a *fixed* absolute step of `1e-5` against a
parameter vector whose entries span 0.0026 to 434, so they are dominated by
truncation error. The trustworthy gradient measure is scipy's own `gopt`
(1.11e-05 and 8.42e-04), computed with the optimiser's internal scaling, and
that is what is used above. The Hessian used a *relative* step
(`1e-4·max(|θ|,1)`) and is better behaved — but with a condition number of
`1e+17` its smallest eigenvalues are at the edge of double precision, which is
exactly why conclusion 2 reads the magnitudes rather than the signs.

**Consequence for the rule — stated as evidence, not as a decision.** Both of
the options `HAMILTON-CAUSAL-POSTFIX.md` §5 floats are contradicted by these
measurements:

* **"Accept a non-converged candidate when it beats every converged one by more
  than some margin."** Correct on **block 11** — the candidate it would accept
  is a genuine local maximum, better conditioned, and satisfies nesting
  (LR +34.4). **Wrong on block 10** — the candidate it would accept is *also*
  not a maximum and sits at `|coef| = 434`, so it would substitute one invalid
  point for another and make the nesting check pass without making the optimum
  valid. A margin rule cannot tell these two cases apart: the margins are
  +873.4 and +1,178.7, both large.
* **"A gradient-norm criterion instead of statsmodels' convergence flag."**
  **Would change nothing.** `|gopt|` is already `1.11e-05` and `1.28e-05` at the
  two selected points — any sane gradient-norm threshold accepts exactly the
  same two non-maxima the current flag accepts, and still rejects block 11's
  genuine maximum (`|gopt| = 0.265`).

**What the evidence does support is a second-order check**, because that is the
discriminator that actually separates the four points: require the Hessian at
the returned point to be negative definite (or, given the `1e-16` relative
noise floor, to have no eigenvalue exceeding `+ε·|λ|_max`). Applied here it
would accept block 11's 41,883.88 (a maximum, nesting satisfied) and reject
**both** of block 10's candidates, flagging that block as having no identified
optimum. That is the correct answer in both blocks, which neither of the two
proposed rules achieves.

This is offered as the inference the measurements license. **It is still a rule
change and therefore still the C7 owner's decision** — in particular, a
second-order check would have returned *no fit at all* for block 10, which
requires deciding what the engine emits in that case (`HAMILTON-UNAVAILABLE-DECISION.md`
is the relevant precedent).

**So the 2/14 nesting violation has two causes, not one, and they differ by
block.** On block 11 it is genuinely the selection rule discarding a valid
optimum. On block 10 it is the TVTP transition block being unidentified, with
no valid optimum available to select. The common substrate — 12 null directions
out of 30 at every point — is a **specification** property, and it is what
makes the convergence flag unreliable in the first place: on a surface that
flat, whether BFGS's tolerance is met is close to arbitrary.

This sits alongside, and does not duplicate, `HAMILTON-REGIME-SUPPORT.md` §5,
which asks a different question (is there regime structure at all?) and answers
**"NOT DISTINGUISHABLE from a no-regime process"** — AAFT surrogate null
`p = 0.7143`, AR(1) `p = 0.9524`. That is a statement about the *regimes*; this
is a statement about the *transition parameterisation*. They are independent
findings pointing the same way, and together with NFR17 separation of 0.291σ
against a 3σ requirement they make the same practical recommendation.

**What Workstream D did NOT do:** change the selection rule, change `maxiter`,
or touch `seraph/pillars/hamilton/engine.py`. Those are the C7 owner's calls.

**For the C7 owner — the decision this evidence actually frames.** The question
is not "converged vs higher-llf", because the answer to that differs by block.
It is whether a 30-parameter TVTP transition block is identifiable at all on
~4,500 observations when 12 of its 30 directions carry no curvature. Options
that follow from the measurements rather than from the convergence flag, in
recommended order:

1. **Raise `maxiter` above 200 and re-test blocks 10 and 11.** Every single
   non-converged candidate across both blocks reports `warnflag = 1` — *maximum
   iterations reached* — and never `2` (precision loss). The convergence
   failures may be nothing more than the 200-iteration budget. **Cheapest
   action, needs no approval, purely diagnostic, and could settle the whole
   question.** Recommended first step.
2. **Replace the binary convergence flag with a second-order check** (Hessian
   negative definite at the returned point, with an `ε·|λ|_max` tolerance for
   the `1e-16` noise floor). This is the only criterion tested here that gets
   both blocks right. Requires deciding what to emit when no candidate passes,
   as happens on block 10.
3. **Reduce the transition parameterisation** so it is identified — a shared
   slope across destination regimes, or one logit coefficient on `z_t` rather
   than one per transition. 12 null directions out of 30 is a specification
   problem with a specification fix, and it would also make options 1 and 2
   better behaved.
4. **Penalise or bound the logit block** so `|coef| = 434` is unreachable. A
   real change to FR21; needs approval.
5. **Report Hamilton as unavailable for the affected blocks**, per
   `HAMILTON-UNAVAILABLE-DECISION.md`, rather than emitting a fit that is not a
   local maximum. Note this is already the de facto position: the causal series
   is not production-eligible (NFR17 0.291σ against 3σ) and `hamilton_output`
   was never written from it.

**Cost note for whichever is chosen:** reproducing this diagnostic took
**~54 minutes** for two blocks (1,055 s and 611 s of start enumeration, seven
fits of 72–193 s each, ~8 s per Hessian). A 14-block re-run at raised `maxiter`
should be budgeted at several hours.

---

## D-4. Data-integrity and reproducibility sweep

### `check_invariants.py` — identical before and after, exit 0 both times

```
$ .venv/Scripts/python.exe scripts/check_invariants.py
  [ok] PILLAR_ORDER consistency
  [ok] C9 fusion purity (no validation/ import, no DB driver)
  [ok] AR_t placement (C4, not C6)
  [ok] Explicit IST timestamps
  [ok] shared_types frozen= audit (info only)
INVARIANTS_EXIT=0
```

Run twice: pre-change in the `-52-` log (12:52Z) and post-change in the `-57-`
log (13:42Z). Byte-identical output, **exit 0** both times.

**On the full suite, and a caveat that matters more than the number.** The
pre-change baseline is the one the mandate designates,
`20261013T072658Z-30-final-full-suite.log`: **1 failed, 170 passed in 950.29s**,
the single failure being CT-3's jump-density check. The `-52-` re-run of it was
**cancelled deliberately** (annotated in the log itself): it was not a clean
"before" — two other workstreams added test files to `tests/` while it was
running (`test_replay_causality.py` at 18:22 IST, the minute it launched;
`test_acceleration_signal_causality.py` at 18:28 IST, after collection) — and it
was starving the critical-path D-3 job of CPU.

**The suite is a moving target across concurrent workstreams**, so the headline
count must not be attributed to Workstream D alone. Collected count was 171 at
the `-30-` baseline and **210** by 13:13 UTC, of which only **6** are
Workstream D's. A third workstream was running its own full suite concurrently
(`20261013T130010Z-64-full-suite-after-replay.log`). The attributable delta is
therefore stated per-file rather than as a total:

| file | Workstream D's effect |
|---|---|
| `tests/contract/test_ct3_jump_sufficiency.py` | **unchanged behaviour** — 1 failed, 3 passed before and after; docstrings only |
| `tests/test_c4_lee_mykland_calibration.py` | **new** — 2 passed, 1 xfailed |
| `tests/test_fr35_ablation_design_pins.py` | **new** — 2 passed, 1 xfailed |

i.e. **+4 passed, +2 xfailed, +0 failed**. Any other movement in the total is
another workstream's.

**Final post-change full suite — two independent runs agree exactly:**

```
$ .venv/Scripts/python.exe -m pytest tests/ -q
  1 failed, 207 passed, 2 xfailed in 1380.60s (0:23:00)   exit 1
      -> 20261013T134259Z-57-post-change-invariants-and-full-suite.log  (Workstream D)
  1 failed, 207 passed, 2 xfailed in 1097.52s (0:18:17)   exit 1
      -> 20261013T135032Z-70-full-suite-FINAL.log                      (coordinator)
```

Against the session-start baseline of **1 failed, 170 passed**:

* **The single failure is unchanged** — `test_ct3_negative_jump_density_supports_a_one_day_window`,
  `assert 0.0909 >= 1.0` on EXIDEIND (2,475 bars, ~33 trading days, 3 negative
  jumps). That is Workstream D's **deliberately preserved** red; §D-1a is what
  it means. Exit code 1 is therefore the expected outcome, not a regression.
* **Both `xfailed` are Workstream D's pins** — the Lee–Mykland calibration
  (§D-1b) and the FR35 Table B fold count (§D-2). Both are
  `xfail(strict=True)`, so each will **fail the suite** the moment the
  underlying question is resolved in code, which is the intended trigger.
* **+37 passed (170 → 207)** across three concurrent workstreams; **4 of those
  are Workstream D's**. The remaining 33 are other workstreams'.
* **Zero new failures from any workstream.**

### The five mandated checks

| # | Check | Verdict |
|---|---|---|
| 1 | Timestamps IST and explicit | **verified correct**, defended at the seam |
| 2 | `writeBatch` idempotency (CT-1) | **verified correct**, read-only |
| 3 | D4 bounded saturating noise | **verified correct**, sole implementation |
| 4 | `PILLAR_ORDER` consistency | **verified correct**, single definition |
| 5 | D3 `Ω_t` on common support | **verified correct** |

**1. Timestamps — verified correct.** The invariant is enforced mechanically at
three layers, so a naive or UTC-implicit timestamp cannot reach storage:

* `ISOTimestamp` (`shared_types/core.py:27`) is
  `StringConstraints(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30$")`
  — the literal `+05:30` is **required**. A `Z`, a `+00:00` or a naive string
  fails pydantic validation at the component seam.
* `ist_timestamp()` raises `ValueError("naive datetime — timestamps must be
  explicit IST (+05:30)")` on a naive input rather than assuming a zone.
* Every timestamp column in `schema.sql` is `timestamptz`. Measured over
  `information_schema.columns`: of the **29** columns whose type is
  `timestamp*`, `date` or an array, **0 are `timestamp without time zone`**.
  `reconciled_state.tau_last_update` reports as `ARRAY`; its element type is
  `timestamptz[]` (`schema.sql:148`) — the live element-type probe in the `-54-`
  log queried the table under the wrong name (`reconciliation_state`) and
  returned "absent", so that one line is inconclusive and the confirmation is
  from `schema.sql`, not from the query.

No silent UTC coercion in the stored data. The server's `TimeZone` is `UTC`, so
values display as `+00:00`, but the stored instants are correct — `csrs.ts` is
**15:30:00 IST on all 4,714 rows** (1 distinct time-of-day), and 99.945% of
`intraday_bars` sit inside the 09:15–15:30 IST session. A silent UTC coercion
would have put ~100% of bars at 14:45–21:00 IST.

**2. `writeBatch` idempotency — verified correct, read-only. No write was
performed.** Two independent lines of evidence:

* *SQL.* `_upsert_sql` emits
  `INSERT … ON CONFLICT (<natural key>) DO UPDATE SET … RETURNING (xmax = 0) AS inserted`.
  The `xmax = 0` predicate is the correct discriminator — true only for a real
  insert — so a re-run of identical rows reports `inserted: 0`. Natural keys
  match AGENTS.md §5: E1 `(symbol, ts)`, E3 `(symbol, date)`, E4 `(date)`,
  E5 `(event_id)`, E14 `(date)`; E6 `(scope, scope_id, ts)` via
  `scripts/write_hawkes_production.py`. The bulk `COPY` path stages into a temp
  table and runs the **same** upsert with `SELECT DISTINCT ON (key)`, so
  within-batch duplicates cannot double-insert. The watermark upsert uses
  `GREATEST(existing, EXCLUDED)`, so a re-run cannot move it backwards.
* *Empirical, already on record.* `20261012T223359Z-14-hawkes-E6-idempotency.log`
  re-wrote 10 real E6 production keys:
  `[hawkes] E6 rows: 473 -> 473 (inserted 0, updated 10)`, exit 0. That is
  CT-1 semantics measured on production data.

**3. D4 noise model — verified correct.** `seraph/reconciliation/noise_model.py:32`
is exactly D4's bounded saturating exponential:

```python
return base + (r_max - base) * (1.0 - exp(-delta_bars / self.h_bars))
```

`r_max = r_max_ratio · base` with `r_max_ratio = 100.0` per D4's
initialisation; `delta_bars == inf` returns `r_max`, so the "absent pillar =
`R → ∞`" limit stays **finite** and the FR29 interval cannot diverge. No linear
or power form anywhere: `SaturatingNoise.r()` is the only observation-noise
implementation in `seraph/`, and all three call sites
(`kalman.py:177`, `:204`, `:225`) go through it. `_virtual_update` applies the
same curve to the age-inflated transient case, which is the D2 row-4 behaviour.

**4. `PILLAR_ORDER` — verified correct.** One definition,
`seraph/shared_types/core.py:54`, `["hawkes", "rmt", "hamilton"]`. Every
consumer imports it rather than re-declaring it — `Vec3`/`Mat3`/
`AvailabilityMask` in `shared_types`, `kalman.py`, `fusion/shapley.py`,
`validation/ablation.py`, `decision_support/artefacts.py`,
`dashboard/gateway.py`, `fixtures/mock_generator.py`. `check_invariants.py`
greps for any redefinition and reports `[ok]`.

Two observations, neither a defect, both in approval-gated or other-owner files
and therefore left alone:

* `PILLAR_ORDER` is a **mutable `list`**, not a tuple, for a value AGENTS.md §5
  calls "global and fixed". Nothing mutates it today; a tuple would make that
  structural. `seraph/shared_types/` is approval-gated — ask before changing.
* `preregistration.py:47` writes the literal `("hawkes", "rmt", "hamilton")`
  instead of importing `PILLAR_ORDER`. The order is correct, so there is no
  bug, but `check_invariants.py`'s regex only matches `PILLAR_ORDER = [...]`
  and would not catch a future divergence here.

**5. D3 `Ω_t` — verified correct.** `seraph/pillars/rmt/engine.py:215-248`
intersects membership (`pairs` from `prev_index`), restricts both eigenvectors
to that support, and **renormalises both before the inner product**:
`omega_t = 1 - |(a/‖a‖) · (b/‖b‖)|`. Empty support returns
`Err(ConstraintViolated("Omega_t requires non-empty common support (D3)"))`
rather than a number; a degenerate restricted vector likewise. Overlap below
`COMMON_SUPPORT_FLOOR = 0.85` emits `COMMON_SUPPORT_LOW` and a
`REBALANCE_ADJACENT` warning fires across a membership change, so a thin
overlap is flagged rather than hidden.

### New finding — the session calendar is undocumented, and four items are real defects

**Classification: mostly legitimate, with a genuine defect residue.**
**15 of 17** non-standard session dates are real NSE calendar behaviour →
**(2)**, missing diagnostic, now supplied. **The residue is 4 items → (1)**,
routine implementation defects. Evidence:
`20261013T133418Z-56-offsession-session-calendar-impact.log`.

**Not a timestamp defect** — the `+05:30` handling is correct (checks 1 above).
The issue is that nothing in the pipeline knows the NSE session calendar.

#### How many rows, and which sessions

| population | rows | share of `intraday_bars` |
|---|---|---|
| bars **outside** 09:15–15:30 IST | **10,368** | 0.0552% |
| bars on **any** of the 17 non-standard session dates | **32,147** | 0.171% |
| of which **genuinely impossible** (post-close, 2021-02-24) | **30** | 0.00016% |
| sessions with the expected 75 bar-times | 2,840 | — |
| sessions with 12 bar-times (Muhurat) | 10 | — |
| **missing** bars implied by the 2017-07-10 morning gap | ~3,100 | — |

So the *present-but-wrong* population is tiny (30 rows); the larger numbers are
**legitimate sessions of non-standard length**, and one defect is an *absence*
rather than a presence. Widening the question from "off-session" to "every
session that is not a standard 75-bar day" gives **17 dates** in four groups:

**(A) Muhurat (Diwali) sessions — 11 dates, legitimate.**

| date | wd | bars | symbols | IST window | in `daily_prices`? |
|---|---|---|---|---|---|
| 2015-11-11 | Wed | 1,100 | 79 | 17:35–18:45 | yes (1,134) |
| 2016-10-30 | Sun | 792 | 79 | 18:30–19:25 | yes (1,262) |
| 2017-10-19 | Thu | 814 | 81 | 18:30–19:25 | yes (1,375) |
| 2018-11-07 | Wed | 1,032 | 86 | 17:30–18:25 | yes (1,454) |
| **2019-10-27** | **Sun** | **1,044** | **87** | **18:15–19:10** | **NO — 0 rows** |
| **2020-11-14** | **Sat** | **1,080** | **90** | **18:15–19:10** | **NO — 0 rows** |
| 2021-11-04 | Thu | 1,092 | 91 | 18:15–19:10 | yes (1,769) |
| 2022-10-24 | Mon | 1,128 | 94 | 18:15–19:10 | yes (1,991) |
| 2023-11-12 | Sun | 1,128 | 94 | 18:15–19:10 | yes (2,249) |
| 2024-11-01 | Fri | 1,128 | 94 | 18:00–18:55 | yes (2,572) |
| 2025-10-21 | Tue | 1,128 | 94 | 13:45–14:40 | yes (2,842) |

Real sessions, so the bars are not spurious. Note 2025-10-21: NSE moved that
year's Muhurat to an **afternoon** window, which sits inside 09:15–15:30 and so
never appeared in the off-session count at all.

**(B) Circuit-breaker halt days — 2 dates, legitimate, and these are the ones
that touch evaluation.**

| date | wd | bar-times | missing | FR32 window |
|---|---|---|---|---|
| 2020-03-13 | Fri | 64 / 76 | 12 (~60 min) | **`covid_2020`: CRISIS** |
| 2020-03-23 | Mon | 64 / 76 | 12 (~60 min) | **`covid_2020`: CRISIS** |

Both are 09:15–15:25 days missing ~12 five-minute bars — NSE's 10% lower
circuit breaker halted trading for 45 minutes on each. **Legitimate, not a
defect**, but they are the two most extreme days of the COVID epoch and both
carry `rmt_output` and `hamilton_output` rows computed over a ~5.3-hour session
instead of 6.25. That belongs in the report's limitations, not in a bug fix.

**(C) Saturday special / DR-site sessions — 2 dates, legitimate.**
2024-03-02 (Sat) and 2024-05-18 (Sat), 1,974 bars each, 09:15–12:25, both
present in `daily_prices`. NSE ran special live trading sessions on both.

**(D) Genuine defects — 4 items, each classified, none fixed.**

| # | defect | class | fixed? | why not |
|---|---|---|---|---|
| **D-4.1** | **2017-07-10**: the entire morning is missing — 2,879 bars over 80 symbols, **12:30–15:25 only**, 36 of 75 bar-times. ~3,120 bars absent. No NSE halt is known for that date and `daily_prices` has a full 1,330 rows, so it is an **intraday ingestion gap**, not a short session. | **(1)** routine implementation defect | **No** | Fix is a re-backfill in `seraph/ingestion/` + a DB write. Both outside Workstream D's scope (DB is read-only). |
| **D-4.2** | **2021-02-24**: 30 **impossible** post-close bars — exactly **LUPIN and NTPC, 15 bars each, 15:45–16:55 IST** — on a day that also has a complete 2,699-bar regular session. NSE equity trading ends 15:30, so these cannot be real. A Kite API artefact. | **(1)** routine implementation defect | **No** | Removal is a `DELETE`. DB is read-only for this workstream. |
| **D-4.3** | **2019-10-27** (Muhurat, Sun): 1,044 intraday bars but **zero** rows in `daily_prices` / `rmt_output` / `hamilton_output`. | **(1)** routine implementation defect | **No** | `seraph/ingestion/` is C2's; remedy needs a daily backfill + write. |
| **D-4.4** | **2020-11-14** (Muhurat, Sat): 1,080 intraday bars, same zero-row absence from the daily corpus. | **(1)** routine implementation defect | **No** | As D-4.3. |

**D-4.3 and D-4.4 are one defect with two instances, and weekday does not
explain them** — 2016-10-30 and 2023-11-12 are also Sundays and *are* present
in `daily_prices`. So the daily (EOD2/bhavcopy) and intraday (Kite) corpora
**disagree about whether a trading day exists**, for those two years only: 2 of
7,825 daily sessions. **None of the four falls inside any FR32 crisis or lead
window**, so none affects an evaluation result.

#### Does it affect any pillar output used in evaluation?

**No published evaluation result is invalidated.** Zero impact on the
epoch-windowed statistics; a 0.30%–1.06% contamination rate on the full-span
ones (quantified below the table). Measured:

| question | answer |
|---|---|
| `hawkes_output` rows on a non-standard session | **5 of 473 (1.06%)** — 2024-11-01 @18:55 (Muhurat), 2024-03-02 and 2024-05-18 @12:25 (Saturday), 2025-10-21 @14:40 (Muhurat), 2020-04-27 @15:30 |
| …of those, inside an FR32 crisis or lead window | **0 of 5** |
| `csrs` rows on an off-session date | **14 of 4,714 (0.30%)** |
| …inside an FR32 window | **0** |
| non-standard dates inside an FR32 window | **2 of 17** — 2020-03-13 and 2020-03-23, both `covid_2020`:CRISIS, both legitimate halts (group B) |
| the four group-(D) defects, inside an FR32 window | **0 of 4** |

FR32 windows used (break + 30 trading days; lead 5–15 trading days before),
from `seraph/validation/epochs.py` against `daily_prices`' own 7,825-session
calendar: `gfc_2008` 2008-09-15…10-29 · `taper_2013` 2013-05-22…07-03 ·
`ilfs_2018` 2018-09-21…11-06 · `covid_2020` 2020-02-20…04-08 ·
`tightening_2022` 2022-01-05…02-17 · `tariff_2026` 2026-02-01…03-16.

Note 2018-11-07 (Muhurat) lands **one session after** `ilfs_2018`'s crisis
window closes on 2018-11-06 — the nearest miss in the set, and it misses.

**Scope of that conclusion, stated precisely.** FR32-window membership is the
right test for the **epoch-windowed** statistics — FR33 AUC, mean lead time,
and the FR35 ablation — and on those the impact is exactly zero. It is *not*
the right test for **full-span** statistics such as the T1 detection
calibration and the early-warning power study, which run over the whole CSRS
series. For those the correct figure is the contamination rate: **14 of 4,714
`csrs` rows (0.30%)** sit on an off-session date, and **5 of 473
`hawkes_output` rows (1.06%)** on a non-standard session. That is small enough
not to move a threshold or an AUC, but it is a contamination rate rather than a
zero, and should be quoted that way rather than as "no impact".

#### Why it matters anyway, and what is recommended

`extract_jumps` runs on the **per-symbol concatenated close series**, so the
first bar after any session gap carries a multi-session gap return scored
against a bipower window estimated from the previous session. That is the single
most likely place in the pipeline for a spurious jump flag, and it compounds
with §D-1b: at an effective level near `1e-5` only a very large return is
flagged, and an overnight-plus-holiday gap return is exactly that.

**Not fixed, deliberately.** A session-calendar filter belongs in
`seraph/ingestion/` or `scripts/write_hawkes_production.py`; neither is
Workstream D's to edit, the daily-corpus gaps are C2's, and any remedy would
require rewriting `hawkes_output`, which the read-only database constraint
forbids. **Recommended, in priority order:**

1. Add an explicit NSE session calendar to `seraph/ingestion/` and treat each
   session as its own series for jump extraction (this also fixes the gap-return
   issue above).
2. Delete the 30 impossible post-close bars for LUPIN and NTPC on 2021-02-24.
3. Backfill 2017-07-10's missing morning, or mark the date as partial.
4. Reconcile 2019-10-27 and 2020-11-14 between the daily and intraday corpora.
5. Document groups (A)–(C) as retained-and-known in the report's limitations,
   with 2020-03-13 / 2020-03-23 called out explicitly because they sit inside
   the COVID crisis window.

---

## What needs approval, and what is executable now

### Approval gates — nothing here was crossed

| # | Decision needed | Owner | Urgency |
|---|---|---|---|
| 1 | **Table B's fold count**: SPEC FR35 literal (2 pre-2015 epochs, 2 folds) or ARCHITECTURE D5(b) (all 6, 6 folds)? Recommendation: **(a)**, §D-2. | C10 | **Blocking.** D5(d) requires the design hashed before the first AUC. One sentence. |
| 2 | **Correct the FR50 Lee–Mykland threshold scaling?** Recommendation: **Alternative A** — fix the code, amend SPEC FR10 `[v4]`'s `0.087`, re-derive AMENDMENT-03, re-run the E6 backfill. §D-1b. | C4/C5 + whoever owns SPEC | Not blocking. Nothing downstream changes verdict. Schedule deliberately. |
| 3 | **Retire CT-3's 1.0-per-symbol-day gate?** `xfail(strict=True)` citing FR10 `[v4]`, or replace with a pooled-stream assertion. §D-1a. | C4/C5 | Cosmetic. The alternative is a permanently red suite whose single red is explained. |
| 4 | **Change the C7 converged-only selection rule?** §D-3's answer is **block-dependent**, so neither proposed rule is safe: on block 11 the discarded candidate IS a genuine interior optimum (Hessian negative definite), on block 10 it is a boundary/ridge point (`|coef| = 434`). A **margin rule** cannot tell them apart and a **gradient-norm rule** changes nothing. What the evidence supports is a **second-order (negative-definite Hessian) check**, which gets both blocks right — but that returns *no fit* for block 10, so it needs a paired decision on what the engine emits then. | C7 | Not blocking; Hamilton is not production-eligible either way (NFR17 0.291σ vs 3σ). **Try raising `maxiter` first — free, and may dissolve the question.** |
| 5 | **`seraph/shared_types/`**: make `PILLAR_ORDER` a tuple rather than a mutable list. §D-4 check 4. | approval-gated | Cosmetic robustness. |

### Executable now, no approval needed

1. **Raise `maxiter` above 200 and re-run blocks 10 and 11.** Every
   non-converged candidate reports `warnflag = 1` — *max iterations reached* —
   so the convergence failures may be nothing but the 200-iteration budget.
   This is a diagnostic run, not a rule change: pass `maxiter=2000` to the
   existing `fit()` from a script, touching no engine code. It is the single
   cheapest action that could collapse the whole §D-3 question, and it is the
   recommended first step for C7.
2. **Add `table_id` to `validation_results`' primary key** (`schema.sql:206`),
   and consider `pre_registration_hash` too. No writer exists yet, so this is
   free now and costs 24 silently-overwritten rows later. §D-2.
3. **Delete the 30 impossible post-close bars** for LUPIN and NTPC on
   2021-02-24. §D-4. Requires a DB write, so outside Workstream D's scope.
4. **Backfill 2017-07-10's missing morning** (~3,120 bars, 09:15–12:25) or mark
   the date partial. §D-4.
5. **Reconcile 2019-10-27 and 2020-11-14** between the daily and intraday
   corpora — present in `intraday_bars`, absent from `daily_prices`. §D-4.
6. **Fix `preregistration.py`'s module docstring** — "fourteen configurations"
   should read "fourteen in Table A, six in Table B". One line, C10's file.

---

## Reproduction

```bash
docker start seraph-timescaledb        # port 5433

# D-1
.venv/Scripts/python.exe -m pytest tests/contract/test_ct3_jump_sufficiency.py -v
.venv/Scripts/python.exe -m pytest tests/test_c4_lee_mykland_calibration.py -v

# D-2
.venv/Scripts/python.exe -m pytest tests/test_fr35_ablation_design_pins.py -v

# D-4
.venv/Scripts/python.exe scripts/check_invariants.py
.venv/Scripts/python.exe -m pytest tests/ -q
```

Every measurement script is embedded **verbatim at the end of its own log**, so
each number in this document is reproducible from the evidence artefact alone
without needing anything from a scratch directory:

| log | appended scripts | runtime |
|---|---|---|
| `-51-` | `lm_size.py` (Monte-Carlo size/power), `ct3_density.py` (full-universe density), plus the effective-α table | ~2 min |
| `-53-` | `d3_opt.py` (D-3 optimum diagnostics) | ~45 min |
| `-54-` | `tz_audit.py`, `offsession.py` | ~4 min |
| `-55-` | `d2_keyspace.py` (no DB access at all) | <1 s |
| `-56-` | `offsession_impact.py`, `odd2.py` | ~3 min |

```bash
# D-3 (the long one) — read-only, one SELECT on hamilton_output
D3_BLOCKS=10,11 .venv/Scripts/python.exe -I <d3_opt.py>
```

**Everything in this document is read-only with respect to the database.** The
only writes Workstream D made anywhere are: three files under `tests/` (one
docstring-only edit, two new files), this document, and the `-51-`…`-57-` logs.

**Workstream D made NO production change.** `git status --porcelain -- seraph/`
lists only `seraph/orchestration/__init__.py`,
`seraph/orchestration/adapters.py` and `seraph/pillars/hamilton/engine.py` —
all three already modified in the working tree *before* this session began (they
appear in the session-start git status). Workstream D edited **no file under
`seraph/`**, and in particular did not touch `seraph/pillars/hamilton/engine.py`
(§D-3), `seraph/validation/` (§D-2), `seraph/shared_types/`, `seraph/fusion/`,
`seraph/features/` or `seraph/reconciliation/` — the last two despite being in
its ownership list, because the only candidate change (§D-1b) turned out to need
a SPEC amendment. `scripts/check_invariants.py` is 5/5 `[ok]`, exit 0, before
and after.
