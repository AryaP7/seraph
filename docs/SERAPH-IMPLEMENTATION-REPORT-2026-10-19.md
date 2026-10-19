# SERAPH — autonomous implementation report

Session date: 19 October 2026. Branch: `seraph/engineering-completion`,
cut from `main` at `51680bb`. Ten commits, nothing pushed.

**Headline:** full suite **2067 passed, 14 skipped, 0 failed**; 236 new
regression tests; O01 and R08 both pass their full acceptance against real
artefacts. 13 of 14 integrity defects closed. R10 and all of W5 deferred
because another agent session holds those files in this same tree.

Against [the development plan](SERAPH-ENGINEERING-DEVELOPMENT-PLAN-2026-10-18.md)
and [its verification](SERAPH-COMPLETION-AUDIT-VERIFICATION-2026-10-18.md).
Dispositions for all 76 backlog rows are in
[the backlog CSV](SERAPH-DEVELOPMENT-PLAN-2026-10-18-BACKLOG.csv); contracts
implemented are recorded in
[DR-11](decisions/DR-11-2026-10-19-runtime-state-contracts.md).

---

## 1. The one thing to know first

**Another agent session is editing this same working tree concurrently.** It
holds `seraph/news/acquisition.py`, `seraph/news/worker_lock.py`,
`scripts/run_news.py`, `scripts/news_supervisor.py`,
`seraph/operations/jobs.py`, and it added `seraph/dashboard/news_service.py`
and an `acquisition_panel` to `prototype_app.py`.

I detected this during W0 (files changed under me between staging and
committing) and routed around it: **every commit below stages only files I
authored**, and I did not touch, revert or stage any of theirs. Their work is
still uncommitted in the tree.

One consequence, load-bearing for how you read this report: **R10 (job lease
fencing) and all of W5 (news) are deferred, not done.** `operations/jobs.py`
is R10's entire subject and they are rewriting it. Two agents editing one file
destroys both efforts; stopping was the correct engineering call, not a
shortfall in effort.

Mid-session, two suite failures belonged to their in-flight state
(`test_news_audit_2026_10_18.py::test_a09_...` and
`test_ni_worker_liveness.py::test_registration_is_reconciled_on_every_launch`
— both reading files no commit of mine touches). **Both resolved by the end of
the session**, so the final suite is clean. Their work remains uncommitted in
the tree.

Decide what you want merged before either of us continues.

## 2. What was implemented

Eight commits, in dependency order. Every repair landed with its regression
tests in the same commit.

| Commit | Items | Tests added |
|---|---|---|
| `0a98274`+`b5a229a` | W0-A baseline, X11 | — |
| `0f1f1d8` | R07a, R07b/**X03**, R09, R08 (bars half) | 47 |
| `73a7c10` | U01 | 23 |
| `8205810` | O01, O02, V03 (part), **X05** | 28 |
| `d0a5f76` | **X01**, **X02**, **X02b** | 43 |
| `89cf8d8` | R02, R03, R04, R05, R06/**X04**, R08, R11 | 35 |
| `44d92fa` | P03, P05 | 41 |
| `22f1fe2` | V02, **X06** | 15 |
| `e3ebcca` | DR-11, backlog disposition, O01 evidence | — |
| `ce11ba8` | R08 acceptance + **the false-conflict it exposed** | 4 |

**236 new tests.** Bold items are findings the original audit did not contain.

### The baseline (W0-A)

The whole product — 403 untracked paths including all of `seraph/live`,
`seraph/news`, `seraph/identity`, `seraph/decision_support`,
`seraph/operations` and the console — existed only on disk on top of
`51680bb`. V03 could not be satisfied at any level while that was true and a
single disk fault would have ended the project. Verified safe before
committing: no credential file, no `.env`, no database, no `.venv`, largest
file 2.3 MB of audit evidence.

### Two reproduced crashes the audit missed

**X03** — `BarBuilder._order_key` returned `(ts, last_price, volume_traded)`
and used that one tuple for both deduplication and ordering. `volume_traded`
is `int | None`, so two ticks sharing a timestamp and price where one carried
no volume reached `None < int`:

```
TypeError: '<' not supported between instances of 'NoneType' and 'int'
```

The exception escaped the per-tick loop and **discarded every remaining tick
in the batch**, not just the offending one. Kite in LTP mode produces exactly
that shape. Fixed by splitting content identity from chronological order —
which also fixed R07b, where price as a tie-breaker meant a same-second
*down*-tick was quarantined and discarded while an up-tick was kept.

**X02** — `news/registry._norm` stripped to `[^a-z0-9 ]+`, so a Devanagari
name normalised to the empty string, and `resolve_asset` tested
`needle in name or name in needle` where `"" in needle` is always True:

```
resolve_asset("Reliance refinery") -> resolved -> as:hindi
resolve_asset("anything at all")   -> resolved -> as:hindi
```

One asset with a non-Latin name made **every** mention in the corpus resolve
to it, reported as `status='resolved'` with no ambiguity flag. Latent only
because all 264 curated rows were ASCII — it would have armed the moment N09's
non-English coverage landed. X01 was the same bug class in the globe slug
(two Devanagari states shared one `geometry_id`); X02b adds Devanagari aliases
to three shipped rows so the class cannot silently return.

### O01 — verified against a real installed wheel

`docs/evidence/PACKAGING-2026-10-19.json`, all seven conditions true:

```
wheel_carries_required_assets                  true   (173 entries, 0 missing)
installs_outside_the_checkout                  true
component_resolves_to_the_installed_package    true
canonical_console_renders                      true
runtime_schema_creates_from_installed_package  true   (was: OperationalError)
curated_registry_carries_rows                  true   (22/21/28/64, empty=false)
migration_sql_readable_from_installed_package  true   (2 files, 5171 bytes)
```

The root cause was two things, and the second is the subtle one:
`seraph/live/migrations/` and `seraph/news/curated/` had no `__init__.py` so
`packages.find` never saw them; and a `package-data` glob does not recurse, so
`"seraph.store" = ["*.sql"]` shipped `schema.sql` and silently dropped
`store/migrations/001_evaluation_identity.sql`. The old verifier checked a
subset, which is why it passed a broken build — `REQUIRED` now lists all 16
assets and a test cross-checks each against the declared globs with `fnmatch`.

### Runtime state (DR-11)

R02's fix belongs in the **cutoff**, not the comparison: `as_of` is now the
bar end plus a declared `DECISION_ALLOWANCE`, so a producer that cannot emit
until the bar is complete is admitted at normal latency instead of being
withheld on every bar while a stale value carried forward forever.

I implemented the availability check against the wall clock first. **That was
wrong and the tests caught it** — `now` is the tick instant, which under
replay can precede the bar timestamps entirely, so every vintage was withheld
and a 40-day-old warm-start value carried forward into a confident-looking
score of 0.79. Reverted to comparing against `as_of`, and recorded why in
both the code and DR-11.

R06/X04 needed all three of: a composite `decision_id` (so the collision
cannot be minted), `payload_hash` comparison (so the same id with different
bytes is a conflict, not a silent replay), and `stream_id` scoping via
migration `002` (so a replay stream cannot be read as the live reading).
Fixing fewer than all three leaves the hole.

## 3. Verification

| Check | Result |
|---|---|
| **Full suite, session end** | **2067 passed, 14 skipped, 0 failed** (18m14s) |
| Full suite at session start | 1705 passed, 4 skipped (1715 collected) |
| `scripts/check_invariants.py` | exit 0, with two `[info]` notes |
| `scripts/verify_packaging.py` | **passed**, all 7 conditions |
| `r08_recovery_probe.py` | **passed**, all 3 crash points |
| JS harnesses (`npm test`) | both clean, 31 + 40 named claims |
| New tests added | 236 |

The collected count rose from 1715 to 2081 — my 236 plus the concurrent
session's additions.

Two new invariant checks were added and both pass: the lockfile must pin every
pyproject dependency (so `-e .` cannot float one), and no credential-shaped
file may sit in the repository root.

### 3.1 Honest accounting of the suite

Separated as the directive requires:

- **Passing: 2067.** No failures, no errors.
- **Skipped, not passed: 14.** Four `test_ct3_jump_sufficiency` cases (need
  more intraday bars) and ten DB-gated cases (need a disposable
  `seraph_test_*` Postgres, which this machine does not currently serve).
  V02's new `migrations` CI job runs exactly those ten and **fails if any
  skips**, because a green job that skipped its subject is not coverage.
- **Blocked: 0.**
- **Untested external dependencies — not covered by any count above:** the
  broker websocket (no authorized credentials; `KiteTickerFeed.health()` says
  so in its own detail string), a real identity provider, the source
  PostgreSQL on 5433, and the three new CI jobs, which cannot be exercised
  from a developer machine — which is itself V02's whole point.

## 4. What I did not do, and why

| Item | Status | Reason |
|---|---|---|
| **R10** job lease fencing | deferred | `operations/jobs.py` is being rewritten by a concurrent session. Co-editing would destroy both. |
| **W5** all news work | deferred | Same tree, same reason. N02–N06 were already repaired before this session and must not be re-implemented. |
| **W0-B** token rotation | owner action | The externalised config, the warning and the invariant check are implemented. **The live token is NOT rotated** — §8 of the directive, and it is the owner's credential. |
| **W0-C** stale worktrees | owner decision | `f79299d` is unreachable from `main`; pruning would discard that work. |
| **X12** duplicate place rows | recorded, not fixed | Found during X01/X02: exactly two states (Maharashtra, Odisha) carry two rows each, so both abstain and cannot be resolved from a mention — though both host NTPC assets. Verified pre-existing against the old normalisation rule. Merging them is a curated-data migration with citation implications that changes registry counts — pinned by a test so the finding cannot silently widen. |
| **W0-D** loose root artefacts | owner decision | Not the trivial cleanup it looked like: `scripts/verify_research_artifacts.py` (run by CI) reads `source_original_manifest.json`, and `HANDOFF.md` references `DEMO-DELETE-ME.md`. Moving them breaks CI and a handoff document that is out of scope to edit. A cosmetic move that breaks the build is worse than leaving it recorded. |
| **W3** data foundation | not started | D01 needs the owner's decision on exposing the 9.2 GB source volume, and the password must come from outside the repo. |
| **W4** real producers | not started | Depends on W3 (D04's real universe) and on R10 for scheduled daily vintages. |
| **W7** identity, **W8** ops, **O07** performance | not started | Downstream of W3/W4; W7 additionally needs an identity provider to verify against. |
| Branch triggers in CI | left open | Widening what CI costs per push is the owner's call. |

## 5. Completion, by evidence

Deliberately not a single percentage. "Code written" is not "verified", and
the categories fail independently.

| Category | State | Basis |
|---|---|---|
| **Integrity defects (W2)** | **13 of 14 closed** | Every P0 state defect in `seraph/live` and `seraph/decision_support`, plus 6 new findings. R10 is the one open, and it is blocked on concurrency, not difficulty. |
| **Distribution (O01/O02)** | **closed and verified** | A real wheel installed outside the checkout satisfies all 7 conditions. |
| **Crash recovery (R08)** | **closed and verified** | All three crash points reproduce the uninterrupted baseline's bars and decisions. |
| **Verification plumbing (V01/V02/X06)** | **substantially closed** | 232 regression tests; 3 CI jobs added; the JS layer has a runner for the first time. V01's remaining sweep is for the deferred items. |
| **Contracts (W1)** | **5 of 7 recorded** | DR-11 covers time, identity, configuration, portfolio validity and scenario revisions. DR-14 (leases) is open with R10. |
| **Baseline/reproducibility** | **W0-A closed, V03 partial** | The tree is captured and the lockfile no longer floats. A full acceptance manifest needs the deferred items. |
| **News (W5)** | **unchanged by me** | N02–N06 were already repaired; the rest is deferred on concurrency. |
| **Data, producers, roles, ops (W3/W4/W6/W7/W8)** | **not started** | Gated on external input or on R10. |
| **Demo readiness** | **see §6** | |

## 6. Demo readiness

**Improved, and still not a live end-to-end demonstration.**

What now works that did not: the console starts and renders on any
combination of present stores (live-only, news-only, archive-only, empty)
instead of printing one line; a committed decision renders its CSRS as a
number instead of raising a Streamlit exception; a separately installed build
creates its own schema and loads its curated registry; `--replay` cannot open
a broker socket; and the live bar path no longer discards a tick batch on a
volume-less tick.

What still blocks the full journey, unchanged by this session: **no producer
is connected** (`NullProducers` remains the honest default, and R01 is gated
on W3/W4), **no scheduler exists** (O03; `operations/jobs.py` says cron
invokes it and no cron or Task Scheduler definition exists anywhere in the
tree), and **the source database is unreachable** (5433 refuses; the 9.2 GB
volume is intact but unattached).

So: the archive-backed and news-backed surfaces are demonstrable and more
robust than before. A *live* market demonstration is not, and nothing in this
session claimed otherwise.

## 7. Genuine remaining blockers

Only these need someone other than an implementer:

1. **Resolve the concurrent session** — decide whose news/jobs work merges.
   Blocks R10 and all of W5.
2. **Rotate the Kite token** and move it out of the tree. The mechanism is
   implemented; the credential is yours.
3. **Decide on the source database** (D01) — whether to attach a container to
   the 9.2 GB volume, with the password from outside the repo. Blocks W3, and
   W4 behind it.
4. **The two stale worktrees** (W0-C) — `f79299d` is unreachable from `main`.
5. **An identity provider** for W7's cross-user verification.
6. **The labelled news corpus** (X08) — the gate reports 0 of 600 documents
   and 0 of 2 reviewers. N12's metrics can be built against synthetic gold;
   real accuracy cannot exist until this is labelled.

## 8. One defect I introduced, and how it was caught

Worth stating plainly, because it is the strongest argument in this report
for acceptance probes over unit tests.

R06's content-bound idempotency hashed the **whole** decision payload. But
`LiveDecision.describe()` carries both the decision and how the run went —
`bar_close_to_decision_ms`, the feed's `last_message_at`, observation
recency — and those differ on every execution. So re-deciding the same bar
after a restart would have raised `DecisionConflict` purely because the
stopwatch read differently: a false conflict in the mechanism that exists to
catch real ones.

Every unit test passed. The 35-case R06 suite passed. It was caught only by
`r08_recovery_probe.py` driving the real `run_live` path through three crash
points and finding matching bars with differing decision hashes — and then
only by diagnosing that difference rather than relaxing the probe. Fixed in
`ce11ba8` with `decision_identity()`, which names the three excluded fields
and the reason.

I also implemented R02's availability check against the wall clock first;
that was wrong (it withheld every vintage under replay and carried a 40-day-
old value into a confident score) and the existing tests caught it. Both
reversals are recorded in DR-11 rather than quietly dropped.

## 9. Git

Branch `seraph/engineering-completion` from `51680bb`. Ten commits, **no
push, no merge, no force**. `main` is untouched.

```
ce11ba8  R08 acceptance, and a false-conflict path it exposed in R06
e3ebcca  Record contracts, backlog disposition and the O01 acceptance evidence
22f1fe2  V02, X06: close the three CI gaps and give the JS harnesses a runner
44d92fa  P03, P05: portfolio import invariants and immutable scenario revisions
89cf8d8  R02-R06, R08, R11, X04: runtime state correctness
d0a5f76  X01, X02, X02b: finish the Unicode identity family N02 started
8205810  O01, O02, V03, X05: ship every runtime asset, pin every dependency
73a7c10  U01: independent startup surfaces and a scalar CSRS
0f1f1d8  R07a, R07b/X03, R09: tick validation, ordering, replay precedence
b5a229a  W0-A: include scientific-audit evidence written during the baseline
0a98274  W0-A: capture the engineering baseline
```

The working tree still carries the other session's uncommitted changes. I
left them exactly as found.
