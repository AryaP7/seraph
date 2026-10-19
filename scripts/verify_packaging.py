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

#: Runtime assets the canonical console cannot start without.
REQUIRED = (
    "seraph/dashboard/console_component/index.html",
    "seraph/dashboard/console_component/bridge.js",
    "seraph/dashboard/console_component/preview_pillars.js",
    "seraph/dashboard/console_component/three.r128.min.js",
    "seraph/dashboard/console_component/THREE-LICENSE.txt",
    "seraph/dashboard/assets/console.html",
    "seraph/dashboard/assets/THREE-LICENSE.txt",
    "seraph/store/schema.sql",
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
    record["verdict"] = dict(
        wheel_carries_required_assets=wheel_ok,
        installs_outside_the_checkout=fresh["is_site_packages"],
        component_resolves_to_the_installed_package=fresh["declared_path_is_installed"],
        canonical_console_renders=render_ok,
        passed=bool(wheel_ok and fresh["is_site_packages"]
                    and fresh["declared_path_is_installed"] and render_ok))
    _write(record)
    print(json.dumps(record["verdict"], indent=2))
    return 0 if record["verdict"]["passed"] else 1


def _write(record: dict) -> None:
    target = ROOT / "docs" / "evidence" / f"PACKAGING-{time.strftime('%Y-%m-%d')}.json"
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"evidence: {target}")


if __name__ == "__main__":
    sys.exit(main())
