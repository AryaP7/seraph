# SERAPH — engineering development plan to completion

Written 18 October 2026. Built on
[SERAPH-ENGINEERING-COMPLETION-AUDIT-2026-10-18.md](SERAPH-ENGINEERING-COMPLETION-AUDIT-2026-10-18.md)
as corrected by
[SERAPH-COMPLETION-AUDIT-VERIFICATION-2026-10-18.md](SERAPH-COMPLETION-AUDIT-VERIFICATION-2026-10-18.md).

**66 tracked engineering items across 10 workstreams (W0–W9)** — the audit's 55
packages, of which 5 need acceptance rather than implementation, plus 11 new
findings. With the baseline and contract tasks this plan adds, the tracking
backlog is 76 rows:
[SERAPH-DEVELOPMENT-PLAN-2026-10-18-BACKLOG.csv](SERAPH-DEVELOPMENT-PLAN-2026-10-18-BACKLOG.csv)
(29 P0, 42 P1, 5 P2).

This is a plan, not a status claim: nothing below has been implemented by
writing this document.

## 0. What this plan commits to

The audit's boundary is adopted unchanged. **Engineering completion means the
documented launcher brings up a coherent application, real authorized inputs
reach real producers and the main console, promised operations work through
normal UI paths and persist, state survives crashes, every datum is
distinguishable as current / stale / replay / estimate / unavailable /
fabricated, a separately installed build contains all its assets, and
acceptance is recorded against exact versions.** Predictive skill, threshold
calibration and economic effect sizes are explicitly out of scope and stay
shown as unpassed.

Three standing rules, all from `AGENTS.md`:

- **Do not re-implement N02–N06.** Their repairs are in the tree and verified
  (verification Part 2). W5 takes them to acceptance.
- **No workflow engine.** `AGENTS.md §2`/`§3` chose cron plus idempotent
  scripts. W7's scheduler is Windows Task Scheduler and a crontab, not Airflow.
- **`seraph/shared_types/` is ask-gated.** Four packages below touch contracts
  that live there (R02, R05, R06/X04, P05). Each must get explicit human
  sign-off on the type change before code lands.

## 1. The critical path, honestly

```
W0 baseline ──► W1 contracts ──► W2 integrity ──┬─► W3 data ──► W4 live path ──► W6 frontend ──► W8 ops ──► W9 acceptance
                                                └─► W5 news acceptance ──► W6
                                                └─► W7 identity+roles ──────► W6
```

W0 and W1 are blocking and short. W2 (integrity repairs) is the long
model-independent stretch and must precede W4, because connecting real
producers on top of broken time semantics, unfenced leases and payload-blind
idempotency produces evidence that cannot be trusted. W3 (data) and W5 (news
acceptance) and W7 (identity/roles) genuinely parallelise against W2 — they
touch disjoint files and different stores.

What does **not** parallelise: W4 → W6 → W9. One coherent live decision has to
exist before the console can show it, and the console has to be real before an
end-to-end journey means anything. Adding workers there buys nothing.

**Independent, start now, blocks nothing:** the labelled news corpus (W5-C,
external), broker authorization (W4 gate), identity-provider configuration (W7
gate), and the source-database container decision (W0-C). These are the items
that will silently become the critical path if they are left to the end.

---

## W0 — Freeze the baseline *(blocking, ~0.5 day, no code)*

The whole product is 204 untracked paths on top of `51680bb` (X11). Until this
closes, no acceptance result in this project is reproducible and a disk fault
ends it.

| ID | Task | Done when |
|---|---|---|
| **W0-A** | Capture the working tree on a branch. Owner decides commit vs. a tagged archive; `AGENTS.md` and the audit both forbid an unauthorized push. At minimum produce an off-disk copy with a manifest. | A SHA or an archive hash exists for the exact tree every later acceptance result refers to. |
| **W0-B** | Rotate the Kite credential (X05). Delete `kite_credentials.tokens.json` from the repo root; read the token from `%LOCALAPPDATA%\seraph\kite.tokens.json` or an env var. Add a `check_invariants.py` rule that fails if any `*token*`/`*credential*` file exists under the repo root. | Token rotated at the broker; no secret file in the tree; the invariant check catches a reintroduction. |
| **W0-C** | Decide the two stale worktrees (X07). `f79299d` is **not reachable from `main`** — inspect both diffs, salvage or explicitly abandon, then `git worktree remove`. Do not prune casually. | `git worktree list` shows one entry; any salvaged work is on a named branch. |
| **W0-D** | Move loose root artefacts (X09) into `prototype_runs/` or `docs/evidence/`; delete `DEMO-DELETE-ME.md`. | Repo root holds only configuration, launchers and docs. |

---

## W1 — Write the contracts before changing schemas *(blocking, ~2 days, design only)*

Six decision records, in the existing `docs/decisions/DR-NN` series. The audit
is explicit that these must precede schema changes, and four of the six pin
types in the ask-gated `shared_types`.

| ID | Decision record | Must settle |
|---|---|---|
| **W1-A** | DR-11 time semantics | The four distinct instants — bar end, provider receipt, emission availability, decision `as_of` — and which one `ServiceEvaluator` may use. Resolves R02. Includes the publication rule for a bar that arrives after its own end. |
| **W1-B** | DR-12 stream and decision identity | `decision_id` composition including stream and mode (X04); `stream_id` scoping for every read; what "same-time revision" means for a vintage (R04). Resolves R04, R06, X04. |
| **W1-C** | DR-13 checkpoint state identity | Exactly which configuration is state-defining: `q_proc`, fusion `weights`, calendar policy, model-bundle **content** hashes not labels. Resolves R05. |
| **W1-D** | DR-14 job lease and fencing | Lease generation numbers, renewal for bounded long jobs, fenced checkpoint/watermark/completion writes, abandoned-lock recovery. Resolves R10 and therefore N05. |
| **W1-E** | DR-15 portfolio import validity | Finiteness, conflicting metadata on merge, valid-time vs. effective-time, unknown-as-null, server-side binding of preview to original bytes. Resolves P03. |
| **W1-F** | DR-16 scenario versioning | Immutable assumption revisions, stored inputs not just hashes, review bound to `(scenario_id, assumption_version, run_key)`. Resolves P05. |

**W1-G — Pin the migration strategy.** `live/migrations/` and
`store/migrations/` both exist and `store/migrations/__init__.py` is a runner.
Decide now whether runtime SQLite stores migrate forward in place or rebuild,
because W2's schema changes are the first real test of it.

---

## W2 — Integrity repairs *(~8–11 days, model-independent, the long pole)*

Every item here is a current defect with a verified mechanism. None needs a
model choice, a data acquisition or an external service. **Each task lands with
its regression test in the same change** (that is V01, distributed rather than
deferred).

### W2.1 — Market runtime (`seraph/live/`)

| ID | File · line | Fix | Regression test |
|---|---|---|---|
| **R07a** | `live/feed.py:54-55` | Reject nonfinite prices (`math.isfinite`), negative or nonfinite volumes, and empty symbols in `Tick.__post_init__`. Return a typed rejection, don't raise across the loop boundary. | NaN, `inf`, `-inf`, negative volume each rejected; a valid tick in the same batch still lands. |
| **R07b/X03** | `live/bars.py:163-166, 196-199` | **P0 crash.** Replace `_order_key`'s price tie-break with provider sequence where available and a monotone arrival counter otherwise; never compare `None` against `int`. Quarantine the offending tick, never the batch. | The probed `TypeError` case passes; a same-timestamp down-tick and up-tick are handled symmetrically; a malformed tick does not discard its neighbours. |
| **R02** | `live/engine_adapter.py:126-127`, `live/loop.py`, `live/publication.py` | Implement DR-11. `as_of` becomes the decision instant under the availability rule, not unconditionally `max(bar.end)`. | A bar arriving one second after its end yields a correctly timed decision; genuinely future information is still refused. |
| **R03** | `live/inference.py:446-461` | Initialize the Kalman filter from warm-start history, or do not mark those vintages assimilated. | Cold warm-start and equivalent chronological replay reach the same filter state and the same first eligible decision, with no double assimilation. |
| **R04** | `live/inference.py:515-530` | Compare `input_end` before replacing `_latest`; apply DR-12's revision rule for a legitimate correction. | Newer-then-older arrival keeps the newer value; an explicit revision supersedes it. |
| **R05** | `live/inference.py:694-750` | Fingerprint `q_proc`, fusion `weights`, calendar policy and model-bundle **bytes** into the snapshot; reject or rebuild on mismatch; compare `bundle_ids` against live deployments on restore. | Changed process noise or weights refuses to resume; identical configuration resumes byte-identically. |
| **R06/X04** | `live/store.py:378-381, 449-468`; `live/engine_adapter.py:130`; `live/migrations/002_*.sql` | Compare `payload_hash` before declaring a replay; raise a conflict on changed content under the same id. Scope `latest_decision` and `decisions` by `stream_id`. Mint `decision_id` with stream and mode per DR-12. | Same id + same bytes is a replay; same id + different bytes is a conflict; a replay stream can never be read as the current live result. |
| **R08** | `live/bars.py:304-324`; `scripts/run_live.py:91-118, 146-170` | Add `seen_keys` and `last_order_key` to the bar snapshot; call `BarBuilder.snapshot/restore` and a durable feed cursor from `run_live.restore/commit`; document the recoverable boundary between a closed bar and the decision transaction. | Crash mid-bar, after finalization, and before/after decision commit each reproduce the uninterrupted OHLC, volume and decisions. |
| **R09** | `live/feed.py:285-294` | Test `allow_replay` **before** `KITE_API_KEY`. Live mode must fail loudly rather than fall back. | Replay with credentials present opens no socket; live mode never silently degrades. |

### W2.2 — Jobs and workflow state (`seraph/operations/`)

| ID | File · line | Fix | Regression test |
|---|---|---|---|
| **R10** | `operations/jobs.py:248-270, 316-325` | Implement DR-14: a generation number on the lease; `checkpoint`, `clear_checkpoint`, `set_watermark` and the completion record all fenced by `(run_id, generation)`; add `renew()`; add backoff to the retry loop. | An expired writer cannot overwrite or clear a successor's checkpoint, advance its watermark, or record its success. A long job renews instead of being stolen. |

### W2.3 — User-owned state (`seraph/decision_support/`)

| ID | File · line | Fix | Regression test |
|---|---|---|---|
| **P03** | `workspace.py:221-249, 300, 484-492` | Implement DR-15: `math.isfinite` on every parsed and every derived number; reject conflicting sector/ISIN/account on a merged symbol instead of last-write-wins; filter the `current` snapshot by `effective_at <= now`; keep unknown value as null rather than zero; bind commit to the server-held original bytes plus portfolio and currency. | Reordering rows cannot change a sector; NaN or negative implied value rejected; a 2099 snapshot is not current; a mutated preview cannot turn an uploaded 100 into a stored 999; an unpriced position stays explicitly uncovered. |
| **P05** | `scenarios.py:161-213` | Implement DR-16: assumption revisions are append-only rows, not an in-place `UPDATE`; store inputs alongside the hash; bind `review()` to `(scenario_id, assumption_version, run_key)`; reject conflicting concurrent retries. **Correct the docstring**, which currently states a guarantee the code does not provide. | An old run reconstructs after assumptions change; approval of revision 1 never approves revision 2. |

### W2.4 — Unicode-safe identity, one family *(new; audit does not contain these)*

The N02 repair fixed one of three places with the same ASCII-only assumption.

| ID | File · line | Fix | Regression test |
|---|---|---|---|
| **X02** | `news/registry.py:93-96, 299-303` | **P0 latent.** Reuse `model.syndication_tokens`' Unicode-category normalisation in `_norm`. Guard the empty needle in `resolve_asset` as `resolve_entity` and `resolve_place` already do — `"" in needle` currently makes one non-Latin asset name resolve **every** mention. | A Devanagari asset name resolves only itself; an unrelated mention returns `unknown`; the probed false positive fails before and passes after. |
| **X01** | `dashboard/globe_payload.py:116-117, 253` | Make `_slug` script-agnostic, or derive `geo:in-state:` from the curated `place_id` rather than the display name. Two non-Latin names must not share a `geometry_id`. | `उत्तर प्रदेश` and `तमिलनाडु` get distinct geometry ids; existing ASCII slugs are unchanged. |
| **X02b** | `news/curated/*.csv` | Add one non-Latin row to the registry fixtures so this class of bug cannot silently return. All 264 current rows are ASCII, which is why X02 is latent. | The fixture is exercised by the registry and globe tests. |

### W2.5 — Immediate repairs the audit calls the first slice

| ID | File | Fix | Regression test |
|---|---|---|---|
| **U01** | `dashboard/prototype_app.py:101, 125, 139` | Move the early returns after the live and news surfaces so live-only, news-only, archive-only and empty-store startups all render. Render the nested CSRS dict as a scalar score or an explicit unavailable state instead of handing a dict to `st.metric`. | AppTest across the four startup shapes; the real payload shape renders a number or "unavailable", never an exception. |
| **O01** | `pyproject.toml:48-53` | Ship all seven missing assets. `seraph/live/migrations/` and `seraph/news/curated/` have **no `__init__.py`**, so `packages.find` never sees them — add the packages, then the `package-data` globs (a `"seraph.store" = ["*.sql"]` glob does not recurse into `migrations/`). Extend `scripts/verify_packaging.py` to assert every runtime asset, not just the older console ones. | A wheel built and installed outside the checkout creates `runtime_head`, loads nonzero curated counts, and imports the console without the source tree. |
| **O02** | `requirements-research.lock.txt`, `orchestration/original_execution.py:37-38` | Add `pypdf` and the optional live/auth/browser extras to the lock; remove the floating `-e .` resolution (V03). Give `original_execution.py` a supported import path instead of `scripts.*`, or declare `scripts` a shipped package. | A fresh environment from the lock runs archive, news, live `--status` and imports the installed source endpoints; optional features fail with a clear message. |

---

## W3 — Data foundation *(~6–9 days, parallel with W2, gated on external access)*

| ID | Task | Blocked on |
|---|---|---|
| **D01** | Stand up the read-only source connection against the intact 9.2 GB `seraphvarya_seraph_pgdata` volume on 5433, and populate the experimental destination. Produce a read-only identity/count/date census per store. **Do not apply test markers or migrations to the source** — `provision_test_db.py`'s three guards already enforce the test side and must stay. | Owner decision on exposing the source volume; the password must come from outside the repo. |
| **D02** | A scheduled daily/intraday acquisition pipeline: idempotent upserts, watermarks, missed-session recovery, quality failures, fresh-universe updates. Existing `ingestion/*` scripts are not an installed scheduler. | D01, **R10** |
| **D03** | Complete the session/holiday/special-session registry and its update policy; `market_calendar/sessions.py:24-26` declares itself partial. `live/clock.py` must never turn guessed coverage into permission to publish. | Source access (exchange circulars) |
| **D04** | Identifier, corporate-action, adjusted/raw price and universe provenance through the operational path; replace `run_live.py:61`'s five hardcoded symbols with the real point-in-time universe. | D01–D03 |
| **D05** | Wire macro vintages, tariff events and FII/DII acquisition into scheduled storage. Every field needs units plus native observation, publication and receipt times. **Do not invent tariff-decay or economic coefficients.** | D01–D02, external data |
| **D06** | Official benchmark ingestion and versioned return alignment for the FR41 overlay; documented past holdings and prices for portfolio history. Score sparklines are not a benchmark. | D01, D04, P03 |

Standing constraint: the ETF contamination fix means the universe must be
rebuilt under the ISIN filter before D04's provenance can be certified.

---

## W4 — The real live path *(~7–10 days, gated on W2 + W3)*

This is where `NullProducers` is replaced. The `Producers` protocol
(`engine_adapter.py:43-50`) is clean, so the work is bounded and well-shaped.

| ID | Task | Notes |
|---|---|---|
| **R01a** | `HawkesBarProducer` — real pillar vintages from closed bars, warm-started from the durable count window in `LiveStore`. | Needs R08's durable state. Preserve the NB-INAR(1)+ToD model and the existing basket-selection policy. |
| **R01b** | `DailyVintageProducer` — RMT and Hamilton daily vintages read from the store, with deployment eligibility. | **Hamilton's current scientific exclusion stands.** Implement, execute diagnostically, withhold honestly. Do not invent eligibility to satisfy a checklist. |
| **R01c** | Wire both into `scripts/run_live.py:87` behind an explicit mode flag; keep `NullProducers` reachable and keep `StaticProducers` for replay. | Record controlled-feed proof and authorized real-feed proof **separately**. A synthetic producer must never be presented as live. |
| **R11** | Separate worker heartbeat/activity/error from score freshness; commit only newly evaluated decisions (`run_live.py:151`); add session supervision, graceful shutdown and next-session scheduling. | Idle, stopped, failed and producing must be four visibly different states. |
| **R12** | Versioned daily model deployment plus a prospective append-only output ledger: generated and withheld outputs, inputs, deployments, latency, retention policy. `prediction/app.py:323` currently only reads saved artefacts. | An incremental cycle produces a new dated output or an explicit abstention; a repeat is idempotent; later labels attach without rewriting the original forecast. |

---

## W5 — News: acceptance, migration and breadth *(parallel with W2/W4)*

**W5-A — close the existing repairs (~2 days, no new implementation).** This is
the plan's biggest correction to the audit.

| ID | Work | Note |
|---|---|---|
| **N02-acc** | Operator procedure for the stored-corpus regroup using `acquisition.py:859-883`'s `dry_run`/`regrouped` path; prove raw history and frozen manifests survive; prove the 28-story and 9-story collisions are gone. | Code done. **Data not migrated.** |
| **N03-acc** | A→B→A fixture through the normal poll path; historical B stays inspectable. | Code done. |
| **N04-acc** | One-document-budget fairness test; then extend fairness **across** sources — the budget is still per-source `max_documents=3`. | Code mostly done. |
| **N05-acc** | Closes automatically when **R10** closes; add the killed-worker-replacement test. | Reporting half done. |
| **N06-acc** | Promote the saved 08:00-replay / 10:00-heartbeat counterexample to a regression test through `roles.py` and the console, not only `news_view`. | Code done. |
| **N01** | Close A01–A05 against these exact code versions with unchanged preregistered thresholds. | — |

**W5-B — remaining news engineering (~8–11 days).**

| ID | Task |
|---|---|
| **N07** | Cross-document instrument linking; analyst correction/retraction/merge/split review; legal timeline. A repeal must deactivate the old duty — `supersedes` currently needs the link supplied. |
| **N08** | Structured rights and retention enforcement per use (fetch / process / store / display / export). A boolean `may_store_full_text` plus prose is not per-use control. Table headings, units and document spans. |
| **N09** | Breadth by a **source × sector × mechanism matrix**: DGFT/CBIC and Indian policy, sector operations, energy, weather, pharma, foreign trade channels. Do not count two fixed historical pages as broad feeds or 54 NTPC edges as diversified coverage. **Gated on W2.4** — adding one non-Latin name before X02 is fixed arms a silent false-positive resolver. |
| **N10** | Persist derived revisions with source/document/parser/extractor/registry/rule identities and input hashes. Frames currently rebuild on read from current code and CSVs; `version_manifest()` has no production caller. |
| **N11** | Finish the three role workflows beyond summary panels: professional document comparison and product/country matrix; regulator review queue, coverage and policy timeline; retail saved relevance and per-position evidence. |
| **N12** | Extend the evaluator. `REQUIRED_SLICES` is currently seven slices with **no F1, no supported-event precision, no entity/location role scoring, no duplicate or unsupported-claim error, no abstention metric and no source/sector/language slices**. Keep the independent-review, corpus and chronological-lock checks. |

**W5-C — the labelled corpus (external, start now).** The gate reports **0 of
600 documents and 0 of 2 reviewers**, every slice `UNEVALUATED` (X08). N12's
metrics can be built and tested against synthetic gold, but no real accuracy
number exists or can exist until this corpus is labelled by two independent
reviewers. It needs its own owner and its own schedule, and it must not block
W5-B.

---

## W6 — The visible product *(~6–8 days, gated on W4)*

| ID | Task |
|---|---|
| **U02** | Independent two-second live refresh and explicit score freshness. `prototype_app.py:92` calls `read_current` with no `max_age`, so fresh head activity validates an arbitrarily old score. Edits, selected evidence and globe camera must survive a refresh. |
| **U03** | Feed the **main** console a coherent current decision bundle. A live metric panel above an archive-backed page is not a live console; `project_run` still builds from the selected historical point. Every panel must name the same decision and input versions, and live / replay / demo must never silently substitute. |
| **U04** | Reconcile every surface against real capability: the method text still says news "Not connected"; retained-body limitations go stale; role weights need sane formatting. Finish measured pillar diagnostics, the benchmark chart, the portfolio map and source-driven asset/sector detail where data exists. |
| **X10** | Decide `dashboard/app.py` and `prediction/app.py` (new). Three Streamlit entry points exist and one has a launcher. Adopt them with acceptance journeys or mark them research-only and exclude them from the release. |
| **U05** | In-scope parts only: weather advisories and asset intersections, commodity connectors where permitted; plus keyboard navigation, non-colour cues, reduced motion, responsive layout and a WebGL fallback. Static cards stay as labelled previews and are never computed on. |
| **P08** | Scoped institution submissions and position valuation/history. Define schema, units and unknown-state UI now; propagation maths and calibrated risk metrics remain science dependencies. |

---

## W7 — Identity and role workflows *(~8–11 days, parallel with W2–W4)*

| ID | Task |
|---|---|
| **P01** | Real login/logout, server-resolved principal, grants, session expiry and revocation, identity-scoped caching, wired into `prototype_app.py` and `console_backend.py`. `prototype_app.py:142` is a `st.session_state` role switch; the 824-line identity package is unreferenced by the console. Raw-claim validation stays behind a signature-verifying provider. The local demo must remain explicitly isolated. |
| **P02** | Connect `WorkspaceStore` portfolios, import preview, history, watchlists and preferences to the canonical UI. Holdings currently live in `st.session_state['console_portfolios']`. **Reuse the existing library, do not rewrite it.** |
| **P04** | Supply real measured sector flags to portfolio arithmetic, preserving identity, as-of and coverage. `console_backend.py:270` passes `{}`. Keep this separate from news hypotheses; complete position-to-news evidence and dedup across routes. |
| **P06** | Institutional create / save / run / compare / review / export using `ScenarioStore`; connect supported news tariff scenarios. Current console shock and policy calls are transient. |
| **P07** | Regulator cases: assignment, evidence pinning, review, decision, closure and reopening, versioned exports, using `CaseStore`. The run action journal is not this workflow. |

Gate: real cross-user verification needs an identity provider. Code can be
complete while that is unavailable, but an unexercised provider integration is
not verified delivery.

---

## W8 — Operate, distribute, recover *(~7–10 days)*

| ID | Task |
|---|---|
| **O03** | One supported service lifecycle for market, daily jobs and news — startup readiness, restart limits, graceful stop, singleton ownership, log rotation, bounded disk growth. **Cron / Task Scheduler definitions, not a workflow engine.** `launch_prototype.ps1` starts news and Streamlit only, and no scheduler definition exists anywhere in the tree. |
| **O04** | A real outbox/alert delivery worker and operator status. The live outbox and `AlertLedger` exist with no transport consumer. Define dedup, retry, dead-letter, acknowledgement and snooze. Replay and demo must be incapable of emitting production alerts; external recipients only with owner authorization. |
| **O05** | Demonstrated backup and restore across PostgreSQL, archive, live, news, identity, workspace, case, scenario and job stores plus content-addressed blobs. Handle SQLite WAL safely, secrets separately, first-seen history immutably. `OPERATIONS.md` has no drill. Record measured recovery duration and loss window. |
| **O06** | Deployment access controls, secret configuration, HTTPS and at-rest policy, scoped export/view audit, retention. Several SQL "append-only" protections cover `UPDATE` only and need a deletion threat-model review. **Includes W0-B's secret-at-rest rule as a standing control.** |
| **O07** | Measure the engineering targets: bar-to-screen and news-to-screen latency, large history and registry performance, concurrency, outage behaviour, long-running memory and disk. In-memory decision and history lists need explicit bounds. A fast unit test is not this measurement. |

---

## W9 — Verification and release *(~5–7 days, last)*

| ID | Task |
|---|---|
| **V01** | Every counterexample in the audit's `runtime-probes.jsonl` and `input-portfolio-probes.jsonl`, plus X01/X02/X03's probes, becomes a regression test **against the normal caller** — `main`, the dispatcher, the worker chain — not an isolated helper. W2 lands most of these inline; this is the sweep for the remainder. |
| **V02** | CI gaps. Add a guarded migration job, an installed-wheel smoke job, and a JS/browser job. **The JS job needs a `package.json` first (X06):** `package-lock.json` exists with no manifest, and nothing in the tree invokes `tests/js/*.mjs`. Replace the `postgresql://disabled` DSN with explicit completed/skipped environment reporting. Widen the branch triggers. |
| **V03** | An immutable acceptance manifest: code, config, model, data, schema and registry versions, input ranges, commands, output hashes. **Depends on W0-A** — an uncommitted tree cannot be reproduced. Separate still-valid research results from results invalidated by W2's changes. |
| **V04** | One canonical end-to-end journey per role plus recovery and release checks: start → acquire → compute or withhold → persist → update the main UI → inspect evidence → save work → restart → recover. No fixture injection into the browser standing in for the normal path. Controlled-feed proof stays labelled separately from real-service proof. |
| **O08** | Reconcile the stale registers into one acceptance index. `DEVELOPMENT-STATUS.md`, `IMPLEMENTATION-STATUS.md`, `NEXT-SESSION.md`, `PLAN-NEXT.md`, `DEVELOPMENT-PLAN.md`, `DEVELOPMENT-HANDOFF.md` and three audit documents now overlap and disagree. Preserve old evidence; every closed ticket links code version and acceptance evidence. |

---

## 2. Current test and evidence baseline

Whatever W2 changes, it changes from here:

- **`pytest tests -q`: 1701 passed, 14 skipped, 1215 s** (independent re-run,
  18 October). Ten of the skips are the `seraph_test_*` Postgres-gated tests
  with the test container down; the other four are
  `tests/contract/test_ct3_jump_sufficiency.py:149,179,191,198`, "not enough
  intraday bars yet". No failures, no errors.
- The audit's own run, with the test container up, was **1705 passed, 4
  skipped, 1307 s** — which that audit mistakenly recorded as incomplete.
- **1715 tests collect cleanly.** The audit's `full-suite.xml` recorded
  `tests="1709"` at 20:44 the same day: six tests were added to this tree while
  its suite was running. Re-probe before implementing any ticket.
- **With the test database provisioned: 98 passed, 0 skipped** across the four
  DB-gated modules.
- The suite is green and covers **none** of the 29 confirmed defects. That gap
  is the point: a large passing suite is not acceptance, and V01 is what closes
  the distance.

Run the expensive suite only after a change that could affect it. Reuse the
saved results otherwise — this is explicit audit guidance and it holds.

---

## 3. Sequencing, effort and parallelism

| Phase | Workstreams | Working days | Can run alongside |
|---|---|---|---|
| 1 | W0 + W1 | 2.5 | nothing (blocking) |
| 2 | W2 | 8–11 | W3, W5-A, W7 |
| 3 | W3 → W4 | 13–19 | W5-B |
| 4 | W5 (A then B) | 10–13 | W2/W4 |
| 5 | W7 | 8–11 | W2/W4 |
| 6 | W6 | 6–8 | — |
| 7 | W8 | 7–10 | W9 prep |
| 8 | W9 | 5–7 | nothing (final gate) |

**Serial critical path: ~42–55 working days.** With W3, W5 and W7 genuinely
parallel against W2/W4 and one owner per workstream, the calendar compresses to
roughly **30–38 working days**. It does not compress below that by adding
people: W4 → W6 → W9 is inherently sequential, and more workers cannot resolve
a missing contract.

Per `AGENTS.md §8`, keep one session per component and do not let a single diff
span two owners' directories. W2's nine runtime items are one owner's work;
W5's news items are another's.

---

## 4. Definition of done, per the audit's own criteria

A package closes only with the acceptance evidence its row names. Beyond that,
eight system-level gates:

1. The documented launcher brings up the application **and** every required
   worker, with a useful empty state and explicit missing-configuration
   messages.
2. Real authorized inputs reach real producers and the main console;
   diagnostic, ineligible and missing outputs are withheld honestly.
3. Every visible promised operation works through the normal UI or API path,
   persists, and respects **server-side** identity in shared mode.
4. Inputs, decisions, evidence, scenarios and corrections survive retries,
   crashes and restarts without losing history or accepting conflicting
   identities.
5. Current, stale, replay, scenario, estimate, unavailable and fabricated
   content stay distinguishable at both the datum and the screen level.
6. A separately installed build contains every asset, data file and migration,
   and restores from an **exercised** backup.
7. Acceptance and known limitations are recorded against exact versions; science
   gates still show as unpassed where they are.
8. Controlled-feed software proof and real-service proof are recorded
   separately and never conflated.

**Not required for engineering completion:** AUC, lead time, calibration,
economic effect size, causal attribution, or any claim of crisis-prediction
skill. A complete experimental platform with honest unvalidated outputs is a
legitimate milestone, and the plan says so on every screen that needs it.

---

## 5. Risks and external gates

| Risk | Consequence | Mitigation |
|---|---|---|
| **W0-A slips** | Every acceptance result stays unreproducible; one disk fault ends the project. | Nothing else starts first. It is half a day. |
| Broker authorization unavailable | W4's real-feed proof cannot be recorded. | Deliver controlled-feed proof, label it as such, keep the real-feed row open rather than claiming it. |
| Identity provider unavailable | W7's cross-user verification cannot run. | Ship the code behind a signature-verifying provider interface; keep the local demo explicitly isolated and the verification row open. |
| Source data gaps (holdings history, benchmark periods, macro vintages) | D03/D05/D06 cannot be fully certified. | Make the gap visible in the UI and the manifest; never forward-fill a future price or invent a coefficient. |
| **N09 delivered before W2.4** | A silent false-positive entity resolver puts wrong arcs on the globe with `status='resolved'`. | Hard dependency: X02 and X01 land first. This is the single most important new sequencing constraint in this plan. |
| Labelled corpus never arrives | N12's metrics have no real denominator. | Build and test metrics on synthetic gold; keep the gate failing honestly at 0/600 rather than lowering the threshold. |
| Audit drift repeats | Work gets redone, as N02–N06 nearly were. | **Re-probe before implementing any ticket.** A stale audit is not an overwrite instruction — the audit says this of itself, and verification Part 2 is what happens when it is ignored. |

---

## 6. First slice, concretely

Start exactly here, in this order:

1. **W0-A** — capture the baseline. Half a day, blocks everything.
2. **W0-B** — rotate the Kite token and get it out of the tree.
3. **O01 + O02** — packaging and dependencies. A wheel that cannot create its
   own schema makes every later integration look broken for the wrong reason.
4. **U01** — four startup shapes and the CSRS scalar. Smallest possible change
   with a visible result.
5. **R09** — one reordered condition in `resolve_feed`. A replay that opens a
   broker socket is the most dangerous defect in the tree relative to its fix
   size.
6. **R07b/X03** — the `None`-volume crash, before any producer work.
7. **X02** — the latent resolver, before any N09 breadth work.
8. Then **W1**'s six decision records, then the rest of **W2**.

Items 2 through 7 are each under a day and each removes a failure that would
otherwise make later integration look broken. **Re-read the current working
tree before editing any of them** — the news repairs are exactly why.

Do not push or commit until the owner asks. This document records pending work
and does not claim any of it was performed.
