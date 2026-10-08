# C4 — Feature Deriver (FR5, FR6, FR50): intraday jump events and the state variable S_t.
"""Lee–Mykland jump extraction, the bar-level tick test, and the `S_t` state.

**Why jumps at all.** SPEC v2 re-specified Pillar 1: true order-flow events are
unobtainable at project budget, so the Hawkes process is estimated on *negative
price-jump events* extracted from intraday bars (FR50, O2). The mathematics of
the Hawkes specification is unchanged; only the definition of an event moves.

**Lee–Mykland test (FR50).** For bar `i`, the statistic is `L_i = |r_i| / σ̂_i`
where `σ̂_i` is a local bipower-variation volatility estimate over the preceding
`K` bars. Bipower variation is used precisely because it is robust to jumps —
it estimates the diffusive volatility without being inflated by the jump it is
meant to detect. Under the null of no jump, the maximum of `L` over `n`
observations is asymptotically Gumbel, so the rejection threshold is

    (L_i − C_n) / S_n  >  −log(−log(1 − α))

with the standard `C_n`, `S_n` normalising constants below.

**Parameter choice (SPEC OQ16 — was open).** ROADMAP §4's agreed default is
"Lee–Mykland's standard default; document it; revisit only if CT-3 fails".
Lee & Mykland's own recommendation for five-minute data is `K = 156`
(≈ two trading days at NSE's 75 bars/day), and α = 0.01 is their conventional
significance level. Both are adopted and both are module constants so FR34's
sensitivity sweep can vary them. **Note a discrepancy to resolve in review:**
the roadmap's parenthetical suggests "a local window of ~20–40 observations",
which is materially shorter than Lee–Mykland's published choice for this
frequency. The published value is used here because the roadmap's own
instruction is to take the paper's standard default; a 20–40 bar window makes
`σ̂_i` noisy enough to inflate the false-positive rate. Flagged rather than
silently reconciled.

**`S_t` (FR6).** The Hawkes excitation kernel is conditioned on market state,
built as the joint quintile of the spread estimate and the signed-volume
imbalance — a 5×5 = 25-value discrete state. If CT-3 shows the jump stream is
too thin to identify a kernel across 25 states, the pre-agreed mitigation
ladder coarsens this to 3×3 = 9 states (ROADMAP Phase 5).
"""
from __future__ import annotations

import numpy as np

LM_WINDOW_K = 156          # Lee–Mykland default for 5-minute data (~2 NSE days)
LM_ALPHA = 0.01            # significance level
_C_CONST = np.sqrt(2.0 / np.pi)      # E|N(0,1)| — the bipower scaling constant
S_T_QUINTILES = 5          # 5x5 joint state => S_t in 1..25


def bipower_volatility(returns: np.ndarray, k: int = LM_WINDOW_K) -> np.ndarray:
    """Local bipower-variation volatility estimate per bar.

    σ̂²_i = (1/(K−2)) · Σ |r_j|·|r_{j−1}| over the K bars preceding i, scaled by
    1/c² where c = E|N(0,1)|. Jump-robust by construction: a single large return
    enters only through products with its neighbours.
    Bars without a full preceding window get NaN.
    """
    r = np.asarray(returns, dtype=float)
    n = r.size
    out = np.full(n, np.nan, dtype=float)
    if n < k + 1:
        return out
    absr = np.abs(r)
    prod = absr[1:] * absr[:-1]          # |r_j| * |r_{j-1}|, length n-1
    csum = np.concatenate([[0.0], np.cumsum(prod)])
    for i in range(k, n):
        # products strictly inside the preceding window, excluding bar i itself
        window_sum = csum[i - 1] - csum[i - k]
        var = window_sum / (k - 2) / (_C_CONST**2)
        if var > 0:
            out[i] = np.sqrt(var)
    return out


def lee_mykland_threshold(n_obs: int, alpha: float = LM_ALPHA) -> float:
    """Gumbel critical value for the maximum of `n_obs` test statistics."""
    if n_obs < 2:
        return float("inf")
    log_n = np.log(n_obs)
    sqrt_2logn = np.sqrt(2.0 * log_n)
    c_n = (
        sqrt_2logn / _C_CONST
        - (np.log(np.pi) + np.log(log_n)) / (2.0 * _C_CONST * sqrt_2logn)
    )
    s_n = 1.0 / (_C_CONST * sqrt_2logn)
    beta_star = -np.log(-np.log(1.0 - alpha))
    return float(c_n + s_n * beta_star)


def extract_jumps(
    prices: np.ndarray,
    *,
    k: int = LM_WINDOW_K,
    alpha: float = LM_ALPHA,
) -> "dict[str, np.ndarray]":
    """FR50 — flag jump bars and their signs from an intraday price series.

    Returns arrays aligned to `prices`: `log_return`, `test_statistic`,
    `is_jump`, `jump_sign` (0 iff not a jump), matching the E1 columns C4 owns.
    """
    p = np.asarray(prices, dtype=float)
    n = p.size
    log_return = np.zeros(n, dtype=float)
    if n < 2:
        return {
            "log_return": log_return,
            "test_statistic": np.zeros(n),
            "is_jump": np.zeros(n, dtype=bool),
            "jump_sign": np.zeros(n, dtype=np.int8),
        }
    with np.errstate(divide="ignore", invalid="ignore"):
        log_return[1:] = np.diff(np.log(np.where(p > 0, p, np.nan)))
    log_return = np.nan_to_num(log_return, nan=0.0, posinf=0.0, neginf=0.0)

    sigma = bipower_volatility(log_return, k)
    with np.errstate(divide="ignore", invalid="ignore"):
        stat = np.abs(log_return) / sigma
    stat = np.nan_to_num(stat, nan=0.0, posinf=0.0, neginf=0.0)

    threshold = lee_mykland_threshold(int(np.isfinite(sigma).sum()), alpha)
    is_jump = stat > threshold
    jump_sign = np.where(is_jump, np.sign(log_return), 0).astype(np.int8)
    # A zero-return bar cannot be a signed jump; keep is_jump/jump_sign coherent
    # with the E1 invariant (jump_sign == 0 iff not a jump).
    is_jump = is_jump & (jump_sign != 0)
    return {
        "log_return": log_return,
        "test_statistic": stat,
        "is_jump": is_jump,
        "jump_sign": jump_sign,
    }


def tick_test(close: np.ndarray, volume: np.ndarray) -> np.ndarray:
    """FR5 — sign each bar's volume by its close-to-close return.

    Replaces Lee–Ready, which needs quotes. A flat bar inherits the previous
    non-zero sign (the standard zero-tick rule); leading flats are signed 0.
    """
    c = np.asarray(close, dtype=float)
    v = np.asarray(volume, dtype=float)
    n = c.size
    signs = np.zeros(n, dtype=float)
    if n < 2:
        return (signs * v).astype(np.int64)
    diffs = np.sign(np.diff(c))
    last = 0.0
    for i, d in enumerate(diffs, start=1):
        if d != 0:
            last = d
        signs[i] = last
    return (signs * v).astype(np.int64)


def _bucket(values: np.ndarray, n: int) -> np.ndarray:
    """1..n bucket by empirical quantile; degenerate inputs land in the middle."""
    v = np.asarray(values, dtype=float)
    mid = (n + 1) // 2
    finite = v[np.isfinite(v)]
    if finite.size == 0:
        return np.full(v.size, mid, dtype=np.int8)
    edges = np.quantile(finite, [i / n for i in range(1, n)])
    if np.allclose(edges, edges[0]):
        return np.full(v.size, mid, dtype=np.int8)
    filled = np.nan_to_num(v, nan=float(np.median(finite)))
    out = np.searchsorted(edges, filled, side="right") + 1
    return np.clip(out, 1, n).astype(np.int8)


def state_variable(
    spread: np.ndarray, imbalance: np.ndarray, *, n_quantiles: int = S_T_QUINTILES
) -> "dict[str, np.ndarray]":
    """FR6 — discretise (spread, imbalance) into the joint state `S_t` in 1..25.

    `n_quantiles=3` gives the 9-state coarsening from the R2 mitigation ladder
    without any other code change.
    """
    sq = _bucket(spread, n_quantiles)
    iq = _bucket(imbalance, n_quantiles)
    s_t = (sq.astype(np.int16) - 1) * n_quantiles + iq
    return {
        "spread_quintile": sq,
        "imbalance_quintile": iq,
        "s_t": s_t.astype(np.int16),
    }
