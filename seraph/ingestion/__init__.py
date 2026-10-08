# C2 — Ingestion Layer (FR1–FR4, FR7, FR51)
"""Lands raw external series into the store unmodified except for schema
normalisation. Owns all outbound network I/O, the Kite credentials, retry and
backoff, and per-source watermarks."""
