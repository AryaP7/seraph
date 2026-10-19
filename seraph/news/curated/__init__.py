# News — curated registry assets (O01)
"""Holds the five curated registry CSVs the news registry loads.

Like `seraph/live/migrations/__init__.py`, this exists so setuptools finds
the directory as a package. Without it the CSVs never entered a wheel, and
`load_master_data()` in a fresh install reported

    entities 0, places 0, assets 0, edges 0, source_places 0, empty True

with the honest-but-misleading reason "the curated registries ship empty.
Curate seraph/news/curated/*.csv" -- advice the operator could not act on,
because the files existed in the source tree and had simply not been
distributed.
"""
from pathlib import Path

#: Where the curated CSVs live, in a source tree or installed.
CURATED_DIR = Path(__file__).resolve().parent

#: Every registry file `load_master_data()` expects. Named rather than
#: globbed so a MISSING file is an error instead of a silently smaller
#: registry.
REGISTRY_FILES = ("entities.csv", "places.csv", "assets.csv",
                  "exposure.csv", "source_places.csv")


def registry_paths() -> "dict[str, Path]":
    """Each registry file and where it resolved to."""
    return {name: CURATED_DIR / name for name in REGISTRY_FILES}


def missing_registry_files() -> "list[str]":
    """Registry files that did not ship. Empty is the healthy answer."""
    return [name for name, path in registry_paths().items() if not path.exists()]
