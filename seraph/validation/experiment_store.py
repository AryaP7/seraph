# C10 — Validation Harness (FR38): experiment report artefacts and archival.
"""Persist an `ExperimentReport`, read it back, and render it for a reader.

Two destinations, for two different jobs:

* **A JSON artefact** is the primary local record. It is content-hashed over
  the rows and the design hash together, so a report cannot be edited after
  the fact without the identifier changing, and it needs no database — which
  matters because the research Postgres is not part of a demonstration and a
  result that only exists inside a database nobody can start is not evidence.
* **`validation_results`** is FR38's archive ("archive all ... ablation
  results ... for retrospective analysis"). `archive_rows()` produces the
  tuples; the writer is `archive()` and needs migration 002, which widens
  `table_id` to include Table C and makes the metric columns nullable.

`render()` exists because the one thing a reader does with three tables is
rank them together, and a renderer that prints three blocks of numbers with no
fold counts and no absences invites exactly that. Every line carries its
measured/declared fold count, and the comparability warning is printed above
the tables rather than appended below them.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from seraph.validation.experiment import ExperimentReport, ExperimentRow


def artefact_id(report: ExperimentReport) -> str:
    """Content hash over the design hash and every row.

    Includes the pre-registration hash on purpose: two runs of the same rows
    under different designs are different results, and an identifier that
    ignored the design would call them the same.
    """
    payload = json.dumps(
        {
            "preRegistrationHash": report.pre_registration_hash,
            "calibrationMaxIter": report.calibration_max_iter,
            "tableBScope": report.table_b_scope,
            "rows": [r.model_dump(mode="json") for r in report.rows],
            **({"datasetProvenance": report.dataset_provenance}
               if report.dataset_provenance else {}),
        },
        sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def save(report: ExperimentReport, path: Path) -> tuple[Path, str]:
    """Write the report and return `(path, artefact_id)`.

    Refuses to overwrite. A report is evidence of one run; replacing it in
    place is how the earlier run's numbers disappear, which is the defect
    migration 001 was written to fix in the database and which would be
    reintroduced here by a convenient `w` mode.
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(
            f"{path} already holds a report. Write the new run to its own "
            f"path: replacing one in place destroys the earlier evidence.")
    digest = artefact_id(report)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"artefactId": digest,
                    "report": report.model_dump(mode="json")},
                   indent=2, sort_keys=True),
        encoding="utf-8")
    return path, digest


def load(path: Path) -> tuple[ExperimentReport, str, bool]:
    """`(report, artefact_id, intact)`.

    `intact` recomputes the hash from the rows. A report whose stored id does
    not match its own content was edited after it was written, and no number
    in it should be quoted.
    """
    blob = json.loads(Path(path).read_text(encoding="utf-8"))
    report = ExperimentReport.model_validate(blob["report"])
    stored = blob.get("artefactId", "")
    return report, stored, artefact_id(report) == stored


# --- FR38 archival -------------------------------------------------------

#: Column order for `validation_results` after migration 002.
ARCHIVE_COLUMNS = (
    "evaluation_run_id", "table_id", "pillar_subset", "reconciliation_mode",
    "xi_mode", "epoch", "availability", "unavailable_reason",
    "unavailable_detail", "auc", "mean_lead_time_days", "precision_at_recall",
    "declared_folds", "train_epochs", "calibration_max_iter",
    "weights_artefact_id", "leakage_check", "pre_registration_hash",
)


def _row_tuple(row: ExperimentRow, run_id: str, budget: int) -> tuple:
    return (
        run_id,
        row.table,
        "+".join(row.pillar_subset),
        row.reconciliation_mode,
        row.xi_mode,
        row.epoch,
        row.availability,
        row.unavailable_reason,
        row.detail,
        row.auc,
        row.mean_lead_time_days,
        row.precision_at_fixed_recall,
        row.folds,
        list(row.train_epochs),
        budget,
        row.weights_artefact_id,
        row.leakage_check,
        row.pre_registration_hash,
    )


def archive_rows(report: ExperimentReport, evaluation_run_id: str
                 ) -> list[tuple]:
    """Every row, measured and unavailable alike.

    Unavailable rows are archived too. They are what FR35's table contains at
    those cells, and an archive that held only the measurable ones would make
    a later reader conclude the run was smaller than it was.
    """
    return [_row_tuple(r, evaluation_run_id, report.calibration_max_iter)
            for r in report.rows]


async def archive(conn, report: ExperimentReport, *, evaluation_run_id: str,
                  design_label: str) -> dict:
    """Write the run and its rows. Idempotent on the 001 primary key.

    Needs migration 002: before it, `table_id` rejects Table C and the metric
    columns are NOT NULL, so an unavailable row cannot be stored without
    inventing a number for it.
    """
    rows = archive_rows(report, evaluation_run_id)
    async with conn.transaction():
        await conn.execute(
            "INSERT INTO evaluation_runs (evaluation_run_id, "
            "pre_registration_hash, design_label, table_b_scope, note) "
            "VALUES ($1,$2,$3,$4,$5) "
            "ON CONFLICT (evaluation_run_id) DO NOTHING",
            evaluation_run_id, report.pre_registration_hash, design_label,
            report.table_b_scope, report.note)
        placeholders = ",".join(f"${i}" for i in range(1, len(ARCHIVE_COLUMNS) + 1))
        statement = (
            f"INSERT INTO validation_results ({','.join(ARCHIVE_COLUMNS)}) "
            f"VALUES ({placeholders}) "
            f"ON CONFLICT (pillar_subset, reconciliation_mode, xi_mode, epoch) "
            f"DO NOTHING")
        await conn.executemany(statement, rows)
    return dict(evaluation_run_id=evaluation_run_id, rows=len(rows),
                measured=len(report.measured()),
                unavailable=len(report.unavailable()))


# --- for a reader --------------------------------------------------------

def render(report: ExperimentReport) -> str:
    """The three tables as text, each row carrying its own fold count."""
    lines = [
        f"pre-registration {report.pre_registration_hash[:16]}  "
        f"table-B scope {report.table_b_scope}  "
        f"calibration budget {report.calibration_max_iter}",
        "",
        "COMPARABILITY",
    ]
    warning = report.comparability or "(the design recorded no warning)"
    for chunk in warning.split(". "):
        if chunk.strip():
            lines.append(f"  {chunk.strip().rstrip('.')}.")
    lines.append("")

    summaries = report.configurations()
    for table in sorted({s.table for s in summaries}):
        rows = [s for s in summaries if s.table == table]
        declared = rows[0].declared_folds if rows else 0
        lines.append(f"TABLE {table}  ({declared} folds declared)")
        lines.append(f"  {'subset':<24}{'mode':<14}{'xi':<10}"
                     f"{'folds':<8}{'mean AUC':<10}{'spread':<16}lead (d)")
        for s in rows:
            subset = "+".join(s.pillar_subset)
            folds = f"{s.measured_folds}/{s.declared_folds}"
            if s.measured_folds:
                mean = f"{s.mean_auc:.4f}"
                spread = f"{s.auc_min:.3f}..{s.auc_max:.3f}"
                lead = ("--" if s.mean_lead_time_days != s.mean_lead_time_days
                        else f"{s.mean_lead_time_days:.1f}")
            else:
                mean, spread, lead = "--", "--", "--"
            note = ""
            if s.unavailable_folds:
                note = "  " + ", ".join(f"{k} x{v}" for k, v
                                        in s.unavailable_folds.items())
            lines.append(f"  {subset:<24}{s.reconciliation_mode:<14}"
                         f"{s.xi_mode:<10}{folds:<8}{mean:<10}{spread:<16}"
                         f"{lead}{note}")
        lines.append("")

    census = report.absence_census()
    if census:
        lines.append("UNAVAILABLE CELLS  (each is a result, not a gap)")
        for reason, count in census.items():
            lines.append(f"  {count:>4}  {reason}")
    else:
        lines.append("UNAVAILABLE CELLS  none: every declared fold measured")
    lines.append("")
    lines.append(f"rows the published EvaluationRow contract cannot carry: "
                 f"{report.unpublishable_rows} of {len(report.rows)}")
    if report.unpublishable_rows:
        lines.append(f"  {report.note}")
    return "\n".join(lines)
