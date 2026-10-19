# SERAPH — verification of the engineering completion audit

Verification date: 18 October 2026 (later the same day than the audit).
Checkout: `C:\Users\Arlop\Downloads\SERAPH VARYA\SERAPH Varya`, base commit
`51680bb`, working tree with 31 modified and 204 untracked paths.

Subject: [SERAPH-ENGINEERING-COMPLETION-AUDIT-2026-10-18.md](SERAPH-ENGINEERING-COMPLETION-AUDIT-2026-10-18.md)
(55 work packages). This document re-derives that audit's claims from current
source, records which are still true, which have been repaired since it was
written, and adds findings it does not contain. The development plan built on
it is [SERAPH-ENGINEERING-DEVELOPMENT-PLAN-2026-10-18.md](SERAPH-ENGINEERING-DEVELOPMENT-PLAN-2026-10-18.md).

No source file was modified, no commit, push, migration or data mutation was
performed for this verification.

## Verdict on the audit

**The audit is substantially correct and unusually well evidenced.** Every
market-runtime, role-workflow, frontend, operations and verification claim
checked below reproduced in current source at the mechanism level. Its
`application.json` and `packaging.json` probes are genuine and I reproduced
their conclusions independently.

Three corrections matter enough to change what should be built:

1. **The news section is stale.** The audit flags A01–A05 as repaired but
   presents N02, N03, N04 as current P0/P1 defects and N05's reporting half as
   broken. All four are **already repaired in this working tree**. Treating
   them as open would mean rewriting working code — exactly the failure mode
   the audit's own closing paragraph warns about. What remains for them is
   corpus migration, regression tests and acceptance, not implementation.
2. **The audit under-reports its own test evidence.** It records
   `engineering-audit-2026-10-18/full-suite.log` as "incomplete at
   inspection". That file is complete: **1705 passed, 4 skipped in 1307.38 s
   (21:47)**, the four skips being `test_ct3_jump_sufficiency` wanting more
   intraday bars. The suite is green; it simply does not cover the defects
   below.
3. **Eleven findings are missing**, two of which are P0-class and one of which
   I reproduced as a hard crash in the live bar path. They are registered as
   X01–X11 below.

The audit's priority vocabulary, its "finish development now, science later"
boundary and its dependency-aware completion order are all sound and are
carried into the plan unchanged.

## Method

- Re-read each cited file and located the cited mechanism by content, not by
  line number — many line numbers had drifted by one to thirty lines.
- Ran `pytest tests --collect-only`: **1715 tests collect cleanly**.
- Ran the full suite independently: **1701 passed, 14 skipped in 1214.60 s**
  (`1701 + 14 = 1715`). The ten extra skips versus the audit's run are the
  `seraph_test_*` Postgres-gated tests — the test container was not up for my
  run (`ConnectionRefusedError [WinError 1225]`), exactly as `tests/conftest.py`
  intends. No failures, no errors.
- Executed targeted runtime probes with `python -I` against the real modules
  for the three findings where a static read was not conclusive (X01, X02,
  X03). Their outputs are quoted inline below.
- Counted curated registry rows, news source registrations, Streamlit entry
  points, SQL assets, lockfile contents and CI jobs directly.
- Read the audit's own evidence files (`application.json`, `packaging.json`,
  `full-suite.log`) and the independent
  `frozen-corpus-evaluation-2026-10-18.json`.

Not attempted: a live broker connection, a fresh dependency install in a clean
environment, a browser traversal, a Postgres census against the 9.2 GB source
volume (no container serves 5433), or any model refit.

---

## Part 1 — Confirmed as stated

Mechanism verified in current source. Line numbers are this checkout's.

| ID | Mechanism confirmed | Location |
|---|---|---|
| D01 | Port 5433 refuses; 5434 serves `seraph_research` with `daily_prices=0`, `intraday_bars=0`, `macro_covariates=0`, `universe_membership` absent. The 9.2 GB source volume `seraphvarya_seraph_pgdata` is intact but unattached. | `application.json`, [DATABASE-STATE-2026-10-18.md](DATABASE-STATE-2026-10-18.md) |
| D03 | `SPECIAL_SESSIONS` is documented as deliberately partial — "registers only sessions this project has verified" — and the module itself says other historical special sessions exist. | `market_calendar/sessions.py:24-26` |
| D04 | The live runner still defaults to five hardcoded symbols. | `scripts/run_live.py:61` |
| O01 | `[tool.setuptools.package-data]` covers `seraph.store = ["*.sql"]` and `seraph.ingestion = ["*.csv"]` only. Probe: 7 missing runtime assets, `OperationalError: no such table: runtime_head`, curated registries ship empty. | `pyproject.toml:48-53`, `packaging.json` |
| O02 | `requirements-research.lock.txt` (63 lines) omits `pypdf`, `kiteconnect` and any browser driver. `original_execution.py` imports `scripts.write_hawkes_production` and `scripts.build_observations`, which no wheel ships. | `requirements-research.lock.txt`, `orchestration/original_execution.py:37-38` |
| O03 | `launch_prototype.ps1` starts the news supervisor and Streamlit only. `operations/jobs.py` states "Nothing here schedules anything itself. Cron (or Task Scheduler) invokes the…". No crontab, systemd unit or Task Scheduler definition exists anywhere in the tree. | `launch_prototype.ps1`, `operations/jobs.py:20` |
| R01 | `attach(loop, service, producers=NullProducers())`. `NullProducers` is honest — every pillar returns a structural absence and nothing is publishable. | `scripts/run_live.py:87`, `live/engine_adapter.py:54-80` |
| R02 | `as_of = max(b.end for b in bars)` while `now=stamp` is the real arrival instant. The decision is timestamped at the bar end regardless of when the bar actually became available. | `live/engine_adapter.py:126-127` |
| R03 | `warm_start` calls `standardizer.assimilate(vintage)` and sets `_assimilated[producer]`, but never touches `self.filter`. The filter stays at its prior while the vintages are marked consumed, so `process()` will not assimilate them either. | `live/inference.py:458-461` |
| R04 | Vintages are sorted by `emission_available_at` and then assigned `self._latest[producer] = vintage` unconditionally. `input_end` is never compared, so a late-arriving older vintage replaces a newer input. | `live/inference.py:515-530` |
| R05 | `restore()` validates `pipeline_version` and `calendar_id` only. **Amplified:** `q_proc` and the fusion `weights` are not in the snapshot payload at all, so a changed process-noise or weight configuration resumes silently; and `snapshot.bundle_ids` are labels that `restore()` never compares against current deployments. | `live/inference.py:694-750` |
| R06 | `commit_decision` returns `dict(existing, replayed=True)` before any payload comparison. `latest_decision` and `decisions` query `live_decisions` with no `stream_id` predicate while `head()` is stream-scoped. | `live/store.py:378-381, 449-468` |
| R07 | `Tick.__post_init__` rejects only `last_price <= 0`; `float('nan') <= 0` and `float('inf') <= 0` are both `False`, so nonfinite prices enter OHLC. `volume_traded` is unvalidated. `_order_key` uses price as the tie-breaker, so at one timestamp a rising tick is accepted and a falling tick is quarantined `out_of_order` and dropped. | `live/feed.py:54-55`, `live/bars.py:163-166, 196-199` |
| R08 | `BarBuilder.snapshot()` omits `seen_keys` and `last_order_key`; `run_live.restore` calls `service.restore` only and never `BarBuilder.restore` or a feed cursor restore; `run_live.commit` records closed bars but persists no bar-builder state. | `live/bars.py:304-324`, `scripts/run_live.py:91-118, 146-170` |
| R09 | `resolve_feed` tests `os.environ.get("KITE_API_KEY")` **before** `allow_replay`. Audit probe: explicit replay with credentials selected `KiteTickerFeed`, `is_live=true`. | `live/feed.py:285-294`, `application.json` |
| R10 | `checkpoint()`, `clear_checkpoint()` and `set_watermark()` carry no owner or generation fence; `clear_checkpoint` has no `run_id` predicate at all. There is **no `renew()` method**, so a job exceeding `lease_minutes` (30) has its lease taken over while still running. On success the worker calls `clear_checkpoint` then records `succeeded` with no ownership re-check. | `operations/jobs.py:248-270, 316-325` |
| R11 | `commit` takes `evaluator.results[-1]`, which is not bound to the `decision` argument of the same call. Score freshness is read from `head.updated_at`. | `scripts/run_live.py:151`, `dashboard/current_reader.py:98-116` |
| R12 | `prediction/app.py` reads saved forecast artefacts and instructs the operator to "Run scripts/run_prediction_experiment.py … then refresh this page". No append-only prospective output ledger exists. | `prediction/app.py:323` |
| P01 | `role = st.session_state.setdefault('console_role','retail')` and a client `op='role'` event switches it. No `Principal`, no `IdentityRegistry` call, no session expiry. The 824-line identity package is unreferenced by the console. | `dashboard/prototype_app.py:142, 226-229` |
| P03 | `number()` returns `float(str(value)…)`, which accepts `"nan"`, `"inf"` and `"Infinity"` without raising; `quantity < 0` is `False` for NaN; `value = quantity * price` then propagates NaN. `workspace.py` contains no `isfinite` check anywhere. `PRIMARY KEY(snapshot_id, symbol)` makes row order decide a merged holding's sector/account. The `current` snapshot query is `ORDER BY effective_at DESC LIMIT 1` with no `<= now` filter, so a 2099-effective snapshot is "current". | `decision_support/workspace.py:221-249, 300, 484-492` |
| P04 | `portfolio_overlay(holdings,{})` — sector flags are an empty dict, with an honest `basis` string. | `dashboard/console_backend.py:270` |
| P05 | `revise_assumptions` runs `UPDATE scenarios SET assumptions=?, assumption_version=assumption_version+1`, **destroying the previous assumption text**. Its docstring claims "The old runs keep pointing at the old set", which is false — only the integer version survives. `record_run` stores `inputs_hash` and not the inputs. `review()` inserts against `scenario_id` and `seq` with no binding to `assumption_version` or `run_key`. | `decision_support/scenarios.py:161-213` |
| U01 | `main()` returns on `not path.exists()` at line 125 and on `not runs` at line 139, both **before** the news surfaces, and the LIVE RUNTIME expander is constructed after line 125. `st.metric('CSRS', payload['csrs'])` passes the nested dict produced by `csrs.model_dump()`. Probe: live-only app → 1 info message, 0 metrics, 0 radios; persisted panel → `Invalid value type … Provided type: dict`. | `dashboard/prototype_app.py:101, 125, 139`, `application.json` |
| U02 | `read_current(store, mode=mode)` — `max_age` defaults to `None`, and `too_old` is computed only `if max_age is not None`. No two-second polling path calls it. | `dashboard/prototype_app.py:92`, `dashboard/current_reader.py:121-154` |
| U03 | `project_run` builds every main panel from the selected historical run/point; the live panel is a separate expander above the page. | `dashboard/prototype_app.py:143-164` |
| N12 | `REQUIRED_SLICES` is exactly seven: `link_precision`, `class_recall`, `negative_specificity`, `field_numeric`, `field_unit`, `field_action`, `field_legal_stage`. There is no F1, no supported-event precision, no entity/location role scoring, no duplicate or unsupported-claim error metric, no abstention metric and no source/sector/language slices. | `validation/news_gate.py:78-82` |
| V02 | CI runs five pytest matrix legs with `SERAPH_DB_DSN=postgresql://disabled…`, installs the stale lock, and has no wheel-build, no migration and no JS or browser job. Triggers only on `main` and `astra-version-codebase`. | `.github/workflows/astra.yml` |
| V03 | The lockfile ends in `-e .`, which resolves `pypdf>=6.21.1` unpinned at install time. A "locked" environment therefore floats a dependency. | `requirements-research.lock.txt:48` |

---

## Part 2 — Already repaired: do not re-implement

These are the audit's own statements that current source contradicts. Each has
working repair code. **The remaining work is migration, regression tests and
acceptance closure — not reconstruction.**

| ID | Audit says | Current source | What actually remains |
|---|---|---|---|
| **N02** | "`news/model.py:155` still tokenizes `[a-z0-9]+`, collapsing unrelated Hindi headlines." | `syndication_tokens()` tokenises by **Unicode general category** (`Lu Ll Lt Lm Lo Nd Nl No Mn Mc`), explicitly including the combining marks `\w` drops; `MIN_GROUPING_TOKENS = 2` gives an unmergeable headline a document-scoped key rather than merging it; `SYNDICATION_KEY_VERSION = "syn/2"` records which rule produced stored groups. The code comment names the exact 28-story and 9-story collisions it fixes. | The **stored corpus** still holds `syn/1` groups. `acquisition.py:859-883` has a `dry_run`/`regrouped` rebuild path — it needs an operator procedure, a frozen-manifest preservation check and acceptance. Code: done. Data: not migrated. |
| **N03** | "`acquisition.py:445` treats a previously seen content hash as unchanged before checking the current revision." | A `document_states` table carries `(source_id, reference, sequence, content_hash, observation_id, story_id, observed_at, reverted)`. The unchanged test is now against the **latest sequence** (`state[1] == item.content_hash`), with `_backfill_document_states` for pre-timeline stores, a `reverted` flag, and `story_id` re-derivation on reversion so A → B → A mints a distinct story. | Acceptance only: an A→B→A fixture through the normal poll path, and a check that historical B stays inspectable. |
| **N04** | "Successful retrieval cache is process-local and repeated leading items can consume the budget. `enrichment.py:91`." | A persistent `documents` table with `refresh_after` and `DOCUMENT_REFRESH_DAYS = 7`; the budget set is chosen **before any fetch**, over the whole candidate set, excluding documents that already have fresh text, ordered **least-recently-attempted first**. The docstring describes the exact starvation it closes. | **Cross-source** fairness: the budget is still per-source (`max_documents=3` per call), so one source's queue cannot starve another's but a slow source's share is not bounded globally. Plus the one-document-budget acceptance test. |
| **N05** | "The loop ignores `jobs.run` outcome then reports waiting/running." | `run_news.py:767-786` branches explicitly: `lock_unavailable` → `beat(status="failed", activity="lock_unavailable")`; any other non-`succeeded` → `beat(status="failed", detail=…)`; success → `beat(status="running")`. Zero-fetch cycles can no longer read as successful. | The **root cause is R10**, which is open: the generic lease is still unfenced and unrenewable, and `reconcile_lock` requires the exclusive OS lock. N05 closes when R10 closes. |
| **N06** | "Strict historical news views must not show future heartbeat/gap/source metadata." | `news_channel(..., strict_replay=...)` threads strictness through `master.as_of(decision_ts, strict=…)`, `store.worker_state(decision_ts, strict_replay=…)`, `store.coverage_at(…, strict_replay=…)` and `sources_at(decision_ts)`, with a documented rationale that liveness is not versioned so a future heartbeat is omitted rather than reconstructed. | Acceptance only: the saved 08:00-replay-shows-10:00-heartbeat counterexample as a regression test through `roles.py` and the console, not just `news_view`. |
| — | "A separate `engineering-audit-2026-10-18/full-suite.log` is incomplete at inspection; it is not counted as a completed pass." | The file is complete: `1705 passed, 4 skipped in 1307.38s`. The four skips are `tests/contract/test_ct3_jump_sufficiency.py` lines 149/179/191/198, all "not enough intraday bars yet". | Nothing. The pass is real. It does not cover any defect in Part 1 or Part 3 — which is the actual finding. |

**Direct evidence of the staleness mechanism.** `full-suite.xml` records
`tests="1709"` at `2026-10-18T20:44:58+05:30`. The same suite now collects
**1715**. Six tests were added to this working tree *while the audit's own suite
was running*. That is why its news section describes code that no longer
exists, and it is the strongest possible argument for the plan's standing rule:
re-probe before implementing any ticket.

**Consequence for the plan.** The audit's completion-order step 2 ("Repair
integrity before connecting producers … N02/N03/N05/N06") shrinks to R02–R08,
R10, P03, P05 and the N0x acceptance work. That is a materially smaller and
differently shaped slice than the audit implies.

---

## Part 3 — Findings the audit does not contain

Eleven items. X02 and X03 are P0-class. X03 is reproduced as a hard crash.

### X03 · P0 · Defect — `BarBuilder.add` crashes on a `None` volume tick

`_order_key` returns `(ts, last_price, volume_traded)` and `volume_traded` is
`int | None`. When two ticks share a timestamp and price and one carries no
volume, the tuple comparison at `bars.py:196` reaches `None < int`:

```
add1 []
X03 CONFIRMED: TypeError '<' not supported between instances of 'NoneType' and 'int'
```

(probe: two `Tick`s at `2026-10-16T10:00:01+05:30`, price `100.0`, volumes `5`
then `None`.)

This is not a quarantine — the exception escapes `add()` and **aborts the whole
batch**, discarding every remaining tick in it. A Kite ticker in LTP mode, or
mixed full/LTP packets for one instrument, produces exactly this shape.
`live/bars.py:163-166, 196`. It must be fixed inside R07's validation work; it
is the reason R07 cannot be deferred behind R01.

### X02 · P0 · Latent defect — one non-Latin registry name resolves every mention

`registry._norm` strips to `[^a-z0-9 ]+`, so a Devanagari name normalises to the
empty string. `resolve_asset` then tests
`needle in _norm(a.name) or _norm(a.name) in needle` — and `"" in needle` is
always `True`:

```
resolve_asset("Reliance refinery") -> status='resolved', entity_id='as:hindi'
resolve_asset("anything at all")   -> status='resolved', entity_id='as:hindi'
```

(probe: a single asset named `एनटीपीसी संयंत्र`.) Every mention in the corpus
silently resolves to that one asset, with `status='resolved'` and no ambiguity
flag — wrong arcs on the globe and wrong assets attached to events, presented
as confident links.

Currently **latent**: all 264 curated rows have ASCII names (verified per file:
assets 54, entities 47, exposure 90, places 42, source_places 31). It arms the
moment N09's non-English and Indian-policy coverage adds one Devanagari or
Tamil name — i.e. exactly when the audit's own N09 is delivered.
`news/registry.py:93-96, 299-303`. `resolve_entity` (`:213`) and
`resolve_place` (`:282`) do guard the empty needle; `resolve_asset` does not.

### X01 · P1 · Defect — the globe slug collapses every non-Latin place to one id

`globe_payload._slug` is `re.sub(r"[^a-z0-9]+", "-", …).strip("-")`:

```
geo:in-state:uttar-pradesh   <- 'Uttar Pradesh'
geo:in-state:                <- 'उत्तर प्रदेश'
geo:in-state:                <- 'तमिलनाडु'
```

Two different states share one `geometry_id`, so the renderer pins both to the
same mesh. `_slug(place.name)` at `globe_payload.py:253` is the live path;
`_slug(asset_id)` and `_slug(place_id)` take curated ASCII ids and are safe
today. Same bug class as N02 and X02 — the plan treats all three as one
work item.

### X04 · P0 · Defect — the decision id carries no stream or mode

`decision_id = f"live:{as_of.isoformat()}"` (`engine_adapter.py:130`). A replay
pass and a live pass over the same bar end mint the **same id**. Combined with
R06's payload-blind `commit_decision` replay return, a replay commit is
accepted as the existing live decision and reported `replayed=True`. The audit
names the read side of this (`latest_decision` is not stream-scoped) but not
the minting side, and fixing only the read side leaves the collision.

### X08 · P1 · Blocking data gap — the gold news corpus is empty

`frozen-corpus-evaluation-2026-10-18.json` reports `gate_passed: false` with
**0 of 600** documents, **0 of 2** reviewers and every one of the seven slices
`UNEVALUATED (only 0 scored example(s))`. The gate is behaving correctly; there
is simply no corpus. The audit's N12 describes the evaluator work and defers
"independent labels and real accuracy" to science, but never states that the
denominator is currently zero — so N12's engineering deliverable has nothing to
run against and cannot be acceptance-tested beyond synthetic fixtures. The plan
splits this into N12-engineering (metrics on synthetic gold) and a separate
labelled-corpus workstream with its own owner.

### X06 · P1 · Distribution gap — the JS test layer has no manifest or runner

`package-lock.json` exists at the repo root with **no `package.json`**, so
`npm ci` and `npm install` both fail. `tests/js/bridge_harness.mjs` and
`tests/js/news_layer_harness.mjs` are referenced by nothing — no Python test
shells out to node, no PowerShell launcher, no CI job, no documentation. The
audit's V02 asks for "JS/browser flows" in CI; there is not yet a manifest to
install from.

### X05 · P1 · Secret hygiene — a live broker token sits in the working tree

`kite_credentials.tokens.json` at the repo root contains an `access_token`,
`public_token`, `user_id` and a `login_time` of `2026-10-16 22:02:53` in
plaintext. It **is** gitignored (`.gitignore:11,13`), so it is not committed —
but it is present in a directory under `Downloads` that gets copied, zipped and
read by every tool and agent session in this project. Kite access tokens are
day-scoped so this one is probably expired, which does not make the pattern
safe. The audit's O06 asks for "secrets absent from logs" and says nothing
about secrets at rest in the checkout. **Treat the token as compromised and
rotate it**; move the file outside the repository and read it from an
environment variable or user-profile path.

### X10 · P2 · Scope gap — three Streamlit entry points, one launcher

`dashboard/app.py` (399 lines), `dashboard/prototype_app.py` (267) and
`prediction/app.py` (382) all call `st.set_page_config` and are independently
runnable. Only `prototype_app.py` has a launcher. `dashboard/app.py` and
`prediction/app.py` have no launch path, no acceptance journey and no stated
ownership. U03 discusses making one console's panels live; it does not say that
two further applications exist unclaimed. Either adopt them with acceptance or
mark them research-only and keep them out of the release.

### X07 · P2 · Repository hazard — two live git worktrees inside the checkout

`git worktree list` reports `.claude/worktrees/c11-fr43-fr49` (locked) and
`.claude/worktrees/c2-macro-ingestion`, both pinned at `f79299d`, 3.5 MB each,
each containing a full stale copy of `AGENTS.md`, `docs/SPEC.md`,
`docs/archive/SPEC-DELTA-01.md` and `docker-compose.yml`. They are gitignored,
so a `grep -r` or an agent file search reaches an obsolete `SPEC.md` and an
obsolete rules file — the exact tiering hazard `AGENTS.md §0` is built to
prevent. **`f79299d` is not reachable from `main`**, so `git worktree prune`
or a directory delete would discard that work: decide deliberately, don't
clean up casually.

### X09 · P2 · Release hygiene — loose artefacts at the repository root

`DEMO-DELETE-ME.md`, `intraday_backfill.checkpoint.json`,
`source_original_manifest.json` and `integration_worktree_manifest.json` sit at
the top level. The checkpoint in particular is live job state stored outside
any store boundary. Folds into O08.

### X11 · P2 · Verification gap — the untracked tree is the product

204 untracked paths and 31 modified tracked files sit on top of `51680bb`.
Effectively all of `seraph/live`, `seraph/news`, `seraph/identity`,
`seraph/decision_support`, `seraph/operations` and the console exist **only in
this working tree**. The audit records this and defers commitment to owner
authorization, which is right. The consequence it does not draw: until that
baseline is captured, **every acceptance result in this project is
unreproducible by definition** — V03 cannot be satisfied at all, and a single
disk fault ends the project. This is the plan's W0 gate and nothing else should
start before it.

---

## Part 4 — Packages carried forward unchanged

Not independently re-derived here; the audit's statements are accepted as
written and carried into the plan with its own priorities: D02, D05, D06, P02,
P06, P07, P08, N01, N07, N08, N09, N10, N11, U04, U05, O04, O05, O06, O07, O08,
V01, V04. Where this verification affects one of them it is noted in the plan's
workstream for that package (most importantly N09, whose delivery arms X02).

## Part 5 — Revised totals

| | count |
|---|---|
| Audit packages confirmed open as stated (Part 1) | 28 |
| Audit packages whose code is already repaired, acceptance/migration remains (Part 2) | 5 (N02–N06) |
| Audit packages carried forward unexamined (Part 4) | 22 |
| **Audit packages total** | **55** |
| Audit statements corrected | 6 |
| New findings added (Part 3) | 11 (X01–X11) |
| **Tracked engineering items after verification** | **66** |

With the 11 W0/W1 baseline and contract tasks the plan adds, the tracking
backlog is 76 rows — see
[SERAPH-DEVELOPMENT-PLAN-2026-10-18-BACKLOG.csv](SERAPH-DEVELOPMENT-PLAN-2026-10-18-BACKLOG.csv).

The denominator moved from 55 to 66, but the *implementation* volume fell: five
news repairs are done, and three of the new findings (X01, X02, X04) are
one-function fixes that belong inside packages already planned (N02's grouping
family and R06's identity work). Of the 11 new findings, four (X05, X07, X09,
X11) are repository and baseline hygiene rather than product code.
