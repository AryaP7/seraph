# C2 — Ingestion Layer (FR4): tariff event registry → E5 tariff_events.
"""Loads and validates the hand-curated USTR / Section 301 / Section 122 event
table that FR22's `G_t` decays over.

THIS MODULE DOES NOT AND WILL NOT GENERATE EVENT DATES
------------------------------------------------------
FR4 specifies a "hand-curated, dated event table … cross-checked against
contemporaneous news coverage for announcement-date accuracy". SPEC §6 E5 names
the *sequence* (~25% mid-2025 → 50% peak on Russian-oil secondary sanctions →
18% under the Feb-2026 interim framework → 10% Section 122 baseline
post-Supreme-Court; sector duties 50% steel/aluminium, 25% certain auto
components, solar CVD action Feb 2026) but gives **no announcement dates**, and
SPEC OQ3 — which of the candidate 2025-26 dates labels Epoch 6 — is explicitly
open. `seraph/validation/epochs.py` carries a single PROVISIONAL placeholder and
says so.

AGENTS.md §9 is binding here: do not silently invent a value. An invented `tau_k`
would propagate into `G_t`, into `z_t`, into every FR22 ablation row, and into
the report's Epoch-6 lead-time figure — while looking entirely plausible. So
this module ships the machinery and an **empty registry**. The dates are a human
curation task, with a citation per row.

`severity_score` has no defined scale (SPEC §6 E5 marks it `[GAP]`, and
SERAPH-BUILD-ROADMAP §4 does not supply a default). It is therefore not computed
here either: the registry must declare its own scale in the `# scale:` header
line, and the loader records that declaration rather than assuming one.

WHAT THE LOADER ENFORCES
------------------------
Every gate below exists to make a fabricated or careless row fail loudly rather
than flow into `G_t`:
  - `source_ref` must be a real-looking citation (URL, or `doc:`/`ref:` prefix).
    A blank or placeholder reference is rejected — an uncited tariff date is
    indistinguishable from an invented one.
  - `tau_k` must parse as ISO-8601, lie inside the corpus window, and not be in
    the future. A future-dated event is either a typo or a forecast, and FR22
    decays `e^{−(t−τ_k)/η}` over *past* events only.
  - `sectors_affected` must come from FR22's five-sector vocabulary. A typo'd
    sector silently drops out of `g_t_sector_weighted` without changing `g_t`,
    which is near-undetectable downstream.
  - `event_id` must be unique. E5's primary key is `event_id` alone, so a
    duplicate would upsert over a different event rather than add one.
  - An empty registry is reported as `events: 0` with an explicit
    `registry_empty` reason — never as a successful ingestion.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import re
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from seraph.shared_types import (
    IST,
    IngestBatch,
    TariffEvent,
)

DEFAULT_REGISTRY = Path(__file__).resolve().parent / "tariff_events.curated.csv"

CORPUS_START = date(2005, 1, 1)

#: FR22's sector restriction, verbatim: "steel, aluminium, auto components,
#: solar and pharmaceuticals". Spellings are the canonical ones; anything else
#: is a curation error, not a new sector.
FR22_SECTORS = ("steel", "aluminium", "auto_components", "solar", "pharmaceuticals")

#: A citation must look like one. Deliberately permissive about *form* and
#: strict about *emptiness* — the gate is against uncited rows, not against
#: unusual citation styles.
_CITATION = re.compile(r"^(https?://\S+|doc:\S+|ref:\S+)", re.IGNORECASE)

#: Values curators leave behind when they mean "I haven't done this yet".
_PLACEHOLDERS = {"", "-", "tbd", "todo", "n/a", "na", "none", "unknown", "?"}

REQUIRED_COLUMNS = (
    "event_id", "tau_k", "delta_r_k", "severity_score",
    "sectors_affected", "source_ref",
)


@dataclass(frozen=True)
class RegistryMeta:
    """Declarations the registry file makes about itself, from `# key: value`
    comment lines. `scale` is the SPEC [GAP] the curator must close."""

    scale: str | None = None
    curator: str | None = None
    curated_at: str | None = None


@dataclass(frozen=True)
class ValidationIssue:
    line: int
    event_id: str
    field: str
    detail: str

    def __str__(self) -> str:
        return f"line {self.line} [{self.event_id or '?'}] {self.field}: {self.detail}"


def parse_sectors(raw: str) -> tuple[str, ...]:
    """`"steel|aluminium"` → `("steel", "aluminium")`, normalised.

    Pipe-separated rather than comma, so the field survives CSV without
    quoting games. Spaces and hyphens normalise to underscores so
    "auto components" and "auto-components" both land on `auto_components`.
    """
    parts = [p.strip().lower().replace(" ", "_").replace("-", "_")
             for p in raw.split("|")]
    return tuple(p for p in parts if p)


def load_registry(
    path: Path = DEFAULT_REGISTRY, *, today: date | None = None
) -> tuple[tuple[TariffEvent, ...], tuple[ValidationIssue, ...], RegistryMeta]:
    """Curated CSV → validated E5 rows, issues, and the registry's own metadata.

    Returns issues rather than raising: a curator fixing a ten-row table wants
    every problem at once, not the first one.
    """
    today = today or datetime.now(IST).date()
    if not path.exists():
        raise FileNotFoundError(f"tariff registry not found: {path}")

    raw_lines = path.read_text(encoding="utf-8").splitlines()

    meta_kv: dict[str, str] = {}
    data_lines: list[tuple[int, str]] = []
    for n, line in enumerate(raw_lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            body = stripped.lstrip("#").strip()
            if ":" in body:
                k, _, v = body.partition(":")
                key = k.strip().lower().replace(" ", "_")
                if key in {"scale", "curator", "curated_at"}:
                    meta_kv[key] = v.strip()
            continue
        data_lines.append((n, line))

    meta = RegistryMeta(
        scale=meta_kv.get("scale") or None,
        curator=meta_kv.get("curator") or None,
        curated_at=meta_kv.get("curated_at") or None,
    )

    if not data_lines:
        return (), (), meta

    header_line_no, header_raw = data_lines[0]
    reader = csv.reader([header_raw])
    header = [h.strip() for h in next(reader)]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise ValueError(
            f"tariff registry {path} missing columns {missing}; "
            f"expected {list(REQUIRED_COLUMNS)}, got {header}"
        )

    events: list[TariffEvent] = []
    issues: list[ValidationIssue] = []
    seen: dict[str, int] = {}

    for line_no, raw in data_lines[1:]:
        row = dict(zip(header, next(csv.reader([raw]))))
        eid = (row.get("event_id") or "").strip()

        def bad(field: str, detail: str) -> None:
            issues.append(ValidationIssue(line_no, eid, field, detail))

        if eid.lower() in _PLACEHOLDERS:
            bad("event_id", "empty or placeholder")
            continue
        if eid in seen:
            bad("event_id", f"duplicate of line {seen[eid]} — E5's primary key "
                            "is event_id alone, so this would overwrite it")
            continue
        seen[eid] = line_no

        # --- tau_k: the field an invented row gets wrong
        raw_tau = (row.get("tau_k") or "").strip()
        if raw_tau.lower() in _PLACEHOLDERS:
            bad("tau_k", "no announcement date — FR4 requires a dated event; "
                         "leaving this blank is correct until it is curated, "
                         "but the row cannot be ingested")
            continue
        try:
            tau = date.fromisoformat(raw_tau)
        except ValueError:
            bad("tau_k", f"not ISO-8601 (YYYY-MM-DD): {raw_tau!r}")
            continue
        if tau > today:
            bad("tau_k", f"{tau} is in the future — FR22 decays over past "
                         "events only")
            continue
        if tau < CORPUS_START:
            bad("tau_k", f"{tau} precedes the corpus start {CORPUS_START}")
            continue

        # --- source_ref: the anti-fabrication gate
        src = (row.get("source_ref") or "").strip()
        if src.lower() in _PLACEHOLDERS:
            bad("source_ref", "missing — an uncited tariff date cannot be "
                              "distinguished from an invented one (FR4 requires "
                              "a contemporaneous cross-check)")
            continue
        if not _CITATION.match(src):
            bad("source_ref", f"not a citation: {src!r} (expected a URL, or a "
                              "'doc:'/'ref:' prefix)")
            continue

        # --- numerics
        try:
            delta_r = float((row.get("delta_r_k") or "").strip())
        except ValueError:
            bad("delta_r_k", f"not numeric: {row.get('delta_r_k')!r}")
            continue
        if not math.isfinite(delta_r):
            bad("delta_r_k", f"not finite: {delta_r!r}")
            continue

        try:
            severity = float((row.get("severity_score") or "").strip())
        except ValueError:
            bad("severity_score", f"not numeric: {row.get('severity_score')!r}")
            continue
        if not math.isfinite(severity) or severity < 0:
            bad("severity_score", f"must be finite and >= 0, got {severity!r}")
            continue
        if meta.scale is None:
            bad("severity_score", "registry declares no '# scale:' line — "
                                  "severity_score's scale is a SPEC [GAP] and "
                                  "must be stated by the curator, not assumed")
            continue

        sectors = parse_sectors(row.get("sectors_affected") or "")
        unknown = [s for s in sectors if s not in FR22_SECTORS]
        if unknown:
            bad("sectors_affected", f"not in FR22's vocabulary: {unknown} "
                                    f"(allowed: {list(FR22_SECTORS)})")
            continue

        events.append(TariffEvent(
            event_id=eid,
            tau_k=tau.isoformat(),
            delta_r_k=delta_r,
            severity_score=severity,
            sectors_affected=sectors,
            source_ref=src,
        ))

    events.sort(key=lambda e: (e.tau_k, e.event_id))
    return tuple(events), tuple(issues), meta


async def ingest(
    *,
    registry: Path = DEFAULT_REGISTRY,
    dry_run: bool = False,
    allow_partial: bool = False,
) -> dict:
    """Validate the registry and write E5. Idempotent on `event_id` (CT-1).

    Refuses to write when any row failed validation unless `allow_partial` is
    set — a half-ingested event table produces a `G_t` that is wrong in a way
    nothing downstream can detect.
    """
    events, issues, meta = load_registry(registry)

    result: dict = {
        "status": "ok",
        "registry": str(registry),
        "events": len(events),
        "issues": [str(i) for i in issues],
        "severityScale": meta.scale,
        "curator": meta.curator,
        "curatedAt": meta.curated_at,
    }

    if not events:
        result["status"] = "empty"
        result["reason"] = (
            "registry_empty — FR4's event table has not been curated. SPEC OQ3 "
            "(Epoch 6 break date) is open and SPEC §6 E5 gives the tariff "
            "sequence without announcement dates. Dates must be curated by hand "
            "with a citation per row; they are deliberately not generated."
        )
        result["written"] = False
        return result

    if issues and not allow_partial:
        result["status"] = "error"
        result["reason"] = (
            f"{len(issues)} invalid row(s) — refusing to write a partial event "
            "table, which would silently corrupt G_t. Fix them, or pass "
            "--allow-partial if the valid subset is genuinely what you want."
        )
        result["written"] = False
        return result

    if dry_run:
        result["written"] = False
        return result

    from seraph.store import StoreWriter

    writer = await StoreWriter.connect()
    try:
        res = await writer.write_batch(IngestBatch(
            run_id=f"tariff-{datetime.now(IST).strftime('%Y%m%dT%H%M%S')}",
            source="tariff-manual",
            entity="E5",
            rows=events,
            watermark=f"{max(e.tau_k for e in events)}T18:00:00+05:30",
            source_schema_version="tariff-curated-csv-v1",
        ))
        if res.status != "ok":
            result["status"] = "error"
            result["reason"] = str(res.error)
            result["written"] = False
            return result
        result["written"] = True
        result["inserted"] = res.value.inserted
        result["updated"] = res.value.updated
    finally:
        await writer.close()
    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Tariff event registry validation + ingestion (C2 → E5)."
    )
    p.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    p.add_argument("--dry-run", action="store_true",
                   help="validate only; report issues without writing")
    p.add_argument("--allow-partial", action="store_true",
                   help="write the valid subset even if some rows failed")
    a = p.parse_args(argv)
    out = asyncio.run(ingest(
        registry=a.registry, dry_run=a.dry_run, allow_partial=a.allow_partial
    ))
    print(json.dumps(out, indent=2, default=str), flush=True)
    # An empty registry is a true statement about the project's state, not a
    # crash — but it is not success either, so it does not exit 0.
    return 0 if out["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
