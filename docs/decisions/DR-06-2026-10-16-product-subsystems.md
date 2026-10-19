# DR-06 — Product subsystems: metadata, identity, news, portfolio, scenario, case, operations

**Date:** 2026-10-16
**Backlog:** `AUTH01`–`AUTH04`, `NEWS01`–`NEWS06`, `PORT01` `PORT02` `PORT04`,
`SCEN01`, `CASE01` `CASE03`, `FIX06` `FIX07`, `DATA01` (partial), `DATA03`,
`PIPE03`, `OPS01` `OPS03`
**Status:** adopted and implemented
**Supersedes:** nothing. Turns PRODUCT-CONTRACTS §1 and §4–§8 from PROPOSAL
into ADOPTED, and leaves §8's institution-data half explicitly unbuilt.

---

## What changed, and the one idea behind it

Phase 1 fixed how SERAPH handles what it already had. This slice builds the
subsystems the contracts described. The single idea they share:

> A number never travels without its meaning — where it came from, when it
> could have been known, what it covers, what unit it is in, and how sure
> anyone is.

`Envelope` makes that mechanical rather than aspirational, and every subsystem
below speaks it.

## 1. `seraph/product_types/` — the metadata envelope (§1)

Four rules the code enforces, because prose did not:

| Rule | How |
|---|---|
| `unknown` is never `0` | an `unavailable` envelope **cannot hold a value**; `value_for_calculation()` raises |
| a replay at `T` reads only what was knowable at `T` | `Timing.first_seen_at` is the bound, **not** `published_at`; `InformationClock` filters or raises |
| `preview` never enters a calculation | `value_for_calculation()` refuses a preview envelope outright |
| status travels with the datum | every `to_payload()` carries `status` and `schemaVersion` |

An `estimate` must publish what its uncertainty **means** — a number in [0,1]
could be a probability, a share, a rank or a confidence, and `Uncertainty.meaning`
makes the producer say which. `Coverage` separates measured quiet from never
looked at.

## 2. `seraph/identity/` — identity and tenancy (`AUTH01`–`AUTH04`)

- **Role and resource scope are separate fields.** "Regulator" is not a
  synonym for "may read every institution's book"; reach is an explicit
  `Scope` on the grant.
- **Roles resolve from server-held grants.** A requested role with no live
  grant is **refused**, not downgraded — a forged request is visible.
- **Revocation is a timestamp, never a delete.** An audit trail that loses the
  fact a grant existed cannot reconstruct a past decision.
- **An unregistered resource is denied.** Nothing vouches for it, so there is
  no safe default but no.
- **The provider fails closed.** No issuer configured ⇒
  `IdentityProviderUnavailable`. There is no fallback to privileged access;
  local demonstration mode is a separate labelled mode.
- **A role claimed in a token grants nothing.** `VerifiedSubject` carries
  issuer and subject only. Authority comes from grants, always.

**`AUTH01` is implemented, unverified.** No OIDC issuer or client id is
configured in this checkout, so the round trip has never run. The verifier's
failure paths are tested; its success path against a real provider is not.

`WorkspaceStore` gives `AUTH04` durable owned state: portfolios, holdings
snapshots, imports, watchlists, preferences — all identity-scoped, all
surviving restart, none visible across organisations.

## 3. `seraph/news/` — flow F2 (`NEWS01`–`NEWS06`)

```
Source → RawObservation → Story → Event → Entity/Place/Asset
       → ExposureEdge → ImpactEstimate → overlay
```

The properties that make it a subsystem rather than a panel of numbers:

- **A double poll is one observation.** The id derives from
  `(source, reference, content_hash)`. Changed content becomes a *correcting*
  story; the earlier version is preserved, never overwritten.
- **Ten syndicated copies are one event with ten witnesses.**
  `Event.confirmations` counts sources; the extractor collapses a syndication
  group into one event.
- **An outage is missing coverage, not quiet.** `coverage_at()` names every
  source that failed or was never fetched.
- **An asset's location is its own.** `place_of()` returns an asset's place and
  **nothing** for an entity, so a Mumbai registered office cannot become the
  site of an Odisha plant.
- **Ambiguity abstains.** `resolve()` returns `ambiguous` with its candidates
  and links nothing.
- **Overlapping paths do not multiply exposure.** Each target keeps one path —
  strongest evidence, then shortest — and the discarded routes are reported.
- **Article text is untrusted.** `scrub()` neutralises instruction-shaped text
  and reports it. The module has no write path to grants, commands or actions.
- **Five dimensions stay five.** Severity, evidence confidence, exposure
  magnitude, direction and horizon are never collapsed into one "stress"
  number, because the collapsed number destroys exactly what a user can check.

**The curated registries ship empty**, following
`seraph/ingestion/tariff_events.curated.csv`'s precedent. Entity, asset and
exposure rows each require a citation and the loader refuses uncited ones. An
invented magnitude would flow into a portfolio exposure figure while looking
entirely plausible.

**`NEWS01` is implemented, unverified against a live source.** No feed is
registered as `accessibility_verified`; nothing has been fetched over the
network. The acquisition layer is tested against injected fetchers.

## 4. Portfolio and scenarios (`PORT01` `PORT02` `PORT04`, `SCEN01`)

- **Long-only equities and cash, enforced.** A negative quantity is rejected
  with the reason, not admitted through the existing percentage arithmetic.
- **Import is preview → commit.** Every rejection states a reason the user can
  act on; the original bytes are preserved; a duplicated instrument is merged,
  not dropped; a file that changed between preview and commit is refused.
- **A past date uses past positions.** `holdings_as_of()` returns the snapshot
  in force, or `basis='unavailable'` — it never substitutes today's holdings
  under yesterday's date.
- **"Why does this affect me?"** returns article → event → each relationship
  with its evidence → the holding. Each holding appears once; linked,
  unlinked and linked-but-unsized reconcile to the portfolio total; and it
  says plainly it is not a loss estimate.
- **A scenario pins its baseline.** Run, date, weights artefact and a hash of
  the reconciled state. Assumptions carry units and justifications and are
  versioned, so a re-run under revised assumptions is a different record.
  Comparing across different baselines is **refused**, not fudged.
- **`kind="economic"` is refused.** It needs a propagation and valuation model
  that does not exist; a rank shock will not be relabelled as one.

## 5. Cases (`CASE01`, `CASE03`)

Extends the journal; nothing in it is rewritten.

- a validated state machine that names the moves that *were* available;
- `expected_version` on every mutation, so two investigators cannot silently
  overwrite each other;
- idempotent delivery by dedupe key;
- **evidence pinned at a revision**, and replay anchored to an **event
  sequence number** rather than a wall-clock timestamp — second granularity
  cannot separate same-second events, and a decision replay has to be exact;
- a source correction **notifies** the cases that pinned a reference and
  preserves their pinned revision;
- `circuit_breaker` records an action category; the export states that SERAPH
  executes no market intervention.

## 6. `FIX07` — the Hawkes fit survives

`HawkesFitArtefact` keeps `mu`, `alpha`, `phi`, dispersion, the seasonality
profile, the training window, the basket and the diagnostics, and
`reconstruct_intensity()` rebuilds `lambda_t` from the artefact alone — tested
through a JSON round trip, so only what was persisted is available. A fit whose
stored parameters do not reproduce its own branching ratio is **refused at
construction**.

`BasketIdentity.validate()` rejects `latest_snapshot` for a historical window
(audit finding A09) and `point_in_time_members()` replaces the
`ORDER BY rebalance_date DESC LIMIT 1` selection. A fixed research basket is
allowed but must state its survivorship limitation.

Where no measured sector baseline exists, **no flag is emitted at all** —
the previous hardcoded `'none'` was indistinguishable from a measurement that
found nothing.

## 7. Operations (`PIPE03`, `OPS01`, `OPS03`)

Lease-based locks, checkpoints that survive failure, bounded retries, recorded
failures, watermarks. Health checks where **a thing with no data never reads
`ok`**. An alert ledger where *issued* and *delivered* are different states and
an undelivered alert is retryable rather than lost.

`docker-compose.yml` hardened: credentials from the environment, loopback-only
binding (it published on every interface), a pinned image, `scram-sha-256`.
Full posture and the explicit non-claims are in [OPERATIONS.md](../OPERATIONS.md).

## Verification

| Suite | Result |
|---|---|
| Core partition | **813 passed, 14 skipped, 1 xfailed, 0 failures** |
| Expensive Hamilton/policy partition | **34 passed** (19m58s) — the gap left open at the previous checkpoint |
| Mechanical invariants | 5 passed |
| Research artifact verifier | passed; data, code and output hashes verified |
| `git diff --check` | clean |

New tests: 197 across `test_product_types_envelope`,
`test_auth_identity_and_tenancy`, `test_port01_port02_workspace`,
`test_news_pipeline`, `test_news06_overlays`, `test_scen01_port04`,
`test_case_workflow`, `test_fix06_evaluation_identity`,
`test_fix07_hawkes_artefact`, `test_data03_bhavcopy`,
`test_ops_jobs_and_monitoring`.

`seraph/shared_types/` was **not** modified. No `WarningCode` or error Literal
was widened. No UI panel was removed and no preview was deleted.

## What this slice did not do

- **`FIX05` stays scientifically unresolved** — see
  [DR-05](DR-05-2026-10-16-fr35-table-b-scope.md). The xfail still fails.
- **`DATA01` execution is blocked** — Docker's Linux engine is unavailable;
  the provisioning path and its guards exist and are tested, the database has
  never been started.
- **`DATA02`, `PIPE01`, `PIPE02`, `VAL01`** remain blocked on the source
  PostgreSQL, which is still unreachable on 5433/5434.
- **`CASE02`** needs authorized institution submissions, which do not exist.
- **`POL01`/`POL02`** need macro vintages and a fitted artefact (`DATA05`,
  `DATA07`).
- **Live news acquisition, OIDC round trip, backup/restore exercise, load and
  latency measurement, browser automation** — none performed.
