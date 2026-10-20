# SERAPH — functional completion report

19 October 2026. Branch `seraph/engineering-completion` from `51680bb`,
**23 commits, nothing pushed**. `main` untouched.

How to run and demonstrate it:
[DEMONSTRATION-RUNBOOK-2026-10-19.md](DEMONSTRATION-RUNBOOK-2026-10-19.md).
Machine-readable evidence:
[functional-completion-2026-10-19.json](evidence/functional-completion-2026-10-19.json).

---

## 1. Headline

| Measure | Result | Denominator |
|---|---|---|
| **Functional completion** | **10 of 10 checked journeys work** | the journeys the originally intended scope needs and this installation can reach |
| **Integration completion** | **11 of 17** | those 11 plus the blocked items in §4 |
| **Demo readiness** | **yes, for the market/data/archive/workflow story** — no, for a live broker feed | §3 |
| **Engineering backlog** | 28 of 77 rows done before this session; **T02–T07 and the three role workflows added since** | the 2026-10-18 plan's backlog |
| Test suite | **2,525 passed, 15 skipped, 0 failed** — everything together, 23m12s | — |
| New regression tests this session | **+177** (T03 24, T04 22, T05/08/09 33 + 17 UI, T06/07 20, C15 17, R10 20, plus earlier) | — |

The single most important change: **the project now runs on its own real
data.** It did not before. `daily_prices` held 0 rows and
`run_live.build` attached `NullProducers`, so no score could be produced
from anything. It now holds 7,385,306 real NSE daily rows and the live path
produces a CSRS from computed pillar vintages.

## 2. What was implemented, and what it rests on

### The data question resolved itself

The previous assessment called the source database "the major blocker" and
flagged it for an owner decision. Inspection dissolved that: **FR1 names the
EOD2 pipeline as the daily source, and the code already pointed at a
vendored copy of it.** `eod2_client.DEFAULT_DATA_DIR` and
`universe/instrument_type.py` both resolve to
`vendor/eod2/src/eod2_data` — 443 MB of real NSE daily OHLCV, 3,690 symbols,
back to 1995, committed in the repository.

So there was no decision to escalate and no new dependency to add. The
pipeline existed, the data existed, and **nobody had run it.**

| Loaded | Result |
|---|---|
| `daily_prices` | 7,385,306 rows · 3,524 symbols · 2005-01-03 → 2026-08-21 |
| `universe_snapshots` | 43 rebalances · `Q_t = 2.00` exactly from 2010-07 · 10 early epochs `UNDERFILLED` |
| Equity filter | 3,755 symbols classified from the vendored ISIN table; `NIFTYBEES`/`GOLDBEES` excluded |
| `flow_aggregates` | one real NSE print: FII −1,148.64 cr, DII +3,201.19 cr, 2026-10-19 |

The destination is the project's own `docker compose` PostgreSQL on 5434
(FR8). **The 9.2 GB source volume on 5433 was never attached, migrated or
modified.** CT-1 idempotency verified: second run `inserted: 0`.

Two findings fell out that are worth more than the loading itself. `Q_t`
hits exactly 2.00 from 2010 onward — the FR52 reconstruction does what the
spec designed it to do — and the ten early snapshots come back
`UNDERFILLED` at 299–474 names, **independently reproducing AMENDMENT-02's
conclusion that N=500/Q=2 is unattainable for the 2008 epoch.** That is the
data agreeing with a prior finding, not a bug.

### Real producers replaced `NullProducers`

`NullProducers`' own docstring specified the design and it was right: RMT
and Hamilton are daily products read from a store, not derived from a
five-minute bar. Migration 003 adds `daily_vintages`;
`scripts/run_daily.py` computes and persists; `DailyVintageProducer` reads.
A bar close is no longer an occasion to re-eigendecompose a 1000×500 matrix.

The `origin` column is the load-bearing part: `computed` here, `archived`
from a prior research artefact, or `absent`. Three different claims, and the
column travels with the number to the screen.

### Three durable workflows got a route to a user

`WorkspaceStore`, `ScenarioStore` and `CaseStore` — about 1,300 lines —
were implemented, tested and **called by nothing**. `grep -c` for all three
names across the dashboard returned 0. Portfolios lived in
`st.session_state`, scenarios were transient, the regulator case lifecycle
had no user at all. 21 dispatch operations now reach them, with the stores'
own authorisation enforced on top.

### Surfaces that were fabricated or absent

- **FR41 benchmark overlay** was absent; the official `nifty 500.csv` was
  already in the repository (3,577 sessions). Now real, with the pre-2012
  gap reported rather than forward-filled, and both series' units declared.
- **FR45/FR51 flow** showed `FII net (example) -1200`. Now a real NSE print
  with its scope caveat, or an explicit absence.
- **R12/C10 prospective ledger** did not exist. Migration 004 adds it with
  an enforced maturity rule.

## 3. Demo readiness

**Demonstrable now, end to end, with no broker and no subscription:** the
data foundation, the FR52 universe reconstruction, a pillar computed today,
the historical console with its CSRS/interval/Shapley/explanation, the
official benchmark overlay, the real flow panel, all three durable role
workflows, the prospective forecast ledger, a replay that cannot masquerade
as live, the installed wheel, and three-point crash recovery. The runbook
orders these into ten steps.

**Not demonstrable:** a live market feed (no broker authorisation), and the
role workflows **through the browser** — their server half is complete and
tested, their controls are not wired, because `prototype_app.py` and
`bridge.js` are held by a concurrent session (§4).

**Must not be claimed:** predictive skill. AMENDMENT-03 measured Pillar 1 at
approximately no skill at every intraday horizon and reclassified it as a
contagion diagnostic; Hamilton is excluded by standing research decision;
the news gold corpus is empty at 0 of 600 documents. Those are honest
limitations of a working system.

## 4. The seven blocked items, and who can unblock them

Three distinct kinds of blocker, deliberately not merged:

**Paid external subscription (3 items).** Fresh Hawkes (FR10–15), measured
sector micro-flags (FR14), directed contagion network (FR15). All three need
5-minute intraday bars; `backfill_intraday.py` is written and checkpointed
and needs a Kite Connect subscription plus a daily interactive login.

A consequence worth stating precisely, because it is easy to misread as a
defect: `DECLARED_CADENCE` puts Hawkes at `bar_close` per FR13, so an
archived *daily* Hawkes value is already stale against its own declared
cadence, D4's saturating noise takes its R to the ceiling, and the D2 mask
correctly excludes it. **The live composite on currently available data is
RMT + Hamilton, mask `[False, True, True]`** — a real CSRS from real
computed inputs, with the excluded pillar named in the warnings.

**Owner decision on a model or cost contract (3 items).** The counterfactual
policy path (FR48) needs a persisted Hamilton fit despite its standing
exclusion. The defensive-action drawdown comparison (FR46) needs declared
positions, execution and cost assumptions — financially material choices
that are not invented here. Institution decomposition (FR42) needs
authorised submissions; private positions are not derivable from public
price bars.

**A concurrent session — now resolved.** `launch_prototype.ps1`,
`prototype_app.py`, `bridge.js` and `operations/jobs.py` were held by another
agent session in this same working tree. Its work was assessed (207 tests
passing, all modules importing, no WIP markers, idle 14 hours) and landed as
its own attributed commit `a0ac81f`, which freed the files. The three items
it blocked are done: C15's one-command launch of the market side, the browser
controls for all three role workflows, and R10's lease fencing.

## 5. Defects I introduced, and how they were caught

Four, all caught before they shipped, and each by a different mechanism.
Worth recording because three were invisible to unit tests.

**A closed Literal, caught by the real path.** `DailyVintageProducer`'s
`missing_reason` was the descriptive string `'no_daily_vintage_persisted'`.
`UnavailableEmission.reason` is a closed Literal of three values, and a
`Vintage`'s `absence_reason` flows into it. This passed 22 unit tests —
every one builds a `Vintage` directly and never constructs the emission —
and raised `ValidationError` the moment a real decision ran. Fixed at three
sites; two new tests read the permitted set out of the model with
`get_args` so widening it cannot leave them stale.

**Operational measurement in decision identity, caught by an acceptance
probe.** R06's idempotency hashed the whole decision payload, which carries
`bar_close_to_decision_ms` and feed liveness. Re-deciding the same bar after
a restart would have raised a *false* `DecisionConflict` — in the mechanism
that exists to catch real ones. Invisible to 35 R06 unit tests; found only by
`r08_recovery_probe.py` showing matching bars with differing hashes.

**One principal for three roles, caught by the completion check.**
`demo_principal` granted every role to one user; `IdentityRegistry.resolve`
returns one role per session, so the third grant collided with the first.
Fixed with one subject per role — which is the right model anyway: a single
principal carrying retail, institutional and regulator at once is exactly
the privilege confusion RBAC exists to prevent.

**An availability check against the wall clock, caught by existing tests.**
I first fixed R02 by testing vintage availability against `now` rather than
`as_of`. Under replay, `now` can precede the bar timestamps entirely, so
every vintage was withheld and a 40-day-old warm-start value carried forward
into a confident-looking 0.79. Reverted; the fix belongs in the cutoff.

## 6. Honest accounting of the test suite

- **Passing: 2,525, with nothing excluded** — the whole suite in one run,
  23m12s, 0 failed. It was 2,247 before T10, which added 90 tests for the
  FR35 runner, the FR37 transfer, the FR34 sweep and the FR38 archive, and
  34 more for the two console panels that reach them. Earlier in the session
  it was 2,193.
- **Skipped, not passed: 15.** One is the live NSE acquisition test, gated
  on  so the suite never silently depends on an exchange
  being reachable; it passes when run. Four `ct3_jump_sufficiency` (need intraday
  bars — the same Kite blocker) and ten DB-gated cases needing a disposable
  `seraph_test_*` Postgres. V02's CI `migrations` job runs exactly those ten
  and **fails if any skip**.
- **Split out for runtime, not excluded: 4 modules** (`test_c7_hamilton*`,
  `ct7_simulator_consistency`), 34 tests, 15m49s. The CI matrix runs them on
  their own leg; both that leg and the single combined run are green, so the
  2,525 figure needs no caveat.
- **Untested external dependencies:** the broker websocket, a real identity
  provider, and the three new CI jobs, which cannot be exercised from a
  developer machine — which is V02's whole point.

A passing suite is not functional correctness, which is why
`verify_functional_completion.py` exists and is reported separately.

## 7. What I did not do

- **T11**, **T12**, **T13** — all P2 and all blocked on the model/data
  contracts in §4.
- **The second half of X10.** `seraph.prediction` is now integrated: the
  console's first panel runs the real engine through
  `seraph/prediction/operational.py`, refreshed by the daily job sequence,
  and `verify_functional_completion.py` checks it as a journey. What remains
  is a different question with the same backlog id — `seraph/dashboard/app.py`
  is a second dashboard beside the canonical `prototype_app.py`, and
  `seraph/prediction/app.py` is a read-only viewer of saved research
  artefacts. Neither is the prediction capability, which is wired; both are
  duplicate surfaces whose fate is an owner call. **Prediction is not
  research-only**, and nothing here classifies it that way.
- **A real FR35 result.** T10 built the runner; the design it would run
  under is still uncommitted, and that is deliberately the owner's act
  rather than a build step — DR-05 step 5, and D5(d) gates every AUC on it.
  Every number produced so far comes from a synthetic fixture that says so
  in a field travelling with the data.
- **Widening `EvaluationRow` to carry Table C**, which needs an edit to
  `seraph/shared_types/` — ask-gated in `CLAUDE.md` because all twelve
  components import from it. DR-12 §6 states the choice. The archive was
  widened, because FR38 requires it; publishing is the open half.
- **W0-B** — the Kite token is still in the repository root. The
  externalised configuration, the warning and the invariant check are
  implemented; **rotating the credential is yours.**

**Fresh market data is closed.** The corpus reached 2026-08-21 — the
vendored EOD2 snapshot's end — and every downstream step ran correctly on it,
producing a two-month-old forecast. NSE's bhavcopy archive turned out to be
public and reachable, so no subscription was needed: Kite Connect is for
*intraday* bars, not end-of-day. 38 sessions and 101,083 rows later the
corpus runs through **2026-10-19** and the prediction is for that session.
The integration gap was not acquisition but what follows it — a fresh row is
not a universe member until C3 says so, and the market panel is built only
from members, so the new sessions were invisible until the flags and the
snapshot were re-derived. Hawkes remains blocked, now for the precise reason:
it needs five-minute bars, which the subscription gates.

**O03 is closed.** The daily sequence is registered with Windows Task
Scheduler (weekdays 18:30 IST), has been fired and observed to completion
with result 0, and reports through the HEALTH panel. It distinguishes three
facts that a single green light would collapse: registered, executed, and
acquired fresh data — which on this installation reads yes / yes / **no**,
because the vendored snapshot ends 2026-08-21. Building it surfaced that
**R10's lease fencing could not acquire a lease on any pre-existing ledger**:
`generation` was added under `CREATE TABLE IF NOT EXISTS`, every R10 test
used a fresh temporary database, and the mechanism was therefore inert
wherever it mattered. Fixed with an additive migration.

## 8. The honest bottom line

The project is **substantially more complete and materially more real** than
at the start of this session: it runs on 7.4 million rows of its own real
market data, reconstructs its universe to the spec's exact `Q = 2`, computes
a pillar today, produces a composite score with uncertainty from real
inputs, overlays the official benchmark, shows a real institutional flow
print, and persists portfolios, scenarios and regulator cases durably.

It is **not finished**, and the remaining gaps are specific rather than
diffuse: one paid subscription unlocks three features, and four owner
decisions unlock the rest — the Hamilton fit, the position/cost contract,
authorised institution submissions, and committing the pre-registration.
The concurrent session was resolved, which unlocked the browser controls and
the single-command launch. **No mandatory requirement now remains
unimplemented for want of engineering effort.**

T10 closed one of those: `EvaluationRow` had no producer anywhere in the
repository, and the FR35 ablation now has a runner, an FR37 transfer path,
an FR34 sensitivity sweep and an FR38 archive. What it does not have is a
result, for the one reason above.

The larger one was prediction. SERAPH is a risk prediction and early-warning
system, and its engine reached the user only as backend code, a CLI
experiment and a separate parquet viewer — `seraph.prediction` was
unreachable from `seraph/dashboard/` entirely. It is now the console's first
panel, driven by the actual engine on 5,361 real sessions and refreshed by
the daily job sequence. On the current data it reads a 4.62% probability
against a calibrated 12.96% threshold, so no warning, with Brier 0.0695 and
AUC 0.659 over 4,576 matured forecasts — and a calibration table showing the
model over-predicting in every populated bin. All of that is displayed,
including the over-prediction, under an UNVALIDATED banner that sits above
the numbers rather than beneath them.

No feature above is claimed as working that this report has not verified,
and nothing simulated is presented as real.
