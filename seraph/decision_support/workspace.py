# C11 — Owned workspace state (PRODUCT-CONTRACTS §6; AUTH04, PORT01, PORT02)
"""Durable, identity-scoped portfolios, holdings history, watchlists and
preferences.

What this adds over the existing C11 portfolio path
---------------------------------------------------
`portfolio.py` is a pure function over caller-supplied holdings and stays that
way. `portfolio_io.py` reads E11, which has **no time dimension** — its key is
`(user_id, symbol)`, so a past-date view is impossible there and the payload
honestly says `holdingsAsOf: "current"`. This module adds the dimension E11
lacks: an append-only series of **holdings snapshots**, each with its own
`effective_at`, so a historical view can use the holdings that actually
existed then.

Rule 2 of the contract, enforced here rather than described: `holdings_as_of`
returns the latest snapshot at or before the asked-for time **and says which
one it used**. When there is no snapshot that old it returns nothing and says
so — it never silently hands back today's holdings under yesterday's date.

Import
------
An import is a three-step affair on purpose: `preview_import` parses and
classifies every row without writing anything, the caller sees what would be
accepted and what would be rejected and why, and `commit_import` then writes a
snapshot. The raw bytes and their hash are preserved so a disputed import can
be re-read exactly as it arrived.

Scope
-----
**Long-only equities and cash**, stated explicitly and enforced: a negative
quantity or value is rejected rather than quietly admitted. Shorts,
derivatives, look-through funds and multi-currency positions need exposure
conventions this release does not define, and allowing a minus sign through
the existing percentage arithmetic would not give them.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from seraph.identity import AuthorizationError, IdentityRegistry, Principal
from seraph.shared_types import IST, ist_timestamp

#: The asset scope this release supports, carried on every portfolio.
DEFAULT_ASSET_SCOPE = "long_only_equity_and_cash"

#: Column spellings an import will accept, normalised to the canonical name.
COLUMN_ALIASES = {
    "symbol": "symbol", "ticker": "symbol", "scrip": "symbol",
    "instrument": "symbol", "tradingsymbol": "symbol",
    "isin": "isin",
    "quantity": "quantity", "qty": "quantity", "units": "quantity",
    "shares": "quantity",
    "value": "value", "market_value": "value", "marketvalue": "value",
    "current_value": "value", "amount": "value",
    "price": "price", "last_price": "price", "ltp": "price",
    "sector": "sector", "industry": "sector",
    "currency": "currency", "ccy": "currency",
    "account": "account", "account_id": "account",
}

CASH_SYMBOLS = {"CASH", "INR", "CASH_INR", "IDLE_CASH"}


def _now() -> str:
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


def _norm_header(name: str) -> str:
    return COLUMN_ALIASES.get(name.strip().lower().replace(" ", "_"), name.strip().lower())


@dataclass(frozen=True)
class RejectedRow:
    index: int
    reason: str
    raw: dict


@dataclass(frozen=True)
class AcceptedRow:
    index: int
    symbol: str
    quantity: float | None
    value: float | None
    price: float | None
    currency: str
    sector: str | None
    isin: str | None
    cash: bool
    account: str | None
    raw: dict

    def to_holding(self) -> dict:
        """The shape `portfolio_overlay` consumes."""
        return dict(symbol=self.symbol, value=self.value or 0.0,
                    quantity=self.quantity or 0.0, sector=self.sector or "unclassified")


@dataclass
class ImportPreview:
    """What an import WOULD do. Nothing is written until commit."""

    import_id: str
    source_name: str
    raw_hash: str
    base_currency: str
    accepted: list[AcceptedRow] = field(default_factory=list)
    rejected: list[RejectedRow] = field(default_factory=list)
    duplicates_merged: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def total_value(self) -> float:
        return sum(r.value or 0.0 for r in self.accepted)

    def describe(self) -> dict:
        return dict(
            import_id=self.import_id, source_name=self.source_name,
            raw_hash=self.raw_hash, base_currency=self.base_currency,
            accepted=len(self.accepted), rejected=len(self.rejected),
            total_value=self.total_value,
            duplicates_merged=list(self.duplicates_merged),
            rejected_rows=[dict(index=r.index, reason=r.reason, raw=r.raw)
                           for r in self.rejected],
            warnings=list(self.warnings),
            asset_scope=DEFAULT_ASSET_SCOPE)


def parse_holdings(data: bytes | str, *, source_name: str,
                   base_currency: str = "INR") -> ImportPreview:
    """Parse CSV or JSON holdings into accepted and rejected rows.

    Pure: no database, no identity, no writes. Every rejection carries a
    reason the user can act on, because "12 rows rejected" is not a result.
    """
    raw = data.encode("utf-8") if isinstance(data, str) else data
    preview = ImportPreview(import_id="imp_" + uuid.uuid4().hex[:16],
                            source_name=source_name,
                            raw_hash=hashlib.sha256(raw).hexdigest(),
                            base_currency=base_currency)
    text = raw.decode("utf-8-sig", errors="replace")
    rows: list[dict]
    stripped = text.lstrip()
    if stripped.startswith("[") or stripped.startswith("{"):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            preview.rejected.append(RejectedRow(0, f"file is not valid JSON: {exc}", {}))
            return preview
        if isinstance(parsed, dict):
            parsed = parsed.get("holdings", parsed.get("rows", []))
        if not isinstance(parsed, list):
            preview.rejected.append(RejectedRow(0, "JSON must be a list of holdings", {}))
            return preview
        rows = [{_norm_header(k): v for k, v in r.items()} if isinstance(r, dict)
                else {"_invalid": r} for r in parsed]
    else:
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            preview.rejected.append(RejectedRow(0, "file has no header row", {}))
            return preview
        rows = [{_norm_header(k): v for k, v in r.items() if k is not None}
                for r in reader]

    by_symbol: dict[str, AcceptedRow] = {}
    for index, row in enumerate(rows, start=1):
        accepted = _classify(index, row, base_currency)
        if isinstance(accepted, RejectedRow):
            preview.rejected.append(accepted)
            continue
        existing = by_symbol.get(accepted.symbol)
        if existing is None:
            by_symbol[accepted.symbol] = accepted
            continue
        # Same instrument twice: add the positions rather than keeping one and
        # losing the other, and say that it happened.
        merged = AcceptedRow(
            index=existing.index, symbol=existing.symbol,
            quantity=(existing.quantity or 0) + (accepted.quantity or 0)
            if (existing.quantity is not None or accepted.quantity is not None) else None,
            value=(existing.value or 0) + (accepted.value or 0)
            if (existing.value is not None or accepted.value is not None) else None,
            price=existing.price or accepted.price,
            currency=existing.currency, sector=existing.sector or accepted.sector,
            isin=existing.isin or accepted.isin, cash=existing.cash,
            account=existing.account, raw=existing.raw)
        by_symbol[accepted.symbol] = merged
        preview.duplicates_merged.append(accepted.symbol)

    preview.accepted = sorted(by_symbol.values(), key=lambda r: r.symbol)
    missing_value = [r.symbol for r in preview.accepted if r.value is None]
    if missing_value:
        preview.warnings.append(
            f"{len(missing_value)} holding(s) have no value and no price "
            f"({', '.join(missing_value[:5])}): they contribute 0 to the total "
            f"and will show as unvalued, not as zero-worth")
    if not preview.accepted:
        preview.warnings.append("no row was accepted; nothing would be saved")
    return preview


def _classify(index: int, row: dict, base_currency: str):
    if "_invalid" in row:
        return RejectedRow(index, "row is not an object", {"value": str(row["_invalid"])})
    symbol = str(row.get("symbol") or "").strip().upper()
    isin = str(row.get("isin") or "").strip().upper() or None
    if not symbol and isin:
        symbol = isin
    if not symbol:
        return RejectedRow(index, "no symbol, ticker or ISIN", _raw(row))

    def number(key):
        value = row.get(key)
        if value is None or str(value).strip() == "":
            return None, None
        try:
            return float(str(value).replace(",", "").strip()), None
        except ValueError:
            return None, f"{key} {value!r} is not a number"

    quantity, qerr = number("quantity")
    if qerr:
        return RejectedRow(index, qerr, _raw(row))
    value, verr = number("value")
    if verr:
        return RejectedRow(index, verr, _raw(row))
    price, perr = number("price")
    if perr:
        return RejectedRow(index, perr, _raw(row))

    cash = symbol in CASH_SYMBOLS
    if quantity is not None and quantity < 0:
        return RejectedRow(index, f"negative quantity {quantity}: this release supports "
                                  f"{DEFAULT_ASSET_SCOPE} only, and a short position needs "
                                  f"exposure conventions that are not defined yet", _raw(row))
    if value is not None and value < 0:
        return RejectedRow(index, f"negative value {value}: see the long-only scope note",
                           _raw(row))
    if value is None and quantity is not None and price is not None:
        value = quantity * price
    if quantity is None and value is None:
        return RejectedRow(index, "row has neither a quantity nor a value", _raw(row))

    currency = str(row.get("currency") or base_currency).strip().upper()
    if currency != base_currency:
        return RejectedRow(index, f"currency {currency} differs from the portfolio's "
                                  f"{base_currency}; multi-currency needs an FX convention "
                                  f"this release does not define", _raw(row))
    sector = str(row.get("sector") or "").strip() or None
    account = str(row.get("account") or "").strip() or None
    return AcceptedRow(index=index, symbol=symbol, quantity=quantity, value=value,
                       price=price, currency=currency, sector=sector, isin=isin,
                       cash=cash, account=account, raw=_raw(row))


def _raw(row: dict) -> dict:
    return {k: ("" if v is None else str(v)[:120]) for k, v in row.items()}


class WorkspaceStore:
    """Identity-scoped durable state. Every call takes a `Principal`."""

    def __init__(self, path, registry: IdentityRegistry):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS portfolios (
                    portfolio_id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL,
                    org_id TEXT NOT NULL, name TEXT NOT NULL,
                    base_currency TEXT NOT NULL, asset_scope TEXT NOT NULL,
                    created_at TEXT NOT NULL, archived_at TEXT);
                CREATE TABLE IF NOT EXISTS imports (
                    import_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL
                        REFERENCES portfolios(portfolio_id),
                    uploaded_at TEXT NOT NULL, source_name TEXT NOT NULL,
                    raw_hash TEXT NOT NULL, raw BLOB NOT NULL,
                    accepted INTEGER NOT NULL, rejected INTEGER NOT NULL,
                    detail TEXT NOT NULL, actor TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS holdings_snapshots (
                    snapshot_id TEXT PRIMARY KEY, portfolio_id TEXT NOT NULL
                        REFERENCES portfolios(portfolio_id),
                    effective_at TEXT NOT NULL, created_at TEXT NOT NULL,
                    import_id TEXT, valuation_at TEXT, note TEXT, actor TEXT NOT NULL,
                    UNIQUE(portfolio_id, effective_at));
                CREATE TABLE IF NOT EXISTS holding_rows (
                    snapshot_id TEXT NOT NULL REFERENCES holdings_snapshots(snapshot_id),
                    symbol TEXT NOT NULL, isin TEXT, quantity REAL, value REAL,
                    price REAL, currency TEXT NOT NULL, sector TEXT, cash INTEGER NOT NULL,
                    account TEXT, PRIMARY KEY(snapshot_id, symbol));
                CREATE TABLE IF NOT EXISTS watchlists (
                    watchlist_id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL,
                    org_id TEXT NOT NULL, name TEXT NOT NULL, items TEXT NOT NULL,
                    updated_at TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS preferences (
                    user_id TEXT NOT NULL, org_id TEXT NOT NULL, key TEXT NOT NULL,
                    value TEXT NOT NULL, updated_at TEXT NOT NULL,
                    PRIMARY KEY(user_id, org_id, key));
                CREATE TRIGGER IF NOT EXISTS snapshots_no_update
                    BEFORE UPDATE ON holdings_snapshots
                    BEGIN SELECT RAISE(ABORT,'holdings snapshots are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS imports_no_update BEFORE UPDATE ON imports
                    BEGIN SELECT RAISE(ABORT,'imports preserve the original'); END;
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    # ------------------------------------------------------- portfolios

    def create_portfolio(self, principal: Principal, *, name: str,
                         base_currency: str = "INR") -> dict:
        portfolio_id = "pf_" + uuid.uuid4().hex[:16]
        created = _now()
        with self.connect() as db:
            db.execute('INSERT INTO portfolios VALUES (?,?,?,?,?,?,?,NULL)',
                       (portfolio_id, principal.user_id, principal.org_id, name,
                        base_currency, DEFAULT_ASSET_SCOPE, created))
        # Register the ACL so authorization has something to read. A resource
        # with no ACL is denied, so this is not optional.
        self.registry.register_resource('portfolio', portfolio_id,
                                        org_id=principal.org_id,
                                        owner_user_id=principal.user_id,
                                        visibility='private')
        return dict(portfolio_id=portfolio_id, name=name, owner_user_id=principal.user_id,
                    org_id=principal.org_id, base_currency=base_currency,
                    asset_scope=DEFAULT_ASSET_SCOPE, created_at=created)

    def portfolios(self, principal: Principal) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                'SELECT portfolio_id,owner_user_id,org_id,name,base_currency,'
                'asset_scope,created_at FROM portfolios WHERE archived_at IS NULL '
                'ORDER BY created_at').fetchall()
        allowed = set(self.registry.visible(principal, 'portfolio', [r[0] for r in rows]))
        return [dict(portfolio_id=r[0], owner_user_id=r[1], org_id=r[2], name=r[3],
                     base_currency=r[4], asset_scope=r[5], created_at=r[6])
                for r in rows if r[0] in allowed]

    def portfolio(self, principal: Principal, portfolio_id: str) -> dict:
        self.registry.require(principal, 'read', 'portfolio', portfolio_id)
        with self.connect() as db:
            row = db.execute(
                'SELECT portfolio_id,owner_user_id,org_id,name,base_currency,'
                'asset_scope,created_at FROM portfolios WHERE portfolio_id=?',
                (portfolio_id,)).fetchone()
        if not row:
            raise AuthorizationError('unknown portfolio')
        return dict(portfolio_id=row[0], owner_user_id=row[1], org_id=row[2],
                    name=row[3], base_currency=row[4], asset_scope=row[5],
                    created_at=row[6])

    # ----------------------------------------------------------- import

    def preview_import(self, principal: Principal, portfolio_id: str, data,
                       *, source_name: str) -> ImportPreview:
        """Parse and classify without writing anything."""
        portfolio = self.portfolio(principal, portfolio_id)
        self.registry.require(principal, 'write', 'portfolio', portfolio_id)
        return parse_holdings(data, source_name=source_name,
                              base_currency=portfolio['base_currency'])

    def commit_import(self, principal: Principal, portfolio_id: str,
                      preview: ImportPreview, raw: bytes | str, *,
                      effective_at: str, note: str | None = None) -> dict:
        """Write the accepted rows as a snapshot, preserving the original."""
        self.registry.require(principal, 'write', 'portfolio', portfolio_id)
        if not preview.accepted:
            raise ValueError('refusing to save an import with no accepted row')
        raw_bytes = raw.encode('utf-8') if isinstance(raw, str) else raw
        if hashlib.sha256(raw_bytes).hexdigest() != preview.raw_hash:
            raise ValueError('the file changed between preview and commit')
        snapshot_id = 'snp_' + uuid.uuid4().hex[:16]
        created = _now()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM holdings_snapshots WHERE portfolio_id=? '
                          'AND effective_at=?', (portfolio_id, effective_at)).fetchone():
                raise ValueError(
                    f'a snapshot already exists at {effective_at}; snapshots are '
                    f'append-only, so record a different effective time')
            db.execute('INSERT INTO imports VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (preview.import_id, portfolio_id, created, preview.source_name,
                        preview.raw_hash, raw_bytes, len(preview.accepted),
                        len(preview.rejected), json.dumps(preview.describe()),
                        principal.user_id))
            db.execute('INSERT INTO holdings_snapshots VALUES (?,?,?,?,?,?,?,?)',
                       (snapshot_id, portfolio_id, effective_at, created,
                        preview.import_id, None, note, principal.user_id))
            db.executemany(
                'INSERT INTO holding_rows VALUES (?,?,?,?,?,?,?,?,?,?)',
                [(snapshot_id, r.symbol, r.isin, r.quantity, r.value, r.price,
                  r.currency, r.sector, int(r.cash), r.account)
                 for r in preview.accepted])
        self.registry.register_resource('holdings_snapshot', snapshot_id,
                                        org_id=principal.org_id,
                                        owner_user_id=principal.user_id)
        return dict(snapshot_id=snapshot_id, import_id=preview.import_id,
                    portfolio_id=portfolio_id, effective_at=effective_at,
                    rows=len(preview.accepted), rejected=len(preview.rejected),
                    total_value=preview.total_value, created_at=created)

    def original_import(self, principal: Principal, import_id: str) -> bytes:
        """The exact bytes as uploaded. A disputed import is re-readable."""
        with self.connect() as db:
            row = db.execute('SELECT portfolio_id,raw FROM imports WHERE import_id=?',
                             (import_id,)).fetchone()
        if not row:
            raise AuthorizationError('unknown import')
        self.registry.require(principal, 'read', 'portfolio', row[0])
        return row[1]

    # --------------------------------------------------- point-in-time

    def snapshots(self, principal: Principal, portfolio_id: str) -> list[dict]:
        self.registry.require(principal, 'read', 'portfolio', portfolio_id)
        with self.connect() as db:
            rows = db.execute(
                'SELECT snapshot_id,effective_at,created_at,import_id,note '
                'FROM holdings_snapshots WHERE portfolio_id=? ORDER BY effective_at',
                (portfolio_id,)).fetchall()
        return [dict(snapshot_id=r[0], effective_at=r[1], created_at=r[2],
                     import_id=r[3], note=r[4]) for r in rows]

    def holdings_as_of(self, principal: Principal, portfolio_id: str,
                       as_of: str) -> dict:
        """Holdings as they stood at `as_of`.

        Returns `basis='historical'` with the snapshot actually used, or
        `basis='unavailable'` when no snapshot is that old. It never falls
        back to current holdings under a past date — that substitution is the
        exact thing contract rule 2 forbids.
        """
        self.registry.require(principal, 'read', 'portfolio', portfolio_id)
        with self.connect() as db:
            row = db.execute(
                'SELECT snapshot_id,effective_at,created_at,import_id FROM '
                'holdings_snapshots WHERE portfolio_id=? AND effective_at<=? '
                'ORDER BY effective_at DESC LIMIT 1',
                (portfolio_id, as_of)).fetchone()
            earliest = db.execute(
                'SELECT MIN(effective_at) FROM holdings_snapshots WHERE portfolio_id=?',
                (portfolio_id,)).fetchone()[0]
        if not row:
            return dict(basis='unavailable', as_of=as_of, holdings=[],
                        snapshot_id=None, effective_at=None,
                        earliest_snapshot=earliest,
                        note=('no holdings snapshot exists at or before this date. '
                              'Current holdings are NOT substituted: they would be '
                              'the wrong positions for this date'
                              if earliest else
                              'this portfolio has no holdings snapshot yet'))
        rows = self._rows(row[0])
        stale_days = _days_between(row[1], as_of)
        return dict(basis='historical', as_of=as_of, snapshot_id=row[0],
                    effective_at=row[1], created_at=row[2], import_id=row[3],
                    holdings=rows, total_value=sum(h['value'] for h in rows),
                    age_days=stale_days,
                    note=(f'positions as recorded at {row[1]}'
                          + (f', {stale_days} days before the requested date'
                             if stale_days else '')))

    def current_holdings(self, principal: Principal, portfolio_id: str) -> dict:
        self.registry.require(principal, 'read', 'portfolio', portfolio_id)
        with self.connect() as db:
            row = db.execute(
                'SELECT snapshot_id,effective_at FROM holdings_snapshots '
                'WHERE portfolio_id=? ORDER BY effective_at DESC LIMIT 1',
                (portfolio_id,)).fetchone()
        if not row:
            return dict(basis='unavailable', holdings=[], snapshot_id=None,
                        note='this portfolio has no holdings snapshot yet')
        rows = self._rows(row[0])
        return dict(basis='current', snapshot_id=row[0], effective_at=row[1],
                    holdings=rows, total_value=sum(h['value'] for h in rows))

    def _rows(self, snapshot_id: str) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                'SELECT symbol,isin,quantity,value,price,currency,sector,cash,account '
                'FROM holding_rows WHERE snapshot_id=? ORDER BY symbol',
                (snapshot_id,)).fetchall()
        return [dict(symbol=r[0], isin=r[1], quantity=r[2], value=r[3] or 0.0,
                     price=r[4], currency=r[5], sector=r[6] or 'unclassified',
                     cash=bool(r[7]), account=r[8]) for r in rows]

    # ------------------------------------------- watchlists, preferences

    def save_watchlist(self, principal: Principal, name: str,
                       items: list[str]) -> dict:
        watchlist_id = 'wl_' + hashlib.sha256(
            f'{principal.user_id}:{principal.org_id}:{name}'.encode()).hexdigest()[:16]
        updated = _now()
        clean = sorted({str(i).strip().upper() for i in items if str(i).strip()})
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO watchlists VALUES (?,?,?,?,?,?)',
                       (watchlist_id, principal.user_id, principal.org_id, name,
                        json.dumps(clean), updated))
        self.registry.register_resource('watchlist', watchlist_id,
                                        org_id=principal.org_id,
                                        owner_user_id=principal.user_id)
        return dict(watchlist_id=watchlist_id, name=name, items=clean,
                    updated_at=updated)

    def watchlists(self, principal: Principal) -> list[dict]:
        with self.connect() as db:
            rows = db.execute(
                'SELECT watchlist_id,name,items,updated_at FROM watchlists '
                'WHERE owner_user_id=? AND org_id=? ORDER BY name',
                (principal.user_id, principal.org_id)).fetchall()
        return [dict(watchlist_id=r[0], name=r[1], items=json.loads(r[2]),
                     updated_at=r[3]) for r in rows]

    def set_preference(self, principal: Principal, key: str, value) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO preferences VALUES (?,?,?,?,?)',
                       (principal.user_id, principal.org_id, key,
                        json.dumps(value), _now()))

    def preferences(self, principal: Principal) -> dict:
        with self.connect() as db:
            rows = db.execute('SELECT key,value FROM preferences WHERE user_id=? '
                              'AND org_id=?',
                              (principal.user_id, principal.org_id)).fetchall()
        return {k: json.loads(v) for k, v in rows}


def _days_between(earlier: str, later: str) -> int:
    try:
        a = datetime.fromisoformat(earlier[:10])
        b = datetime.fromisoformat(later[:10])
    except ValueError:
        return 0
    return max(0, (b - a).days)
