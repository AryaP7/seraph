# October 26 CSRS pillar-eligibility audit — current handoff

Supersedes the "Pillar eligibility, and a cadence error of mine" section below
where they overlap. **Read `docs/DECISION-REGISTER-2026-10-26.md` first** — it
holds the six decisions and every measured number.

## The correction that matters most

The previous section said D4 staleness is why Hawkes is in no mask. **That is
true for only 3 of 254 sessions.** Measured: 251 of 254 carry a stored Hawkes
absence of kind `structural`, written by `scripts/run_daily.py` whenever that
job supplies no fresh fit, and a structural absence clears the mask bit
UNCONDITIONALLY — before D4 is consulted at all. Verified: a fit observing
through 2026-10-22 15:15, evaluated 78 bars later and NOT saturated, is masked
out under `structural` and in under `transient`.

So the dominant gate is an absence **misclassification**, not a staleness
parameter. AGENTS.md §5's structural case is "cannot exist for this period";
"this daily job does not supply it" is a transient condition, and the native
producer already classifies the identical condition as transient. Two producers
disagree and the replay reads the stricter one.

D4 is the *second* gate, and it is real: `h_bars[hawkes] = 1.0` bar against a
measured 5-session (375-bar) pillar cadence, so Hawkes is eligible for 0.80% of
one of its own update cycles where RMT gets 299%. Saturation is at exactly
2.9857·h for every pillar, so the freshest possible fit (15:15, the continuous
session end) is excluded at a 15:30 decision by **4.3 seconds** of trading time.

## Why none of it should be "fixed" yet

With both corrected and the mis-spaced fits excluded, Hawkes enters the mask and
the latest composite moves **0.0900 -> 0.2950**. That movement is not a reading.
On 2026-10-22 the Hawkes ECDF window held ZERO prior observations, so
`standardise` returned its documented no-information midpoint 0.5, and the
implied filter state is **x_hawkes = 0.500000000000000 exactly** — the untouched
`x0` prior. The whole +0.2050 is one hard-coded constant averaged against RMT's
real 0.0900.

It gets through because **no pillar supplies an estimation variance** — 0 of 777
stored vintages carry one — so a rank from 0 reference observations is
assimilated at the same `R0 = 0.02` as a rank from 1,260. That is the third
defect (D-3) and it must be settled BEFORE the other two, or correcting them
publishes a higher risk score built from a placeholder.

**So the current single-pillar CSRS is the right output today, for the wrong
reason.** The binding constraint is the Hawkes reference history: 3 observations
exist, 252 are required, ~49.7/year are attainable. That is data acquisition,
not a gate to relax.

## Hamilton — settled, no change

Fails its own pre-registered criteria: surrogate-null p = 0.9524 (AR1) and
0.7143 (AAFT), NFR17 2.020σ against 3.0 required, R6 4/6 at k=3, BIC prefers
k=4, and **R2 fails** — a one-regime AR(1) surrogate was not rejected, so the
criteria have no discriminating power. Causal TVTP separately shows 6/14 nesting
violations to LR = −2,322.88. `AMENDMENT-05` §5–6 still said this was blocked on
Docker; a dated §7 addendum now points at the evidence that resolved it.

## Fixed this session

- **FIX-1** `scripts/run_daily.py` archived Hawkes path emitted the FR13-GATED
  `mts` (0.0 on 352 of 473 rows) while the native producer emits the ungated
  `n/(1−n)`. FR13 v4: "the branching ratio is reported regardless". No stored
  value changed — that row's gate was open.
- **FIX-2** `scripts/live_session_pass.py` called `SessionCalendar.default()`,
  which does not exist, so the scheduled live recorder raised AttributeError on
  step 1 and could never reach the broker probe or the pass. Now routed through
  the same `MarketClock` / `next_session_window` helpers `run_live.py` uses.
- **`scripts/register_live_task.py`** written. It was named in
  `live_session_pass.py`'s own docstring and did not exist. Defaults to printing
  the plan; `--install` registers Mon–Fri 09:25 and 15:05 with
  `StartWhenAvailable`. NOT installed — that is persistent machine state.
- `tests/test_d4_cadence_and_eligibility.py`, 10 tests, pins the saturation
  geometry, the 15:15→15:30 crossing, the absence-kind override, the
  transient/carried-forward asymmetry, the empty-window 0.5, and FIX-1.

## Operational gaps worth knowing

- There is **no scheduled in-session live pass**. The one registered task runs
  `run_market_jobs.py` at 18:30, after the close, and its last run (2026-10-24
  17:21) returned **0x800710E0** — refused, because
  `DisallowStartIfOnBatteries = True`. It will silently skip on battery.
- The next legitimate native Hawkes refit is due **2026-10-30**: the 11
  mis-spaced fits advanced `trained_through` to 2026-10-23, where without them
  it would be 2026-10-22 and the next fit would fall on 2026-10-29.
- Kite tokens die daily at ~06:00 IST and `kite_login.py` is interactive, so no
  scheduled pass is truly unattended.


---

# October 24 native-session continuation — current handoff

Supersedes older native-coverage blockers below. Preserve the independent
energy-coverage continuation that follows.

- Overall estimate remains **97%: 40 implemented units, two partial**.
- The current native Hawkes fit now succeeds on **500 sessions, 95 members,
  37,170 common continuous-session bins, zero unexplained gaps**. The old
  14,630 missing-symbol-bar count was caused by NSE closing auctions and four
  dated special pre-open auctions. Raw history remains 4,150,272 closes.
- The dated-source collector and optional common-session policy are implemented
  and selected in `prototype_runs/live.native-hawkes.json`. Actual source
  receipt times are October 24; never backdate them or extrapolate to new days.
- One native fit is registered with actual availability at October 24,
  18:02:45.081189 IST. Cold start admits **1 Hawkes / 253 RMT / 0 Hamilton**.
  This is computational evidence, not predictive validation.
- F02 remains partial: build legitimate Hawkes standardizer history (252
  observations required) and verify a genuine in-session current publication.
  Respect point-in-time baskets, the five-session refit cadence and five-year
  ECDF; never duplicate one fit to satisfy the history floor.
- F07 remains on explicit owner hold. No network fit was run.
- **49 focused tests pass**, mechanical invariants and whitespace checks pass.
  No new full-suite pass is claimed; the separate environment-dependent news
  verification below remains applicable. One-shot worker exited; no commit/push.
- Read `NATIVE-SESSION-COVERAGE-2026-10-24.md` and
  `evidence/engineering-closeout-2026-10-24/native-session-continuation.json`.

---

# October 24 energy-coverage continuation

Supersedes the October 22 handoff below only where it overlaps.

- **Energy coverage now exists.** `et_energyworld` and `mercom_india` are
  registered in `ENERGY_SOURCES` (`scripts/run_news.py`), inside the
  probe-gated loop so an unusable feed is skipped rather than registered.
  Verified BY ACQUISITION into an isolated store, not by registration: both
  HTTP 200, 20 stories, every body empty under `may_store_full_text=False`.
  Rights are NOT reviewed (DR-10 default); trade-press reporting of a
  Ministry decision is NOT independent corroboration of that instrument.
- **The 54 curated NTPC edges are now reachable, not firing.** Measured on
  the 20 acquired headlines: 4 classify (1 `subsidy_change`, 1
  `production_halt`, 2 `capacity_expansion`), 16 are `other`, and **0 reach
  an exposure route**. An edge starts at a facility and no headline named a
  station. Only `ntpc`, `oil_india` and `kpi_green_energy` carry
  `sector=energy`, so POWERGRID, Adani Power, HPCL, CG Power and Petronet
  resolve to no issuer. No sector was invented for them.
- **Next curation step (needs cited evidence, not inference):** register the
  NSE-listed power issuers with a source URL and retrieval time, per the
  registry's citation convention. Until then, energy stories about them are
  correctly unmapped — missing evidence, not absence of risk.
- `capacity_expansion` now matches `commissions`, the form the trade press
  actually uses ("POWERGRID Commissions Project ..."). The bare noun stays
  excluded on purpose: `commission` alone matches 13 stored titles
  (FERC/SEC bodies), while `commissions` matches 0 of 1,581. Measured, not
  assumed.
- **Full suite on 2026-10-24 with Docker STOPPED: 2,585 passed, 25 skipped,
  1 failed.** The failure is
  `test_t06_t07_measured_surfaces.py::TestT06FlowPanelIsMeasuredOrAbsent::test_a_date_before_any_print_is_an_explicit_absence`,
  which needs the research database on 5434. `market_flow` correctly reports
  "the flow store could not be read (ConnectionRefusedError)" instead of
  "no free bulk history" — the structural-versus-transient absence
  distinction working as intended, **not** a defect. Do not "fix" the code:
  the "no free bulk history" message hangs off a successful read returning
  no row, and the code deliberately hard-codes no first-capture bound. This
  reconciles exactly with the documented 2,585 / 22 / 0 baseline — the four
  differing tests are the T06 flow tests that require that database.
- 789 tests covering the changed modules pass (720 + 69);
  `scripts/check_invariants.py` passes.
- **F07 and F02 were deliberately NOT advanced:** both need an owner
  decision, not engineering. F07's data gates are already met (10,641 bars
  against the 750 required; every sector node above the 10-event floor,
  solar lowest at 40), so only adoption of
  `evidence/engineering-closeout-2026-10-21/NETWORK-DIAGNOSTIC-DESIGN.md`
  is missing — and its window is 2019-10-01 to 2020-04-30, not a trailing
  2026 window. F02 additionally needs a genuine in-session publication,
  impossible on 24 October (a Saturday).
- F01/F08 were not re-walked: `final-reconciliation.json` records both
  `complete` with saved browser evidence.
- No commit or push.

## Authoritative suite, 2026-10-26 — clean

**2,773 passed, 0 failed, 5 skipped (23m21s).** `check_invariants.py`: 7 ok.
Run with both databases live and the disposable `seraph_test_auth`, with
nothing acquiring, no replay writing, and both sessions off the tree.

The preceding run was 1 failed / 2,772 passed. The single failure was a stale
count in `tests/test_redesign_console_e2e.py`: the fork's nav gained a
`current` entry when CURRENT became the landing view, and neither
`REDESIGN_VIEWS` nor the hardcoded 13 was updated. Verified that the entry
has a renderer — `seraph/dashboard/redesign/app.py:390` registers
`"current": V.current(...)` — before changing the number, because bumping a
count to match reality is exactly how a genuine disagreement gets hidden.
The meaningful assertion in that test is `set(nav) == set(ALL_VIEWS)`, which
would also have failed.

The 5 skips are external-data only: 4 × `test_ct3_jump_sufficiency` (needs
`scripts/backfill_intraday.py`) and 1 × `test_fresh_data_acquisition` (needs
`SERAPH_LIVE_NSE=1`).

### What the composite actually is, stated plainly

**The CSRS is a single-pillar composite.** 255 replay decisions, latest
`archive:2026-10-23`, csrs `0.08998820433752137`, mask `(False, True, False)`.
RMT carries it alone: Hamilton is excluded by a standing research decision,
Hawkes by cadence staleness. It is a genuine score from the official engine —
the same Kalman reconciliation, the same pure C9 `score()`, the same D2 mask
and publication gate — resting on one of three pillars. All 255 decisions are
`withheld`, and the live stream holds 0 decisions.

D4 is visibly doing its job. Between the 10-22 and 10-23 decisions the point
estimate is IDENTICAL, because there is no RMT vintage for 10-23 and the
10-22 observation is carried forward, while the FR29 interval widened from
[−0.161, 0.341] to [−0.503, 0.683]. Carried with growing uncertainty rather
than re-stamped as fresh.

## Pillar eligibility, and a cadence error of mine — 2026-10-26

### Why Hawkes is in no historical mask, and what would change that

Measured across the replay stream: **255 decisions carry a mask, 254 are
`(False, True, False)` and one historical one is `(False, True, True)`.
Hawkes appears in the mask ZERO times.** That is not a defect and not a
missing fit.

`DECLARED_CADENCE['hawkes'] = 'bar_close'` (`seraph/live/inference.py:94`).
A fit dated to a session close is therefore already stale against Hawkes's
OWN declared cadence by the time a decision is evaluated, D4 inflates its
`R` with age until it saturates, and D2 excludes it — with the exclusion
stated rather than silent (`inference.py:712-725`: "a pillar silently
dropping out of the composite is exactly the kind of invisible degradation
the mask is meant to make visible").

So **no number of historical warm-up observations can put Hawkes in the
mask.** The 252-observation requirement gates PUBLICATION
(`_warmup_complete_at` -> `assess_publication`); D4 staleness gates MASK
INCLUSION. They are different gates and only a live session, with the native
producer fitting at bar close, satisfies the second. That is the one thing
market hours are genuinely required for.

### Hamilton is excluded by a research decision, not a fault

`HAMILTON_EXCLUSION` (`scripts/run_daily.py:90`): "regime support
unvalidated; diagnostic only, and excluded from the composite by a standing
research decision (NOT_PRODUCTION). This is NOT a feed outage." A
`--hamilton diagnostic` mode exists to recompute the walk-forward estimate
for inspection without entering the composite.

So Hamilton is not a scientifically supported pillar today, and enabling it
in the composite would reverse an owner-level validation decision. It was not
enabled. The machinery works — one historical decision does carry Hamilton in
its mask — so this is a validation gate, not an implementation gap.

### A cadence error I introduced, and the guard that now prevents it

To avoid a 40-minute scan that produced no fits, I added `--newest-first` to
`warm_native_hawkes_history.py` and argued it changed "order only". **That was
wrong.** `_previous_fit(cutoff)` keeps only fits with
`trained_through <= cutoff`, so walking backwards hides every fit already
written: `previous` is always None, every candidate reads as due, and the
declared 5-session gate never fires. The run produced **12 fits on
consecutive trading days (2026-10-07 .. 2026-10-23)** — an effective
`refit_sessions` of 1, which is a change to a declared parameter.

The flag is now refused with `--execute` and usable only for planning, where
nothing is written. `--since` gives the same speed-up honestly, because it
only moves where the FORWARD walk starts and the cadence gate still fires.

**Open for the owner:** those 12 fits are real, dated and provenanced
computations, each with 500 sessions and zero incomplete members, but their
SPACING is daily rather than the declared five sessions. They are in
`prototype_runs/live.sqlite`. Options: keep them and accept a daily-cadence
ECDF for those dates, or have exactly those 12 removed so the series is
rebuilt forward at the declared cadence. Nothing was removed without
instruction, and no further fits were written after the error was found.

### Live readiness, verified 2026-10-26 04:05 IST

| check | result |
|---|---|
| Kite authentication | **valid** — read-only probe returned 10,255 NSE instruments |
| market state | `pre_open`, opens 2026-10-26T09:15, closes 15:30 |
| calendar_verified | true |
| live stream | **"NO DECISION HAS EVER BEEN COMMITTED"** — 0 rows, by design |

The live run must include the native Hawkes config, because that producer
fitting at bar close is the only thing that can make Hawkes fresh enough to
enter the mask:

```
python scripts/run_live.py --once --hawkes-config prototype_runs/live.native-hawkes.json
```

A Kite access token is a DAILY token. It was valid at 04:05, but it was
issued 2026-10-25T17:32, so it may expire before the 09:15 open; if it does,
`scripts/kite_login.py` must be re-run before the live pass.

## F07 executed, 2026-10-25

The owner adopted the specification (recorded verbatim in
`docs/decisions/DR-11-2026-10-25-f07-adoption.md`). The proposal file is
unchanged; the adopted constants are a separate artefact,
`prototype_runs/f07-specification-user-declared.json`, with
`model_status=user_declared` and every value transcribed from the proposal.

**The fit ran and produced a saved, inspectable artefact:**
`prototype_runs/hawkes_network/07d00f7365201da1....json`

| | |
|---|---|
| status | `insufficient_support` |
| coverage.bars | 10,641 (clears `minimum_bars` 750) |
| supported_nodes | all five (aluminium, auto_components, pharmaceuticals, solar, steel) |
| matrix / edges | `None` / 0 -- no graph was fabricated |
| input_sha256 | `77071f4c105d2db4...` |
| convention | `matrix[target, source]` |

**Why it is unavailable, measured not assumed.** The adopted interval
2019-10-01..2020-04-30 contains exactly two within-session breaks, both
3,600 s: **2020-03-13 09:20->10:20 IST** and **2020-03-23 09:55->10:55 IST**
(64 bins each against the usual 75). Those are the COVID market-wide
circuit-breaker halts -- real suspensions of trading, not absent data.
2019-10-27's Diwali Muhurat evening block has 12 contiguous bins and was
never a problem; 2020-04-27 has 76 bins, one more than usual, and did not
break contiguity.

**Reproducibility verified:** a second run over the same interval returns an
identical `input_sha256`, `status` and `coverage`; only `fitted_at` differs,
which the design requires to be an actual time.

**Engineering change made, and its limit.** `fit_network` previously RAISED
`ValueError('Within-session input has a missing native five-minute bin')`
from inside the lag recursion, so the runner saved nothing -- the one outcome
the design does not allow, since it says "missing support or an optimizer
failure remains an unavailable result" and an unavailable result has to be
inspectable. The same condition is now measured with the other support
checks and returns `insufficient_support`, naming the offending timestamps in
`coverage.within_session_breaks`. The refusal itself is unchanged: nothing is
fitted across a break, and no equation, parameter or threshold moved.

**The decision this leaves (owner's, not engineering's).** To obtain a graph
over the adopted interval, one of these is needed, and each is a model or
scope choice rather than a fix:

1. **Declare the halts as session structure** and let the lag state reset at
   an intraday break, exactly as it already resets at a session open. The
   calendar ALREADY supports multi-window sessions (`SPECIAL_SESSIONS` holds
   two `special_live` dates with two windows each), but it does not declare
   2020-03-13 or 2020-03-23, and `fit_network` cannot express an intraday
   break even if declared. This changes where lag resets, which is model
   behaviour.
2. **Exclude the two halt dates** (2 of 143 sessions). Defensible -- there
   was no continuous session to model -- but it is a scope reduction and must
   be disclosed on the artefact rather than applied silently.
3. **Accept the recorded unavailable result** as F07's outcome. The audit's
   own acceptance text allows this: "all-zero/unidentifiable outcomes remain
   valid and visible."

Nothing was chosen here. Option 1 needs NSE's record of the two halts before
any date could be registered, which is the same evidence discipline the CAS
schedule followed.

## F07 FITTED under a disclosed exclusion, 2026-10-25

### Why the dated-session framework could not represent the halts

The halts CAN be described in the calendar -- `SPECIAL_SESSIONS` already
supports multi-window days and holds two `special_live` dates with two
windows each. But **the F07 path never consults a calendar**:
`counts_from_stream(stream, timeline, sector_members, start, end)` and
`fit_network(counts, timestamps, spec, node_ids, provenance)` take no
schedule, so a multi-window session would not reach the estimator.

Making it reach would mean giving `fit_network` declared break points and
resetting the excitation state at an intraday reopen. `session_reset` is a
DECLARED parameter of the adopted specification ("session-open lag reset"),
so redefining a session open to include a mid-day reopen after a halt changes
where excitation resets and therefore changes the fitted weights. That is a
model decision, not a representation detail, and it was not taken.

### The exclusion variant, as the owner asked

`scripts/write_hawkes_network.py --exclude-dates` drops WHOLE sessions --
never part of one, which would leave the same discontinuity -- and records
them plus the reason in the artefact's provenance, so an exclusion can never
be read as the adopted fit.

Artefact `prototype_runs/hawkes_network/a4a228b31626716a....json`:

| | |
|---|---|
| status | **`fitted`** |
| excluded_sessions | `2020-03-13`, `2020-03-23` (disclosed on the artefact) |
| coverage.bars | 10,513, `within_session_breaks` 0 |
| supported_nodes | all five |
| input_sha256 | `867586990fa4a994...` (distinct from the adopted run's `77071f4c...`, as it must be) |
| hidden_edges | 0 |

Matrix `B[target, source]`, four edges above the 0.001 display threshold:

| source | target | weight |
|---|---|---|
| auto_components | aluminium | 0.0069 |
| solar | aluminium | 0.0319 |
| steel | solar | 0.0092 |
| auto_components | steel | 0.0434 |

Self-excitation: aluminium 0.0533, auto_components 0.0859,
pharmaceuticals 0.0993, solar 0.2809, steel 0.0696. Every source column sum
is within the declared 0.95 stationarity bound, the largest being solar at
0.3128.

**Honest negatives, retained rather than tuned away:** `aluminium` and
`pharmaceuticals` emit NO cross-sector edge at all. The proposal's own
instruction applies -- the parameters "are not to be tuned to produce a
connected or visually attractive graph" -- and nothing was.

The artefact carries its three limitations: conditional excitation weights
rather than causal effects or loss probabilities; an integrated infinite-lag
kernel whose session resets truncate realized within-session excitation; and
a full-sample descriptive fit unavailable to decisions before its sample end.

**Both artefacts stand.** The adopted full-interval fit remains
`insufficient_support` with its own hash, and the specification is unchanged.
The exclusion is a scope reduction, disclosed on its artefact, not a model
change.

**Still the owner's to decide:** whether the exclusion variant is the F07
result of record, or whether the halts should instead be declared as session
structure with an intraday lag reset (which needs NSE's record of the two
halts and the model decision above), or whether the recorded
`insufficient_support` over the full interval is the answer. All three are
defensible; nothing here chooses.

## NI17: the language quota cannot be met today

Two findings, both measured.

**1. The corpus window is historical, so new acquisition cannot fix it.**
`export_corpus` takes the FIRST 600 unique documents by `first_seen`.
Anything acquired now lands after that window. Reaching `non_english: 100`
in a 600-document chronological corpus needs the store's non-English DENSITY
over a 600-document stretch to be about 17%; `pib_releases`, the only
registered Hindi source, supplies 29 of 600, about 5%. Re-sampling the corpus
to raise the count would break the chronological split and risk leakage, so
it was not done.

**2. No additional non-English source probed as usable** (2026-10-25,
read-only HTTP):

| candidate | result |
|---|---|
| PIB Hindi, `Regid=0` and `Regid=9` | HTTP 200 but **0 items** |
| PIB `ModId=5` | HTTP 404 |
| RBI Hindi press | HTTP 418 (bot detection) |

Only the already-registered `ModId=6&Lang=2&Regid=3` combination yields
items. So the quota is blocked on SOURCE AVAILABILITY, not on acquisition
effort: it needs either a non-English source this project can lawfully reach
(which may require authorisation this session does not have), or an explicit
owner decision about the quota itself. Neither was assumed.

## NI17 materials prepared, 2026-10-25

`prototype_runs/review-corpus-2026-10-25/` -- 600 documents, hash
`144c8f6496d707f0...`, split 300 train / 100 calibration / 200 test by
`first_seen` chronologically, with a blank `reviews.jsonl`, a
`review-template.jsonl` per document and the README's review procedure. No
scores are generated by export and no review was fabricated:
`reviewed_documents: 0`.

This clears the corpus-size requirement that the 2026-10-18 snapshot could
not (395 documents, zero test documents). Two requirements are measurable
without any review:

| requirement | have | need |
|---|---|---|
| total | 600 | 600 OK |
| locked_test | 200 | 200 OK |
| **non_english** | **29** | **100 -- short by 71** |

The only Hindi source registered is `pib_releases`, which supplies all 29. So
NI17 cannot pass on this corpus however good the review is, and more
non-English acquisition is needed before a corpus is re-exported.

A further composition risk, flagged before anyone reads 600 documents: the
six reviewer-assigned category quotas (120 + 120 + 120 + 80 + 80 + 80) sum to
exactly 600, so there is NO slack -- every document must land in a quota that
needs it. `logistics_hazards` needs 80 against roughly 43 plausible
candidates (40 `usgs_earthquakes`, 1 `production_halt`, 2
`facility_incident`). 457 of the 600 classify as `other` under the
extractor, which is a proxy for the reviewers' judgement and not a
substitute for it. The corpus spans 2026-10-16..2026-10-19 from 19 sources,
and 483 of 600 are `headline_only`, so a reviewer sees a headline and no
body for most of them.

Gate run against it (`gate.json`): `gate_passed: false`,
`corpus_sufficient: false`, every slice `evaluated: false` with 0 scored
against the 20 minimum, `reviewer_independence: "attested by reviewers; not
established by software"`. The lookahead and adversarial checks DID run:
0 breaches, 8 adversarial cases, 0 outstanding.

## Authoritative suite, 2026-10-25

**2,684 passed, 5 skipped, 0 failed (26m44s), 2,689 collected.**
`scripts/check_invariants.py`: 7 ok.

Run after both sessions stopped editing, with nothing acquiring and a freshly
created disposable database (`seraph_test_auth`), so the 17 database-gated
tests executed. The 5 remaining skips are external-data only and named:
4 x `contract/test_ct3_jump_sufficiency.py` (needs
`scripts/backfill_intraday.py`) and 1 x `test_fresh_data_acquisition.py:445`
(needs `SERAPH_LIVE_NSE=1`).

Two hazards wasted earlier runs; both are avoidable and worth recording.

1. **Editing a module while the suite runs.** pytest keeps the pre-edit module
   in memory while Streamlit's `AppTest` re-executes the post-edit app from
   disk, so five `ImportError`s appeared in `tests/test_u01_console_startup.py`
   that a clean process did not reproduce (23 passed). Do not edit during a
   run; in a shared checkout, agree who runs it.
2. **A news worker writing to the live store mid-run.** Several tests read
   `prototype_runs/news-intelligence-pilot.sqlite` by its real path, and
   `pagination.total` was seen moving 2032 -> 2087 -> 2137. Check
   `worker_state(_now())` shows no live beat and that no `run_news` /
   `news_supervisor` process exists before starting.

Also: a used test database is not disposable. The guard refuses
`seraph_test_local` and `seraph_test_redesign` once `validation_results` holds
rows, which is correct. Create a fresh `seraph_test_*` and provision it.

## Fifth continuation -- Classic defects closed

Two user-facing defects fixed, both found by building the second frontend.

**1. The news-only console panel reported zeros against a full store.**
`build_news_payload` returns `surfaces` / `source_coverage` / `freshness` and
has NEVER returned a `channel` key, but `news_only_panel` in
`seraph/dashboard/prototype_app.py` read `payload.get('channel')`. So it
showed "Events visible now: 0" and "Sources reporting: 0" against a store
holding thousands of events. The panel is only reachable with no archive
store attached, which is why it went unnoticed.

The row shape was wrong too: rail items carry `headline` (not `title`) and
`sources`, a list (not `source_id`); and `freshness` has no `state` key, it
has `stale`. Counts now come from `pagination['total']` rather than the
length of one page, because the rail is paginated. Pinned by
`test_the_payload_has_no_channel_key_and_counts_live_on_surfaces` in
`tests/test_news06_overlays.py`, which asserts the key names from the
Classic side; the redesign has its own adapter test asserting them from the
other side.

**2. The warm-up shortfall was not disclosed anywhere.**
`assess_publication` can only emit `warmup_incomplete` -> "the model state
has not finished warming up". Nothing said how far short, or which pillar,
so a pillar two observations in looked identical to one nearly ready.
`console_backend.warmup_progress(store, required=None)` now reports per
pillar, counted the way `StandardizerHistory.assimilate` counts -- one
observation per distinct `input_end`, so a retained model re-emitted under a
second timestamp cannot inflate it. A pillar holding only declared absences
is reported `absent`, which is a different fact from partial progress, and an
archived research value is reported as `archived_not_counted` rather than
dropped. `live_panel` now names the shortfall on screen. It reports only; it
changes no threshold and gates nothing.

Against the production store today: **hawkes 1 of 252 (plus 1 archived, not
counted), rmt 253 of 252 ready, hamilton absent** with 256 declared absences.

Pinned by `test_warmup_progress_counts_distinct_input_ends_and_names_absence`
in `tests/test_closeout_input_contracts.py`.

**3. The historical news branch RAISED for any decision from 2026-10-19.**
`NewsStore.sources_at` rebuilt each roster entry with `Source(**payload)`.
The stored payload carries `permitted_uses`, which is not a `Source` field,
so it raised `TypeError: unexpected keyword argument 'permitted_uses'`.
21 of the 73 stored versions carry it, the earliest 2026-10-19 (so this
predates the energy registrations, which merely added more such rows).

That is the STRICT REPLAY path -- `coverage_at(..., strict_replay=True)` --
which is what `news_mode='historical_decision'` uses, the console's default.
`source()` has always constructed field by field and so tolerated extra keys;
`sources_at` now filters the payload to `Source`'s dataclass fields, so a
roster stays readable across a build that stored a field this one does not
know. Unknown keys are ignored, never guessed at. Verified: 21 sources today,
11 at 2026-10-18 (correctly fewer). Pinned by
`test_sources_at_reads_a_stored_field_this_build_does_not_know`.

**4. The console paid the whole news projection on every render.**
Measured here: `build_news_payload` alone takes **27.0 s** on the current
store (2,137 eligible events, 4,938 stories), and a second identical call
25.0 s; a peer session measured the whole branch at 46.5 s against 0.2 s with
no store. `project_run` attaches the store on every render, so every
interaction paid it, and it grows as the worker acquires.

`news_branch` now caches the **`historical_decision`** branch for 30 seconds.
Only that branch, deliberately: its clock is `point['evaluation_timestamp']`,
so for a given decision the projection is deterministic and caching changes
nothing the screen says, and it performs no writes. `current_news` calls
`store.save_snapshot(...)` and stays uncached. The TTL equals the console's
own re-projection interval, since `bridge.js` fires `news_project` on a 30 s
`setInterval` -- shorter would start a rebuild that cannot finish before the
next tick, longer would let a projection outlive the interval meant to
refresh it. The key covers store, registry counts, decision, role, offset,
portfolio, sector flags and preview, because a key that missed one would
serve one role's projection to another. Entries are deep-copied in and out so
a caller cannot corrupt the next render, and the cache is bounded at 8.

Measured after: **cold 4.86 s, warm 0.00 s**, identical projection, a
different role correctly missing. `clear_news_branch_cache()` is exported for
tests and an explicit reload.

Not changed: `LIVE_POLL_SECONDS` in `prototype_app.py` is declared and never
referenced, so Classic has no polling behaviour. It was left alone rather
than either removed or implemented, because Classic is the preserved
fallback; the redesign implements the intent as a Streamlit fragment, which
is the safe shape -- a plain rerun loop would hit the half-typed-form problem
`main()`'s own comment describes.

### Audit status

`SERAPH-OVERALL-ENGINEERING-COMPLETION-AUDIT-2026-10-20.md` now has exactly
**one** package still marked PARTIAL: **F07**, whose stated remaining work is
"adopt a supported specification and obtain real native counts before
fitting" -- an owner decision, not engineering. Every other package is
complete or closed within its stated bounds.

The redesign's parity checklist had two open code gaps (live revision
polling, sector-basis toggle); both were handed to the session that owns
those files rather than edited concurrently in the shared checkout.

## Fourth continuation -- what the Hawkes cadence actually is

Investigated the question "was the standardizer meant to consume distinct
daily point-in-time Hawkes estimates, rather than only newly fitted-model
vintages?" **Answer: no.** Evidence, measured not assumed:

- `research_data/original_hawkes.parquet` is the ORIGINAL pillar output: 473
  observations, 2017-02-09..2026-08-20 (9.52 years) = **49.7 per year**.
  Consecutive gaps are 7 calendar days 349 times, 8 days 79 times. Stamps are
  09:55 UTC = **15:25 IST**. Weekly, i.e. every ~5 trading sessions.
- Its ungated statistic `branching_ratio_n` has **473 distinct values in 473
  observations** (every run length 1), so the model really was refit at every
  emission. One vintage per fit at `refit_sessions = 5` therefore REPRODUCES
  the original cadence. The native producer is faithful; it is not deviating.
- The `mts` column is the FR13-GATED statistic and is 0.0 for 350 of the 473
  (two runs, 2017-09-05..2019-06-25 and 2021-01-04..2026-03-24). `_persist`
  already carries the note that the pillar value is the UNGATED
  `n/(1-n)` "rather than destroying the rank signal with repeated zeros",
  which is the right call and should not be revisited.
- There is no daily-varying pillar statistic to emit. The value is a function
  of the fitted parameters, so re-emitting it between refits would be
  duplicate observations. (`excitation_path` / `sector_flags` DO vary daily,
  but they drive the FR14 sector micro-flags, not the pillar value.)
- For comparison, RMT in the live store emits **250.7 per year** -- daily.

### The one genuine incompatibility (owner decision)

`seraph/orchestration/standardize.py`:

    #: Trading days in the FR28 window. 252 x 5 ...
    FULL_WINDOW_OBS = 252 * ECDF_WINDOW_YEARS
    #: ... One trading year.
    MIN_WINDOW_OBS = 252

`MIN_WINDOW_OBS` is a **trading-day** count ("One trading year"), calibrated
for a daily pillar -- RMT reaches it in a year and holds 256.
`scripts/run_live.py:110` passes it as `warmup_observations` for EVERY pillar.

At the Hawkes cadence of ~49.7/year, a 5-calendar-year ECDF window holds
**~248 observations, which is below 252**. So the Hawkes warm-up gate is
unsatisfiable BY CONSTRUCTION, independent of data depth. The archived series
proves it: 9.52 years is the deepest Hawkes history that has ever existed in
this project, and any 5-year slice of it holds ~248.

Note also that the standardizer's own response to a short window is to WARN,
not withhold: below `MIN_WINDOW_OBS` it attaches `PARTIAL_COVERAGE` saying
"The rank is emitted and flagged, not withheld". The hard withholding is a
separate, deliberately declared policy -- `PublicationPolicy.require_warmup`
defaults True -- so the two are consistent, not contradictory.

Options, with their scientific consequences:

| | change | needs | consequence |
|---|---|---|---|
| **A (recommended)** | count the warm-up threshold in the pillar's OWN cadence: one trading year of Hawkes observations is ~50, not 252 | ~198 more all-member sessions (~9 months) | preserves every equation, the 500-session window, the 5-session cadence, the ECDF transform and the 5-year window; corrects a unit. Cost: the ECDF reference holds ~50 points at warm-up, so rank granularity is ~2% rather than ~0.4%, and `PARTIAL_COVERAGE` stays attached until 252 -- exactly as designed |
| A' | threshold = a FULL five years at the pillar's cadence (~248) | ~1,200 more sessions (~5 years; Kite has 5-minute data from 2015-02-02, so it is obtainable) | keeps rank granularity essentially at the intended 252; much larger acquisition |
| B | nothing | nothing | honest status quo: Hawkes never completes warm-up, the composite stays RMT-only with the D2 mask excluding Hawkes, and no current market reading is ever published |
| C | make the pillar a daily statistic (e.g. realised excitation under the retained model) | revalidation | a genuine METHODOLOGY change -- the pillar would no longer be the weekly fitted-branching-ratio statistic. Not recommended |
| D | set `require_warmup=False` | nothing | publishes a current reading with `warmup_incomplete` disclosed; weakens a declared safeguard. Not recommended |

A is a unit correction, not a weakening: 252 weekly observations was never
attainable, and the constant's own docstring says "One trading year".

### Replay proven, and the driver exists

Three past cutoffs now fit, against the real 652MB native history with writes
going to an ISOLATED copy of the live store (production untouched):

    2026-08-06  fitted=True  input_end=2026-08-06T15:15:00+05:30
    2026-09-15  fitted=True  input_end=2026-09-15T15:15:00+05:30
    2026-10-09  fitted=True  input_end=2026-10-09T15:15:00+05:30

Each reports `observed_sessions=500` and `incomplete_members=0`, and each
`input_end` lands at **15:15** -- the CAS-correct session end, so the dated
session policy is being applied inside the replay. The resulting vintages
carry distinct historical `input_end`s with `emission_available_at` set to the
ACTUAL computation time, which is the `run_daily.persist` convention for a
computed observation and the one the RMT warm-up used.

Before the look-ahead fix all three answered `refit_not_due`, because the
existing fit trained through 2026-10-22 was visible to an earlier cadence
point. That was a genuine defect, not a configuration issue.

`scripts/warm_native_hawkes_history.py` is the companion to
`warm_runtime_history.py` (which does RMT and explicitly does not do Hawkes).
It walks the declared cadence with `fit_pending(data_cutoff=...)`, defaults to
printing a plan, resumes where it stopped, bounds a run with `--max-fits`, and
writes a status JSON. It counts admitted observations the way
`StandardizerHistory.assimilate` does -- one per distinct `input_end` -- so the
number cannot be inflated by re-emitting a retained model, and it reports a
shortfall rather than lowering `--required`.

Plan output against the current history: 695 sessions visible, **196 candidate
cadence points** (2026-01-06..2026-10-22). Only the later ones can succeed:
a candidate whose 500-session window reaches back before 2024-08-01 fails on
`incomplete_members`, because the 72 members that begin then have no bars
there. Those failures are counted by reason in the status file rather than
hidden.

### Driver proven, and the dated-basket scope measured

First bounded `--execute` run (isolated store, production untouched):

    fitted 2026-08-13 -> input_end=2026-08-13T15:15:00+05:30
                         sessions=500  incomplete_members=0
    admitted_before 4 -> admitted_after 5    shortfall 247 (reported, not lowered)
    skipped: no_eligible_basket 117
             Incomplete common native-bar coverage 26
             refit_not_due 5

So the replay, the cadence, the persistence and the observation counting all
work. The run took ~26 minutes for 149 candidates and one fit, because a
candidate that fails coverage still pays the coverage query.

**`no_eligible_basket` on 117 of 196 candidates is the next real constraint,
and the producer is right to refuse.** The live config carries one
`rebalance_date` (2026-07-01), and a window ending before that date cannot
legitimately use a basket that did not exist yet. With a single basket, fits
are only possible at cadence points at or after 2026-07-01 -- about 16 of
them at cadence 5, regardless of which observation threshold is chosen.

`--baskets dated` now selects the basket each cadence point actually had,
from C3's `universe_snapshots` via the same `build_symbol_list` projection
the live config uses: **43 epochs, 2005-07-01..2026-07-01, baskets of 91-98
members** (semi-annual). `--baskets config` remains the default so the
verified behaviour above is unchanged.

**But dated baskets need bars this history does not have.** Measured:

| | |
|---|---|
| epochs inside a 5-year window | 12 |
| union of their basket members | **183** |
| symbols with native bars today | 95 |
| of that union, MISSING native bars | **88** |
| additional bars | ~8.2M (~1,144 Kite requests at the 100-day cap) |

That is on top of deepening the existing 95 members, and it is the honest
scope of a correct point-in-time Hawkes warm-up: not a 380-request job but
roughly 1,500 requests and ~10M bars. All of it is gated on broker
authentication; none of it changes a model, a window, a cadence or a
threshold.

### Engineering completed regardless of that decision

`seraph/pillars/hawkes/runtime.py` now separates BAR-TIME from ARRIVAL-TIME
selection. Previously `rows`/`sessions`/`eligible_count`/`coverage` filtered
`end<=?` and `received_at<=?` with the SAME mark, and every native bar carries
the same bulk `received_at`, so a historical cutoff saw ZERO bars and no
point-in-time replay was possible. The new `arrival` keyword defaults to the
bar cutoff, so live behaviour is unchanged; `fit_pending(data_cutoff=...)`
fits a past window while the arrival guard stays on the real clock. Dated
rule sets (the CAS schedule) are filtered by arrival, because a replay run
today legitimately knows today's exchange evidence and records its ACTUAL
availability -- the convention `run_daily.persist` already uses for computed
observations. Verified: `test_native_hawkes_runtime.py` and
`test_closeout_input_contracts.py`, 21 passed.

## Third continuation, same day -- Hawkes warm-up feasibility

**Correction to the F02 section below.** That section treats the 14,630
missing symbol-bars as the blocker for the native Hawkes fit. Measured
against the fit gate, they are not, because
`docs/evidence/engineering-closeout-2026-10-24/native-session-schedule/schedule.json`
(56 dated sessions, 4 special pre-open notices, 61 sources, zero failures)
declares the ACTUAL common continuous session. With it applied at a current
cutoff, `NativeHistory.coverage` over the 500-session window returns:

| | without schedule | with schedule |
|---|---|---|
| missing_symbol_bars | 14,630 | **0** |
| incomplete_members | 87 | **0** |
| excluded_noncommon_rows | 0 | 4,750 |
| input_end | 15:30 | **15:15** |
| fit gate | FAILS | **PASSES** |

That is a legitimate resolution -- the grid is shortened to the session that
actually traded, rather than bars being imputed. The census figure of 14,630
remains true as a statement about raw bars, and re-acquiring them is still
worth doing because it recovers real observations, but it does NOT gate the
fit. A schedule rule only applies to cutoffs at or after its own `received`
time, which is correct information-time discipline (an earlier probe that
used a 2026-10-23 cutoff saw no effect for exactly this reason).

**The real blocker for warm-up is native history DEPTH, and it is arithmetic.**

- `_fit_pending` requires `observed_sessions >= window_sessions` (500) with
  zero incomplete members, and `days` is the UNION of sessions any configured
  member reports, with `window_start = days[-500]`.
- Native history: 695 union sessions (2019-10-01..2026-10-22) but only **552
  with all 95 members** (2024-08-01..2026-10-22). The older 143 sessions
  carry 23 members, so any window reaching into them makes the other 72
  incomplete and fails the gate.
- Therefore only **53** cutoffs have a 500-session window inside all-member
  coverage: 2026-08-06..2026-10-22.
- A historical vintage may not use a fit trained after its own date, and
  `DailyVintageProducer` only READS stored rows, so each legitimate
  observation needs a rolling fit trained through its own date.
- **CORRECTED 2026-10-24 (supersedes the 199-session figure below).** An
  earlier revision of this section said 252 observations need 751 sessions,
  a shortfall of 199. That assumed one observation per SESSION. The code says
  otherwise, and it was checked against the store:
  `_persist` writes exactly ONE `record_daily_vintage` per fit, with
  `input_end` = the fit's input end; between refits `vintages_for` returns
  that same stored vintage and `assimilate` dedupes on
  `producer@input_end#bundle_id`. The store holds exactly one
  `native-hawkes:` deployment and exactly one computed vintage, sharing
  input_end `2026-10-22T15:15:00+05:30`.
  **So it is one observation per FIT.**

With `refit_sessions = 5`:

| | |
|---|---|
| sessions for 252 fits | `500 + 5 x 251` = **1,755** |
| all-member sessions available | 552 |
| shortfall | **1,203** (~4.8 years) |

**And acquiring them would still not work.** `StandardizerHistory.window`
PRUNES observations older than `window_years = 5`, and readiness counts the
window. At the measured rate of 248.3 sessions/year, a 5-year window spans
~1,241 sessions, which at cadence 5 holds only **~248 fits — fewer than the
252 required.** So at cadence 5 the requirement is unsatisfiable no matter
how much history is acquired.

This is the direct answer to "verify that the five-session refit cadence and
five-year history window can satisfy the requirement": **they cannot, and
they are mutually inconsistent at cadence 5.**

The cadence is what the requirement is sensitive to (measured, and NOT a
recommendation to change a declared parameter -- `refit_sessions` is part of
`_compatible`, so changing it invalidates existing fits and must be an
explicit owner decision):

| cadence | sessions for 252 fits | 5-year window holds | verdict |
|---|---|---|---|
| 1 | 751 | ~1,241 | fits; needs **199** more sessions |
| 2 | 1,002 | ~621 | fits; needs 450 more |
| 3 | 1,253 | ~414 | fits; needs 701 more |
| 5 (current) | 1,755 | ~248 | **impossible** |

Note that moving the cadence from 5 to 1 refits MORE often; it weakens
neither the 500-session window nor the 252-observation count.

### A second, structural blocker to a point-in-time replay

Every row in the native history carries the same `received_at` (the bulk
seeding time, 2026-10-22T18:57), and `NativeHistory.sessions` /
`coverage` / `rows` all filter `received_at <= mark` using the SAME mark as
the bar-time cutoff. So a replay at any historical cutoff sees **zero bars**,
and per-session historical fits cannot be produced from this history at all.

The established, honest convention for backfilled observations is already in
the repo and does not require inventing arrival times: `run_daily.persist`
records a computed vintage with `emission_available_at = ` the ACTUAL
computation time (preserving first availability on replay), with `input_end`
historical. That is how the RMT warm-up built its 252 observations. A native
Hawkes replay should follow it.

To do that, `NativeHistory`/`NativeHawkesProducer` need an explicit replay
data cutoff on BAR TIME, separate from the availability mark used for
`received_at`. That is more restrictive on bar time and unchanged on arrival,
so it does not weaken the live guard -- but it is a change to C5 and should
be made deliberately, not as a side effect. The CAS session schedule is also
only valid for cutoffs at or after its own received time (2026-10-24T18:00),
which is correct information-time discipline and means historical CAS-period
fits must carry that availability rather than an earlier one.

**Unblocking command** (verified by dry-run: 4 windows/symbol, 380 requests):

```
python scripts/backfill_intraday.py --from 2023-09-01 --to 2024-08-01 \
  --checkpoint prototype_runs/depth-extension.checkpoint.json
```

That adds ~230 all-member sessions (552 -> ~782, clearing 751). It needs a
fresh Kite login; tokens expire daily. Afterwards re-seed with
`prepare_native_hawkes.py`, regenerate the session schedule to cover the new
dates, then replay the rolling fits.

Current admitted state: `daily_vintages` holds 253 hawkes rows but only **2
with a value** (one `computed` 2026-10-22T15:15, one `archived` 2026-08-20),
and 251 absences, all reading "no fresh native-intraday Hawkes estimate". RMT
is complete at 256 values; Hamilton is 256 declared absences by design. A
`run_native_hawkes.py --once` today returns `refit_not_due`, which means a
compatible fit already exists and the cadence is being respected.

Building the 53 reachable observations was deliberately NOT done: the warm-up
gate is binary at 252, so 53 unlocks no capability and would spend a long
rolling-fit run for no change in readiness.

## Second continuation, same day

- **The pilot store is now live with energy coverage.** Verified through the
  normal pipeline (`run_news.py --register`, then `--once`): 21 sources,
  3,546 stories (+750 in one pass), both energy feeds `ok=True` with 10
  stories each, zero failures. A first `--once` was correctly REFUSED by the
  poll lock left by a killed run -- the lock works; wait for the lease.
- **36 energy issuers registered, sector cited not guessed.** Source is NSE
  Indices' own Nifty 500 constituent list, whose `Industry` column supplies
  the sector, plus Symbol and ISIN:
  `https://nsearchives.nseindia.com/content/indices/ind_nifty500list.csv`
  (retrieved 2026-10-24T17:32:08+05:30). `Power` and
  `Oil Gas & Consumable Fuels` both map to the single existing `energy`
  sector because that is what the curated edges target; the cost is that an
  oil-price event and a generation event reach the same bucket. NTPC and
  Oil India were skipped as already registered. Entities 22 -> 58;
  `sector=energy` 3 -> 39; places/assets/edges UNCHANGED at 19/28/64.
  Zero resolution regressions across the 22 pre-existing entities.
- **Exposure routing now demonstrably fires on real news.**
  "POWERGRID Commissions Project to Evacuate Renewable Energy in Karnataka"
  (Mercom, 2026-10-24) produces `event.affected =
  ('power_grid_of_india', 'sector:energy')` with an evidence span citing the
  token `Commissions`. Three things had to compose: a registered source, the
  `commissions` classification fix, and the issuer being in the registry.
  Measured honestly: 20 energy stories -> 4 classified -> 1 routed. The
  other three correctly abstain (a state government, a place name, and an
  unnamed issuer are not routes). Aliases are mechanical (official name +
  NSE symbol); a bare one-token alias that is also a token of another
  company's name is dropped, so `RELIANCE` was not added -- it would have
  cross-attributed "Reliance Power" stories to Reliance Industries.
  Consequence: a mention like "HPCL" does NOT resolve until separately cited.

### F02 -- why only 72 bars/day, answered

Measured on the stored native history (4,150,272 rows), not inferred:

- The premise was wrong. The broker returns **75** bars/day on 50,417
  symbol-days (91%) and 72 on 4,888. The 213 twelve-bar days are the real
  Diwali Muhurat evening session (max observed slot 19:15).
- In the trailing 500 sessions the 14,630 missing symbol-bars split into
  **14,616 (99.90%)** session-tail bars (15:20/15:25/15:30) across 56
  CONTIGUOUS sessions 2026-08-03..2026-10-22 for the identical same 87 of 95
  members, and **14 (0.10%)** bars in just four symbol-days: ITC 2025-01-06,
  TMPV 2025-10-14, HINDUNILVR 2025-12-05, VEDL 2026-04-30 -- 0.0084% of the
  47,500 symbol-days in the window. Every one is 3-4 CONSECUTIVE bars
  starting at 09:25, in four of the most liquid names on the exchange, on
  four unrelated dates. That signature is inconsistent with illiquidity and
  consistent with a delayed start to continuous trading, such as NSE's
  special pre-open call auction on a corporate-action date. Which event
  applies needs the exchange's own record; either way the handling is the
  same -- the market was not in continuous trading, so there is no price to
  impute and these must not be filled. CONFIRMED: the owner's schedule
  carries four `special_preopen_notices` (CMTR65845, CMTR70614, CMTR71508,
  CMTR73856), one per symbol-day, so the delayed continuous-trading start is
  sourced from the exchange's own notices rather than inferred.
- The same 87 members every day rules out illiquidity and randomness. All 95
  were seeded in one 51-second pass from one source, so it is not fetch
  timing -- the truncation was already in the research DB.
- **RETRACTED 2026-10-24: this was NOT a request-side artifact.** The
  original claim here was that because eight members (BORORENEW, DATAPATTNS,
  EXIDEIND, GRSE, HINDCOPPER, MTARTECH, SUNDRMFAST, WEBELSOLAR) carry
  15:20/15:25/15:30 for the same 56 sessions -- 41,274 rows against the
  others' 41,106, a difference of exactly 168 = 56 x 3 -- the source must
  serve the tail and our request must be at fault. The row arithmetic is
  correct but the inference was wrong.
  The real cause is NSE's **Closing Auction Session**, introduced by SEBI
  circular and effective from 2026-08-03 for a dated member list. For a CAS
  member, continuous trading ends at 15:15 and the close is set by auction,
  so no continuous five-minute candle exists at 15:20/15:25/15:30.
  Checked against the owner's dated schedule: of the 95 configured members,
  **87 are in the CAS list and exactly the 8 that are not are the 8 holding
  those bars.** The split is explained completely.
  Consequence: **those 14,616 candles do not exist and must not be
  re-acquired.** Any instruction above or below to recover them is void, and
  the predicted census change from 14,630 to 14 will not happen.
- Those eight are NOT simply "the tariff representatives" -- only four are
  (EXIDEIND, SUNDRMFAST, WEBELSOLAR, BORORENEW); DATAPATTNS, GRSE,
  HINDCOPPER and MTARTECH are not in `TARIFF_SECTOR_BASKET`, and the eight
  straddle both history groups (23 members from 2019-10-01, 72 from
  2024-08-01). What they share is having been acquired by a separate run
  that passed an explicit end. Which run is recorded in the research DB as
  `run_id = intraday-backfill-<to.date()>`; that could not be read because
  the database is down.
- **Cause:** `scripts/backfill_intraday.py` ended its window at
  `now - 5 minutes` when `--to` was omitted (the form the unblocking guide
  documents). A daily job runs during market hours, so each run asked for a
  window ending mid-session and Kite answered correctly with what existed by
  then. One run truncates one day; 56 daily runs truncate 56 days.
- **Fixed:** the default is now the close of the last COMPLETED session, via
  `SessionCalendar.close_timestamp`, so a short session ends at its own close
  rather than a hardcoded 15:30. Regression tests in
  `tests/test_intraday_backfill_resume.py`.
- **Nothing to re-acquire.** The earlier recheck recording
  `returned_bars: 72` was CORRECT after all: for a CAS member the session
  really does end at 15:15. It should be cited as evidence, not doubted.
  The `backfill_intraday.py` default-window fix made today remains worth
  keeping on its own merits -- a run genuinely executed mid-session would
  truncate that day -- but it addresses a latent risk and recovers nothing
  here.
- Note for F07: the estimator refuses input with a missing within-session bin
  outright (`network.py`), so no imputation choice can be smuggled past it.
  Its proposed window (2019-10-01..2020-04-30) predates this truncation.

#### Missing-bar handling: the options, costed on the actual data

Denominators: 37,374 interval-slots and 14,630 missing symbol-bars in the
trailing 500 sessions; 47,500 symbol-days.

| option | what it does | measured cost | verdict |
|---|---|---|---|
| **Re-acquire with explicit `--to`** | ask the source for the whole session | recovers **14,616 of 14,630 (99.90%)** | **recommended** |
| Drop the three tail slots on those 56 sessions | shortens 56 sessions for every member | loses 168 slots (0.45%) AND discards 1,344 bars that genuinely exist (the 8 complete members') | fallback only |
| Per-symbol unbalanced panel (NaN) | each member keeps its own observed bars | no loss, no fabrication | rejected for the network diagnostic: `fit_network` raises on a missing within-session bin |
| Forward-fill / last observation carried forward | carry the 15:15 close across 15:20-15:30 | invents 14,616 prices | **rejected**: fabrication, and a carried close is a ZERO return, which biases negative-jump counts DOWN exactly at the close where auction jumps cluster |
| Common-support intersection | keep only slots every member has | identical to the drop row here | same objection |

**Recommendation -- SUPERSEDED.** This recommended re-acquisition on the
belief that the bars existed. They do not: see the CAS retraction above. The
correct handling is the owner's dated common-session policy, which declares
the session that actually traded (ending 15:15 for CAS members) and so
reports zero missing bars without imputing any. Re-acquisition would return
nothing. The comparison table above remains useful only as a record of which
imputation options were rejected and why; forward-fill in particular stays
rejected, and now doubly so -- it would invent prices for a period in which
continuous trading did not occur at all.

For the 14 that remain after re-acquisition: **exclude, do not fill.** They
are 4 symbol-days (0.0084%), each 3-4 consecutive bars from 09:25 in a
highly liquid name, which indicates the market was not yet in continuous
trading rather than that a price is missing. Filling them would invent
trading that did not occur. Excluding 4 symbol-days is not "shrinking the
dataset" in the sense the owner prohibited -- the window, basket and session
grid are untouched; the exclusion is recorded per symbol-day with its reason.

Sequence: restore the broker login -> re-acquire 2026-08-03..2026-10-22 with
an explicit `--to` -> re-seed the native history -> re-check the 500-session
census (expect 14 missing, not 14,630) -> then revisit the native fit.

### F07 -- hold kept, approval prepared

The recorded hold stands; nothing was fitted. The estimator enforces it in
code: `model_status='proposed_unadopted'` returns `design_required`. A
pre-flight passed the proposal's exact constants through `fit_network`'s
validation and they are structurally valid, so only the adoption line and
real counts are missing. See the response for the exact approval text.

### Environment -- restored

Docker Desktop was wedged on a dialog offering only "Quit" or "Reset to
factory defaults". Its own log gave the cause: `initializing Secrets Engine:
... rename engine.sock -> engine.sock.stale: The file cannot be accessed by
the system`. The socket resisted deletion even with every Docker process
killed, so its PARENT DIRECTORY was renamed to
`%LOCALAPPDATA%\docker-secrets-engine.stale-20261024180040` and Docker
recreated it clean. The factory reset was NOT used -- it destroys volumes.
Engine 29.8.2 came up ~160s after relaunch.

- research DB: `seraph-research-timescaledb`, healthy, 127.0.0.1:5434
- disposable test DB: `seraph-test-timescaledb`, healthy, 127.0.0.1:5435,
  `seraph_test_local`, 19 tables, migrations 001 + 002 applied, guard row
  present. Started with `docker start` because the container predates the
  compose project name; `--remove-orphans` was NOT passed (it would delete
  the research container).

### Full suite with both databases live

**2,621 passed, 0 failed, 5 skipped in 23:57.** Up from the 2,585 / 1 / 25
recorded earlier the same day with Docker stopped. The single earlier failure
(`test_a_date_before_any_print_is_an_explicit_absence`) passes, and
`tests/test_t06_t07_measured_surfaces.py` is 20/20 -- so that failure was the
stopped database, never a code defect.

The 5 remaining skips are named and environmental, not masked failures:
4 x `contract/test_ct3_jump_sufficiency.py` ("not enough intraday bars yet"),
which the tail recovery plus further backfill should clear, and 1 x
`test_fresh_data_acquisition.py:445`, the deliberate `SERAPH_LIVE_NSE` guard
against the suite silently depending on the exchange being reachable.

Honesty note on the arithmetic: the tree now collects 2,626 tests under every
flag combination tried, while the earlier run accounted for 2,611. Four of
that 15 are the window regression tests added today; the other 11 could not
be decomposed from the summary lines, and that run differed in BOTH `-I` and
database availability. No module-level skip or dynamic generation explains
it. The clean run above is the one to cite.

Also measured, against an earlier guess of mine: the 36 new entities slow
extraction 2.13x (22 -> 58 entities), which is close to LINEAR, not
quadratic, at 3.9 ms/story. The very slow suite attempt seen earlier was
caused by running acquisition against the production store while the suite
executed, not by the registry.

---

# October 22 native-runtime continuation — current handoff

Updated after the October 22 evening continuation. This section supersedes the
older October22 handoff immediately below.

- RMT warm-up is complete: 252 registered observations, zero failures; the
  evening runtime admits 253 including the October 22 daily observation.
- Native Hawkes producer, durable native history, seed CLI and explicit runtime/
  launcher wiring are implemented. See `NATIVE-HAWKES-RUNTIME-2026-10-22.md`.
  The worker now checks coverage before jump extraction, reports missing bars by
  member and reuses unchanged evaluations; eligible late arrivals trigger a retry.
- Refreshed broker login works for REST and the actual 95-symbol websocket.
  The latest probe is after-hours and published nothing. Do not repeat the old
  403 diagnosis. The next loaded-calendar opening is October 23, 09:15 IST.
- Recent backfill completed: 3,906,400 bars, 95 members, no rejected bars or
  incomplete request windows. Native seed has 4,150,272 configured-member bars.
  Its trailing 500 sessions contain 182 incomplete intervals / 14,630 missing
  symbol-bars; only eight members cover every observed interval. The native fit
  is withheld. Three direct source retries still omit the sampled gaps.
- F02 remaining: supported native coverage (or a separately specified and
  validated missing-bar method), actual Hawkes standardizer history, and genuine
  in-session publication. Do not silently shrink the window/basket, manufacture
  closes, backdate fit availability or promote legacy estimates. Use
  `native-readiness-final.json`, `native-common-grid-gaps.json` and
  `native-gap-source-recheck.json` to resume precisely.
- F07: owner explicitly chose **keep network fit pending**. Do not fit it.
- Evidence: `docs/evidence/engineering-closeout-2026-10-22/evening-continuation.json`.
  Full suite: 2,585 passed / 22 skipped / zero failures/errors. The 17 database
  skips subsequently passed on isolated port 5435; that disposable container is
  stopped again. Latest native coverage/cache changes: 38 passed. Invariants and
  whitespace checks pass. Counts overlap; no broad rerun without a new reason.
- Fresh canonical cold-start evidence: `engineering-closeout-2026-10-21/runtime-history-complete.json` confirms252 usable RMT observations and latest daily-input admission. This does not establish native Hawkes readiness or a live current decision.
- Preserve inherited uncommitted work. No commit or push was made.

---

# Earlier October 22 engineering continuation

Use `SERAPH-OVERALL-ENGINEERING-COMPLETION-AUDIT-2026-10-20.md`, especially its October22 reconciliation. Earlier notes below are historical and contain superseded blockers.

- F01/F03/F04/F05/F06/F08/F09/F10 have bounded actual-input/browser evidence. Do not repeat completed implementations or broadly audit again.
- F02: `scripts/warm_runtime_history.py --through 2026-10-21 --workers 2 --execute` is resumable. Inspect `prototype_runs/runtime-warmup-status.json` and the worker lock before starting it again. It computes actual RMT vintages, retains real emission times and never promotes legacy archives. Initial plan: 250 missing of252. Broker connected in the latest pre-open probe; no closed bar/current decision yet. Live Hawkes producer remains unconnected; Hamilton remains excluded.
- F07: native five-sector counts now exist. The concrete diagnostic proposal still awaits explicit adoption; do not fit or tune merely because time elapsed. Proposal: `evidence/engineering-closeout-2026-10-21/NETWORK-DIAGNOSTIC-DESIGN.md`.
- FR35 registration was authorized and performed; the real report has152 unavailable cells and canonical UI acceptance. The old registration-pending note below is superseded.
- Full-suite attempt crashed in optional Hamilton parameter covariance. Eight targeted contracts pass after disabling that unused computation; full-suite remainder is being checked separately. Preserve failure evidence; do not claim a full pass until results exist.
- All earlier sessions stopped per owner. Preserve inherited unrelated changes; no commits/pushes performed. User wants implementation through all unblocked essential work, with audit reconciliation and truthful demo status.

---

# Next session — SERAPH

Updated 2026-10-17 after batch **T04 · T05 · T06 · T13 · T07 · T08 · T09**,
then the **news-intelligence plan** (NI00–NI15 work; its own ledger is
`docs/NEWS-INTELLIGENCE-IMPLEMENTATION.md`).
The T00–T03 batch is summarised in
`docs/evidence/T01-T03-REPRODUCTIONS-2026-10-16.json`.

## Done in this batch

| Ticket | Behaviour now possible |
|---|---|
| **T04** (authorization half) | A `Principal` is a snapshot, never standing authority. Revoked grant, revoked session, revoked membership, disabled user and expired session all deny; `visible()` revalidates **once** for a 50-resource list. |
| **T05** | Each Hawkes window's counts are pooled from **that window's** member set, and every row carries a `WindowManifest`. A window whose manifest does not describe its counts is refused, not emitted. |
| **T06** | The live loop **invokes the risk engine**. Decisions are keyed by timestamp: ordered, idempotent, each vintage assimilated exactly once, each producer gated by declared cadence and five separately-stored times. |
| **T13** (+T10/T11 partial) | **Real sourced news reaches the real globe.** 30 RBI stories place India and Mumbai on the original Three.js globe, beside the fabricated layer, in a different palette, with click-through to real headlines and both timestamps. |
| **T07** | A decision, its checkpoint, the advanced head and its outbox events commit in **one transaction**. Crash injected at all four writes leaves nothing; a replay returns the same logical decision. A lifecycle says which state the runtime is in and why it is not publishing. |
| **T08** | A live decision reaches the screen **labelled for what it is**. `live`/`replay`/`demo` is chosen, never fallen back to; the latest score and the worker's health are separate facts; an outage never re-dates the last score. |
| **T09** | Acquisition went from **3 RBI feeds / 30 stories** to **6 sources across 3 jurisdictions / 116 stories**. SEBI, the US Federal Register and USGS are registered and polling; Washington D.C. now appears on the globe as a real foreign origin. |

## Evidence

- `docs/evidence/T04-AUTHZ-FRESHNESS-2026-10-16.json`
- `docs/evidence/T05-BASKET-SELECTION-2026-10-16.json` — **465 of 473** windows had different pooled counts; terminal-basket selection inflated contributors ×1.41 and negative events ×1.42; Δn up to **+0.0324** against a corpus `n` of mean ≈0.108.
- `docs/evidence/T06-EQUIVALENCE-FULL-2026-10-17.json` / `-1530-` — **5,361 archive sessions under both decision policies, 0 disagreements**.
- `docs/evidence/T13-NEWS-TO-GLOBE-2026-10-17.json` + `T13-GLOBE-BROWSER-2026-10-17.jpg`
- `docs/evidence/T07-DURABILITY-2026-10-17.json`
- `docs/evidence/T08-CURRENT-READER-2026-10-17.json`
- Decisions: **DR-08** (Hawkes membership policy), **DR-09** (intraday process clock).

## News intelligence (separate plan, separate ledger)

`docs/SERAPH-NEWS-INTELLIGENCE-DEVELOPMENT-PLAN-2026-10-17.md` is a
feature-specific plan with its own ticket set (NI00–NI18). What works now, on
the pilot store (`prototype_runs/news-intelligence-pilot.sqlite`, 200 stories,
11 feeds, 8 publishers, 181 eligible events):

**real news → interpretation → inferred sector impact → globe → clickable
evidence**, end to end, in the ordinary Streamlit flow:

- a US anti-dumping determination on an Indian product is classified
  `trade_remedy_determination`, its **legal stage** is read from the
  instrument (`consultation` → `announced` → `adopted` → `effective`), and its
  **subject origin** comes from the Federal Register's documented
  `"<Product> From <Country>:"` title form;
- direction is **role-based and stage-gated** — only an adopted determination
  or an issued order establishes a measure, and `exporter` is adverse while
  `domestic_producer` is favourable;
- the sector panel shows `steel · export, operation · adverse for this sector
  · size unknown · 8 unsized relationship(s)`, and clicking it opens all 8
  source documents;
- the globe carries five layers — origins, subjects, mentions, affected and
  documented paths — beside the preserved FABRICATED preview.

See the ledger for the defect-by-defect record. The ones worth knowing:
sector impacts were computed from the *displayed page* (a documented steel
exposure vanished); real evidence was captioned FABRICATED; a *preliminary*
determination was read as final (a false adverse signal); places had no
aliases, so `"People's Republic of China"` matched nothing; an earthquake
epicentre was labelled a city.

**Still not true there:** three RBI feeds plus SEBI, the Federal Register and
USGS are not world coverage; 13 of 28 remedies name countries the curated
registry does not hold; four exposure edges are a pilot, not a transmission
model; and no claim here is a measured loss or evidence of predictive skill.

## Defects found by running on real data, not fixtures

| Where | What |
|---|---|
| news resolution | the mention **"India" resolved to the RBI *entity*** — substring matching let a common word inside a longer name capture a mention. Now a contiguous whole-token run with a two-token floor. |
| news extraction | a **speech venue was recorded as an *affected* place**. Located records are now `mentions` with the role explicitly not established. |
| current reader | a decision stamped after now was reported as **"-340 min old"** and allowed through. Now refused as a clock or data defect. |
| market clock | `next_open` took the day's **first** window only, so during the lunch gap of a two-window special session it reported the market shut until the next day. |
| T06 harness | the first `standard_1530` equivalence run reported 449 disagreements; the cause was the harness letting `InferenceSession` build its own default clock, comparing two policies. |
| news acquisition | **SEBI parsed 30 items with zero usable dates** — its `pubDate` is `16 Oct, 2026 +0530`, a real date in a format RFC-822 does not cover. A comma was discarding an entire market regulator. |
| news acquisition | **PIB carries no date element at all** — `<title>` and `<link>` only. Rejected, with the reason recorded rather than dropped from the plan. |
| news acquisition | USGS times are epoch **milliseconds** (read as seconds: the year 57000); GDELT's `seendate` is 15 or 16 characters and pinning one length discarded every live timestamp. |

## Commands

```bash
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/python.exe scripts/run_live.py --status        # reads only
.venv/Scripts/python.exe scripts/run_live.py --once --replay # bounded wait
.venv/Scripts/python.exe scripts/verify_t06_equivalence.py --start 2005-01-01 --end 2026-12-31
node tests/js/news_layer_harness.mjs && node tests/js/bridge_harness.mjs
.venv/Scripts/python.exe scripts/build_implementation_status.py
```

## What is still NOT true, stated plainly

1. **No live feed.** The durable path, the engine-in-the-loop and the current
   reader have never run against a real tick stream. Every pass so far is a
   replay or a fixture, and the lifecycle correctly sits in `degraded`.
2. **No live pillar producer.** The loop calls the engine on every bar close,
   and `NullProducers` returns a *structural* absence for all three pillars,
   so a live tick produces no CSRS.
3. **No exposure edge is curated**, so the globe's **paths** layer is empty
   and browser acceptance 2 (foreign origin → evidenced Indian exposure) is
   unmet. Both endpoints now exist as real nodes — Washington D.C. and
   Mumbai — but the evidenced relationship between them does not, and nothing
   is invented to fill it.
4. **The corrected Hawkes rows are not persisted** — the source database is
   read-only, so `--write` needs the research instance on 5434.
5. **Engineering completion is not predictive validation.** The original
   advance-warning claim remains unestablished.

## Next

**T11/T12 — the extractor's vocabulary is RBI-shaped.** Broadening the sources
made this visible: **10 of 12 visible events now classify as `other`**,
because the classifier knows monetary and banking prose and does not know
trade-action, enforcement or seismic language. That is the single highest-value
next fix, and it is now measurable against a real multi-source corpus.

**T10 remainder — assets and exposure edges.** 5 places, 1 entity and 5 source
locations are curated. An exposure edge needs a documented, citable
relationship; until one exists the globe shows origins and mentions only,
which is the honest state and is why browser acceptance 2 is still unmet.

Also worth doing while it is cheap: **USGS already supplies its own
coordinate**, parsed and carried by the adapter but not yet used to place a
node. That is the one source where geography comes from the source rather than
the registry, and it would put a real physical-hazard node on the globe
without any curation at all.

Then **T14** (three role journeys through the actual UI), **T15** (operations,
delivery transport, backup/restore) and **T16** (prospective ledger).

### Also unblocked, out of sequence

**FIX05** is a normal task now: the owner recorded the FR35 decision (two
epochs for Table B, six-epoch kept separately as Table C) in
`docs/decisions/DR-05-2026-10-16-fr35-table-b-scope.md`. Parameterise
`configuration_list()` with an explicit `table_b_scope`, add Table C, replace
the xfail in `tests/test_fr35_ablation_design_pins.py` with a real assertion,
and commit `preregistration.json` **before** any AUC is computed.


---

# Batch 2026-10-17 (evening) — NI11/NI12/NI16 and FIX05

## What changed

**The exposure registry stopped being the bottleneck.** With 32 recognised
trade remedies and four curated edges, only five reached a sector — the
pipeline could read a determination correctly and had nowhere to send it.
Three more edges were curated (chemicals, aluminium, agriculture), each cited
to a first-party Federal Register document **read out of the store** by
`scripts/curate_trade_remedy_exposure.py` rather than transcribed, so a
mistyped reference is impossible and an edge whose document is not held is
refused. Impacts went 5 → **20**, across five sectors.

**The live channel was broken by real data, and is fixed.** One ordinary poll
brought 70 new stories and every subsequent read of the store raised:
`first_seen_at … precedes published_at … a source cannot be read before it
publishes`. The Federal Register places documents on public inspection and
schedules publication days ahead, so a document held today carries a future
publication date. 44 rows in the pilot store are of this kind. The guard was
kept — its real target is a back-filled `first_seen_at`, which is hindsight
dressed up as information the system held — and given the one fact that
separates the cases, which exists only at acquisition. See the ledger.

**`other` was never an extraction failure.** 132 of 263 events classified as
`other` and that had been read as an extraction problem for the whole of this
work. The Federal Register feed carries the entire US federal daily register:
polar bears, fishery councils, OMB paperwork. Relevance is now a separate
question from classification, and on that split the in-scope unclassified
count is **16 of 132**, 13 of them Hindi items abstaining by design.

**FIX05 is implemented.** The owner's DR-05 decision (Table B = two pre-Hawkes
epochs, six-epoch run retained as Table C) is in the code, the hash and the
tests. The long-standing `xfail` is retired because the question was answered.

## Numbers, measured not estimated

| | before | after |
|---|---|---|
| eligible events | 206 | 263 |
| trade remedies recognised | 32 | 38 |
| sector/entity impacts | 5 | **20** |
| sectors reached | 2 | **5** |
| exposure edges | 4 | **7** |
| in scope / received-but-not-relevant | — | 132 / 133 |
| in scope and unidentified | 132 (unsplit) | **16** (13 Hindi) |
| in scope, English, unidentified | 23 | **3** |
| scientifically unresolved tickets | 1 | **0** |

## Defects found by checking output rather than counting it

1. **"Scheduling of Full Five-Year Reviews" → `expired`.** A sunset review
   being *scheduled* is the proceeding that decides whether an order
   continues, published while it is in force; `expired` asserts the opposite.
   The first fix was a negative lookbehind and did not work — the Register
   writes "Scheduling of **Full** Five-Year Reviews" and `re` has no
   variable-width lookbehind — and the rule itself was wrong, so `expired` now
   needs explicit lapse wording.
2. **A revocation carried no sign.** Direction was gated on
   `adopted`/`effective`, so the clearest favourable trade-remedy outcome
   there is read identically to an opened investigation. Repealed/suspended is
   now `favourable` for an exporter, `adverse` for a domestic producer. A
   *rescission of an administrative review* is deliberately **not** treated as
   relief: it discontinues the proceeding and leaves the duty in place.
3. **"Advance Traveler Information for Rail" → `logistics_disruption`.** The
   rule keyed on bare transport nouns, so any document mentioning a railway
   was a disruption of one.
4. **A Hindi PIB release about India ruled out of scope.** The Hindi
   interpreter abstains, so no Indian place resolved — which hid a declared
   coverage gap behind a relevance label. An Indian publisher is now a basis
   in its own right; a US publisher's jurisdiction explicitly is not, or the
   filter would admit everything.
5. **Two tests of mine encoded defects** and are corrected in place with the
   reason, not quietly rewritten: the Table B stage expectation, and a
   logistics case that was a bad discriminator.

## Verified in the browser, not in the payload

`scripts/verify_news_sectors_browser.py`, ordinary Streamlit flow, read-only
store copies, no payload injection:

```
scope_line: "132 in scope · 133 received but not about this system
             (carried and linked, never deleted) · 16 in scope and unidentified"
scope_reason_labels: 56   sectors_named: 5
forthcoming_labels: 31    government_links: 1
```

Evidence: `docs/evidence/news-intelligence/ni12-sector-edges.json`,
`ni16-relevance-and-enforcement.json`, `sectors-and-forthcoming.json`,
`sectors-and-forthcoming.png`.

## What remains

**Owner's, not mine:**

- **DR-05 step 5** — commit `preregistration.json` **before the first AUC**.
  Deliberately not scripted: pre-registration exists so a person fixes the
  design before seeing a result.
  `python -c "from seraph.validation.preregistration import commit; print(commit())"`

**News plan (NI):**

| Ticket | What is left |
|---|---|
| NI08 | Official document bodies. Only ~20 of 278 stories have bodies; the rest are headline-only, which caps what interpretation can assert. Needs the redistribution terms actually read, per source — `may_store_full_text` is `False` everywhere on purpose. |
| NI10/NI12 | More cited edges. 7 against the plan's pilot target of 20 issuers / 20 facilities / 50 relationships. This is still the binding constraint on inferred impact; the extractor is ahead of the registry. |
| NI13 | Energy, power, IMD, pharma, China/EU source pilots. |
| NI14 | Evaluate optional NLP/LLM extractors against the deterministic baseline — including Hindi, which would retire the 13 abstentions. |
| NI17 | Frozen extraction/impact benchmark and release gates. |

**Market plan (T):** T14 (three role journeys), T15 (operations, backup and
restore), T16 (prospective ledger), T18 (release gate).

**Operational, not code:** the poller is not running as a service. One
`python scripts/run_news.py --once` is what brought in the 70 stories that
exposed the forthcoming-publication bug; `python scripts/run_news.py` polls on
the registered intervals. Until it runs continuously, "continuously updated"
is a capability rather than a state.

## Things worth not relearning

- `fed_press` reporting `new=0` is **correct**: it holds 20 stories and the
  server answers 304 Not Modified against a stored ETag. An earlier reading of
  that line as a dead source was wrong.
- The suite genuinely takes ~20 minutes; `tests/contract/test_ct7_simulator_consistency.py`
  alone is ~190s. It is not hung.
- Heredocs mangle backslashes and quotes in this environment. Write a patch
  script to the scratchpad and run it with `-I`.
- `sector:` targets terminate in the sector panel, not on the globe, because a
  sector is not a place. A thin arc count on the globe is the design, not a
  missing feature.


---

# Batch 2026-10-18 (early) — FIX05, and closing the 14 skipped tests

## FIX05 — the last `scientifically unresolved` ticket

The owner's DR-05 decision (Table B = the two pre-Hawkes epochs, six-epoch
RMT/Hamilton run retained as Table C) is implemented across steps 1–4 in one
change, because the scope, the hash and the test are only sound together.

```
two_epoch  rows=26  tables={'A': 14, 'B': 6, 'C': 6}  folds={'A': [4], 'B': [2], 'C': [6]}
six_epoch  rows=20  tables={'A': 14, 'B': 6}          folds={'A': [4], 'B': [6]}
hash two_epoch d12ed87f9a9e1f60…   hash six_epoch 68cea514cfdc655f…
```

`configuration_list(*, table_b_scope)` has **no default** — a `TypeError`
without it, a `ValueError` naming DR-05 on an unknown value — because the fold
count is inside the pre-registration hash, so a caller that inherits the scope
can produce a result under one reading and have it read as the other. SPEC
FR35's "20 configurations" is preserved as A + B; Table C is additional, not a
renumbering. `PRE_HAWKES_EPOCHS` is reached by a code path for the first time.

The long-standing `xfail` is retired **because the question was answered**, not
because the marker was inconvenient — DR-05 was explicit that this distinction
mattered. The diagnostic test that recorded the contradiction is kept, inverted
to guard the resolution: if Table B ever stops being built from
`PRE_HAWKES_EPOCHS` without DR-05 being revisited, it fails.

**Step 5 is the owner's and is deliberately not scripted.**
`preregistration.json` must be committed by a person before the first AUC —
a script writing it unprompted defeats what pre-registration is for.
`commit()` already refuses to overwrite.

## The 14 skipped tests → 4

Docker was simply not running. But starting it was not enough, and finding out
why took longer than it should have:

**`DEFAULT_DSN` could never authenticate.** `bootstrap.py` hardcoded
`postgresql://seraph:seraph@localhost:5434/seraph_research`; compose sets
`POSTGRES_PASSWORD: ${SERAPH_DB_PASSWORD:-change-me-locally}`. Two copies of
one default in two files, drifted. Following AGENTS.md §7 produced
`InvalidPasswordError` and a message telling you to run the command you had
just run. The default is now assembled from the same variables compose reads,
and a password is no longer hardcoded in a versioned source file.

**The skip reason named a cause it had not established.** The probe caught
every exception and reported "TimescaleDB not reachable". An auth failure, a
wrong port, a missing database and a stopped container are four different
problems and three are not unreachability. It now carries the real error and
names `SERAPH_TEST_DB_DSN` / `SERAPH_TEST_TOKEN`, with "`docker compose up -d`
alone is not enough" stated outright.

**A misconfigured opt-in printed an INTERNALERROR traceback.** Setting
`SERAPH_TEST_DB_DSN` to something unusable let the exception escape
`pytest_configure`, so a wrong password looked like a broken harness. Now a
one-line `pytest.UsageError`. The guard's behaviour is unchanged; only its
reporting.

With the guard satisfied: **98 passed, 0 skipped** across
`test_ct1_ingestion_idempotency`, `test_c2_macro_ingestion`,
`test_c5_hawkes_writer`, `test_fix06_evaluation_identity`.

## Two things I got wrong, recorded

**I improvised a test database the project already had tooling for.** I created
`seraph_test_ct` inside the research container before finding
`docker-compose.test.yml` + `scripts/provision_test_db.py` — tmpfs, own port,
own container, three independent refusals. Theirs is better on every count. I
re-ran against it (98 passed again) and **dropped mine**; `seraph_research` is
the only database in that container again. *Look for the provisioning script
before writing the setup by hand.*

**One of my tests depended on the wall clock.** `test_syndication_groups_read_a_
forthcoming_story` hardcoded `visible_at="2026-10-18T00:00:00+05:30"`, which
was comfortably in the future when written and went stale when the date rolled
over mid-session — the ingested story's `first_seen_at` is `_now()`, so it
sorted after the cutoff and the query returned nothing. It now takes the cutoff
from the story the store actually recorded. It also called `stories()` while
claiming to test `syndication_groups()`, which is the line that actually raised
in the original bug; it now calls the latter and checks the withheld case too.

## Database state — read `docs/DATABASE-STATE-2026-10-18.md`

Bringing compose up removed an older **stopped** container (`seraph-timescaledb`)
predating the source/research split. Nothing running was stopped and nothing
was deleted: `seraphvarya_seraph_pgdata` still holds a complete 9.2 GB PG 16
directory, verified by a read-only mount. But **nothing serves 5433 now**, and
OPERATIONS.md §1 says the source database is never started from this repo, so
no service was added for it. Restore recipe is in that document; the password
must come from outside the repo.

**One trap closed structurally.** Both compose files defaulted to the same
project name, so compose reported the research container as an "orphan" of the
test project and suggested `--remove-orphans` — which **would have deleted it**.
`docker-compose.test.yml` now declares `name: seraph-test`. It applies on the
next recreate; not applied here because a suite run was using the instance.

## Suite, definitive

```
1407 passed, 4 skipped in 1250.26s (0:20:50)     exit 0
```

Against the canonically provisioned test database. Previous run was
`1397 passed, 14 skipped` — 12 of those skips were the DB-dependent tests,
which now run; 10 extra passes come from them plus the new tests in this batch.

The 4 remaining skips are environmental and named: `test_ct3_jump_sufficiency`
needs `scripts/backfill_intraday.py` run first. Nothing is skipped for a
reason the suite cannot state.

Evidence: `docs/evidence/SUITE-2026-10-18-FINAL.json`.

---

# Batch 2026-10-18 (NI08) — the rights question, answered

`may_store_full_text` was `False` for every source, capping interpretation to
headlines: ~20 of 278 stories had bodies, and the Federal Register adapter was
extracting each document's `abstract` only for the store to discard it.

The terms are now **read per source** — `docs/decisions/DR-10-2026-10-18-source-text-rights.md`
carries the quotes and citations — and the answer differs by source, which is
why a blanket answer would have been wrong.

**Permitted:** `federal_register`, `federal_register_india` (17 U.S.C. §105),
`usgs_earthquakes` (USGS public domain), `pib_releases` (PIB's own policy
needs no prior approval), `fed_press` (already).
**Refused:** three RBI feeds ("© Reserve Bank of India. All Rights Reserved" —
no grant) and `sebi_press` (permitted only after a permission that has not
been requested).

Refusals now record "terms REVIEWED and REFUSED" with the reason, not "NOT
reviewed" — SEBI is one email away rather than an open question.

**Two facts checked rather than assumed:** the extractor does use bodies
(`text = f"{title}. {body}"`), and old abstracts cannot be recovered because
`observations.raw` is gated on the same flag — refused sources never had their
bytes kept. Bodies therefore accrue forward only, 20/278 -> 22/280 and
climbing.

**Retaining bodies is not a uniform improvement**, measured on 34 real
documents: 9 interpreted differently, of which **two were regressions**, both
fixed — PRA boilerplate making `action=decrease`, and a *Final Debarment
Order* read as `proposed` because its abstract narrates the preceding
proposal. The latter is the third instance of one family (after "Postponement
of Final Determination" and "Scheduling of Full Five-Year Reviews"), so it is
now a named rule: a finality marker in the **title** outranks a pending stage
found only in the **body**.

A real gap surfaced too: the stage rule matched `propose/proposes/proposed/
proposal` but **not `proposing`**, which is how a Federal Register abstract
almost always phrases it.

## Suite

```
1433 passed, 4 skipped in 913.22s (0:15:13)     exit 0
```

Up from 1407. The 4 skips are environmental and named (`backfill_intraday.py`).
Evidence: `docs/evidence/news-intelligence/ni08-source-text-rights.json`.

## What remains

**Owner's:** DR-05 step 5 (commit `preregistration.json` before the first
AUC); port 5433 not served (see `docs/DATABASE-STATE-2026-10-18.md`); and, if
wanted, one email to SEBI to unlock their full text.

**News:** NI10/NI12 more cited edges (7 against a pilot target of 50 — still
the binding constraint on inferred impact), NI13 further source pilots, NI14
NLP/LLM evaluation incl. Hindi (would retire the 13 abstentions), NI17 frozen
benchmark and release gates.

**Market:** T14 role journeys, T15 operations/backup/restore, T16 prospective
ledger, T18 release gate.

**Operational:** the poller still is not running as a service.
