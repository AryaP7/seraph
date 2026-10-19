# Live runtime — migration assets (O01)
"""Holds `001_runtime.sql`, the runtime store's schema.

This file exists so that `[tool.setuptools.packages.find]` sees this
directory as a package at all. Without it the directory is not found,
`package-data` has nothing to attach to, and the SQL is silently dropped
from a built wheel -- which is exactly what the audit's wheel probe caught:

    OperationalError: no such table: runtime_head

A `package-data` glob on the PARENT (`"seraph.live" = ["*.sql"]`) would not
have helped either: those globs do not recurse into subdirectories.
"""
from pathlib import Path

#: Where the ordered `NNN_*.sql` files live, in a source tree or installed.
MIGRATIONS_DIR = Path(__file__).resolve().parent


def migration_files() -> "list[Path]":
    """Every shipped migration, in filename order."""
    return sorted(MIGRATIONS_DIR.glob("[0-9][0-9][0-9]_*.sql"))
