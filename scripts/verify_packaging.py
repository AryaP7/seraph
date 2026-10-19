"""QA03 — build a wheel, install it into a FRESH environment, and check that
the canonical C12 console actually ships and renders from there.

An editable checkout proves nothing about a built distribution: the source tree
is on `sys.path` either way. This builds a real wheel, installs it into a
throwaway virtual environment, and renders the Streamlit app from
`site-packages` so the component path cannot resolve against the repository.

Needs `uv` on PATH. Writes `docs/evidence/PACKAGING-<date>.json`. Creates
nothing inside the repository except that evidence file.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

#: Every runtime asset the product cannot start without.
#:
#: O01: this tuple used to cover the console assets and `store/schema.sql`
#: only, so it passed a wheel that was missing seven other files. A verifier
#: that checks a subset reports success for a broken distribution, which is
#: worse than no verifier -- the audit's own probe found the gaps this script
#: was supposed to find.
REQUIRED = (
    # C12 console
    "seraph/dashboard/console_component/index.html",
    "seraph/dashboard/console_component/bridge.js",
    "seraph/dashboard/console_component/preview_pillars.js",
    "seraph/dashboard/console_component/three.r128.min.js",
    "seraph/dashboard/console_component/THREE-LICENSE.txt",
    "seraph/dashboard/assets/console.html",
    "seraph/dashboard/assets/THREE-LICENSE.txt",
    # C1 schema and migrations. A wheel without these installs an
    # application that cannot create the tables it reads.
    "seraph/store/schema.sql",
    "seraph/store/migrations/001_evaluation_identity.sql",
    "seraph/live/migrations/001_runtime.sql",
    # News curated registry. Without these `load_master_data()` returns an
    # empty registry and the globe has nothing to resolve a mention against.
    "seraph/news/curated/entities.csv",
    "seraph/news/curated/places.csv",
    "seraph/news/curated/assets.csv",
    "seraph/news/curated/exposure.csv",
    "seraph/news/curated/source_places.csv",
    # C2 tariff registry.
    "seraph/ingestion/tariff_events.curated.csv",
)

#: Scratch copies that must NOT be distributed.
FORBIDDEN_SUFFIXES = (".bak", ".broken")

CHECK_SCRIPT = '''
import json, os
from pathlib import Path
import seraph
root = Path(seraph.__file__).resolve().parent
component = root / "dashboard" / "console_component"
index = component / "index.html"
text = index.read_text(encoding="utf-8", errors="ignore") if index.exists() else ""
out = dict(
    installed_from=str(root),
    is_site_packages="site-packages" in str(root),
    component_files=sorted(p.name for p in component.iterdir()) if component.is_dir() else [],
    index_html_bytes=index.stat().st_size if index.exists() else 0,
    index_has_console_markup=all(m in text for m in
        ('id="stage"', 'id="roles"', 'data-view="console"', "bridge.js")),
    three_js_bytes=(component / "three.r128.min.js").stat().st_size
        if (component / "three.r128.min.js").exists() else 0,
    three_licence_present=(component / "THREE-LICENSE.txt").exists(),
    original_console_asset_present=(root / "dashboard" / "assets" / "console.html").exists(),
    schema_sql_present=(root / "store" / "schema.sql").exists(),
)

# O01 -- the two probes whose failure the audit recorded. Both run from the
# INSTALLED package, outside the checkout, so a source-tree copy cannot
# stand in for a shipped one.
#
# 1. Can the runtime store create its own schema? The saved probe got
#    `OperationalError: no such table: runtime_head`.
try:
    import tempfile
    from seraph.live.store import LiveStore
    with tempfile.TemporaryDirectory() as scratch:
        probe = LiveStore(Path(scratch) / "runtime.sqlite")
        out["live_head"] = probe.head().describe() if hasattr(
            probe.head(), "describe") else str(probe.head())
        out["live_store_error"] = None
except Exception as exc:                                    # noqa: BLE001
    out["live_head"] = None
    out["live_store_error"] = f"{type(exc).__name__}: {exc}"

# 2. Does the curated registry carry rows? The saved probe reported
#    entities 0, places 0, assets 0, edges 0 and `empty: True`.
try:
    from seraph.news.curated import missing_registry_files
    from seraph.news.registry import load_master_data
    master, report = load_master_data()
    out["curated"] = dict(
        entities=len(getattr(master, "entities", {})),
        places=len(getattr(master, "places", {})),
        assets=len(getattr(master, "assets", {})),
        edges=len(getattr(master, "edges", {})),
        empty=bool(report.get("empty")) if isinstance(report, dict) else None,
        files_missing=missing_registry_files())
    out["curated_error"] = None
except Exception as exc:                                    # noqa: BLE001
    out["curated"] = None
    out["curated_error"] = f"{type(exc).__name__}: {exc}"

# 3. Migration SQL must be readable from the installed package, not just
#    present as a file name in the archive.
try:
    from seraph.live.migrations import migration_files
    out["live_migrations"] = [p.name for p in migration_files()]
    out["live_migration_bytes"] = sum(p.stat().st_size for p in migration_files())
except Exception as exc:                                    # noqa: BLE001
    out["live_migrations"] = None
    out["live_migration_error"] = f"{type(exc).__name__}: {exc}"
import seraph.dashboard.prototype_app as app
declared = Path(getattr(app.console, "path", getattr(app.console, "_path", component)))
out["declared_component_path"] = str(declared)
out["declared_path_is_installed"] = str(declared).startswith(str(root))
store = os.environ.get("SERAPH_PROTOTYPE_STORE")
if store and Path(store).exists():
    from streamlit.testing.v1 import AppTest
    at = AppTest.from_file(str(root / "dashboard" / "prototype_app.py")).run(timeout=120)
    out["render_exception"] = None if not at.exception else str(at.exception[0].value)
    out["run_selected"] = at.selectbox[0].value[:12] if at.selectbox else None
    out["date_options"] = len(at.selectbox[1].options) if len(at.selectbox) > 1 else 0
else:
    out["render_exception"] = "no persisted run supplied; render not attempted"
print("@@JSON@@" + json.dumps(out))
'''


def main() -> int:
    if shutil.which("uv") is None:
        print("uv is not on PATH; cannot build or provision a fresh environment")
        return 2
    store = os.environ.get("SERAPH_PROTOTYPE_STORE")
    record: dict = {"generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "store_used_for_render": store}

    with tempfile.TemporaryDirectory() as temp:
        area = Path(temp)
        dist, env = area / "dist", area / "env"

        build = subprocess.run(["uv", "build", "--wheel", "--out-dir", str(dist)],
                               cwd=ROOT, capture_output=True, text=True)
        if build.returncode != 0:
            print(build.stderr[-2000:])
            return 1
        wheel = next(dist.glob("*.whl"))
        names = zipfile.ZipFile(wheel).namelist()
        record["wheel"] = dict(
            name=wheel.name, entries=len(names),
            payload=sorted(n for n in names
                           if not n.endswith(".py") and ".dist-info" not in n),
            missing_required=[r for r in REQUIRED if r not in names],
            forbidden_present=[n for n in names if n.endswith(FORBIDDEN_SUFFIXES)])

        subprocess.run(["uv", "venv", "--python", "3.12", str(env)],
                       capture_output=True, text=True, check=True)
        python = env / "Scripts" / "python.exe"
        if not python.exists():
            python = env / "bin" / "python"
        install = subprocess.run(
            ["uv", "pip", "install", "--python", str(python), str(wheel)],
            capture_output=True, text=True)
        record["install_ok"] = install.returncode == 0
        if install.returncode != 0:
            record["install_error"] = install.stderr[-2000:]
            _write(record)
            return 1

        script = area / "check.py"
        script.write_text(CHECK_SCRIPT, encoding="utf-8")
        # Run from OUTSIDE the repository so nothing resolves against source.
        proc = subprocess.run([str(python), "-I", str(script)], cwd=area,
                              capture_output=True, text=True,
                              env={**os.environ, "PYTHONPATH": ""})
        marker = [line for line in proc.stdout.splitlines() if line.startswith("@@JSON@@")]
        if not marker:
            record["fresh_environment_error"] = (proc.stdout[-1500:] + proc.stderr[-1500:])
            _write(record)
            return 1
        record["fresh_environment"] = json.loads(marker[0][len("@@JSON@@"):])

    wheel_ok = (not record["wheel"]["missing_required"]
                and not record["wheel"]["forbidden_present"])
    fresh = record["fresh_environment"]
    render_ok = fresh["render_exception"] is None
    # O01's two acceptance conditions, from the installed package.
    schema_ok = fresh.get("live_store_error") is None
    curated = fresh.get("curated") or {}
    curated_ok = bool(
        fresh.get("curated_error") is None
        and not curated.get("files_missing")
        and all(curated.get(k, 0) > 0
                for k in ("entities", "places", "assets", "edges")))
    migrations_ok = bool(fresh.get("live_migrations")
                         and fresh.get("live_migration_bytes", 0) > 0)
    record["verdict"] = dict(
        wheel_carries_required_assets=wheel_ok,
        installs_outside_the_checkout=fresh["is_site_packages"],
        component_resolves_to_the_installed_package=fresh["declared_path_is_installed"],
        canonical_console_renders=render_ok,
        runtime_schema_creates_from_installed_package=schema_ok,
        curated_registry_carries_rows=curated_ok,
        migration_sql_readable_from_installed_package=migrations_ok,
        passed=bool(wheel_ok and fresh["is_site_packages"]
                    and fresh["declared_path_is_installed"] and render_ok
                    and schema_ok and curated_ok and migrations_ok))
    _write(record)
    print(json.dumps(record["verdict"], indent=2))
    return 0 if record["verdict"]["passed"] else 1


def _write(record: dict) -> None:
    target = ROOT / "docs" / "evidence" / f"PACKAGING-{time.strftime('%Y-%m-%d')}.json"
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"evidence: {target}")


if __name__ == "__main__":
    sys.exit(main())
