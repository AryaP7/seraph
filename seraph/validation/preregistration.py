# C10 — Validation Harness (D5d): pre-registration.
"""Hash the evaluation design **before the first AUC is computed**.

D5's constraint is blunt: six positive events, fourteen configurations. Any
split can be made to produce a flattering number, and with n=6 the temptation is
severe. Pre-registration is cheap and, at this sample size, the only real
defence — against a reviewer and against ourselves.

The committed file records the split policy, the loss ratios, the primary
metric, the amber-threshold rule and the full configuration list. Every
`EvaluationRow` carries the resulting hash, and **a result whose hash does not
match the committed file is not reportable**. That is a mechanical check, not a
discipline: `verify()` recomputes the hash from the file and compares.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DEFAULT_PATH = Path("preregistration.json")

#: The six labelled structural-break epochs (FR32).
EPOCHS = ("gfc_2008", "taper_2013", "ilfs_2018", "covid_2020",
          "tightening_2022", "tariff_2026")
#: Epochs with Hawkes coverage (SPEC §4). Table A is restricted to these.
HAWKES_EPOCHS = ("ilfs_2018", "covid_2020", "tightening_2022", "tariff_2026")
#: Pre-2015 epochs — Table B, RMT/Hamilton subsets only.
PRE_HAWKES_EPOCHS = ("gfc_2008", "taper_2013")


def _subsets(pillars: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """All non-empty subsets, ordered by size then name — deterministic."""
    out = []
    n = len(pillars)
    for mask in range(1, 1 << n):
        out.append(tuple(p for i, p in enumerate(pillars) if mask & (1 << i)))
    return tuple(sorted(out, key=lambda s: (len(s), s)))


def configuration_list() -> list[dict]:
    """FR35's 14 configurations: Table A is 7 subsets x 2 reconciliation modes
    on the Hawkes-covered epochs; Table B is 3 subsets x 2 modes on the
    pre-2015 epochs. Table A and Table B AUCs are computed over different fold
    counts (4 vs 6) and are therefore **not directly comparable** — D5(b)."""
    configs = []
    for subset in _subsets(("hawkes", "rmt", "hamilton")):
        for mode in ("kalman", "forward_fill"):
            configs.append({
                "table": "A", "pillarSubset": list(subset),
                "reconciliationMode": mode, "epochs": list(HAWKES_EPOCHS),
                "folds": len(HAWKES_EPOCHS),
            })
    for subset in _subsets(("rmt", "hamilton")):
        for mode in ("kalman", "forward_fill"):
            configs.append({
                "table": "B", "pillarSubset": list(subset),
                "reconciliationMode": mode, "epochs": list(EPOCHS),
                "folds": len(EPOCHS),
                # R5: Hamilton is both a signal and the weighting over signals.
                # Every Table B row needs its uniform-xi control companion.
                "xiModes": ["hamilton", "uniform"],
            })
    return configs


def build(
    *,
    kappa_miss: float = 10.0,
    kappa_fa: float = 1.0,
    amber_threshold: float = 0.5,
    primary_metric: str = "auc",
) -> dict:
    """The design to commit. Nothing here may change once results exist."""
    return {
        "splitPolicy": "leave_one_epoch_out",
        "kappaMiss": kappa_miss,
        "kappaFa": kappa_fa,
        "primaryMetric": primary_metric,
        "amberThresholdRule": (
            f"CSRS >= {amber_threshold} sustained for 1 update; threshold fixed "
            f"before evaluation, not tuned per configuration"
        ),
        "reporting": (
            "mean AUC with full per-fold spread; the ablation is DESCRIPTIVE, "
            "no configuration is selected as best and reported as a headline"
        ),
        "tableComparability": (
            "Table A (4 folds) and Table B (6 folds) are not directly comparable "
            "and must not be placed in a single ranking"
        ),
        "configurations": configuration_list(),
    }


def content_hash(design: dict) -> str:
    payload = json.dumps(design, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def commit(design: dict | None = None, path: Path = DEFAULT_PATH) -> tuple[Path, str]:
    """Write the design and return its hash. Refuses to overwrite: the point of
    pre-registration is that it cannot be revised after seeing results."""
    design = design or build()
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        return path, content_hash(existing.get("design", existing))
    digest = content_hash(design)
    path.write_text(
        json.dumps({"design": design, "hash": digest}, indent=2, sort_keys=True),
        encoding="utf-8")
    return path, digest


def verify(path: Path = DEFAULT_PATH) -> tuple[bool, str]:
    """Recompute the hash from the committed file. `(ok, hash)`."""
    if not path.exists():
        return False, ""
    blob = json.loads(path.read_text(encoding="utf-8"))
    design, stored = blob.get("design", {}), blob.get("hash", "")
    return content_hash(design) == stored, stored
