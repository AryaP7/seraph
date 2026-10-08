# C4 — Feature Deriver (FR6, FR20, FR53): cross-sectional observation vector y_t.
"""Builds `y_t = (RV_t, AR_t, BAS_t)ᵀ`, the observation vector Pillar 3 consumes.

**`AR_t` lives here, not in C6.** Computing the Absorption Ratio inside the RMT
engine would make Pillar 3 depend on Pillar 2 and break FR35, which requires
each pillar to be independently evaluable in the ablation. Duplicating a
covariance computation across C4 and C6 is the correct price — this is an
explicit ARCHITECTURE §1 decision, mechanically checked by
`scripts/check_invariants.py`.

Components:

* `RV_t` (FR20) — market realised volatility via the Yang–Zhang OHLC estimator,
  which combines overnight, open-to-close and Rogers–Satchell components and is
  both drift-independent and minimum-variance among OHLC estimators. It is
  computed per symbol over a rolling window and then aggregated
  cross-sectionally by median. A portfolio has no meaningful OHLC of its own, so
  the market-level figure is the median of member-level estimates rather than a
  single index-level computation; the median resists the fat tails of individual
  small-cap ranges. Where true 5-minute realised volatility exists (post-2015,
  ~100 symbols) FR53 asks for the correlation between the two as a validation of
  the estimator substitution — `volatility_estimator_agreement` provides it.

* `AR_t` (FR20) — Absorption Ratio: the share of total cross-sectional variance
  captured by the leading `k = 10` principal components of the member covariance
  matrix. Rises as the market's variance concentrates into fewer modes.

* `BAS_t` (FR6, FR20) — cross-sectional median Abdi–Ranaldo close-high-low
  spread estimate. Abdi–Ranaldo is the primary estimator; Corwin–Schultz is
  computed alongside as the documented fallback and cross-check. **These are
  estimators, not observations** — SPEC §7 item 12 puts true limit-order-book
  microstructure out of scope, so nothing here may be described as a measured
  spread, queue depth or quote-level quantity.
"""
from __future__ import annotations

import numpy as np

AR_COMPONENTS = 10          # FR20, k = 10 principal components
YZ_WINDOW = 21              # ~1 trading month for the Yang–Zhang estimator
AR_WINDOW = 250             # ~1 trading year of returns for the covariance
TRADING_DAYS = 252


def yang_zhang_volatility(
    open_, high, low, close, *, window: int = YZ_WINDOW, annualize: bool = True
) -> float:
    """Yang–Zhang volatility from OHLC over the trailing `window` days.

    σ²_YZ = σ²_overnight + k·σ²_open_to_close + (1−k)·σ²_RogersSatchell,
    with k = 0.34 / (1.34 + (n+1)/(n−1)) chosen to minimise estimator variance.
    Arrays must be aligned and at least `window + 1` long (the overnight term
    needs the previous close). Returns NaN if there is not enough clean data.
    """
    o = np.asarray(open_, dtype=float)
    h = np.asarray(high, dtype=float)
    low_arr = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    if min(o.size, h.size, low_arr.size, c.size) < window + 1:
        return float("nan")
    o, h, low_arr, c = o[-(window + 1):], h[-(window + 1):], low_arr[-(window + 1):], c[-(window + 1):]
    if np.any(o <= 0) or np.any(h <= 0) or np.any(low_arr <= 0) or np.any(c <= 0):
        return float("nan")

    log_o, log_h, log_l, log_c = np.log(o), np.log(h), np.log(low_arr), np.log(c)
    overnight = log_o[1:] - log_c[:-1]          # close-to-open
    open_close = log_c[1:] - log_o[1:]          # open-to-close
    rs = (                                       # Rogers–Satchell, drift-free
        (log_h[1:] - log_c[1:]) * (log_h[1:] - log_o[1:])
        + (log_l[1:] - log_c[1:]) * (log_l[1:] - log_o[1:])
    )
    n = overnight.size
    if n < 2:
        return float("nan")
    var_o = overnight.var(ddof=1)
    var_c = open_close.var(ddof=1)
    var_rs = float(rs.mean())
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    var_yz = var_o + k * var_c + (1.0 - k) * var_rs
    if not np.isfinite(var_yz) or var_yz < 0:
        return float("nan")
    sigma = float(np.sqrt(var_yz))
    return sigma * np.sqrt(TRADING_DAYS) if annualize else sigma


def absorption_ratio(returns: np.ndarray, *, k: int = AR_COMPONENTS) -> float:
    """FR20 — share of total variance in the leading `k` principal components.

    `returns` is a (T, N) panel. Uses the covariance matrix, per SPEC's wording
    ("top k = 10 principal components of the Nifty 500 covariance matrix"), so
    more volatile names carry more weight — unlike C6, which works on the
    correlation matrix. That difference is deliberate and is part of why the two
    computations are kept separate.
    """
    r = np.asarray(returns, dtype=float)
    if r.ndim != 2 or r.shape[1] < 2 or r.shape[0] < 2:
        return float("nan")
    r = r[:, np.isfinite(r).all(axis=0)]
    if r.shape[1] < 2:
        return float("nan")
    cov = np.cov(r, rowvar=False)
    eig = np.linalg.eigvalsh(cov)[::-1]
    total = float(eig.sum())
    if total <= 0:
        return float("nan")
    kk = min(k, eig.size)
    return float(eig[:kk].sum() / total)


def abdi_ranaldo_spread(high, low, close) -> float:
    """FR6 — Abdi–Ranaldo (2017) close-high-low spread estimator.

    S = 2·√(max(0, E[(c_t − η_t)(c_t − η_{t+1})])) with η_t = (h_t + l_t)/2 in
    logs. The expectation is taken over the supplied window. Returns NaN when
    the window is too short; negative covariance estimates are floored at zero,
    which is the estimator's standard treatment and not an error.
    """
    h = np.asarray(high, dtype=float)
    l_ = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)
    if min(h.size, l_.size, c.size) < 3:
        return float("nan")
    if np.any(h <= 0) or np.any(l_ <= 0) or np.any(c <= 0):
        return float("nan")
    log_c = np.log(c)
    eta = (np.log(h) + np.log(l_)) / 2.0
    prod = (log_c[:-1] - eta[:-1]) * (log_c[:-1] - eta[1:])
    val = float(np.mean(prod))
    return float(2.0 * np.sqrt(val)) if val > 0 else 0.0


def corwin_schultz_spread(high, low) -> float:
    """FR6 fallback — Corwin–Schultz (2012) high–low spread estimator.

    Kept as the documented cross-check on Abdi–Ranaldo. Negative estimates are
    floored at zero, as the original paper prescribes.
    """
    h = np.asarray(high, dtype=float)
    l_ = np.asarray(low, dtype=float)
    if min(h.size, l_.size) < 2 or np.any(h <= 0) or np.any(l_ <= 0):
        return float("nan")
    log_hl = np.log(h / l_) ** 2
    beta = log_hl[:-1] + log_hl[1:]
    h2 = np.maximum(h[:-1], h[1:])
    l2 = np.minimum(l_[:-1], l_[1:])
    gamma = np.log(h2 / l2) ** 2
    denom = 3.0 - 2.0 * np.sqrt(2.0)
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / denom - np.sqrt(gamma / denom)
    spread = 2.0 * (np.exp(alpha) - 1.0) / (1.0 + np.exp(alpha))
    spread = spread[np.isfinite(spread)]
    if spread.size == 0:
        return float("nan")
    return float(max(0.0, float(np.mean(spread))))


def observation_row(
    *,
    date: str,
    panel: "dict[str, dict[str, np.ndarray]]",
    returns: np.ndarray,
    rv_5min: float | None = None,
) -> "dict[str, float | str | None]":
    """Assemble one `y_t` row (S4 ObservationRow shape) for `date`.

    `panel` maps symbol → {"open","high","low","close"} arrays over the trailing
    window; `returns` is the (T, N) panel used for the Absorption Ratio.
    Per-symbol estimates are aggregated by median across the cross-section, and
    symbols whose estimator returns NaN are dropped from that median rather than
    poisoning it.
    """
    rv_each, bas_each = [], []
    for bars in panel.values():
        rv = yang_zhang_volatility(
            bars["open"], bars["high"], bars["low"], bars["close"]
        )
        if np.isfinite(rv):
            rv_each.append(rv)
        bas = abdi_ranaldo_spread(bars["high"], bars["low"], bars["close"])
        if np.isfinite(bas):
            bas_each.append(bas)
    return {
        "date": date,
        "rv_yang_zhang": float(np.median(rv_each)) if rv_each else float("nan"),
        "rv_5_min": rv_5min,
        "ar_t": absorption_ratio(returns),
        "bas_t": float(np.median(bas_each)) if bas_each else float("nan"),
    }


def volatility_estimator_agreement(yz: np.ndarray, rv5: np.ndarray) -> "dict[str, float]":
    """FR53 — correlation between Yang–Zhang OHLC volatility and true 5-minute
    realised volatility over their overlap, as evidence for the substitution."""
    a = np.asarray(yz, dtype=float)
    b = np.asarray(rv5, dtype=float)
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 3:
        return {"correlation": float("nan"), "nOverlappingDays": int(mask.sum())}
    return {
        "correlation": float(np.corrcoef(a[mask], b[mask])[0, 1]),
        "nOverlappingDays": int(mask.sum()),
    }


def bid_ask_spread(high, low, close) -> tuple[float, str]:
    """FR6 — spread estimate with the specified estimator ladder.

    Abdi–Ranaldo is the primary estimator, Corwin–Schultz the documented
    fallback. The fallback is not decoration: Abdi–Ranaldo floors at zero
    whenever its covariance term comes out negative, and on NSE daily data that
    happens for **more than half the cross-section**, which drives the
    cross-sectional median to exactly zero and leaves `BAS_t` degenerate as an
    observation channel for Pillar 3. Falling back to Corwin–Schultz on those
    symbols restores a live series while keeping Abdi–Ranaldo primary wherever
    it is informative, exactly as FR6 prescribes.

    Returns `(spread, estimator)` where estimator is "abdi_ranaldo",
    "corwin_schultz" or "none" — the caller records which was used so the
    ESTIMATOR_FALLBACK rate is reportable rather than invisible.
    """
    ar = abdi_ranaldo_spread(high, low, close)
    if np.isfinite(ar) and ar > 0.0:
        return float(ar), "abdi_ranaldo"
    cs = corwin_schultz_spread(high, low)
    if np.isfinite(cs) and cs > 0.0:
        return float(cs), "corwin_schultz"
    return float("nan"), "none"
