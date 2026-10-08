# C8 — Reconciliation Layer (FR25–FR27)
"""Maintains a time-aligned latent pillar-state estimate with age-aware
uncertainty. Owns Q_proc, the D4 noise model R^(p)(·), per-pillar τ^(p), and
the forward-fill ablation baseline."""
from seraph.reconciliation.kalman import KalmanReconciler
from seraph.reconciliation.noise_model import SaturatingNoise

__all__ = ["KalmanReconciler", "SaturatingNoise"]
