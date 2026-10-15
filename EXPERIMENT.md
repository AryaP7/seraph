# SERAPH experimental continuation

Created 2026-10-14 under the owner's explicit authorization to redesign, test,
and implement a separate copy while retaining Hawkes, RMT, and Hamilton.
This authorization supersedes historical component-owner approval gates for this
copy only. The original project in Downloads is not a working directory.

## Boundaries

- Keep all three original pillar families and preserve historical negative results.
- Never manufacture predictive skill, backdate information, select only winning
  crises, or relabel a contemporaneous detector as an advance warning.
- Original database is a read-only source. Experimental data/results are local.
- Original credentials, virtual environment, vendor corpus, and nested worktrees
  were not copied. Their files were not changed. Nested worktree additions have
  not been merged into this experiment.
- Mathematical repairs may supersede old formula-based tests, with analytic
  justification and new regression tests recorded separately.

## Research design, fixed before experimental fits

The primary original question remains pre-onset warning, evaluated at 15 trading
sessions on all six existing event labels. Tariff-2026 remains provisional.
An additional endpoint is a 10% loss from today's level at any close within the
next 15 sessions. This is a new predictive-risk endpoint, not a replacement for
the original claim. All failed configurations remain reportable.

Initial candidates: a volatility baseline; a regularized logistic predictor of
future losses using three named pillar families; baseline plus pillars; and
explicit ablations removing each family for research comparison only. No final
production architecture removes any of the three families.

Training uses only matured future labels. First forecast follows at least 756
observations; model refits every 63 sessions. Fixed loss horizon 15, barrier 0.10,
and logistic regularization are chosen before results. Alert thresholds use only
previous out-of-sample predictions and matured labels, with a fixed budget of
two false-alarm episodes per year. Early periods without calibration are
unassessable. Report all alarm episodes and time under warning.

COVID and the other crises have already influenced project design: these are
retrospective chronological research results, never an untouched holdout.
Original persisted pillars were selected in prior full-period research; any
comparison using them must retain that limitation. New variants re-estimate
parameters causally; they cannot undo research-selection history.

No success is declared unless measured. Engineering completion and predictive
acceptance are separate. Simulated/unit data establish software behavior only.

### Exact first-run candidates (fixed before looking at forecast results)

- Baseline logistic: `ewma_volatility`.
- Three pillars: `hawkes_daily_intensity`, `rmt_fast_leading_share`,
  `rmt_fast_minus_slow`, `hamilton_daily_next_volatility`.
- Combined: the five above. Three ablations drop one named family each; they
  are controls, never a proposed production architecture.
- Fixed C=0.1, no interactions, no class weighting, expanding training window.
- EWMA Student-t and fitted GJR-GARCH Student-t are additional loss-probability
  benchmarks. They are not treated as calibrated onset probabilities.
- Daily-tail Hawkes, 10 hash-portfolio RMT, and restricted variance Hamilton are
  explicit variants. Original intraday Hawkes, 500-stock RMT, and TVTP Hamilton
  implementations remain present. This does not imply unchanged numerical models.
- Thresholds refit every 63 sessions from up to 1,260 past out-of-sample scores
  with matured labels, minimum 252. In addition to two false episodes/year,
  maximum historical time under warning is 10%. This prevents satisfying an
  episode budget by raising one continuous alarm. No feasible finite threshold
  means abstention; insufficient calibration means unassessable. These budgets
  are calibration constraints, not guarantees about subsequent performance.
- Every one of the 15 pre-onset sessions must have a score and calibrated policy
  to count an event as assessable. All six project dates remain unchanged; their
  provisional status remains visible, with tariff explicitly unresolved.
- Probability comparisons use common coverage. A paired 63-session circular
  block bootstrap is descriptive, not correction for research/model selection.
- HMM numerical convergence uses an 80-iteration cap and MAP-objective tolerance;
  cap-limited fits are reported. This numerical choice did not use target labels.
