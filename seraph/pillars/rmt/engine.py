# C6 — RMT Engine (FR16, FR17, FR18, FR19)
"""Spectral monitoring of the rolling universe correlation matrix.

FR16 builds `C_t` over a rolling window of T = 1000 trading days across the
point-in-time universe. Per AMENDMENT-02 the cross-section floats —
`N_t = min(500, eligible_t)` — so this engine **must read N_t from the data it
is handed and recompute `Q_t = T / N_t` per date**, evaluating the
Marchenko–Pastur edges at the `Q_t` in force. It must never assume N = 500 or
Q = 2; doing so would misstate the noise band on every pre-mid-2010 date.

FR17 emits three spectral signals:
  * `F_t`  — fraction of eigenvalues above the MP upper edge λ₊(Q_t);
  * `V_t^eig` — eigenvalue collapse velocity (see the definitional note below);
  * `Ω_t`  — leading-eigenvector rotation speed, on common support only (D3).

FR19 attaches a parametric-bootstrap p-value to `F_t`. Because the null
distribution depends only on the shape `(T, N_t)` and not on the observed data,
it is computed once per configuration and cached; with N_t changing only at
semi-annual rebalances there are a few dozen distinct configurations across the
whole corpus, so this turns an otherwise prohibitive 1,000 eigendecompositions
per day into 1,000 per configuration. Under AMENDMENT-02 the bootstrap p-value,
not raw `F_t`, is the statistic comparable across dates with different `N_t`.

**Definition of `V_t^eig`.** SPEC FR17 names "the eigenvalue collapse velocity"
without defining it, and SERAPH-BUILD-ROADMAP §4 records no default. The
definition adopted here is fixed by the report's own account of the phenomenon
(§1: "the leading eigenvalue inflates dramatically, **sub-leading eigenvalues
collapse** toward the noise band"), so the quantity named "collapse" is the
sub-leading spectral mass:

    m_t     = (Σ_{i≥2} λ_i) / N          # sub-leading share of total variance
    V_t^eig = (m_{t−Δ} − m_t) / Δ        # positive ⇒ collapsing ⇒ stress rising

**This is identical to the leading eigenvalue's inflation rate, exactly rather
than approximately.** A correlation matrix has unit diagonal, so
`trace(C_t) = Σλ_i = N` for every date; hence `m_t = 1 − λ₁/N` and

    V_t^eig = (λ₁/N)_t − (λ₁/N)_{t−Δ}

identically. The two readings of FR17 that were open — "sub-leading mass
collapses" and "leading mode inflates" — are therefore the same statistic up to
sign, and no interpretive choice remains to be made. The implementation
computes the right-hand form; the docstring leads with the left because that is
what the requirement names.

Two consequences worth stating in the report. Because `Σλ = N` is an exact
identity and not an approximation, the normalisation is exact: `λ₁/N` is a pure
variance *share* in [0,1], **so `V_t^eig` is directly comparable across dates
with different `N_t`** — unlike `F_t`, whose null depends on `Q_t`. And a
third candidate reading — spectral concentration measured by a participation
ratio — is excluded by SPEC §7 out-of-scope item 4 ("higher-order spectral
statistics: eigenvalue gap, participation ratio"), so it is not an available
alternative.
"""
from __future__ import annotations

import numpy as np

from seraph.shared_types import (
    ConstraintViolated,
    Err,
    InsufficientHistory,
    Ok,
    RmtDetail,
    SeraphWarning,
    err,
    ok,
)

T_WINDOW = 1000                 # FR16
COMMON_SUPPORT_FLOOR = 0.85     # D3 — below this, Ω_t is flagged
BOOTSTRAP_REPS = 1000           # FR19
#: FR18 aggregation weights for SCA_t, ordered (F_t, V_t^eig, Omega_t).
#: Equal thirds over ECDF-STANDARDISED components — an uninformative prior, not
#: a calibration (SPEC §8 lists these among the undefined constants). See sca().
SCA_WEIGHTS = (1 / 3, 1 / 3, 1 / 3)
#: Minimum observations before the SCA_t empirical-CDF standardisation is stable.
#: One trading year; below this the aggregate is emitted with PARTIAL_COVERAGE.
SCA_MIN_HISTORY = 250

_null_cache: dict[tuple[int, int, int], np.ndarray] = {}


def mp_bounds(q: float, sigma2: float = 1.0) -> tuple[float, float]:
    """Marchenko–Pastur support edges at aspect ratio q = T/N.

    λ± = σ²(1 ± 1/√q)². Evaluated per date at the realised q (AMENDMENT-02).
    """
    if q <= 0:
        raise ValueError(f"aspect ratio q must be positive; got {q}")
    root = 1.0 / np.sqrt(q)
    return float(sigma2 * (1.0 - root) ** 2), float(sigma2 * (1.0 + root) ** 2)


def _correlation(returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Correlation matrix of a (T, N) return panel, plus a degenerate-column mask.

    **The Gram divisor must match the `ddof` used for the standard deviation.**
    Dividing the Gram matrix of `ddof=1` z-scores by `T` rather than `T - 1`
    puts exactly `(T - 1) / T` on every diagonal entry, so
    `trace(C_t) = N_t (T - 1) / T` and FR16's arithmetic guard fails by exactly
    `N_t / T` — 0.499 at `N_t = 499, T = 1000`. That is a uniform scale error on
    the whole matrix: every eigenvalue is shrunk by the same 0.999 factor while
    the MP edges, evaluated at `sigma^2 = 1`, are not, which biases `F_t`
    downward for any eigenvalue sitting near the upper edge. Dividing by
    `T - 1` makes the diagonal exactly unit, which is also what makes
    `sum(lambda_i) = N_t` an identity rather than an approximation — the fact
    `V_t^eig`'s normalisation rests on (see the module docstring).

    A column with zero sample variance is uncorrelated with everything by
    construction. Its z-scores are identically zero, which would leave a zero on
    the diagonal and silently drop that symbol from the trace. It is given its
    own isolated unit-variance mode instead: that contributes exactly one
    eigenvalue of 1.0, which lies strictly inside the MP band for every `Q > 1`
    and so cannot inflate `F_t`, while keeping `trace(C_t) = N_t` exact. The
    mask is returned so the caller can say so out loud rather than absorb it.
    """
    sd = returns.std(axis=0, ddof=1)
    degenerate = ~(sd > 0)
    z = (returns - returns.mean(axis=0)) / np.where(degenerate, 1.0, sd)
    c = (z.T @ z) / (returns.shape[0] - 1)
    c = (c + c.T) / 2.0
    if degenerate.any():
        c[degenerate, :] = 0.0
        c[:, degenerate] = 0.0
        c[degenerate, degenerate] = 1.0
    return c, degenerate


def _null_exceedance(t_obs: int, n_sym: int, reps: int, seed: int = 0) -> np.ndarray:
    """Bootstrap null for the MP-exceedance fraction at shape (t_obs, n_sym).

    The null depends only on the shape, so results are cached per
    (T, N, reps) configuration and reused across every date sharing it.
    """
    key = (t_obs, n_sym, reps)
    if key in _null_cache:
        return _null_cache[key]
    rng = np.random.default_rng(seed)
    _, lam_plus = mp_bounds(t_obs / n_sym)
    out = np.empty(reps, dtype=float)
    for i in range(reps):
        sim = rng.standard_normal((t_obs, n_sym))
        eig = np.linalg.eigvalsh(_correlation(sim)[0])
        out[i] = float((eig > lam_plus).sum()) / n_sym
    _null_cache[key] = out
    return out


def compute_rmt(
    *,
    returns: np.ndarray,
    members: tuple[str, ...],
    prev_v1: np.ndarray | None = None,
    prev_members: tuple[str, ...] | None = None,
    prev_share: float | None = None,
    delta_days: int = 1,
    bootstrap_reps: int = BOOTSTRAP_REPS,
    rebalance_adjacent: bool = False,
    seed: int = 0,
) -> Ok[RmtDetail] | Err:
    """Pure spectral core (FR16–FR19). `returns` is (T, N) aligned to `members`."""
    returns = np.asarray(returns, dtype=float)
    if returns.ndim != 2:
        return err(ConstraintViolated(
            constraint="returns must be a (T, N) matrix", observed=returns.ndim, bound=2
        ))
    t_obs, n_sym = returns.shape
    if n_sym != len(members):
        return err(ConstraintViolated(
            constraint="returns columns must align with members",
            observed=n_sym, bound=len(members),
        ))
    if n_sym < 2 or t_obs < n_sym:
        # Q < 1 puts a point mass at zero and breaks the support formula used
        # here; the window is simply too short for the cross-section.
        return err(InsufficientHistory(
            required=n_sym, available=t_obs, as_of="1970-01-01"
        ))

    warnings: list[SeraphWarning] = []
    q_t = t_obs / n_sym                       # AMENDMENT-02: per-date aspect ratio
    lam_minus, lam_plus = mp_bounds(q_t)

    corr, degenerate = _correlation(returns)
    n_degenerate = int(degenerate.sum())
    if n_degenerate:
        warnings.append(SeraphWarning(
            code="ESTIMATOR_FALLBACK",
            message=(
                f"{n_degenerate} of {n_sym} columns have zero sample variance "
                f"over the {t_obs}-day window; each is given an isolated "
                f"unit-variance mode so that trace(C_t) = N_t holds exactly "
                f"(FR16). Their eigenvalue is exactly 1.0, inside the MP band, "
                f"so F_t is not inflated by the substitution"
            ),
            context={"degenerateColumns": n_degenerate, "nT": n_sym},
        ))
    eigenvalues, eigenvectors = np.linalg.eigh(corr)     # ascending
    eigenvalues = eigenvalues[::-1]
    eigenvectors = eigenvectors[:, ::-1]
    v1 = eigenvectors[:, 0]

    # FR17 — exceedance fraction above the MP upper edge.
    f_t = float((eigenvalues > lam_plus).sum()) / n_sym

    # FR17 — eigenvalue collapse velocity. trace(C) = N exactly for a
    # correlation matrix, so this share is the leading mode's fraction of total
    # variance and its rise is identically the sub-leading mass's collapse
    # (see the module docstring). Exact normalisation ⇒ comparable across N_t.
    total = float(eigenvalues.sum())
    share = float(eigenvalues[0] / total) if total > 0 else 0.0
    v_eig = 0.0 if prev_share is None else (share - prev_share) / max(delta_days, 1)

    # FR17 + D3 — rotation speed on COMMON SUPPORT ONLY.
    omega_t = 0.0
    common_fraction = 1.0
    if prev_v1 is not None and prev_members is not None:
        prev_index = {s: i for i, s in enumerate(prev_members)}
        pairs = [(i, prev_index[s]) for i, s in enumerate(members) if s in prev_index]
        common_fraction = len(pairs) / max(len(members), 1)
        if not pairs:
            return err(ConstraintViolated(
                constraint="Omega_t requires non-empty common support (D3)",
                observed=0, bound=1,
            ))
        now_idx = np.fromiter((p[0] for p in pairs), dtype=int, count=len(pairs))
        then_idx = np.fromiter((p[1] for p in pairs), dtype=int, count=len(pairs))
        a = np.asarray(v1, dtype=float)[now_idx]
        b = np.asarray(prev_v1, dtype=float)[then_idx]
        na, nb = np.linalg.norm(a), np.linalg.norm(b)
        if na <= 0 or nb <= 0:
            return err(ConstraintViolated(
                constraint="Omega_t: degenerate eigenvector on common support",
                observed=float(min(na, nb)), bound=0.0,
            ))
        # Renormalise BOTH restricted vectors before the inner product (D3a).
        omega_t = float(1.0 - abs(float((a / na) @ (b / nb))))
        if common_fraction < COMMON_SUPPORT_FLOOR:
            warnings.append(SeraphWarning(
                code="COMMON_SUPPORT_LOW",
                message=(
                    f"eigenvector overlap {common_fraction:.2f} is below the "
                    f"{COMMON_SUPPORT_FLOOR} floor — Omega_t is computed on a thin "
                    f"overlap and is noisy; emitted and flagged, not hidden"
                ),
                context={"commonSupportFraction": round(common_fraction, 4)},
            ))
    if rebalance_adjacent:
        warnings.append(SeraphWarning(
            code="REBALANCE_ADJACENT",
            message="Omega_t computed across a membership change (D3c)",
            context={"commonSupportFraction": round(common_fraction, 4)},
        ))

    # FR19 — bootstrap p-value for the MP-exceedance null.
    p_value = 1.0
    if bootstrap_reps > 0:
        null = _null_exceedance(t_obs, n_sym, bootstrap_reps, seed=seed)
        p_value = float((null >= f_t).sum() + 1) / float(bootstrap_reps + 1)

    if n_sym < 500:
        warnings.append(SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=(
                f"N_t = {n_sym} < 500, so Q_t = {q_t:.2f} rather than 2 "
                f"(AMENDMENT-02); F_t is not directly comparable to full-size "
                f"dates — use the bootstrap p-value for cross-date inference"
            ),
            context={"nT": n_sym, "qT": round(q_t, 4)},
        ))

    return ok(
        RmtDetail(
            f_t=f_t,
            v_eig_t=float(v_eig),
            omega_t=omega_t,
            mp_p_value=p_value,
            lambda_minus=lam_minus,
            lambda_plus=lam_plus,
            leading_eigenvector=tuple(float(x) for x in v1),
            common_support_fraction=float(common_fraction),
            rebalance_adjacent=bool(rebalance_adjacent),
        ),
        tuple(warnings),
    )


def _ecdf_rank(value: float, window) -> float:
    """Right-continuous empirical-CDF rank of `value` within `window` → [0,1].

    Deliberately duplicated rather than imported from C9's standardiser: C6
    must not depend on the fusion layer (no such edge exists in ARCHITECTURE
    §3), and duplicating three lines of a pure statistic is the correct price
    for keeping the pillar independently evaluable — the same reasoning that
    keeps the cross-sectional absorption ratio in C4 rather than here (AGENTS.md
    §5). An empty window has no distribution to rank against and yields the
    uninformative midpoint.
    """
    arr = np.sort(np.asarray(window, dtype=float).ravel())
    if arr.size == 0:
        return 0.5
    return float(np.searchsorted(arr, value, side="right")) / float(arr.size)


def sca(
    detail: RmtDetail,
    *,
    history: "dict[str, object] | None" = None,
    weights: tuple[float, float, float] = SCA_WEIGHTS,
) -> tuple[float, tuple[SeraphWarning, ...]]:
    """FR18 — aggregate the three spectral signals into `SCA_t`.

    **Standardise, then weight.** The three components are on incommensurable
    scales: `F_t` is a fraction in [0,1], `Ω_t` is in [0,1] by construction,
    and `V_t^eig` is a signed daily velocity of order 1e-4. Any fixed weighting
    of the raw values is therefore not a weighting at all — whichever component
    happens to carry the largest variance dominates the aggregate, and the
    nominal weights describe nothing. Each component is instead mapped to its
    own rolling empirical-CDF rank first, which puts all three on a common
    [0,1] footing and makes the weights mean what they say. This is the same
    standardisation FR28 already mandates one layer up, applied for the same
    reason.

    **On "calibrated weights" (FR18).** Equal thirds is an explicitly
    uninformative prior, not a calibration, and must not be reported as one —
    SPEC §8 lists `w^p_F, w^p_V, w^p_Ω` among the undefined constants. It is
    nonetheless a defensible default rather than a placeholder: with the
    components standardised, equal weighting is the unique choice that assumes
    nothing about their relative informativeness, and it is what FR34's
    sensitivity analysis exists to vary. Note also that the pillar is not left
    uncalibrated overall — `SCA_t` enters the reconciled state and FR30 then
    jointly optimises the pillar-level weight, so the calibration FR18 asks for
    is applied downstream where the epoch labels live (D1).

    Returns `(sca_value, warnings)`; a short standardisation history is
    surfaced as `PARTIAL_COVERAGE` rather than being silently absorbed.
    """
    w_f, w_v, w_o = weights
    warnings: list[SeraphWarning] = []
    history = history or {}
    hist_f = history.get("f_t", ())
    hist_v = history.get("v_eig_t", ())
    hist_o = history.get("omega_t", ())

    shortest = min(len(hist_f), len(hist_v), len(hist_o)) if history else 0
    if shortest < SCA_MIN_HISTORY:
        warnings.append(SeraphWarning(
            code="PARTIAL_COVERAGE",
            message=(
                f"SCA_t standardisation window holds {shortest} observations, "
                f"below the {SCA_MIN_HISTORY} needed for a stable empirical CDF; "
                f"components without history default to the 0.5 midpoint"
            ),
            context={"available": shortest, "required": SCA_MIN_HISTORY},
        ))

    value = (
        w_f * _ecdf_rank(detail.f_t, hist_f)
        + w_v * _ecdf_rank(detail.v_eig_t, hist_v)
        + w_o * _ecdf_rank(detail.omega_t, hist_o)
    )
    return float(value), tuple(warnings)


class RmtEngine:
    """S5 — Pillar 2. Stateful driver around the pure `compute_rmt` core.

    Rolling state that spans dates — the previous leading eigenvector and
    membership (for D3's `Omega_t`), the previous variance share (for
    `V_t^eig`), and the SCA_t standardisation history — lives here rather than
    in the caller. `compute_rmt` stays pure and directly testable; this class
    just carries what one date needs from the last.
    """

    pillar = "rmt"

    def __init__(self, *, bootstrap_reps: int = BOOTSTRAP_REPS,
                 weights: tuple[float, float, float] = SCA_WEIGHTS,
                 history_window: int = 1250):
        self._bootstrap_reps = bootstrap_reps
        self._weights = weights
        self._history_window = history_window   # ~5y, matching FR28's ECDF span
        self._prev_v1: np.ndarray | None = None
        self._prev_members: tuple[str, ...] | None = None
        self._prev_share: float | None = None
        self._hist: dict[str, list[float]] = {"f_t": [], "v_eig_t": [], "omega_t": []}

    def step(self, *, returns, members, date: str, delta_days: int = 1,
             rebalance_adjacent: bool = False):
        """Advance one date. Returns Ok((RmtDetail, sca_t)) or Err."""
        res = compute_rmt(
            returns=returns,
            members=tuple(members),
            prev_v1=self._prev_v1,
            prev_members=self._prev_members,
            prev_share=self._prev_share,
            delta_days=delta_days,
            bootstrap_reps=self._bootstrap_reps,
            rebalance_adjacent=rebalance_adjacent,
        )
        if res.status == "error":
            return res
        detail = res.value
        sca_t, sca_warnings = sca(detail, history=self._hist, weights=self._weights)

        eig_share = self._share_from(returns)
        self._prev_v1 = np.asarray(detail.leading_eigenvector, dtype=float)
        self._prev_members = tuple(members)
        self._prev_share = eig_share
        for key, value in (("f_t", detail.f_t), ("v_eig_t", detail.v_eig_t),
                           ("omega_t", detail.omega_t)):
            self._hist[key].append(value)
            if len(self._hist[key]) > self._history_window:
                del self._hist[key][0]
        return ok((detail, sca_t), tuple(res.warnings) + sca_warnings)

    @staticmethod
    def _share_from(returns) -> float:
        eig = np.linalg.eigvalsh(_correlation(np.asarray(returns, dtype=float))[0])
        total = float(eig.sum())
        return float(eig[-1] / total) if total > 0 else 0.0
