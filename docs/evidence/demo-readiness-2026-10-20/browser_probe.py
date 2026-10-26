"""C12 audit: browser traversal against copied stores, acquisition disabled."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from probe import ROOT, OUT, backup
from audit_console_browser import CDP, await_http, free_port
from websockets.sync.client import connect


def main():
    report, processes = {}, []
    with tempfile.TemporaryDirectory(prefix="seraph-demo-browser-") as tmp:
        scratch = Path(tmp)
        env = dict(os.environ, SERAPH_NEWS_WORKER="0",
                   SERAPH_WORKSPACE_DIR=str(scratch / "workspace"),
                   OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1",
                   PYTHONIOENCODING="utf-8")
        for name, variable in (
            ("seraph.sqlite", "SERAPH_PROTOTYPE_STORE"),
            ("live.sqlite", "SERAPH_LIVE_STORE"),
            ("news-intelligence-pilot.sqlite", "SERAPH_NEWS_STORE"),
            ("jobs.sqlite", "SERAPH_JOB_STORE"),
        ):
            backup(ROOT / "prototype_runs" / name, scratch / name)
            env[variable] = str(scratch / name)
        app_port, debug_port = free_port(), free_port()
        edge = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft/Edge/Application/msedge.exe"
        with (OUT / "browser.log").open("w", encoding="utf-8") as log:
            try:
                processes.append(subprocess.Popen([
                    sys.executable, "-m", "streamlit", "run",
                    str(ROOT / "seraph/dashboard/prototype_app.py"),
                    "--server.address=127.0.0.1", f"--server.port={app_port}",
                    "--server.headless=true", "--browser.gatherUsageStats=false"],
                    cwd=ROOT, env=env, stdout=log, stderr=log))
                await_http(f"http://127.0.0.1:{app_port}/_stcore/health")
                processes.append(subprocess.Popen([
                    str(edge), "--headless=new", "--no-first-run", "--no-default-browser-check",
                    "--disable-background-networking", "--enable-unsafe-swiftshader",
                    "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
                    f"--user-data-dir={scratch / 'edge'}",
                    f"--remote-debugging-port={debug_port}",
                    "--window-size=1600,1200", "about:blank"],
                    stdout=log, stderr=log))
                targets = json.loads(await_http(f"http://127.0.0.1:{debug_port}/json/list"))
                page = next(t for t in targets if t["type"] == "page")
                with connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
                    cdp = CDP(ws)
                    cdp.call("Page.enable")
                    cdp.call("Runtime.enable")
                    cdp.call("Page.addScriptToEvaluateOnNewDocument", source="""
                        window.__auditErrors = [];
                        addEventListener('error', e => __auditErrors.push({
                          message:e.message, filename:e.filename, line:e.lineno,
                          stack:e.error?.stack}));
                        addEventListener('unhandledrejection', e =>
                          __auditErrors.push({rejection:String(e.reason)}));
                    """)
                    cdp.call("Page.navigate", url=f"http://127.0.0.1:{app_port}")
                    context = None
                    deadline = time.monotonic() + 35
                    while context is None and time.monotonic() < deadline:
                        report["outer_page"] = cdp.evaluate("document.body.innerText")
                        cdp.evaluate("[...document.querySelectorAll('iframe')].at(-1)?.scrollIntoView()")
                        for candidate in list(cdp.contexts):
                            try:
                                if cdp.evaluate("Boolean(document.querySelector('#roles button') && document.getElementById('preview-banner')?.textContent.includes('RUN '))", candidate):
                                    context = candidate
                                    break
                            except RuntimeError:
                                pass
                        if context is None:
                            time.sleep(.5)
                    if context is None:
                        report["contexts"] = list(cdp.contexts.values())
                        report["javascript_errors"] = {}
                        for candidate in list(cdp.contexts):
                            try:
                                report["javascript_errors"][candidate] = cdp.evaluate(
                                    "window.__auditErrors || []", candidate)
                            except RuntimeError:
                                pass
                        report["streamlit_exceptions"] = cdp.evaluate(
                            "[...document.querySelectorAll('[data-testid=stException]')].map(e=>e.innerText)")
                        shot = cdp.call("Page.captureScreenshot", format="png")
                        (OUT / "browser.png").write_bytes(base64.b64decode(shot["data"]))
                        raise RuntimeError("Canonical component did not bind a run within the probe timeout")
                    report["outer_page"] = cdp.evaluate("document.body.innerText")
                    report["streamlit_exceptions"] = cdp.evaluate(
                        "[...document.querySelectorAll('[data-testid=stException]')].map(e=>e.innerText)")
                    report["roles"] = {}
                    for role in ("retail", "institutional", "regulator"):
                        cdp.evaluate(
                            f"document.querySelector('#roles button[data-role={role}]').click()", context)
                        time.sleep(3)
                        report["roles"][role] = cdp.evaluate("""({
                            selected: document.querySelector('#roles button.on')?.dataset.role,
                            banner: document.getElementById('preview-banner')?.textContent,
                            news: document.getElementById('role-news-home')?.textContent,
                            status: document.getElementById('req-status-global')?.textContent
                        })""", context)
                    report["navigation"] = []
                    routes = cdp.evaluate(
                        "[...document.querySelectorAll('nav a[data-view]')].map(e=>e.dataset.view)", context)
                    for route in routes:
                        cdp.evaluate(
                            "document.querySelector(" + json.dumps(f'nav a[data-view="{route}"]') + ").click()", context)
                        time.sleep(.6)
                        report["navigation"].append(cdp.evaluate("""({
                            selected: document.querySelector('nav a.on')?.dataset.view,
                            visible: [...document.querySelectorAll('.vw.show')].map(e=>e.id),
                            text: [...document.querySelectorAll('.vw.show')].map(e=>e.innerText).join('\\n').slice(0,5000)
                        })""", context))
                    report["streamlit_exceptions_after"] = cdp.evaluate(
                        "[...document.querySelectorAll('[data-testid=stException]')].map(e=>e.innerText)")
                    shot = cdp.call("Page.captureScreenshot", format="png")
                    (OUT / "browser.png").write_bytes(base64.b64decode(shot["data"]))
                    report["completed"] = True
            except Exception as exc:
                report["error"] = f"{type(exc).__name__}: {exc}"
            finally:
                for process in reversed(processes):
                    if process.poll() is None:
                        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                       stdout=log, stderr=log, check=False)
                report["owned_processes_stopped"] = all(p.wait(timeout=15) is not None for p in processes)
                (OUT / "browser.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("outer_page", "roles", "navigation")}))


if __name__ == "__main__":
    main()
