# SERAPH — how to run and demonstrate it

Written 19 October 2026 against branch `seraph/engineering-completion`.
Every command here was run on this checkout and its output is recorded in
[functional-completion-2026-10-19.json](evidence/functional-completion-2026-10-19.json).

Verified state: **10 of 10 checked journeys work; 7 are blocked** on a paid
subscription, an owner decision, or a concurrent editing session. §5 lists
them precisely.

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

Loads the daily corpus. ~8 minutes, and idempotent — a second run reports
`inserted: 0`. Produces **7,385,306 rows across 3,524 symbols,
2005-01-03 → 2026-08-21**.

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

**Known gap (C15):** the launcher starts the console and news, not the
market and daily jobs. Those are the commands in §2 and must be run
separately or from a scheduler. Wiring them into one launcher is blocked —
see §5.

---

## 4. The demonstration, in order

Each step below is something that works. Nothing here needs a broker
connection or a paid subscription.

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

**6. Show the durable role workflows.** These have **no browser controls
yet** (§5, last row), so demonstrate them through the dispatcher:
```bash
python -m pytest tests/test_t05_t08_t09_workflows.py -v
```
33 cases driving the real `dispatch()` with the browser's own event shape:
upload a portfolio with a bad row and see the actionable rejection, save and
reopen it after a restart, save a scenario and run it against the real
simulator, review the exact revision, and take a regulator case from opening
through evidence, decision, closure and reopening to a versioned export.

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
store creates its own schema and the curated registry loads 22 entities, 21
places, 28 assets and 64 edges.

**10. Show the crash recovery.**
```bash
python docs/evidence/engineering-audit-2026-10-18/r08_recovery_probe.py
```
Three crash points, each reproducing the uninterrupted run's bars and
decisions.

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
| **One-command launch; browser controls for the role workflows** (C15, O03) | `launch_prototype.ps1`, `prototype_app.py` and `bridge.js` are being edited by a concurrent session in this working tree. The server half of every role workflow is complete and tested; its browser controls are not wired. | owner: decide whose changes land first |

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
