# C2 — Ingestion Layer (FR1): Kite Connect intraday client.
"""Checkpointed, resumable 5-minute bar ingestion (DATA-ACQUISITION §1).

Credentials come from KITE_API_KEY / KITE_API_SECRET (environment or the
repo-root .env, which is gitignored and never committed). The daily access
token — Kite tokens expire every morning — is cached in
`kite_credentials.tokens.json` (also gitignored). The api_secret is used only
to compute the session checksum and is never logged.

Compliance (SPEC §7 item 14): Kite-derived data may not be publicly
redistributed; anything built on these bars stays local/demo-only.

Interactive login is the user's own action (scripts/kite_login.py) — this
module never sees a Zerodha password.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from seraph.shared_types import IST, IntradayBar, ist_timestamp

API_ROOT = "https://api.kite.trade"
LOGIN_ROOT = "https://kite.zerodha.com/connect/login"

_REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = _REPO_ROOT / ".env"
TOKEN_CACHE = _REPO_ROOT / "kite_credentials.tokens.json"

#: Max days returnable per request, per interval (DATA-ACQUISITION §1).
INTERVAL_MAX_DAYS = {
    "minute": 60, "3minute": 100, "5minute": 100, "10minute": 100,
    "15minute": 200, "30minute": 200, "60minute": 400, "day": 2000,
}
_REQUEST_GAP_S = 0.35   # ~3 req/s — confirmed conservative for the historical endpoint


def _load_env_file() -> None:
    """Best-effort KEY=VALUE loader for the repo-root .env (no dependency)."""
    if not ENV_FILE.exists():
        return
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


@dataclass(frozen=True)
class KiteCredentials:
    api_key: str
    api_secret: str

    @classmethod
    def from_env(cls) -> "KiteCredentials":
        _load_env_file()
        key = os.environ.get("KITE_API_KEY", "")
        secret = os.environ.get("KITE_API_SECRET", "")
        if not key or not secret:
            raise RuntimeError(
                "KITE_API_KEY / KITE_API_SECRET not set — add them to the "
                "repo-root .env (gitignored) or the environment"
            )
        return cls(api_key=key, api_secret=secret)


def login_url(creds: KiteCredentials) -> str:
    return f"{LOGIN_ROOT}?v=3&api_key={creds.api_key}"


def exchange_request_token(creds: KiteCredentials, request_token: str) -> dict:
    """POST /session/token with checksum = sha256(key + request_token + secret).
    Caches the daily access token; returns the session payload (minus secret)."""
    checksum = hashlib.sha256(
        (creds.api_key + request_token + creds.api_secret).encode("utf-8")
    ).hexdigest()
    r = requests.post(
        f"{API_ROOT}/session/token",
        data={"api_key": creds.api_key, "request_token": request_token, "checksum": checksum},
        headers={"X-Kite-Version": "3"},
        timeout=30,
    )
    r.raise_for_status()
    data = r.json()["data"]
    TOKEN_CACHE.write_text(json.dumps({
        "access_token": data["access_token"],
        "public_token": data.get("public_token"),
        "user_id": data.get("user_id"),
        "login_time": data.get("login_time"),
    }, indent=2), encoding="utf-8")
    return data


def cached_access_token() -> str:
    if not TOKEN_CACHE.exists():
        raise RuntimeError(
            "no cached Kite access token — run `python scripts/kite_login.py` "
            "and log in (tokens expire daily)"
        )
    return json.loads(TOKEN_CACHE.read_text(encoding="utf-8"))["access_token"]


class KiteClient:
    """Thin REST client over the endpoints C2 needs. Retries 429/5xx with
    backoff; raises on auth errors so a dead daily token surfaces loudly."""

    def __init__(self, creds: KiteCredentials | None = None, access_token: str | None = None):
        self._creds = creds or KiteCredentials.from_env()
        token = access_token or cached_access_token()
        self._session = requests.Session()
        self._session.headers.update({
            "X-Kite-Version": "3",
            "Authorization": f"token {self._creds.api_key}:{token}",
        })
        self._instruments: dict[str, int] | None = None

    # ------------------------------------------------------------ endpoints

    def _get(self, path: str, params: dict | None = None) -> dict | str:
        for attempt in range(6):
            r = self._session.get(f"{API_ROOT}{path}", params=params, timeout=60)
            if r.status_code in (429, 502, 503, 504):
                time.sleep(1.5 * (attempt + 1))
                continue
            if r.status_code == 403:
                # Kite returns 403 for both a dead token and a plan without
                # historical access; the body distinguishes them, so say which.
                body = r.text[:200]
                if "TokenException" in body or "access_token" in body:
                    raise RuntimeError(
                        "Kite access token has expired — re-run "
                        "`python scripts/kite_login.py`. Tokens are invalidated "
                        "daily at ~06:00 IST regardless of when they were issued, "
                        "so a token minted shortly before 06:00 lives only minutes. "
                        "Long backfills are best started just after 06:00 IST."
                    )
                raise RuntimeError(
                    f"Kite returned 403 and the body does not indicate a token "
                    f"problem — check that the Connect plan includes historical "
                    f"data: {body}"
                )
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            return r.json() if "json" in ctype else r.text
        raise RuntimeError(f"Kite kept rate-limiting {path} after 6 attempts")

    def instruments_nse(self) -> dict[str, int]:
        """tradingsymbol → instrument_token for NSE equities (cached per client)."""
        if self._instruments is None:
            raw = self._get("/instruments/NSE")
            table: dict[str, int] = {}
            for row in csv.DictReader(io.StringIO(raw)):
                if row.get("instrument_type") == "EQ" and row.get("segment") == "NSE":
                    table[row["tradingsymbol"]] = int(row["instrument_token"])
            self._instruments = table
        return self._instruments

    def historical(
        self, instrument_token: int, interval: str, frm: datetime, to: datetime
    ) -> list[list]:
        """Raw candles [[ts, o, h, l, c, volume], ...] for one window (caller
        keeps windows within INTERVAL_MAX_DAYS)."""
        fmt = "%Y-%m-%d %H:%M:%S"
        data = self._get(
            f"/instruments/historical/{instrument_token}/{interval}",
            params={"from": frm.strftime(fmt), "to": to.strftime(fmt)},
        )
        time.sleep(_REQUEST_GAP_S)
        return data["data"]["candles"]

    # ------------------------------------------------------------- workflows

    def iter_candles(
        self, symbol: str, interval: str, frm: datetime, to: datetime
    ):
        """Yield (window_start, candles) chunked by the per-interval cap —
        the resumable unit: re-running any window is idempotent via C1."""
        token = self.instruments_nse().get(symbol)
        if token is None:
            raise KeyError(f"{symbol!r} not found among NSE EQ instruments")
        step = timedelta(days=INTERVAL_MAX_DAYS[interval])
        cursor = frm
        while cursor < to:
            window_end = min(cursor + step, to)
            yield cursor, self.historical(token, interval, cursor, window_end)
            cursor = window_end

    def probe_earliest(
        self, symbol: str, interval: str = "5minute", search_from: date = date(2014, 1, 1)
    ) -> str | None:
        """First available candle timestamp — the roadmap's 'ten-minute test
        that pins your actual Pillar-1 start date'. Walks forward in
        max-window steps until the first non-empty response."""
        frm = datetime(search_from.year, search_from.month, search_from.day, tzinfo=IST)
        horizon = datetime.now(IST)
        for _, candles in self.iter_candles(symbol, interval, frm, horizon):
            if candles:
                return ist_timestamp(datetime.fromisoformat(candles[0][0]))
        return None


#: Volumes above this are vendor data errors, not real trades — NSE's busiest
#: single-stock 5-minute bars are ~1e8 shares. Bars beyond it are dropped rather
#: than allowed to abort a multi-hour backfill (a bigint overflow on one bad row
#: killed a run at 11M rows before this guard existed).
MAX_PLAUSIBLE_BAR_VOLUME = 10**12


def candles_to_bars(
    symbol: str, candles: list[list]
) -> tuple[tuple[IntradayBar, ...], int]:
    """Map raw candles to E1 rows, dropping unusable ones.

    signed_volume / log_return / jump fields are C4's to fill (FR5/FR50) — they
    land at their schema defaults here. Returns `(bars, n_rejected)` so the
    caller can report the rejection rate instead of silently losing bars: a
    vendor row with a non-finite price or an out-of-range volume is a data
    defect worth counting, not worth crashing on.
    """
    bars: list[IntradayBar] = []
    rejected = 0
    for c in candles:
        try:
            o, h, low_, cl = float(c[1]), float(c[2]), float(c[3]), float(c[4])
            vol = int(c[5])
        except (TypeError, ValueError, OverflowError):
            rejected += 1
            continue
        if not all(math.isfinite(x) for x in (o, h, low_, cl)):
            rejected += 1
            continue
        if vol < 0 or vol > MAX_PLAUSIBLE_BAR_VOLUME:
            rejected += 1
            continue
        bars.append(IntradayBar(
            symbol=symbol,
            ts=ist_timestamp(datetime.fromisoformat(c[0])),
            open=o, high=h, low=low_, close=cl, volume=vol,
        ))
    return tuple(bars), rejected


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Kite client utilities (C2).")
    parser.add_argument("--probe", nargs="+", metavar="SYMBOL",
                        help="print the earliest available 5-min candle per symbol")
    args = parser.parse_args(argv)
    if args.probe:
        client = KiteClient()
        for symbol in args.probe:
            try:
                earliest = client.probe_earliest(symbol)
            except KeyError as e:
                print(f"{symbol:>12}: {e}")
                continue
            print(f"{symbol:>12}: earliest 5-min candle {earliest or 'NONE FOUND'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
