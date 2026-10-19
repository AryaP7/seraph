# SERAPH development plan

Created 2026-10-16. Working directory: `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`
(WSL: `/mnt/c/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya`).

This is the executable program of work. It is derived from
[the development audit](AUDIT-2026-10-16-DEVELOPMENT.md) and its
[59-item backlog](AUDIT-2026-10-16-BACKLOG.csv), under the Astra baseline
authority recorded in `AGENTS.md`, `README-RESEARCH.md` and `EXPERIMENT.md`.

Companion documents:

| Document | Purpose |
|---|---|
| [DEVELOPMENT-STATUS.md](DEVELOPMENT-STATUS.md) | Per-backlog-ID state register, evidence and blockers |
| [SOURCE-TO-SCREEN-INVENTORY.md](SOURCE-TO-SCREEN-INVENTORY.md) | Every visible panel: source, status, intended producer, permission, acceptance test |
| [PRODUCT-CONTRACTS.md](PRODUCT-CONTRACTS.md) | Shared product metadata, news/identity/portfolio/scenario/case/UI transport contracts |
| [DEVELOPMENT-HANDOFF.md](DEVELOPMENT-HANDOFF.md) | Current workspace state, commands, evidence paths, exact next step |
| `docs/decisions/` | Dated decision records (DR-NN) |

---

## 1. Binding scope

The existing interface is the product. Its identity, navigation, globe,
geography, sector overlays, strategic assets, news rail, commodity and weather
surfaces, portfolio exposure, role tools and drill-downs are intended
functionality, not legacy to be removed. Preview content marks unfinished
functionality: each preview's **data provider** is replaced as its subsystem
becomes ready; the panel itself stays.

Three flows remain separate, attributable and separately evaluated:

```
F1  Market observations → C4 → Hawkes / RMT / Hamilton → C8 → C9 → CSRS
F2  External sources → timestamped news/events → entities/places/assets
        → exposure relationships → news impact estimates → overlays, role workflows
F3  Causal daily research features → Astra future-target models
        → probabilities and separately calibrated alarms
```

Non-identities that must never be collapsed in code, labels, units or
evaluation:

- News sector stress **is not** Hawkes sector stress.
- A geography arc **is not** a fitted contagion edge.
- A CSRS rank **is not** a portfolio-loss probability.
- A Hamilton volatility state **is not** a named-crisis probability.

All three pillar families are retained. Diagnostic-only models stay diagnostic
until evidence supports a different eligibility decision. Weights are never
changed to make a scenario control appear responsive.

---

## 2. Dependency graph

Arrows are hard prerequisites. Items on the same line are independent of each
other and may proceed in any order.

```
                            ┌─ DOC01 ─────────────────────────────────┐  (continuous)
                            │                                         │
P0  orientation ── QA03 assessment                                     │
     │                                                                 │
P1  FIX01 ─┬─ FIX02 ─┬─ FIX03 ─┬─ FIX10                                │
           │         │         └─ (seal) ──────┐                       │
           ├─ FIX08  ├─ FIX09   FIX11          │                       │
           └─ FIX07  └─ FIX05 ── FIX06         │                       │
           └─ FIX04                            │                       │
                                               │                       │
P2  DATA01 ─ DATA02 ──────────────┬────────────┤                       │
     FIX04 FIX05 FIX06 FIX07      │            │                       │
                                  │            │                       │
P3  AUTH01 ─ AUTH02 ─┬─ AUTH03    │            │                       │
                     └─ AUTH04    │            │                       │
                        │         │            │                       │
P4  NEWS01 ─ NEWS02 ─┐  │         │            │                       │
    NEWS01 ─ NEWS03 ─┴─ NEWS04 ─ NEWS05 ─┬─ NEWS06                     │
                                         └─ NEWS07 (needs AUTH02)      │
                                                                       │
P5  DATA03 DATA04 DATA05 ─ DATA07 (needs DATA06)                       │
    DATA06  DATA08  DATA09 (needs DATA02) ─ DATA10                     │
    PIPE01 (needs DATA02 DATA09 FIX01 FIX02 FIX03) ─┬─ PIPE03 ─ OPS01  │
    PIPE02 (needs DATA02 FIX03) ─ VAL01             └─ PIPE04          │
                                                                       │
P6  PORT01 (needs AUTH04) ─┬─ PORT02 ─┬─ PORT05                        │
                           ├─ PORT03 (needs FIX07)                     │
                           └─ PORT04 (needs NEWS04 NEWS05)             │
    SCEN01 (needs AUTH02 FIX03) ─ SCEN02 (needs PORT02 NEWS04)         │
                                                                       │
P7  CASE01 (needs AUTH02 AUTH03 FIX08) ─ CASE03 (needs FIX03 NEWS02)   │
    CASE02 (needs AUTH02)                                              │
                                                                       │
P8  POL01 (needs DATA05 DATA07) ─ POL02 (needs SCEN01)                 │
    VAL02 (needs PORT02 SCEN02 VAL01)   VAL03 (needs DATA02 FIX05)     │
                                                                       │
P9  NEWS08 (needs NEWS03)  OPS02  OPS03 (needs AUTH02)                 │
    QA01 (needs AUTH02 NEWS06 SCEN01) ─ QA02      QA03 ────────────────┘
```

Known external blockers and the paths they block **only**:

| External dependency | Blocks | Does **not** block |
|---|---|---|
| Source PostgreSQL (5433/5434 unreachable) | DATA02, PIPE01 real execution, real-corpus density tests | Synthetic persistence tests, contract work, identity abstractions, news fixtures, case logic, DATA01 |
| OIDC provider configuration | AUTH01 round-trip verification | AUTH01 abstractions, AUTH02–AUTH04 logic and their deterministic tests |
| Authorized news-source credentials/rights | NEWS01 live acquisition | Source registry schema, fixtures, dedup/extraction/exposure logic, replay tests |
| Authorized institution submissions | CASE02 | CASE01, CASE03 |
| FR35 Table B scientific decision | FIX05 resolution | FIX06 storage-identity migration design |

---

## 3. Phases, gates and current position

| Phase | Scope | Gate | State |
|---|---|---|---|
| **P0** Orientation, scope, contracts | DOC01, QA03 assessment | Source-to-screen inventory and dependency-aware status register exist; canonical UI scope preserved; first slice specified | **complete** (2026-10-16) |
| **P1** Historical execution and persistence | FIX01 FIX02 FIX03 FIX08 FIX09 FIX10 FIX11 | Reproduced defects have regression coverage; special-session archive replay succeeds causally; completed results sealed; no-op actions work; stale responses cannot contaminate current context | **complete** (2026-10-16) — all 7 verified |
| **P2** Data foundation and research contracts | DATA01 DATA02 FIX04 FIX05 FIX06 FIX07 | DB assertions backed by isolated execution; feature transforms and fitted artifacts have reproducible causal identities; unresolved science stays visibly blocked | **next** |
| **P3** Authenticated workspaces | AUTH01–AUTH04, OPS03 start | Permission tests pass; private paths scoped; owned state survives restart; provider round-trip verified when credentials exist | not started |
| **P4** First news-to-map vertical slice | NEWS01–NEWS07 | One genuine source event traced through a verified relationship into a real overlay; every non-preview number has meaning/source/as-of/version; replay cannot see future revisions | not started |
| **P5** Fresh execution and supporting data | DATA03–DATA10, PIPE01–PIPE04, VAL01 start | Verified fresh source-to-view run; retries reproduce it; outages explicit; shadow forecast record begins | not started |
| **P6** Portfolios and institutional scenarios | PORT01–PORT05, SCEN01–SCEN02 | Authenticated user imports/saves/revisits a real portfolio, inspects event exposures, distinguishes measured risk from coverage; scenarios reproduce without cross-tenant leakage | not started |
| **P7** Operational regulator cases | CASE01–CASE03 | Scoped regulator triages→assigns→reviews→closes across sessions/users with complete actor/evidence trail and reproducible export | not started |
| **P8** Fitted policy and measured decision value | POL01 POL02 VAL02 VAL03, VAL01 continue | Policy scenarios use a real eligible fitted artifact; economic benefit claims backed by completed evaluation | not started |
| **P9** Operations and release verification | NEWS08, OPS01–OPS03, QA01–QA03, DOC01 | Chosen release audience has a tested end-to-end workflow, recovery, access controls and accurate status | not started |

### Slices completed

| Slice | Backlog | Outcome | Decision record |
|---|---|---|---|
| P1-S1 | `FIX01` `FIX02` | Session-aware decision clock, as-of vintage selection, declared absence. The full supported history (5361 sessions, 2005-01-03 → 2026-08-21) now replays under both clock policies with zero future-information violations; previously **every** range ending on or after 2024-11-01 aborted | [DR-01](decisions/DR-01-2026-10-16-session-clock-and-absence.md) |
| P1-S2 | `FIX03` `FIX08` `FIX09` | Sealed runs with exact date-set verification, immutable report revisions, two-stage completion, command/event separation for journal no-ops, and a fail-closed instrument-classification policy | [DR-02](decisions/DR-02-2026-10-16-run-sealing-and-command-results.md) |

| P1-S3 | `FIX10` `FIX11` | One coherent run/as-of bundle on every supported route with genuinely applied, scope-keyed caching; a recoverable request lifecycle with bounded timeout, same-id retry, preserved drafts and context-bound results | [DR-03](decisions/DR-03-2026-10-16-coherent-reads-and-request-lifecycle.md) |

**Phase 1 is complete.** All seven items are verified and every reproduced
defect has regression coverage.

### Current slice

**P2-S1 is part done:** `FIX04` (causal state bins) is **verified** —
see [DR-04](decisions/DR-04-2026-10-16-causal-state-bins.md).

Remaining in Phase 2, in dependency order:

1. **`DATA01`** — provision a disposable guarded `seraph_test_*` Timescale
   service and run the 13 skipped database tests. Blocked only if Docker's
   Linux engine stays unavailable.
2. **`FIX07`** — persist Hawkes fit parameters, training cutoff, basket
   identity, seasonality and diagnostics; reconstruct an intensity from a saved
   fit; replace latest-universe selection with point-in-time membership or a
   disclosed fixed research basket.
3. **`FIX05`** — **scientifically unresolved.** FR35 Table B is two pre-Hawkes
   epochs in SPEC and six in `configuration_list()`. Needs a dated design
   decision; must not be closed by picking an interpretation to clear the xfail.
4. **`FIX06`** — evaluation-identity migration, which needs the `FIX05` design.
5. **`DATA02`** — blocked on source PostgreSQL.

See [DEVELOPMENT-HANDOFF.md §2](DEVELOPMENT-HANDOFF.md).

---

## 4. Slice discipline

Every slice follows the same seven steps, and its evidence is recorded before
the next slice starts:

1. State the user-visible outcome and the backlog IDs it closes.
2. Inspect the relevant existing implementation and contracts first.
3. Reproduce the defect, or define a behaviour-focused acceptance test, **before**
   changing consequential behaviour.
4. Implement the smallest coherent end-to-end change, including migration,
   transport and UI work where the outcome needs it.
5. Verify positive, missing-data, stale-context, retry and permission cases.
6. Record what passed, what was skipped, and what remains unverified.
7. Update status and handoff, then move to the next dependency-ready slice.

State vocabulary (software completion and empirical acceptance are separate):

`not started` · `in progress` · `implemented, unverified` · `verified` ·
`blocked on external input` · `scientifically unresolved`

### Testing cadence

- Targeted module tests during development.
- Core partition at each slice close:
  `pytest tests --ignore=tests/test_c7_hamilton.py --ignore=tests/test_c7_hamilton_causal.py --ignore=tests/test_c7_hamilton_regime_recovery.py --ignore=tests/contract/test_ct7_simulator_consistency.py -q`
- Expensive model/policy partition (~18 min at audit time) only at integration
  gates or when numerical behaviour changed:
  `pytest tests/test_c7_hamilton.py tests/test_c7_hamilton_causal.py tests/test_c7_hamilton_regime_recovery.py tests/contract/test_ct7_simulator_consistency.py -q`
- `python scripts/check_invariants.py` and `python scripts/verify_research_artifacts.py`
  at every slice close.

A unit-test pass never substitutes for an empirical acceptance result.

---

## 5. Standing constraints

- **Evidence is append-only.** Preserve original evidence, preregistrations and
  hashed records. Write dated amendments and new result artifacts; never edit a
  historical record so it agrees with new code.
- **Databases.** The original source database is read-only. New production-like
  results go to a separate experimental database. Tests use a guarded disposable
  `seraph_test_*` database carrying `seraph_test_guard(token)`; that marker never
  enters a source or research database. Credentials stay out of versioned files
  and logs.
- **Stack.** Python 3.12, Polars for large ETL, NumPy/SciPy numerics, Pydantic v2,
  asyncpg/SQL with COPY, PostgreSQL/Timescale, Streamlit plus the existing
  frontend component, cron/idempotent scripts, bounded process workers. No ORM,
  workflow platform, frontend rewrite or GPU dependency.
- **Repository invariants** (`AGENTS.md` §5) hold throughout: fixed
  `PILLAR_ORDER`, pure C9, immutable weight identity, explicit IST timestamps,
  structural/transient distinction, common-support rotation, `AR_t` in C4,
  filter-before-rank, idempotent writes, role-based field omission. Astra's
  corrected variance and missing-measurement mathematics supersede the historical
  formulas where they conflict.
- **No commits, pushes, merges, publication or deployment** are authorised by the
  current instruction. Existing modified and untracked work is preserved; nothing
  is reset, cleaned or overwritten.
- **Blocked means blocked.** An unavailable endpoint stays explicitly unavailable.
  Archives and mocks are never silently substituted and labelled fresh.
