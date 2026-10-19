# DR-02 — Run sealing, immutable report revisions, command/event separation

**Date:** 2026-10-16
**Backlog:** `FIX03`, `FIX08`, `FIX09` (audit findings A03, A04, A13, A14)
**Status:** adopted and implemented
**Supersedes:** nothing. Existing stores are migrated additively; no persisted
row is rewritten or deleted.

## 1. Run lifecycle (`FIX03`, findings A03/A04)

```
running  ──finish()──▶  inference_complete  ──report()──▶  complete
                 └──finish(requires_report=False)──────────▶ complete
```

- **`put()`** rejects a point whose date lies outside the manifest's declared
  `start..end`, rejects a point missing any required schema field, and rejects
  any new point once the run is sealed. A **byte-identical** retry of an
  already-stored point still succeeds, so deterministic replay recovery is
  unaffected.
- **`finish(run_id, expected)`** verifies the exact expected **date set**, not
  a row count (an integer count is still accepted for store-level callers that
  do not model dates). It records `sealed_dates`, a `content_hash` over the
  payloads, and `sealed_at`. Calling it again on a sealed run is a no-op that
  *re-verifies* the contents and raises if they changed.
- **`requires_report=True`** stops at `inference_complete`. The run becomes
  `complete` only when its report exists, so a crash between the last point
  and the report can never present itself as finished. `run_archive()` uses
  this; the fresh-source diagnostic endpoint does not, because it has no
  report obligation. The dashboard continues to show only `complete` runs.
- **Reports are immutable revisions.** An identical rewrite is a no-op; a
  different report appends a new revision and preserves the previous one.
  `report_revisions()` lists the history. SQL triggers reject UPDATE and
  DELETE on the revision table.

### Why separate states rather than one atomic transaction

The audit allowed either. Separate states were chosen because inference and
evaluation genuinely complete at different times and can fail independently —
a replay can be sound while its retrospective comparison is not yet computed.
Collapsing them into one transaction would have hidden that distinction and
made partial recovery (re-running only the report) impossible.

### Migration

`runs` gains `sealed_dates`, `content_hash`, `sealed_at` by `ALTER TABLE`.
The legacy single-row `reports` table is copied into `report_revisions` as
revision 1 and preserved under `reports_legacy`. Migration is idempotent and
runs on every `RunStore` construction.

## 2. Command results versus journal events (`FIX08`, finding A13)

C11's `RegulatoryActionLog` deliberately appends **no** journal event when an
update leaves an action unchanged. The store previously took `journal()[-1]`
regardless and reinserted the *previous* event, hitting
`UNIQUE constraint failed: action_events.run_id, action_events.seq`.

Commands and events are now distinct:

| Table | Role |
|---|---|
| `action_events(run_id, seq, request_id, request, event)` | the append-only journal; trigger-protected; one row per genuine event |
| `action_commands(run_id, request_id, request, result, event_seq, created_at)` | one row per command, keyed by idempotency id; `event_seq` is NULL for a no-op |

`action()` measures the journal length before and after the C11 call. If an
event was appended, it is persisted and the command points at it. If none was,
**no sequence number is consumed**; the command result is recorded as
`{noop: true, …}` so a retry returns the identical result, and a conflicting
retry of the same request id is still rejected. Both inserts happen in one
transaction, so an injected failure rolls back the event *and* the command
record together.

## 3. Instrument-classification failure policy (`FIX09`, finding A14)

`equity_symbols()` returned an empty set when the vendored ISIN table was
absent, and `is_equity()` then answered **True for every symbol** — silently
readmitting ETFs to the FR52 equity universe, which inflates exactly the
leading eigenvalue the RMT pillar measures.

- `classification_status()` reports availability explicitly, and treats a file
  with fewer than `MIN_USABLE_SYMBOLS` (100) equity symbols as unusable rather
  than as a very aggressive filter.
- `is_equity()` **raises** `ClassificationUnavailable` instead of defaulting to
  True. An unclassified instrument is unknown, not equity.
- `build_snapshot(equities_only=True)` returns `MISSING_DEPENDENCY` when
  classification is unavailable. `allow_unclassified=True` is the documented,
  visibly degraded escape hatch: the filter is skipped and the snapshot carries
  a `PARTIAL_COVERAGE` warning stating that it is not an equity universe.
- `build_symbol_list()` (Hawkes basket) refuses to pool an unclassified basket.

No `WarningCode` or other `shared_types` Literal was widened; the existing
`PARTIAL_COVERAGE` code and `MISSING_DEPENDENCY` error variant carry this.

## Verification

- `tests/test_fix03_fix08_persistence.py` — 18 tests: sealing, out-of-range
  rejection, exact-date-set verification, schema validation, identical retry,
  interruption before the report, immutable revisions, trigger protection,
  no-op success, no-op retry, conflicting retry, real change after a no-op,
  repeated retraction across a restart, command recording, transactional
  rollback, and legacy-store migration.
- `tests/test_fix09_classification_policy.py` — 9 tests: status reporting for
  present / missing / sparse tables, `is_equity` raising, explicit
  `MISSING_DEPENDENCY`, opt-in degraded mode with its warning, the normal
  filtering path, and the Hawkes basket refusal.
- `scripts/reverify_audit_findings.py` → `docs/evidence/REVERIFY-2026-10-16.json`
  records A03/A04 and A13 as `fixed`.
