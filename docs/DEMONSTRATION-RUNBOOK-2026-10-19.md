# SERAPH — how to run and demonstrate it

Written 19 October 2026 against branch `seraph/engineering-completion`.
Every command here was run on this checkout and its output is recorded in
[functional-completion-2026-10-19.json](evidence/functional-completion-2026-10-19.json).

Verified state: **11 of 11 checked journeys work; 8 are blocked** on a paid
subscription or an owner decision. §5 lists them precisely. The three items
that were blocked on a concurrent editing session are now closed: its news
work was landed, and the launcher, the workflow controls and the job-lease
fencing followed.

---

## 1. One-time setup

```bash
docker compose up -d
```

Brings up the research PostgreSQL on `127.0.0.1:5434` and applies
`seraph/store/schema.sql` on first boot. **Do not pass `--remove-orphans`** —
it would delete the research container, as `DATABASE-STATE-2026-10-18.md`
warns.

The 9.2 GB source volume on port 5433 is **not** used and was never
attached, migrated or modified. Everything below runs off the vendored EOD2
snapshot that ships in the repository.

```bash
python -m seraph.ingestion.eod2_client
```

Loads the vendored historical corpus. ~8 minutes, and idempotent — a second
run reports `inserted: 0`. Produces **7,385,306 rows across 3,524 symbols,
2005-01-03 → 2026-08-21**, which is where the vendored EOD2 snapshot ends.

```bash
python scripts/run_acquisition.py
```

Brings it up to date from **NSE's own public bhavcopy archive — no
credentials**. On this installation that added 38 sessions and 101,083 rows,
taking the corpus to **7,489,028 rows through 2026-10-19**. Two days came
back `not_published` (2026-09-14 and 2026-10-02, real NSE holidays), which is
the designed outcome of having no holiday calendar rather than a failure.

Kite Connect is needed for **intraday** bars — FR1's five-minute cadence, and
therefore the Hawkes pillar. It is not needed for end-of-day data, which is
why the daily pillars and the prediction engine run fresh while Hawkes stays
blocked on the subscription. Rows acquired this way also carry the exchange's
exact `TOTTRDVAL` rather than EOD2's `close × volume` proxy, which is what
FR52 ranks the universe on.

```bash
python scripts/build_universe.py --from 2005 --to 2026
```

Builds the FR52 point-in-time universe. **43 snapshots**; `Q_t = 2.00`
exactly from 2010-07-01 onward. The ten early snapshots print
`UNDERFILLED` — that is AMENDMENT-02's finding reproduced from data, not an
error.

---

## 2. Daily operation

```bash
python scripts/run_daily.py --day 2026-08-21
```

Computes the day's pillar vintages (~2 minutes) and persists them. Output:

```
rmt       origin=computed  value=0.2332
hawkes    origin=archived  value=0.0515
hamilton  origin=absent    standing research exclusion
```

Read `origin` as the honesty column, because the three are different claims:

| `origin` | means |
|---|---|
| `computed` | this installation ran the estimator, now, on corpus data |
| `archived` | read from a prior research artefact — a real measurement **of an earlier run** |
| `absent` | no estimate; the absence kind says whether that is structural or transient |

`--hamilton diagnostic` runs the full walk-forward instead of recording the
standing exclusion. It is much slower (it iterates all 5,363 calendar dates
with two queries each) and its result is excluded from the composite either
way, which is why it is not the default.

```bash
python -m seraph.ingestion.flow_client --turnover-source nse-index
python scripts/run_forecast.py --as-of 2026-08-21
python scripts/run_forecast.py --settle
```

The flow client reads NSE's public `fiidiiTradeReact` endpoint — no
credentials. The forecast commands issue and later settle prospective
forecasts; `--settle` refuses to attach an outcome before its horizon has
elapsed.

---

## 3. Running the application

```bash
./launch_prototype.ps1
```

Starts the console and the supervised news worker on
`http://127.0.0.1:8512`.

```bash
python scripts/run_live.py --status          # read-only; connects to nothing
python scripts/run_live.py --replay --once   # one bounded pass, no broker
```

`--status` is safe to run at any time: it reads persisted state and the clock
and starts no job. `--replay` **cannot** open a broker socket even with
credentials present — that was a repaired defect and there is a test for it.

The launcher also runs the market jobs in the background — the daily
vintages, the prospective forecast, and settling anything matured — so §2's
commands are not a second terminal any more. Every step there is idempotent,
so a relaunch repeats them harmlessly, and the console's **MARKET JOBS**
panel reports what the last run achieved.

It deliberately does **not** start the live tick loop. Opening a market feed
is an operator's decision, not a side effect of opening a dashboard.
`-NoMarketJobs` skips the market side; `-NoNewsWorker` skips the news side.

---

## 4. The demonstration, in order

Each step below is something that works. Nothing here needs a broker
connection or a paid subscription.

**If you have five minutes, lead with step 13.** Prediction and early warning
is what SERAPH is for, it is the console's first panel, and it is the one step
that shows the whole chain — market data through features, models, a forecast
and a warning decision — in one place.

**1. Show the data foundation is real.**
```bash
python scripts/verify_functional_completion.py
```
Ten journeys, each naming the requirement it satisfies, with the blocked
list printed beside them.

**2. Show the universe reconstruction.** Re-run `build_universe.py` for a
narrow range and point at `Q_t = 2.00` with 6–11% churn, then at the
`UNDERFILLED` early epochs. The FR52 filter-before-rank order is the
documented bug trap; the equity filter excludes `NIFTYBEES` and `GOLDBEES`
so mechanical ETF correlation stays out of `C_t`.

**3. Show a pillar computed today.** `run_daily.py` as above, then
`python scripts/run_daily.py --status`. Point at `origin=computed` for RMT
against `origin=archived` for Hawkes and explain why an archived
bar-frequency estimate cannot enter a live composite (§5, first row).

**4. Show the historical console.** Open the app, pick a complete run and a
date. The CSRS, its FR29 interval, the pillar diagnostics, the Shapley
decomposition and the plain-language explanation are all real archive
outputs. The history panel now carries the **official Nifty 500 overlay**
with its own units and an explicit gap before 2012-02-21, where the index
series begins and the CSRS archive does not.

**5. Show the flow panel.** Real NSE print — on the capture used here, FII
net −1,148.64 crore and DII net +3,201.19 crore for 2026-10-19 — with the
scope caveat attached: it is a market aggregate and a proxy for
non-institutional participation, never a per-instrument retail attribution.

**6. Show the durable role workflows in the browser.** Open **MY
WORKSPACE** under the run/date selection. Three tabs:

- *Portfolios* — upload a CSV with one bad row and show the rejection with
  its reason, save a dated snapshot, reload the page and show it is still
  there, then open History.
- *Scenarios* — switch to the institutional role, save a rank shock (it
  refuses without a justification), run it, compare two, review one, and
  download the export.
- *Regulator cases* — switch role again, open a case against the selected
  alert, pin evidence at a revision, record a decision, move the status (only
  legal moves are offered), and download the case export.

The 33 dispatcher tests still back this, if you want the same journeys
without clicking:
```bash
python -m pytest tests/test_t05_t08_t09_workflows.py tests/test_t05_t08_t09_ui.py -v
```

**7. Show the prospective ledger.**
```bash
python scripts/run_forecast.py --status
```
Forecasts with `outcome: null` — that is the ledger being prospective, not
missing data. Then show `--settle` refusing an immature outcome.

**8. Show that a replay cannot masquerade as live.** Run
`run_live.py --replay --once` and point at `publication_state: withheld` and
the stream-scoped decision id `historical_replay:replay:<bar end>`.

**9. Show the installed distribution.**
```bash
python scripts/verify_packaging.py
```
Builds a wheel, installs it outside the checkout and probes it: the runtime
store creates its own schema and the curated registry loads 22 entities, 19
places, 28 assets and 64 edges. Places was 21 until X12's two duplicated
rows (Maharashtra, Odisha) were merged into their canonical entries.

**10. Show the crash recovery.**
```bash
python docs/evidence/engineering-audit-2026-10-18/r08_recovery_probe.py
```
Three crash points, each reproducing the uninterrupted run's bars and
decisions.

**11. Show the FR35 ablation runner, and what gates it.**
```bash
python scripts/run_experiment.py --status
```
The most useful thing in this step is a **refusal**. `--status` reports that
`preregistration.json` is absent, so no AUC can be computed at all: D5(d)
makes a committed design the precondition for a result, and DR-05 step 5
leaves committing it to a person on purpose — a script writing it as a build
step would defeat the mechanism it exists to provide.

To show the plumbing, commit a design to a scratch path and run the supplied
fixture through it:

```bash
python -c "from pathlib import Path; from seraph.validation.preregistration import build, commit; print(commit(build(calibration_max_iter=50), Path('prereg-demo.json')))"
```

```bash
python scripts/run_experiment.py --dataset fixture --tables B --preregistration prereg-demo.json --transfer JSE
```

Four things worth pointing at in the output:

- the **comparability warning printed above the tables**, not after them.
  Tables A (4 folds), B (2) and C (6) answer three different questions and are
  never ranked together.
- **`folds` as measured/declared** on every line. The mean is over one
  configuration's own folds; there is deliberately no table-level mean, because
  pooling six configurations and two xi modes answers no question and reads as
  a ranking.
- the two **xi-mode rows being identical for single-pillar subsets**. That is
  the arithmetic, not agreement: under a one-pillar mask every regime row
  renormalises to the same indicator vector, so CSRS is just that pillar's own
  value and the R5 control cannot diverge. It does move for `rmt+hamilton`.
- the transfer stating in its own output that its target is a **fixture epoch
  standing in for a second market**, and is therefore not an O9 result.

Every number here comes from `fixtures/experiment_dataset.py`, which declares
itself synthetic in a field that travels with the data. The point of the step
is that the machinery and its refusals work — not that anything has been
measured about any market.

```bash
python -m pytest tests/test_t10_experiment_runner.py tests/test_t10_transfer_sensitivity_archive.py -q
```

86 cases, including every refusal: no design, an edited design, a design with
no threshold, a leaking fold, a single-class fold, a subset that outruns its
epoch's coverage, a transfer that would be in-sample, and a sweep whose
designs do not actually differ.

**In the browser**, the same run is the **EVALUATION** panel under the run/date
selection, as an institutional or regulator role. It shows the three tables
with their measured/declared fold counts, the comparability warning above
them, the absence census and the count of rows the published contract cannot
carry. It deliberately offers **no commit control and no run control**: the
design belongs in a person's hands (D5(d), DR-05 step 5) and a full ablation
calibrates once per fold, so a button would make either a side effect of
opening a page. Retail is told whose tool it is rather than shown an empty
panel.

**12. Show that the console can say what is broken.**

Open the **HEALTH** panel. It reads `operations/monitoring.py`, whose own rule
is that silence is never health: a source never fetched is `never_succeeded`
and a job never run is `never_run`, and neither is drawn as success.

On the installation this runbook was written against it reports, truthfully:
`news.poll` **failing**, with three abandoned leases since its last success at
22:13 the previous evening, and **14 of 19 sources stale**. The detail names
the cause and the remedy — a worker process was killed and a replacement
cleared the lease, so the work stopped rather than erred; restart the worker —
rather than reporting three code failures, which is what it said before the
reconciled-lease case was separated out.

That is the panel working. Point at it deliberately: a console that cannot
report its own staleness is the specific thing a green banner hides, and this
one was that console until these panels existed.

```bash
python -m pytest tests/test_t10_evaluation_ui.py -q
```

34 cases: both panels render, the role gate fires before the design is even
consulted, an edited design and an edited artefact are both refused, an
unreadable artefact does not take the page down, and the control assertions
parse the panel's call graph rather than its text.

**13. Show the prediction and the warning — the system's purpose.**

Open the console. **PREDICTION & EARLY WARNING** is the first panel and it is
already expanded. On the data this runbook was written against it reads:

| | |
|---|---|
| Decision date | 2026-08-21 |
| Predicted probability | **4.62%** |
| Warning threshold | 12.96% |
| Warning level | **NO WARNING** |
| Horizon | 15 sessions |

The forecast is the probability that the research market index falls 10% or
more from that close at any close in the next 15 sessions. It is produced by
the actual engine — `build_pillar_features`, `walk_forward_predict`,
`calibrate_alerts` — over 5,361 sessions from 2005-01-03, in about eighteen
seconds:

```bash
python scripts/run_prediction.py
```

`run_market_jobs.py` runs it as the fourth daily step, so the panel is current
on a schedule rather than whenever somebody ran it by hand.

Four things to point at, in this order:

- **The three headings are three different claims.** *Measured* is the pillar
  feature values at that close — one row each for Hawkes, RMT and Hamilton,
  plus the volatility baseline. *Predicted* is one model output. *Warning* is a
  policy decision against a threshold calibrated on **past** out-of-sample
  scores under a declared budget: at most 2 false episodes per year and at
  most 10% of sessions in alarm. Conflating those three is how a research
  instrument starts sounding like an oracle.
- **The UNVALIDATED banner sits above every number**, not in a footnote. No
  advance-warning skill has been demonstrated; AMENDMENT-03 measured Pillar 1
  at approximately no skill at every intraday horizon.
- **The realised history is labelled retrospective.** Brier 0.0695, AUC 0.659
  over 4,576 matured forecasts against a 7.69% base rate, and 1.46 false
  episodes per year — inside the 2.0 budget. That is what the instrument
  *would have* produced, which is implementation behaviour, not foresight.
- **The calibration table shows the model over-predicting.** Days it called
  7.5% came in at 5.4%; days it called 28% came in at 19%. This is the
  uncertainty the model actually supports — the logistic challenger yields no
  interval, so inventing one would be worse than showing whether days it
  called *p* turned out *p*. Show it rather than explaining it away.

```bash
python scripts/run_prediction.py --status
```

Prints the same state in the terminal, computing nothing.

```bash
python -m pytest tests/test_prediction_integration.py -q
```

50 cases, including: the operational feature set still matches the frozen
experiment's `combined` candidate, all three pillar families are present,
training labels are purged by the horizon, no confidence interval is claimed
for the probability, an abstained threshold is never drawn as a quiet
all-clear, and nothing under `seraph/` imports a module from `scripts/` —
which is what an installed wheel cannot do.

**14. Show that it refreshes itself.**

```bash
python scripts/schedule_market_jobs.py --status
```

On the machine this runbook was written against:

```
registration  REGISTERED
  TaskName:              \SERAPH Daily Market Jobs
  Next Run Time:         10/20/2026 6:30:00 PM
  Last Result:           0
  Scheduled Task State:  Enabled
  Schedule Type:         Weekly
  Days:                  MON, TUE, WED, THU, FRI
```

The task runs `run_market_jobs.py --scheduled` at 18:30 IST on weekdays —
three hours after the regular close, with room for the end-of-day files to
publish. It adds no pipeline logic: the trading-day gate reuses
`MarketClock`'s weekday-plus-registry rule, and overlap prevention reuses
`JobStore`'s lease, which also puts each run in the ledger the HEALTH panel
reads. A hand-run and a scheduled run behave identically.

Register it on a fresh machine with `--register`; `--cron` prints the
equivalent crontab line for the other supported environments; `--unregister`
removes it.

The **HEALTH** panel now opens with a *Daily schedule* section, and it is
worth reading aloud because it separates three facts that are routinely
collapsed into one green light:

| Fact | Right now |
|---|---|
| **Registered?** | yes, next run 18:30 |
| **Executed?** | yes, all four steps ok, ledger run succeeded |
| **Acquired fresh data?** | **no** — unchanged, and 59 days behind |

That third row is the point. The vendored snapshot ends 2026-08-21, so the
pipeline can run perfectly and still bring nothing new, and the panel says
so: *"a gap this wide is the extent of the loaded corpus, not a holiday —
extending it needs an ingestion run, not another scheduled execution."* The
PREDICTION panel independently marks its forecast **STALE** while still
showing it, because the last valid forecast is information and discarding it
would lose that, but presenting it as current would be a lie.

**Holidays.** No exchange holiday calendar exists in this repository, so the
trigger is Mon–Fri — the two days that are certainly not sessions — and the
job decides the rest from the corpus at run time. On an unregistered NSE
holiday the task fires and records *executed, data unchanged*. Inventing a
holiday table would be fabricating exchange data; say that rather than
claiming holiday awareness the system does not have.

```bash
python -m pytest tests/test_o03_scheduling.py -q
```

47 cases: the trading-day gate, overlap refusal, the freshness vocabulary,
staleness marking, recovery from an abandoned lease, and the ledger
migration that R10's fencing turned out to need.

**15. Show that it acquires, not just executes.**

This is the step that separates a working pipeline from a working *system*.
Everything before today ran correctly on a snapshot ending 2026-08-21 and
produced a two-month-old forecast: every step green, the scheduler firing,
and no new observation ever entering the store.

```bash
python scripts/run_acquisition.py --dry-run
```

Says what it would fetch and why, without fetching. Then the real thing:

```bash
python scripts/run_acquisition.py
```

Three things as one unit, because acquiring data and *using* it are not the
same act:

1. **Acquire** the missing sessions from NSE's archive.
2. **Re-flag the universe** for the years that gained sessions. This was the
   actual integration gap — a fresh `daily_prices` row has
   `universe_member_flag = false` until C3 applies membership, and the market
   panel is built only from flagged rows, so the new sessions existed and
   were *invisible*. Acquisition alone changed nothing downstream.
3. **Rebuild the market snapshot** the prediction engine reads.

Steps 2 and 3 run only when step 1 stored something.

Then open the console. **PREDICTION & EARLY WARNING** now reads:

| | |
|---|---|
| Decision date | **2026-10-19** |
| Predicted probability | 6.23% |
| Warning threshold | 12.52% |
| Warning level | NO WARNING |
| Snapshot | `rebuilt`, 2005-07-01 → 2026-10-19 |

and the **STALE** banner is gone. The protocol is unchanged — horizon 15,
barrier 10%, the same combined feature set, the same alert budget — so this
is the same instrument on current inputs, not a different one.

The **HEALTH** panel separates four facts that a single green light would
collapse, and they do not always agree:

- **registered** — the task exists and is enabled
- **executed** — the steps ran
- **acquired fresh data** — a new observation actually entered the store
- **failed** — acquisition tried and could not

Point at the fourth: a failed acquisition leaves the last valid forecast in
place and marks its age, rather than discarding it or presenting it as
current.

```bash
python -m pytest tests/test_fresh_data_acquisition.py -q
```

54 cases, offline against a synthesised bhavcopy: five refusals (a file
dated differently from the day requested, an empty file, an implausibly small
one, impossible OHLC, a non-positive price), the listing-day carry-forward
FR52 depends on, and the bundle admission that had kept the daily vintages
out of the current-risk path. One live test is gated on `SERAPH_LIVE_NSE=1`,
so the suite never silently depends on an exchange being reachable.

---

## 5. What does not work, and who can unblock it

| Blocked | Why | Who |
|---|---|---|
| **Fresh Hawkes pillar** (FR10–15) | `intraday_bars` is empty. FR1 sources 5-minute bars from Kite Connect; `backfill_intraday.py` is written and checkpointed but needs a paid subscription and a daily interactive login. Because `DECLARED_CADENCE` puts Hawkes at `bar_close`, the archived daily estimate is stale against its own cadence and the D2 mask correctly excludes it — so the live composite is RMT + Hamilton, mask `[False, True, True]`. | owner: subscription + login |
| **Measured sector micro-flags** (FR14) | Same dependency: per-sector jump counts come from Lee–Mykland extraction over 5-minute bars (FR50). The overlay names the absence and its cause; no substitute is used. | owner: same |
| **Directed contagion network** (FR15) | Needs the Hawkes branching matrix, which needs the same estimation. Nothing inferred is displayed. | owner: same |
| **Counterfactual policy path** (FR48) | `project_xi` needs a *fitted* `HamiltonEngine` and no fit artefact is persisted; Hamilton is also under a standing research exclusion. The direct regime-path simulator works; the macro z→ξ mapping says it is unavailable. | owner: decide whether to persist a Hamilton fit despite the exclusion |
| **Defensive-action drawdown** (FR46) | Needs declared positions, execution and cost assumptions. Those are financially material and are not invented. | owner: the contract |
| **Institution decomposition** (FR42) | Needs authorised institution submissions. Private positions are not derivable from public price bars. | owner: data + schema |
| **A real FR35 ablation result** (FR35–37) | The runner, the FR37 transfer, the FR34 sweep and the FR38 archive are built and tested. `preregistration.json` is not committed, and D5(d) makes it the precondition for any AUC; DR-05 step 5 left that to a person deliberately. A real result also needs per-epoch reconciled states for all six labelled epochs, which the archive does not hold. | owner: commit the design |
| **Publishing a Table C row** (FR35) | The archive accepts `table_id` 'C' after migration 002, because FR38 requires every ablation result to be archived. `shared_types.EvaluationRow` still declares `Literal["A","B"]`, and widening it edits a package all twelve components import — ask-gated in `CLAUDE.md`. The runner counts such rows rather than dropping them. DR-12 §6 states the choice. | owner: one contract decision |

**Closed since the first version of this runbook**, because the concurrent
session's news work was landed and freed the files: one-command launch of
the market side (C15/O03), browser controls for the three role workflows,
and the job-lease fencing (R10).

---

## 6. What to say, and what not to

Say: this is an **experimental risk and research platform**. The pipeline is
real, the inputs are real, the arithmetic is the specified arithmetic, and
every output carries its provenance and its absences.

Do not say: that it predicts crises. No advance-warning skill, calibration
or economic effect size has been demonstrated, and three of the plan's own
gates remain deliberately unpassed. AMENDMENT-03 measured Pillar 1 at
approximately no skill at every intraday horizon and reclassified it as a
contagion diagnostic; Hamilton is excluded by a standing research decision;
the news evaluator's gold corpus is empty at 0 of 600 documents.

Those are honest limitations of a working system, not defects to hide. A
complete experimental platform with truthful unvalidated outputs is the
milestone this reaches.
