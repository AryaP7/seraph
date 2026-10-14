# Stress-Signal Study and the Pillar-3 Architecture Decision

> ## ⚠ §3 AND §6 PARTLY SUPERSEDED — read `DETECTION-CALIBRATION.md`
>
> The headline below — T1 detection AUC **0.5372 → 0.6743**, "the measurable
> incremental detection value the mandate asked for" — was measured against a
> nominal null that treats the 30 positive days per epoch as independent. They
> come from **four onsets** on the 2017+ CSRS span, and under a calibrated null
> the no-signal 95th percentile there is **0.7078**. Both configurations sit
> inside their own nulls, so the difference is not a detection result.
>
> Re-run on a full 2005+ span (6 onsets, `run_csrs_research.py --full-span`):
> **0.5218 → 0.6573**, where the 3-pillar value does clear both nulls
> (p = 0.034 / 0.040) but **fails Holm across 15 comparisons**.
>
> Also newly established, and more important: **Hawkes + RMT do not detect
> crises** — 2-pillar CSRS 0.5218 (p 0.40/0.41), RMT alone 0.4283 (p 0.79),
> Hawkes alone 0.5937 (p 0.32). §6's "Contemporaneous detection IMPROVED and
> measured" should read **NOT YET VALIDATED**.
>
> §1's `rv_level` correction, §2's refusal to claim `drawdown`'s T3 0.6735, and
> §3's decision not to add a fourth pillar all stand.

**2026-10-13, git `f3eaac8`, branch `evidence/pre-arya-experimentation`. Nothing committed.**
Evidence: `*-17-stress-candidate-study.log`, `*-18-csrs-with-stress-pillar.log`,
`*-19-stress-pillar-evaluation.log`.

---

## 1. The audit came first, and it overturned my own headline number

**Correction: realised volatility's AUC is 0.6098, not 0.7698.**

The 0.7698 I reported previously was measured on the **4-epoch, 2017+ CSRS span**.
On the full 6-epoch 2005–2026 span it is **0.6098**. That number was a
small-sample artefact of the shorter window, and the correction matters because
it changes which candidate wins.

Three further audit findings:

* **Label alignment is correct** — all six epochs produce exactly 30 labelled
  trading days from their break date.
* **The advantage is partly tautological.** Mean `rv_t_yz` is 0.6109 inside
  crisis windows vs 0.4979 outside — a ratio of only **1.23×**. Crisis windows
  *are* high-volatility windows by construction, so a volatility predictor is
  partly measuring the label. This is precisely why detection and prediction are
  scored against different targets below.
* **The signal is genuinely missing from the architecture**, not duplicated:
  `corr(rv, λ₁/N) = +0.28`, `corr(rv, hawkes n) = +0.23`, `corr(rv, CSRS) = +0.16`.

The market return series used for the derived candidates validates against
reality: its worst four days are **2020-03-23 (−12.5%)**, **2008-01-21 (−10.7%)**,
**2015-08-24 (−10.3%)** and **2020-03-12 (−10.2%)** — the actual NSE crashes.

## 2. Nine candidates, three targets, six epochs

Targets fixed before any result was seen. **T3 excludes every day already inside
a crisis window**, because otherwise a model "predicts" a crisis from inside one.

| candidate | T1 detect | T2 post-onset | **T3 lead** | epochs led |
|---|---|---|---|---|
| **semivar_20** | **0.7832** | **0.7873** | 0.4928 | **0 / 6** |
| rv_accel | 0.7706 | 0.7766 | 0.4229 | 1 / 6 |
| jump_int_20 | 0.7515 | 0.7538 | 0.5349 | 1 / 6 |
| vol_of_vol | 0.7278 | 0.7282 | 0.5098 | 0 / 6 |
| drawdown | 0.7185 | 0.7207 | **0.6735** | 2 / 6 |
| dd_accel | 0.7064 | 0.7094 | 0.5924 | 3 / 6 (weak) |
| rv_level | 0.6098 | 0.6161 | 0.3722 | 0 / 6 |
| ar_t | 0.4453 | 0.4469 | 0.4036 | 1 / 6 |
| bas_t | 0.3799 | 0.3825 | 0.3356 | 1 / 6 |
| *[inc] hawkes* | 0.5933 | 0.5932 | 0.5031 | 1 / 4 |
| *[inc] CSRS 2-pillar* | 0.5372 | 0.5426 | 0.3723 | 0 / 4 |
| *[inc] rmt λ₁/N* | 0.4283 | 0.4296 | 0.4340 | 1 / 6 |

**No candidate provides reliable advance warning.** Drawdown's 0.6735 comes from
2 of 6 epochs (GFC, IL&FS); across 9 candidates × 6 epochs = 54 cells at a ~10%
alert rate, isolated hits are what multiple comparisons produce. **Not claimed as
a signal.** Every volatility measure is at or below chance on T3, and `rv_level`
at 0.3722 is *inverted* — volatility is already high during crises (excluded from
T3) and mean-reverts, so a high reading anti-predicts an onset.

**Two C4 observations that feed Hamilton are below chance for crisis detection:**
`ar_t` 0.4453 and `bas_t` 0.3799. Worth knowing before anyone invests further in
the Hamilton observation vector.

## 3. Decision: REPLACE pillar 3, do not add a fourth

Mandate §5 P3: *"If Hamilton remains unsuitable, replace it with a simpler,
defensible regime or stress-state estimator rather than forcing it into
production."* That is what the evidence supports:

* Hamilton's slot is **empty in practice** — its causal run is unidentified
  (6/14 nesting violations to LR = −2,322.88, 3/14 non-converged folds, 53%
  near-absorbing dates, NFR17 0.269σ).
* `semivar_20` is the **best contemporaneous detector** (0.7832) and is **nearly
  orthogonal** to both live pillars (corr 0.06 / 0.21).
* It needs **no new table and no schema change** — it is computed causally from
  `daily_prices` (universe-flagged) plus data already in the store.
* A **fourth** pillar would require changing `PILLAR_ORDER`, `Vec3`, `Mat3` and
  `Simplex3` in ask-gated `seraph/shared_types/`, and would propagate through
  every one of the twelve components. Not justified by this evidence.

### Measured result of the replacement

| | AUC (T1) | precision | recall | T3 lead |
|---|---|---|---|---|
| CSRS 2-pillar (349a6874) | 0.5372 | 0.0529 | 0.0611 | 0.3723 |
| **CSRS 3-pillar (36b6f9bb)** | **0.6743** | **0.1653** | **0.2278** | 0.4367 |

**AUC +0.137, precision 3.1×, recall 3.7×.** That is the measurable incremental
detection value the mandate asked for.

### Two limits that travel with it

1. **The composite still loses to the single best signal.** `semivar_20` alone is
   0.7832 against the composite's 0.6743. The equal-weight baseline **dilutes**
   the strongest signal with RMT (0.4283, below chance) and a Hawkes input that
   is masked off 80% of the time. This is the dilution the mandate warned about,
   and it is now the strongest argument for actually running FR30 — there are
   three signals of demonstrably different quality to weight.
2. **Advance warning remains absent.** 0.4367 is still below chance. The 3-pillar
   CSRS is a better **detector** and is not an early-warning system.

## 4. Provenance hazard, stated loudly

`PILLAR_ORDER` slot 3 is **named `"hamilton"`**. A `CsrsPoint` with `mask[2] =
True` produced by `stress_emission` does **not** mean the Hamilton regime filter
was available. A clean fix requires renaming that slot in ask-gated
`seraph/shared_types/` — **not done, and surfaced for sign-off.**

Until then the two line-ups are separated by `weights_artefact_id`, which is part
of the `csrs` primary key:

| artefact | mask_profile | rows | mean CSRS |
|---|---|---|---|
| `349a6874e8bc6884` | (T, T, **F**) — 2 pillars | 2,357 | 0.6131 |
| `36b6f9bb7977e544` | (T, T, **T**) — with stress | 2,357 | 0.5563 |

This was a real defect caught before it bit: `baseline_weights()` initially
returned one artefact id for both configurations, which — since the id is in the
primary key — would have silently **overwritten** one run with the other.

## 5. State after this phase

```
csrs                4,714 rows, 2 artefacts, 0 duplicate PKs, 0 invariant violations
masks           [F,T,F] 1,889 | [F,T,T] 1,889 | [T,T,F] 468 | [T,T,T] 468
tests           92 passed (C5/C5-writer/C6/C10/C12/T0/C4); invariants 5/5
contract        46 passed, 1 pre-existing CT-3 failure (SPEC v4 O2); no regression
```

Changed, all additive: `seraph/orchestration/adapters.py` (+112, new
`stress_emission` and `hawkes_contagion_emission`; `hawkes_emission` untouched),
`orchestration/__init__.py` (+4 exports), `scripts/run_csrs_research.py`
(`--stress-slot`), `scripts/study_stress_candidates.py` (new),
`scripts/evaluate_csrs_research.py` (new). **C8, C9, C10, shared_types, schema.sql
and all Hamilton code: untouched.** Both parallel worktrees intact.

## 6. Honest status

| | 3-pillar CSRS |
|---|---|
| Mathematical correctness | C8/C9 unchanged; invariants 5/5 |
| Synthetic behaviour | covered by CT-4…CT-9, 92 tests |
| Real-data reproducibility | **PASS** — 2,357 points, deterministic, idempotent |
| Contemporaneous detection | **IMPROVED and measured** (0.537 → 0.674) |
| Advance warning | **FAIL — 0.4367, below chance** |
| Beats best single signal | **NO** — 0.674 vs semivar alone 0.783 |
| Production readiness | not claimed |

**SERAPH is now a validated research prototype of a composite risk *state* with a
measurably better detector than it had this morning. It is still not an
early-warning engine, and this evidence does not support calling it one.**

### Limitations

1. Six epochs, one with a provisional date (SPEC OQ3 open). No pooled
   significance claim; per-epoch outcomes are reported individually.
2. T1/T2 are partly tautological for volatility candidates (§1).
3. Nine candidates × six epochs invites multiple-comparison artefacts; this is
   why no isolated per-epoch lead is treated as a finding.
4. Hawkes still participates in only 19.9% of ticks (D4 `h_hawkes = 1.0 bar` vs a
   5-session refit cadence). Not patched — tuning a spec'd constant to keep a
   pillar in the mask is not a fix.

## 7. Reproduction

```bash
docker start seraph-timescaledb
python scripts/study_stress_candidates.py                       # 9 candidates, 3 targets, 6 epochs
python scripts/run_csrs_research.py --stress-slot --write        # 3-pillar CSRS -> E10
python scripts/evaluate_csrs_research.py                         # 2-pillar baseline eval
pytest tests/test_c5_hawkes_writer.py -q                         # 14 passed
python scripts/check_invariants.py                               # 5/5
```

## 8. Next highest-value task

**Run FR30 weight calibration (C10) under leave-one-epoch-out.** It is now
justified for the first time: there are three signals with measured, very
different detection quality (semivar 0.78, hawkes 0.59, rmt 0.43), and the
equal-weight baseline demonstrably dilutes the best one. A calibrated weighting
is the specific, evidence-backed fix for the §3 limitation — and with six epochs
under D5's leave-one-epoch-out policy it is estimable, though the sample will
remain too small for a confident lead-time claim.
