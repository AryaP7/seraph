# C5 — Hawkes fit artefacts (FIX07; audit findings A08, A09)
"""Persist a fit so its intensity can be rebuilt, and pin the basket it used.

Two defects this closes.

**A08 — the fit was thrown away.** `scripts/write_hawkes_production.py` stored
`"alpha_beta": None` and a hardcoded `"flag": "none"`, so nothing about the
fitted kernel survived. The branching ratio was kept and the parameters that
produced it were not, which makes the number unreproducible and the model
unauditable. `HawkesFitArtefact` keeps `mu`, `alpha`, `phi`, the dispersion,
the time-of-day seasonality profile, the training window and the convergence
diagnostics — enough that `reconstruct_intensity()` reproduces `lambda_t`
exactly from the artefact alone.

**A09 — historical windows used today's universe.** The writer selected
`ORDER BY rebalance_date DESC LIMIT 1`, so a 2019 refit was computed over the
2026 membership. `BasketIdentity` records which basket a fit actually used and
how it was chosen, and `point_in_time_members()` picks the snapshot in force at
the window's end instead. Where a fixed research basket is deliberate, it is
recorded as such rather than passed off as point-in-time.

The artefact is content-hashed. Refit the same window with the same inputs and
you get the same id; change the basket, the window or the seasonality and you
get a different one, so a regenerated artefact can never be mistaken for the
original.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Literal

import numpy as np

from seraph.pillars.hawkes.engine import excitation_path

ARTEFACT_VERSION = "c5.hawkes_fit/2026-10-16.1"

BasketBasis = Literal["point_in_time", "fixed_research_basket", "latest_snapshot"]


@dataclass(frozen=True)
class BasketIdentity:
    """Which symbols a fit used, and how that set was chosen.

    `latest_snapshot` is retained only to describe pre-FIX07 artefacts
    honestly. It is never a valid choice for a NEW historical fit, and
    `validate()` says so.
    """

    basis: BasketBasis
    symbols: tuple[str, ...]
    rebalance_date: str | None = None
    note: str | None = None

    @property
    def digest(self) -> str:
        return hashlib.sha256("|".join(sorted(self.symbols)).encode()).hexdigest()

    def validate(self, *, window_end: str) -> list[str]:
        problems = []
        if not self.symbols:
            problems.append("the basket is empty")
        if self.basis == "latest_snapshot":
            problems.append(
                "basis 'latest_snapshot' applies today's membership to a "
                "historical window (audit finding A09). Use 'point_in_time', or "
                "declare 'fixed_research_basket' and accept the survivorship "
                "limitation explicitly")
        if self.basis == "point_in_time":
            if self.rebalance_date is None:
                problems.append("a point-in-time basket must name its rebalance date")
            elif self.rebalance_date > window_end:
                problems.append(
                    f"rebalance date {self.rebalance_date} is after the window end "
                    f"{window_end}: that membership did not exist yet")
        if self.basis == "fixed_research_basket" and not self.note:
            problems.append(
                "a fixed research basket must state its survivorship limitation")
        return problems

    def describe(self) -> dict:
        return dict(basis=self.basis, size=len(self.symbols), digest=self.digest,
                    rebalance_date=self.rebalance_date, note=self.note)


@dataclass(frozen=True)
class FitDiagnostics:
    converged: bool
    n_bars: int
    n_sessions: int
    n_neg: int
    n_pos: int
    log_likelihood: float | None = None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class HawkesFitArtefact:
    """A fit, complete enough to rebuild its own intensity."""

    as_of: str                       # the window's last session, ISO date
    training_start: str              # the window's first session
    mu: float
    alpha: float
    phi: float
    dispersion: float
    tod_profile: tuple[float, ...]   # the seasonality the fit was conditioned on
    n_slots: int
    basket: BasketIdentity
    diagnostics: FitDiagnostics
    branching_ratio: float
    mts: float | None = None
    estimator: str = "discrete_pooled_counts"
    version: str = ARTEFACT_VERSION
    sector_baselines: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not 0.0 < self.branching_ratio < 1.0:
            raise ValueError(
                f"branching ratio {self.branching_ratio} violates FR11 stationarity")
        implied = self.alpha / max(1.0 - self.phi, 1e-12)
        if abs(implied - self.branching_ratio) > 1e-6:
            raise ValueError(
                f"the stored parameters imply n = {implied:.6f} but the artefact "
                f"records {self.branching_ratio:.6f}: a fit whose parameters do "
                f"not reproduce its own headline number is not reconstructible")
        if len(self.tod_profile) != self.n_slots:
            raise ValueError(
                f"the seasonality profile has {len(self.tod_profile)} slots but "
                f"n_slots is {self.n_slots}")

    @property
    def artefact_id(self) -> str:
        payload = json.dumps(dict(
            version=self.version, estimator=self.estimator, as_of=self.as_of,
            training_start=self.training_start, mu=self.mu, alpha=self.alpha,
            phi=self.phi, dispersion=self.dispersion,
            tod=[round(t, 12) for t in self.tod_profile],
            basket=self.basket.digest, basket_basis=self.basket.basis,
        ), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()

    # ------------------------------------------------------ reconstruct

    def reconstruct_intensity(self, counts, session_starts, tod_index):
        """Rebuild `lambda_t` from the artefact alone.

        This is the FIX07 acceptance criterion: given the saved parameters and
        the same event stream, the intensity comes back identically. Nothing
        is re-fitted.
        """
        return excitation_path(np.asarray(counts, dtype=float),
                               np.asarray(session_starts),
                               self.mu, self.alpha, self.phi,
                               np.asarray(self.tod_profile),
                               np.asarray(tod_index))

    # --------------------------------------------------------- transport

    def describe(self) -> dict:
        return dict(
            artefact_id=self.artefact_id, version=self.version,
            estimator=self.estimator, as_of=self.as_of,
            training_start=self.training_start,
            parameters=dict(mu=self.mu, alpha=self.alpha, phi=self.phi,
                            dispersion=self.dispersion,
                            branching_ratio=self.branching_ratio),
            seasonality=dict(n_slots=self.n_slots,
                             profile=[round(t, 10) for t in self.tod_profile]),
            basket=self.basket.describe(),
            diagnostics=asdict(self.diagnostics),
            mts=self.mts,
            sector_baselines=self.sector_baselines or None,
            sector_flags_note=(
                "per-sector flags require measured sector baselines. Where "
                "sector_baselines is empty no flag is emitted at all, rather "
                "than a constant 'none' standing in for a measurement"),
        )

    def to_json(self) -> str:
        return json.dumps(self.describe(), sort_keys=True)

    @classmethod
    def from_describe(cls, payload: dict) -> "HawkesFitArtefact":
        parameters = payload["parameters"]
        basket = payload["basket"]
        diagnostics = payload["diagnostics"]
        return cls(
            as_of=payload["as_of"], training_start=payload["training_start"],
            mu=parameters["mu"], alpha=parameters["alpha"], phi=parameters["phi"],
            dispersion=parameters["dispersion"],
            branching_ratio=parameters["branching_ratio"],
            tod_profile=tuple(payload["seasonality"]["profile"]),
            n_slots=payload["seasonality"]["n_slots"],
            basket=BasketIdentity(
                basis=basket["basis"], symbols=(), rebalance_date=basket["rebalance_date"],
                note=basket.get("note")),
            diagnostics=FitDiagnostics(**diagnostics),
            mts=payload.get("mts"), estimator=payload["estimator"],
            version=payload["version"],
            sector_baselines=payload.get("sector_baselines") or {})


def artefact_from_fit(fit, *, as_of: str, training_start: str,
                      tod_profile, n_slots: int, basket: BasketIdentity,
                      n_neg: int, n_pos: int, n_sessions: int,
                      mts: float | None = None,
                      warnings: tuple[str, ...] = (),
                      sector_baselines: dict | None = None) -> HawkesFitArtefact:
    """Package a `DiscreteHawkes` fit as a persistable artefact."""
    branching = fit.alpha / max(1.0 - fit.phi, 1e-12)
    return HawkesFitArtefact(
        as_of=as_of, training_start=training_start,
        mu=float(fit.mu), alpha=float(fit.alpha), phi=float(fit.phi),
        dispersion=float(fit.dispersion),
        tod_profile=tuple(float(t) for t in tod_profile), n_slots=int(n_slots),
        basket=basket, branching_ratio=float(branching), mts=mts,
        diagnostics=FitDiagnostics(
            converged=bool(fit.converged), n_bars=int(fit.n_bars),
            n_sessions=int(n_sessions), n_neg=int(n_neg), n_pos=int(n_pos),
            warnings=tuple(warnings)),
        sector_baselines=sector_baselines or {})


async def point_in_time_members(pool, window_end: str) -> BasketIdentity:
    """The universe snapshot in force at `window_end` — not the latest one.

    Replaces `ORDER BY rebalance_date DESC LIMIT 1` (audit finding A09).
    """
    row = await pool.fetchrow(
        "SELECT rebalance_date, members FROM universe_snapshots "
        "WHERE rebalance_date <= $1 ORDER BY rebalance_date DESC LIMIT 1",
        window_end)
    if not row:
        return BasketIdentity(
            basis="point_in_time", symbols=(), rebalance_date=None,
            note=f"no universe snapshot exists at or before {window_end}")
    return BasketIdentity(basis="point_in_time", symbols=tuple(row["members"]),
                          rebalance_date=str(row["rebalance_date"]))
