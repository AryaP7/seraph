#!/usr/bin/env python3
# C2 — Ingestion Layer: one-shot Kite Connect login helper.
"""Listens on http://localhost:3000/zerodha/callback (the app's registered
redirect URL), prints the Kite login URL for the HUMAN to open and sign in —
this script never sees the Zerodha password — then exchanges the returned
request_token for the daily access token and caches it for KiteClient.

Run: python scripts/kite_login.py     (re-run each morning; tokens expire daily)
"""
from __future__ import annotations

import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from seraph.ingestion.kite_client import (  # noqa: E402
    KiteCredentials,
    exchange_request_token,
    login_url,
)

_DONE_HTML = (b"<html><body style='font-family:sans-serif'>"
              b"<h2>SERAPH: Kite login captured.</h2>"
              b"<p>You can close this tab and return to the terminal.</p>"
              b"</body></html>")


class _Callback(BaseHTTPRequestHandler):
    request_token: str | None = None

    def do_GET(self):  # noqa: N802 — http.server API
        parsed = urlparse(self.path)
        if parsed.path != "/zerodha/callback":
            self.send_response(404)
            self.end_headers()
            return
        token = parse_qs(parsed.query).get("request_token", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(_DONE_HTML)
        _Callback.request_token = token

    def log_message(self, *args):  # silence per-request stderr noise
        pass


def main() -> int:
    creds = KiteCredentials.from_env()
    url = login_url(creds)
    print(f"[kite-login] open and sign in:\n  {url}", flush=True)
    try:
        webbrowser.open(url)
    except Exception:
        pass

    server = HTTPServer(("127.0.0.1", 3000), _Callback)
    server.timeout = 600
    print("[kite-login] waiting on http://localhost:3000/zerodha/callback ...", flush=True)
    while _Callback.request_token is None:
        server.handle_request()

    data = exchange_request_token(creds, _Callback.request_token)
    print(f"[kite-login] access token cached for user {data.get('user_id')} "
          f"(login_time {data.get('login_time')}) -> kite_credentials.tokens.json",
          flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
