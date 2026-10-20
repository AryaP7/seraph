# Operations — where the daily market-job status lives, and how to read it.
"""One definition of the status file's location, owned by the package.

`scripts/run_market_jobs.py` writes it and the console reads it. When the
console read it by importing that script, the console worked in a source
checkout and failed in an installed wheel, which has no `scripts/` directory
-- `verify_packaging.py` installs one and renders the console in it, and the
render died on `No module named 'run_market_jobs'`.

The same mistake was about to ship for the prediction state, which matters
more: a risk warning the installed application cannot display is not a
warning. Both now read through their package.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULT_RELATIVE = Path("prototype_runs") / "market-jobs-status.json"


def status_path() -> Path:
    """`SERAPH_MARKET_JOBS_STATUS` wins; otherwise beside the package root.

    Absolute on purpose: a relative default resolves against the caller's
    working directory, so the writer and the reader would disagree about
    where the file is depending on where each was started from.
    """
    override = os.environ.get("SERAPH_MARKET_JOBS_STATUS")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / DEFAULT_RELATIVE


def read_status() -> dict:
    """What the last run achieved. Absence and damage are reported, not raised.

    A console that raised on a missing or truncated status file would take
    every other surface on the page down with it.
    """
    path = status_path()
    if not path.is_file():
        return dict(ran=False, path=str(path),
                    note=("the market jobs have not run in this "
                          "installation. The launcher runs them; "
                          "`python scripts/run_market_jobs.py` runs them by "
                          "hand"))
    try:
        body = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return dict(ran=False, path=str(path),
                    note=f"status file unreadable: {exc}")
    if not isinstance(body, dict):
        return dict(ran=False, path=str(path),
                    note="the status file does not contain an object")
    return dict(ran=True, path=str(path), **body)
