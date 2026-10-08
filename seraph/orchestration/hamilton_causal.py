# Orchestration — causal (walk-forward) Pillar 3 regime probabilities.
"""Removes both of C7's leakage paths without touching the estimator.

The E8 series was produced by fitting once over all 5,365 observations and
reading `smoothed_marginal_probabilities`. That leaks the future twice:

  1. **Smoother leak.** `P(S_t | y_1..y_T)` runs the Kim smoother backward over
     the whole sample, so `ξ_t` depends directly on observations after `t`.
  2. **Parameter leak.** One fit over the entire sample means the parameters
     used at `t` were estimated with data from after `t`.

Fixing only (1) is not enough, which is why filtered-only was rejected as the
production answer. This module fixes both:

  * parameters for the block `(t_k, t_{k+1}]` come from a fit on `y[:t_k]`;
  * `ξ_t` inside that block is the **filtered** `P(S_t | y_1..y_t)`, obtained by
    running the Hamilton filter forward with those fixed parameters.

`model.filter(params)` is the mechanism: it applies a given parameter vector to a
sample without re-estimating, and the filtered probability at index `i` is by
definition conditioned on `y[0..i]` only. So a block's probabilities use data
through `t` and parameters through `t_k ≤ t`. Nothing anywhere reads ahead.

Dates before the first fit have no causal estimate at all — that is a genuine
`insufficient_history` absence for C8, not a value to be back-filled.

**This changes reported numbers, and that is the point.** Occupancy, NFR16 and
NFR17 measured on the smoothed series describe in-sample behaviour; the causal
series is a different object and must be re-measured, not reconciled to the old
figures.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass, field

import numpy as np

from seraph.pillars.hamilton.engine import (
    K_REGIMES,
    MultivariateTVTPHamilton,
    _MIN_OBS,
    fit as fit_hamilton,
)

#: One trading year between refits — the cadence the user set as the starting
#: point. It is a default to be validated, not a locked constant.
DEFAULT_REFIT_EVERY = 252
#: Five years before the first causal emission. Above `_MIN_OBS` (250) by a wide
#: margin because the first fit sets the regime labelling every later block
#: inherits, so it should not be the least-informed fit in the series.
#: Raised from 1,260 after the diagnostic: at 1,260 observations the likelihood
#: is flat enough toward the absorbing boundary that the fit drifted to
#: P(tranquil|stressed) ~ 1.8e-9, while a 2,146-observation fold was healthy
#: (47.6/26.3/26.1). ~8 years.
DEFAULT_INITIAL_TRAIN = 2000


#: Observations before the expanding z-score is trusted. Below this the sample
#: sd is dominated by noise and the standardised value explodes.
Z_WARMUP = 60


def causal_tvtp_exog(rv, warmup: int = Z_WARMUP) -> np.ndarray:
    """FR21's driver — lagged standardised RV — with the standardisation made causal.

    **This closes a third leakage path**, independent of the smoother and of the
    parameter fit. `scripts/fit_hamilton.py` builds the driver as
    `(rv - rv.mean()) / rv.std()` over the **whole corpus**, so the z-score at
    date `t` is computed with the mean and variance of data from after `t`.
    Here the moments expand with the sample, so `z_t` uses only `rv[0..t]`, and
    the lag then means the transition into `t` is informed by `t-1` alone.

    Returns the `(n, 2)` design `[1, z_{t-1}]` the engine expects.
    """
    rv = np.asarray(rv, dtype=float)
    n = rv.size
    idx = np.arange(1, n + 1, dtype=float)
    mean = np.cumsum(rv) / idx
    var = np.maximum(np.cumsum(rv ** 2) / idx - mean ** 2, 0.0)
    sd = np.sqrt(var)
    z = np.where(sd > 0, (rv - mean) / np.maximum(sd, 1e-12), 0.0)
    z[:warmup] = 0.0                     # not yet a meaningful location/scale
    return np.column_stack([np.ones(n), np.r_[0.0, z[:-1]]])


@dataclass(frozen=True)
class RefitBlock:
    """One walk-forward segment, recorded so the schedule is auditable."""

    index: int
    train_start: int
    train_end: int          # exclusive; parameters see y[train_start:train_end]
    emit_start: int         # inclusive; first date this block's params serve
    emit_end: int           # exclusive
    train_first_date: str
    train_last_date: str
    emit_first_date: str
    emit_last_date: str
    llf: float
    order: tuple[int, ...]
    converged: bool


@dataclass
class CausalRun:
    xi: np.ndarray                      # (K_REGIMES, n_dates), NaN before warm-up
    blocks: list[RefitBlock] = field(default_factory=list)
    first_causal_index: int = 0

    def lsd(self) -> np.ndarray:
        """`LSD_t = ξ₂ + 2ξ₃`, NaN wherever no causal estimate exists."""
        return self.xi[1] + 2.0 * self.xi[2]

    def variance(self) -> np.ndarray:
        """FR23 uncertainty, unchanged in form: `Σ w²ξ − LSD²` with w = (0,1,2)."""
        w = np.array([0.0, 1.0, 2.0])[:, None]
        return np.maximum((w**2 * self.xi).sum(axis=0) - self.lsd() ** 2, 0.0)


def walk_forward(
    dates,
    y,
    exog_tvtp=None,
    *,
    initial_train: int = DEFAULT_INITIAL_TRAIN,
    refit_every: int = DEFAULT_REFIT_EVERY,
    maxiter: int = 200,
    progress: bool = False,
) -> CausalRun:
    """Expanding-window walk-forward filtered regime probabilities.

    Returns a `CausalRun` whose `xi[:, t]` is `NaN` for every `t` before the
    first fit could be made. Callers must emit absence there rather than
    substituting a prior.
    """
    dates = list(dates)
    y = np.asarray(y, dtype=float)
    exog = None if exog_tvtp is None else np.asarray(exog_tvtp, dtype=float)
    n = len(dates)
    if initial_train < _MIN_OBS:
        raise ValueError(
            f"initial_train={initial_train} is below the estimator's {_MIN_OBS}-"
            f"observation identifiability floor")
    if n <= initial_train:
        raise ValueError(f"need more than {initial_train} observations; got {n}")

    xi = np.full((K_REGIMES, n), np.nan)
    run = CausalRun(xi=xi, first_causal_index=initial_train)

    t_k, block_i = initial_train, 0
    while t_k < n:
        emit_end = min(t_k + refit_every, n)

        # --- parameters from data available AT t_k (exclusive end) -----------
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            res, order, _ = fit_hamilton(
                y[:t_k], exog_tvtp=None if exog is None else exog[:t_k],
                maxiter=maxiter)

        # --- filter forward over [0, emit_end) with those parameters fixed ---
        model = MultivariateTVTPHamilton(
            y[:emit_end], exog_tvtp=None if exog is None else exog[:emit_end],
            k_regimes=K_REGIMES)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            filt = model.filter(res.params)
        probs = np.asarray(filt.filtered_marginal_probabilities)
        if probs.shape[0] != K_REGIMES:
            probs = probs.T
        probs = probs[:, :emit_end]

        xi[:, t_k:emit_end] = probs[np.asarray(order)][:, t_k:emit_end]
        run.blocks.append(RefitBlock(
            index=block_i, train_start=0, train_end=t_k,
            emit_start=t_k, emit_end=emit_end,
            train_first_date=dates[0], train_last_date=dates[t_k - 1],
            emit_first_date=dates[t_k], emit_last_date=dates[emit_end - 1],
            llf=float(res.llf), order=tuple(int(o) for o in order),
            converged=bool(getattr(res, "mle_retvals", {}).get("converged", True)),
        ))
        if progress:
            print(f"  [wf] block {block_i}: train<={dates[t_k-1]} "
                  f"({t_k} obs) -> emit {dates[t_k]}..{dates[emit_end-1]}",
                  flush=True)
        t_k, block_i = emit_end, block_i + 1

    return run


def assert_causal(run: CausalRun) -> None:
    """Structural check that no block's parameters saw its own emission window.

    Cheap, and it is the invariant the whole module exists to provide, so it is
    asserted rather than assumed.
    """
    for b in run.blocks:
        if b.train_end > b.emit_start:
            raise AssertionError(
                f"block {b.index}: parameters trained to index {b.train_end} but "
                f"emit starts at {b.emit_start} — future data reached the fit")
        if b.train_last_date >= b.emit_first_date:
            raise AssertionError(
                f"block {b.index}: training ends {b.train_last_date} which is not "
                f"before its first emitted date {b.emit_first_date}")
