# FR35 pre-registration enumerates 20 configurations; ARCHITECTURE says 14

> ## ⚠ SUPERSEDED IN PART — 2026-10-14. READ THIS FIRST.
>
> **This document's framing is wrong and its §5 recommended fix must NOT be
> applied.** It argues from ARCHITECTURE D5's prose and never quotes SPEC.
>
> **SPEC FR35 `[v2]`, `docs/SPEC.md` line 243, verbatim:**
>
> > *"The system shall produce **Table A** (7 subsets × 2 reconciliation modes,
> > on the 4 Hawkes-covered epochs) and **Table B** (3 subsets × 2 modes, on the
> > 2 pre-2015 epochs), each reporting AUC and mean lead time."*
>
> 7 × 2 = 14, plus 3 × 2 = 6, is **20**. So `configuration_list()`'s 20
> configurations are **SPEC-correct**, and there is no 20-versus-14 defect. This
> document's §5 proposal to restrict Table A to the Hawkes-covered subsets (8
> configurations) **would violate SPEC and freeze a wrong pre-registration
> hash.** Do not apply it.
>
> There is also a methodological reason the duplication is right rather than
> accidental: `(rmt)` must appear in Table A on the **same 4 folds** as
> `(hawkes,rmt)`, or Hawkes's marginal contribution cannot be obtained by
> differencing them. Two tables with different fold counts is exactly what
> D5(b) means by keeping them separate.
>
> **What remains genuinely open is narrower, and still blocking:** Table B's
> **fold count**. SPEC says *"the 2 pre-2015 epochs"* (2 folds); ARCHITECTURE
> D5(b) says Table B uses all 6. `configuration_list()` implements D5(b)'s 6,
> while `preregistration.PRE_HAWKES_EPOCHS` encodes SPEC's reading, is exported,
> and is **never used**.
>
> **A new, independent argument for SPEC's reading**, found 2026-10-14:
> `validation_results`' primary key is `(pillar_subset, reconciliation_mode,
> xi_mode, epoch)` and **omits `table_id`**, which is declared `NOT NULL`. Under
> D5(b)'s 6-fold Table B the three subsets that appear in both tables collide on
> the 4 Hawkes-covered epochs — **24 of 128 `EvaluationRow`s would be silently
> overwritten**. Under SPEC's 2-fold reading, none would. No writer exists yet,
> so this is free to settle now.
>
> The original §1–§4 measurements below are accurate and are retained. Only the
> *interpretation* and the §5 recommendation are superseded.
>
> Evidence: `docs/evidence/BLOCKER-TRIAGE.md` §D-2, with
> `tests/test_fr35_ablation_design_pins.py` pinning the open question as a
> `strict=True` xfail and guarding the SPEC-correct 7/3 shape against this
> document's recommendation.


**2026-10-13, git `f3eaac8`. Found while assessing whether the FR35 ablation is
estimable on the new full-span CSRS series. NOT FIXED — surfaced for the C10
owner (D). No code or test changed.**

> **This must be settled before `preregistration.json` is committed.** D5(d):
> *"Before the first AUC is computed, commit a file recording … the full list of
> 14 configurations. Hash it. Every `EvaluationRow` carries
> `preRegistrationHash`. A result whose hash does not match the committed file
> is not reportable."* `build()`'s docstring adds: *"Nothing here may change once
> results exist."*
>
> Right now `preregistration.json` **does not exist** and the ablation has not
> been run, so this is free to fix. After the file is committed it is frozen, and
> every ablation result produced under a wrong list is unreportable.

---

## 1. The measurement

```
$ python -c "from seraph.validation.preregistration import configuration_list; ..."
total configurations: 20
by table: Counter({'A': 14, 'B': 6})

subsets in BOTH tables (double-counted): [('hamilton',), ('rmt',), ('rmt','hamilton')]
Table A subsets NOT involving hawkes: [('hamilton',), ('rmt',), ('rmt','hamilton')]
```

`(rmt)`, `(hamilton)` and `(rmt, hamilton)` each appear **twice**: in Table A at
`folds=4`, and again in Table B at `folds=6`.

## 2. Why that looks wrong

| source | says |
|---|---|
| ARCHITECTURE **D5** premise | "six positive events, **14 configurations**" |
| ARCHITECTURE **D5(b)** | "**Table A subsets involving Hawkes** can only use the 4 Hawkes-covered epochs → 4 folds. **Table B subsets (RMT, Hamilton, RMT+Hamilton)** use all 6 → 6 folds." |
| ARCHITECTURE **D5(c)** | "**All 14 configurations** are reported." |
| ARCHITECTURE **D5(d)** | "the **full list of 14 configurations**. Hash it." |
| ARCHITECTURE **R4** | "Six positive events, **14 configurations**, one calibration step." |
| `preregistration.py` **module docstring** | "six positive events, **fourteen** configurations" |
| `configuration_list()` **implementation** | **20** |
| `test_c10_harness.py::test_fr35_configuration_counts_match_the_spec` | asserts `len(a) == 14 and len(b) == 6`, i.e. **20**, with the docstring "Table A: 7 subsets x 2 modes = 14" |

D5(b) describes Table A as "subsets **involving Hawkes**" and enumerates Table B
as exactly {RMT, Hamilton, RMT+Hamilton}. On that reading:

* Table A = Hawkes-containing subsets = `(hawkes)`, `(hawkes,rmt)`,
  `(hawkes,hamilton)`, `(hawkes,rmt,hamilton)` = **4 × 2 modes = 8**
* Table B = **3 × 2 modes = 6**
* **Total = 14** — which is the only reading on which ARCHITECTURE's arithmetic
  closes, in all five places it states a count.

Note the module's own docstring already says "fourteen" while its code returns
20, so this is an internal contradiction, not only a doc/code divergence.

## 3. The competing reading, stated fairly

"14" could refer to **Table A alone** (7 subsets × 2 modes), with Table B's 6
additional and a 20 total. Against it: D5(d) says "the **full list** of 14", R4
and the D5 premise both use 14 to characterise the whole exercise, and no passage
anywhere states 20. For it: `_subsets(("hawkes","rmt","hamilton"))` returning all
7 is the natural way to write "the ablation over three pillars", and the existing
test's docstring reads that way.

I do not think the second reading survives D5(d)'s "full list", but it is not
absurd, which is why this is being surfaced rather than decided.

## 4. Why it matters beyond the count

1. **`(rmt)` and `(rmt, hamilton)` would be scored on 4 folds in Table A**, when
   D5(b) explicitly assigns those subsets 6. That discards two of six epochs —
   a third of the positive events — for no stated reason, on exactly the subsets
   that do not need restricting.
2. **The same subset appearing in two tables at two fold counts** is an active
   invitation to the error D5(b) exists to prevent: "Table A and Table B AUCs
   are not directly comparable and must not be placed in a single ranking." I
   made that exact mistake earlier this session with the nine-candidate table.
3. **The hash gates reportability.** A committed 20-config design that the spec
   says should be 14 makes every `EvaluationRow` carry a hash that does not
   correspond to the authoritative design.

## 5. Recommended fix, not applied

In `seraph/validation/preregistration.py::configuration_list()`, restrict Table A
to Hawkes-containing subsets:

```python
for subset in _subsets(("hawkes", "rmt", "hamilton")):
    if "hawkes" not in subset:
        continue            # D5(b): non-Hawkes subsets are Table B, on 6 folds
```

and update `test_fr35_configuration_counts_match_the_spec` to assert
`len(a) == 8`, `len(b) == 6`, total 14, plus a new assertion that no subset
appears in both tables. Per the mandate's rule on tests, that is a change to a
test whose *specification* is demonstrably wrong — against five statements in
ARCHITECTURE and the module's own docstring — and not a change to conceal a
failure. The evidence is recorded here either way.

## 6. Why I did not apply it

* C10 is owner **D**'s component (AGENTS.md §8), and this sets a hashed design
  that gates the reportability of every future ablation result.
* AGENTS.md §9: where the specification is open to reading, "flag it and ask
  rather than guessing" — and §1: "If you think a doc is wrong, say so and ask —
  don't silently deviate."
* It unblocks nothing today. The FR35 ablation is already blocked on Hamilton
  availability (`HAMILTON-REGIME-SUPPORT.md` §6): with Hamilton unavailable,
  every Hamilton-containing subset collapses to its available part via
  `score_subset`'s mask intersection, which degenerates 4 of 7 Table A subsets
  and 2 of 3 Table B subsets.

So the cost of waiting for a decision is zero, and the cost of guessing wrong is
a frozen, incorrect pre-registration hash.

## 7. Reproduction

```bash
python -c "
from collections import Counter
from seraph.validation.preregistration import configuration_list
cl = configuration_list()
print(len(cl), Counter(c['table'] for c in cl))
a = {tuple(c['pillarSubset']) for c in cl if c['table']=='A'}
b = {tuple(c['pillarSubset']) for c in cl if c['table']=='B'}
print('double-counted:', sorted(a & b))
"
```
