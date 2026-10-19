# DR-04 — Causal, versioned bins for the FR6 state variable

**Date:** 2026-10-16
**Backlog:** `FIX04` (audit finding A05)
**Status:** adopted and implemented
**Scope limit:** this is the **state-bin path**. It does not claim leakage was
present in every Hawkes variant — the prototype's fresh Hawkes path uses the
pooled count estimator, not these bins. Regenerating historical feature
artefacts is separate work (`DATA09`, which needs `DATA02`).

## The defect

`seraph/features/jump_extraction.py::_bucket(values, n)` computed its quantile
edges from the **entire supplied array**. The bin assigned to bar `t` therefore
depended on bars after `t`. Reproduction, unchanged from the audit: appending
20 future observations changed **28 of 40** earlier bucket assignments.

That matters because `S_t` is the state the Hawkes conditional intensity is
indexed by. A leaky state is a leaky conditioning set, and nothing errors.

## Decisions

1. **The fitting basis is declared, never inferred.** `state_variable()` now
   requires a keyword-only `basis`:

   | basis | Edges fitted on | Causal | Use |
   |---|---|---|---|
   | `train_prefix` | `values[:train]` only | yes | cheap, future-append invariant |
   | `trailing_window` | per index, `values[max(0,i-window):i]` — strictly past | yes | fully causal online assignment |
   | `full_sample` | everything | **no** | reproduction of pre-FIX04 artefacts only |

   There is no default. Omitting `basis` is a `TypeError`, because a silent
   default is exactly how the leak survived.

2. **`full_sample` is retained but self-describing.** Its returned transform
   carries `causal: False` and a warning naming audit finding A05. Deleting it
   would make existing artefacts unreproducible; hiding what it is would be
   worse than keeping it.

3. **Unknown is not typical.** An observation without enough trailing history,
   a non-finite value, or a degenerate (no-spread) series yields
   `UNDETERMINED = 0`, not the middle bucket. A joint `S_t` with one unknown
   coordinate is unknown. `scripts/fit_hawkes.py` skips such events and counts
   them rather than pooling them into a guessed state.

4. **Transforms are versioned and content-hashed.** `QuantileBins` carries
   `version`, `basis`, `fitted_on`, `window`, `degenerate` and the edges, and
   derives an `artefact_id` from all of them. A different basis, a different
   training length or different data gives a different identity, so a
   regenerated feature cannot be mistaken for the old one.
   `BIN_TRANSFORM_VERSION = "2026-10-16.1"`.

5. **Callers declare their basis.**
   - `scripts/fit_hawkes.py` uses `trailing_window` with
     `STATE_BIN_WINDOW = 20 × 75` five-minute bars (about one NSE month).
   - `tests/contract/test_ct3_jump_sufficiency.py` uses `train_prefix` on the
     first half of its fixture.

## New API

```python
BIN_TRANSFORM_VERSION, UNDETERMINED
QuantileBins(n, edges, basis, fitted_on, window, degenerate, version)
    .causal -> bool
    .artefact_id -> str
    .describe() -> dict
fit_quantile_bins(values, n, *, basis, train=None, window=None) -> QuantileBins
apply_quantile_bins(values, bins) -> np.ndarray      # fixed edges, no peeking
trailing_quantile_bucket(values, n, *, window, min_history=None) -> np.ndarray
state_variable(spread, imbalance, *, n_quantiles=5, basis, train=None,
               window=None, min_history=None) -> dict   # + "transform"
```

`_bucket` remains, marked deprecated and non-causal in its docstring.

## Verification

`tests/test_fix04_causal_state_bins.py` — 14 tests, written as falsification
attempts:

- future-append invariance and truncation invariance, for **both** causal bases
  (0 of 40 assignments move);
- the legacy `full_sample` path still moves 28 of 40 **and says it is not
  causal**, so the kept path cannot be mistaken for the fixed one;
- a missing basis, a missing window and a missing train length all raise;
- identical inputs give an identical `artefact_id`; four different fitting
  bases give four different ids; different data gives a different id;
- insufficient trailing history, non-finite values and degenerate series give
  `UNDETERMINED`, never the middle bucket;
- `apply_quantile_bins` gives the same code for a value whether or not extreme
  values sit beside it in the batch.

`scripts/reverify_audit_findings.py` now reports A05 as `fixed`, recording
`production_bins_changed_by_future_append: {train_prefix: 0, trailing_window: 0}`
alongside `legacy_full_sample_bins_changed: 28`.
