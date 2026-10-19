"""C12 audit: exercise actual role buttons in Edge against an isolated store copy.

Requires the existing Windows Python environment, websockets and Microsoft Edge.
No portfolio/action commands are sent. Original stores and evidence stay intact.
"""
from __future__ import annotations

import base64
from contextlib import closing
import json
import os
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

from websockets.sync.client import connect

ROOT = Path(__file__).resolve().parents[1]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def await_http(url, timeout=40):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urlopen(url, timeout=2) as response:
                return response.read()
        except OSError:
            time.sleep(0.25)
    raise RuntimeError(f"Local service did not start: {url}")


class CDP:
    def __init__(self, websocket):
        self.ws = websocket
        self.seq = 0
        self.contexts = {}

    def call(self, method, **params):
        self.seq += 1
        request_id = self.seq
        self.ws.send(json.dumps(dict(id=request_id, method=method, params=params)))
        while True:
            message = json.loads(self.ws.recv(timeout=20))
            if message.get("method") == "Runtime.executionContextCreated":
                context = message["params"]["context"]
                self.contexts[context["id"]] = context
            if message.get("method") == "Runtime.executionContextDestroyed":
                self.contexts.pop(message["params"]["executionContextId"], None)
            if message.get("method") == "Runtime.executionContextsCleared":
                self.contexts.clear()
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(str(message["error"]))
                return message.get("result", {})

    def evaluate(self, expression, context=None):
        params = dict(expression=expression, returnByValue=True)
        if context is not None:
            params["contextId"] = context
        result = self.call("Runtime.evaluate", **params)
        if "exceptionDetails" in result:
            raise RuntimeError(str(result["exceptionDetails"]))
        return result.get("result", {}).get("value")

    def component(self):
        for _ in range(100):
            self.evaluate("document.readyState")
            for context in list(self.contexts):
                try:
                    if self.evaluate("Boolean(document.getElementById('roles') && document.getElementById('preview-banner')?.textContent.includes('RUN '))", context):
                        return context
                except RuntimeError:
                    pass
            time.sleep(0.2)
        raise RuntimeError("Canonical component did not render a run")


SNAPSHOT = """JSON.parse(JSON.stringify({
 role: document.querySelector('#roles button.on')?.dataset.role,
 mainVisible: getComputedStyle(document.querySelector('main')).display !== 'none',
 visibleViews: [...document.querySelectorAll('.vw.show')].map(n=>n.id),
 extraTitle: document.getElementById('extra-title')?.textContent,
 tools: [...document.querySelectorAll('#extra-content button')].map(n=>n.textContent),
 status: document.getElementById('req-status')?.textContent,
 banner: document.getElementById('preview-banner')?.textContent
}))"""


def main():
    out = (Path(sys.argv[1]) if len(sys.argv) > 1 else
           ROOT / "docs/evidence/INDEPENDENT-BROWSER-2026-10-16.json")
    if out.exists():
        raise SystemExit("Refusing to overwrite prior browser evidence")
    edge = Path(os.environ["ProgramFiles(x86)"]) / "Microsoft/Edge/Application/msedge.exe"
    app_port, debug_port = free_port(), free_port()
    processes = []
    with tempfile.TemporaryDirectory(prefix="seraph-browser-audit-") as tmp:
        tmp = Path(tmp)
        copied = tmp / "runs.sqlite"
        source = ROOT / "prototype_runs/seraph.sqlite"
        with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src:
            with closing(sqlite3.connect(copied)) as dest:
                src.backup(dest)
        env = dict(os.environ, SERAPH_PROTOTYPE_STORE=str(copied),
                   OPENBLAS_NUM_THREADS="1", OMP_NUM_THREADS="1")
        with (tmp / "app.log").open("w") as log:
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
                    f"--user-data-dir={tmp / 'edge'}", f"--remote-debugging-port={debug_port}",
                    "--window-size=1600,1200", "about:blank"], stdout=log, stderr=log))
                targets = json.loads(await_http(f"http://127.0.0.1:{debug_port}/json/list"))
                page = next(t for t in targets if t["type"] == "page")
                with connect(page["webSocketDebuggerUrl"], max_size=20_000_000) as ws:
                    cdp = CDP(ws)
                    cdp.call("Page.enable")
                    cdp.call("Runtime.enable")
                    cdp.call("Page.navigate", url=f"http://127.0.0.1:{app_port}")
                    context = cdp.component()
                    observations = {"initial": cdp.evaluate(SNAPSHOT, context)}
                    for role in ("institutional", "regulator", "retail"):
                        cdp.evaluate(f"document.querySelector('#roles button[data-role={role}]').click()", context)
                        for _ in range(50):
                            time.sleep(0.2)
                            state = cdp.evaluate(SNAPSHOT, context)
                            if state["role"] == role:
                                break
                        observations[f"after_{role}_click"] = state
                    cdp.evaluate("document.querySelector('#roles button[data-role=retail]').click()", context)
                    time.sleep(1)
                    cdp.evaluate("document.querySelector('nav a[data-view=tools]').click()", context)
                    time.sleep(16)
                    observations["same_role_timeout_in_tools"] = cdp.evaluate(SNAPSHOT, context)
                    cdp.evaluate("document.getElementById('req-cancel')?.click()", context)
                    cdp.evaluate("document.querySelector('#roles button[data-role=regulator]').click()", context)
                    for _ in range(50):
                        time.sleep(0.2)
                        state = cdp.evaluate(SNAPSHOT, context)
                        if state["role"] == "regulator":
                            break
                    observations["regulator_tools"] = state
                    screenshot = cdp.call("Page.captureScreenshot", format="png")
                    image_path = out.with_suffix(".png")
                    image_path.write_bytes(base64.b64decode(screenshot["data"]))
                    out.write_text(json.dumps(observations, indent=2) + "\n", encoding="utf-8")
                    print(json.dumps(observations, indent=2))
            finally:
                for process in reversed(processes):
                    # The Windows venv executable may launch a child interpreter.
                    # Stop only this audit's process trees, including that child.
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                   stdout=log, stderr=log, check=False)
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        process.kill()
                # Edge subprocesses may briefly retain their isolated profile.
                time.sleep(1)


if __name__ == "__main__":
    main()
