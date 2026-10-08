# C10 — Validation Harness (FR32): labelled structural-break epochs.
"""The six labelled breaks, and the provenance of each date.

**SPEC OQ13 ("who fixes the exact break date, against what source") is open, and
SPEC OQ3 (which of the candidate 2025-26 tariff dates labels Epoch 6) is open.**
The dates below are therefore **provisional defaults, not settled labels**. They
are gathered here as a single constant so the team can fix them once and have
every downstream result move together; nothing else in the codebase hard-codes
an epoch date.

Each is the widely-cited onset of the episode as it affected Indian equities,
chosen so that FR32's "30 trading days following the labelled break" covers the
drawdown rather than the recovery. Where a reasonable alternative exists it is
named, because the choice materially moves lead-time figures and a reader should
be able to see what was picked and what was not.

Any published result must state the labelling used. Changing a date invalidates
the pre-registration hash and forces a re-run — which is the intended behaviour.
"""
from __future__ import annotations

#: epoch id -> (break date, provenance note)
EPOCH_BREAKS: dict[str, tuple[str, str]] = {
    "gfc_2008": (
        "2008-09-15",
        "Lehman Brothers bankruptcy; the global transmission date. Alternative: "
        "2008-01-21, the Indian market's own crash, which precedes the global "
        "event by eight months and would test a different phenomenon.",
    ),
    "taper_2013": (
        "2013-05-22",
        "Bernanke's taper testimony; the trigger for the emerging-market "
        "outflow episode that hit the rupee and Indian equities.",
    ),
    "ilfs_2018": (
        "2018-09-21",
        "IL&FS default cascade and the single-day NBFC selloff; the domestic "
        "shadow-banking shock.",
    ),
    "covid_2020": (
        "2020-02-20",
        "Onset of the global COVID selloff, chosen so the 30-day window covers "
        "the drawdown. Alternative: 2020-03-23, the Indian market bottom, which "
        "would place the window over the recovery instead.",
    ),
    "tightening_2022": (
        "2022-01-05",
        "Start of the 2022 global tightening drawdown. Alternative: 2022-06-16, "
        "the peak-hawkishness repricing.",
    ),
    "tariff_2026": (
        "2026-02-01",
        "PROVISIONAL - SPEC OQ3 is explicitly open. Placeholder for the Feb-2026 "
        "interim framework; the 50% peak and the solar CVD single-day drop are "
        "the other candidates. MUST be resolved before Epoch 6 results are "
        "reported.",
    ),
}

#: Epochs with Hawkes coverage (SPEC §4) — Table A is restricted to these.
HAWKES_COVERED = ("ilfs_2018", "covid_2020", "tightening_2022", "tariff_2026")
#: Pre-2015 epochs — Table B, RMT/Hamilton subsets only.
PRE_HAWKES = ("gfc_2008", "taper_2013")

CRISIS_WINDOW_DAYS = 30      # FR32
LEAD_WINDOW_DAYS = (5, 15)   # FR32 early-warning window


def break_date(epoch: str) -> str:
    return EPOCH_BREAKS[epoch][0]


def provenance(epoch: str) -> str:
    return EPOCH_BREAKS[epoch][1]


def unresolved() -> tuple[str, ...]:
    """Epochs whose label is still explicitly provisional (SPEC OQ3/OQ13)."""
    return tuple(e for e, (_, note) in EPOCH_BREAKS.items()
                 if "PROVISIONAL" in note or "OQ" in note)
