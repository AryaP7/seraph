# C1 — Store & Schema (FR8, FR38)
"""Owns the physical schema and typed, versioned access to every persisted
entity. The only component allowed a connection pool; E1–E14 exist nowhere
else. All other components go through StoreWriter / StoreReader (S1/S2)."""
from seraph.store.bootstrap import apply_schema, resolve_dsn
from seraph.store.reader import StoreReader
from seraph.store.writer import StoreWriter

__all__ = ["StoreReader", "StoreWriter", "apply_schema", "resolve_dsn"]
