# Orchestration — the repository-scripts capability boundary (O02)
"""Import helpers that live in `scripts/`, or say precisely why you cannot.

`seraph/orchestration/original_execution.py` needs four functions that are
defined in research scripts: `load_stream` and `tod_profile` from
`scripts/write_hawkes_production.py`, and `build_row` and `universe_for`
from `scripts/build_observations.py`.

Those scripts are **not** part of the distribution. A built wheel ships
`seraph*` and `fixtures*` only, so in a fresh install `import scripts` fails
with a bare `ModuleNotFoundError: No module named 'scripts'` from inside a
function three frames down -- which tells an operator nothing about what is
actually missing or what to do about it.

Why the functions are not simply moved here
-------------------------------------------
They are the implementation of two research scripts with saved evidence
under `docs/evidence/`. Relocating them would change which module produced a
recorded result, and `write_hawkes_production.py` in particular is pinned by
`verify_hawkes_production.py` and by the E6 production backfill logs. The
audit asked for "supported distribution handling. Fail clearly for optional
features", not for a refactor of research code under a packaging ticket.

So this module makes the dependency explicit and its absence actionable. The
capability is available from a source checkout and absent from a wheel, and
both states are reported honestly rather than discovered as a stack trace.
"""
from __future__ import annotations

import importlib
import sys
from pathlib import Path


class ResearchScriptsUnavailable(RuntimeError):
    """The `scripts/` tree is not importable, and this path needs it."""


#: Repository root, when this package is being used from a source checkout.
#: In an installed wheel this points inside `site-packages` and the
#: `scripts/` probe below simply fails, which is the correct answer.
_CANDIDATE_ROOT = Path(__file__).resolve().parents[2]


def scripts_root() -> "Path | None":
    """The importable `scripts/` directory, or `None`."""
    candidate = _CANDIDATE_ROOT / "scripts"
    marker = candidate / "build_observations.py"
    return _CANDIDATE_ROOT if marker.is_file() else None


def available() -> bool:
    """Is the fresh-source-execution path usable in this installation?"""
    return scripts_root() is not None


def describe() -> dict:
    """Capability report, for `--status` output and operator diagnosis."""
    root = scripts_root()
    return dict(
        capability="fresh original C4/C5/C6/C7 execution from a read-only source",
        available=root is not None,
        scripts_root=str(root / "scripts") if root else None,
        reason=(None if root else
                "this installation does not ship the research `scripts/` "
                "tree. Fresh source execution is a source-checkout "
                "capability: run it from a clone of the repository, or use "
                "the verified archive adapter instead, which is packaged. "
                "Nothing is estimated in its absence."),
    )


def load(module: str, *names: str):
    """Import `names` from `scripts.<module>`, or raise with instructions.

    Puts the repository root on `sys.path` only when the marker file is
    actually there, so this cannot silently pick up an unrelated `scripts`
    package that happens to be importable.
    """
    root = scripts_root()
    if root is None:
        raise ResearchScriptsUnavailable(describe()["reason"])
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        imported = importlib.import_module(f"scripts.{module}")
    except ImportError as exc:                              # pragma: no cover
        raise ResearchScriptsUnavailable(
            f"`scripts/{module}.py` is present at {root} but could not be "
            f"imported ({exc}). Its own dependencies may be missing: the "
            f"research path needs the `research` extra "
            f"(`pip install -e '.[research]'`)") from exc
    missing = [n for n in names if not hasattr(imported, n)]
    if missing:
        raise ResearchScriptsUnavailable(
            f"`scripts/{module}.py` does not define {', '.join(missing)}. "
            f"This checkout's research scripts and "
            f"`seraph/orchestration/original_execution.py` have drifted apart")
    return tuple(getattr(imported, n) for n in names)
