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
#: Pre-2015 epochs — Table B, RMT/Hamilton subsets only. Declared and then
#: never used for as long as `configuration_list()` built Table B from all
#: six epochs, which is how the module came to hold both readings of FR35 at
#: once: this constant said one thing and the code did another. DR-05 settled
#: it and this is now the epoch set Table B is actually built from.
PRE_HAWKES_EPOCHS = ("gfc_2008", "taper_2013")


def _subsets(pillars: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """All non-empty subsets, ordered by size then name — deterministic."""
    out = []
    n = len(pillars)
    for mask in range(1, 1 << n):
        out.append(tuple(p for i, p in enumerate(pillars) if mask & (1 << i)))
    return tuple(sorted(out, key=lambda s: (len(s), s)))


#: The two readings of FR35's Table B scope that DR-05 set against each other.
#: `two_epoch` is the owner's recorded decision (2026-10-16); `six_epoch` is
#: ARCHITECTURE D5(b), retained as a named value so a historical row can say
#: which reading produced it instead of being silently relabelled.
TABLE_B_SCOPES = ("two_epoch", "six_epoch")


def configuration_list(*, table_b_scope: str) -> list[dict]:
    """FR35's configurations, under an explicitly chosen Table B scope.

    Table A is 7 subsets x 2 reconciliation modes on the Hawkes-covered
    epochs. Table B is 3 subsets x 2 modes x 2 xi modes on whichever epoch set
    `table_b_scope` names. Table C is the six-epoch RMT/Hamilton run, present
    only under the two-epoch reading, where it is the thing Table B stopped
    being.

    `table_b_scope` has **no default on purpose** (DR-05 step 1). The fold
    count is inside the pre-registration hash, so a caller that inherits the
    scope instead of stating it can produce a result under one reading that is
    later read as the other. Every call site has to say which question it is
    asking.

    The three tables answer three different questions and must never be placed
    in a single ranking:

    * **A** — what the full pillar set can do where Hawkes exists (4 folds).
    * **B** — what RMT and Hamilton can do where Hawkes *cannot* exist
      (2 folds under the decision). Two folds is the honest weakness: it is a
      property of the data, since only two pre-2015 labelled epochs exist.
    * **C** — the same subsets over the whole labelled period (6 folds). A
      legitimate full-period ablation, but not the pre-Hawkes evidence,
      because four of its six folds are Table A's own epochs.
    """
    if table_b_scope not in TABLE_B_SCOPES:
        raise ValueError(
            f"table_b_scope must be one of {TABLE_B_SCOPES}, got "
            f"{table_b_scope!r}. There is no default: see DR-05.")
    table_b_epochs = (PRE_HAWKES_EPOCHS if table_b_scope == "two_epoch"
                      else EPOCHS)
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
                "reconciliationMode": mode, "epochs": list(table_b_epochs),
                "folds": len(table_b_epochs),
                # R5: Hamilton is both a signal and the weighting over signals.
                # Every Table B row needs its uniform-xi control companion.
                "xiModes": ["hamilton", "uniform"],
            })
    if table_b_scope == "two_epoch":
        # DR-05 step 3: nothing is lost by narrowing Table B. The six-epoch
        # RMT/Hamilton run is a real full-period ablation; it just is not the
        # pre-Hawkes table, so it gets its own identity rather than being
        # folded into one that answers a different question.
        for subset in _subsets(("rmt", "hamilton")):
            for mode in ("kalman", "forward_fill"):
                configs.append({
                    "table": "C", "pillarSubset": list(subset),
                    "reconciliationMode": mode, "epochs": list(EPOCHS),
                    "folds": len(EPOCHS),
                    "xiModes": ["hamilton", "uniform"],
                })
    return configs


def build(
    *,
    table_b_scope: str = "two_epoch",
    kappa_miss: float = 10.0,
    kappa_fa: float = 1.0,
    amber_threshold: float = 0.5,
    primary_metric: str = "auc",
) -> dict:
    """The design to commit. Nothing here may change once results exist.

    `table_b_scope` defaults to the owner's recorded DR-05 decision, and is
    written into the design body so the hash differs between the two readings
    (DR-05 step 2). A result can then never be mistaken for one produced under
    the other reading -- which matters because `verify()` compares hashes and
    "a result whose hash does not match the committed file is not reportable".
    """
    return {
        "splitPolicy": "leave_one_epoch_out",
        "tableBScope": table_b_scope,
        "tableBScopeDecision": (
            "DR-05, owner decision recorded 2026-10-16: Table B is the two "
            "pre-Hawkes epochs (gfc_2008, taper_2013). The six-epoch "
            "RMT/Hamilton run is retained as Table C"),
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
            "Tables A, B and C answer three different questions, are not "
            "directly comparable, and must not be placed in a single "
            "ranking. A (4 folds) is the full pillar set "
            "where Hawkes exists; B (2 folds) is RMT/Hamilton where Hawkes "
            "cannot exist; C (6 folds) is RMT/Hamilton over the whole labelled "
            "period, which overlaps A on four of its six folds"
        ),
        "configurations": configuration_list(table_b_scope=table_b_scope),
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
