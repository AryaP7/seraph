# Pillar 1 model-selection rule — committed BEFORE the final results

Written 2026-08-23, ahead of the full comparison, so the winner is chosen by a rule rather than by
preference. This mirrors D5's pre-registration discipline at the model-family level.

## Primary metric

**Mean out-of-sample negative log-likelihood per bar**, averaged over chronological, disjoint
forward folds. No shuffling: every test block is strictly later than the block it was trained on.

## Gates — a model must pass ALL of these to be eligible

- **G1 Materiality** — at least a 5% mean OOS NLL improvement over the constant-Poisson baseline.
- **G2 Consistency** — beats the baseline in *every* fold, not merely on average.
- **G3 Identifiability** — parameters interior (not pinned at a bound) and stable across folds,
  coefficient of variation < 0.50.
- **G4 Calibration** — randomised PIT approximately uniform; mean and sd reported against the
  uniform targets of 0.500 and 0.289.
- **G5 Parsimony** — if a simpler nested model comes within **2%** of the best NLL, the simpler
  model wins. Complexity must be paid for in measured predictive value.

## Secondary metric — the one that decides whether this is a *risk* model

**Does the statistic predict FUTURE activity, or only describe the current bar?**

Using information available through bar `t` only, predict total jumps in bars `t+1 … t+H`
(H = 15, roughly one trading hour):

- Spearman rank correlation with the realised forward count.
- AUC for "the next window lands in the top decile of activity".

A model that fits the current bar well but carries no forward information is **not usable for
Pillar 1**, whatever its likelihood. This is the gate that separates a description of the market
from a risk instrument.

## Declared in advance

If no candidate clears **G1 and G2**, the honest conclusion is *"no candidate meaningfully beats
the baseline"*, and that will be reported as such — with an investigation into why — rather than
being replaced by a more flattering metric or a re-specified target.
