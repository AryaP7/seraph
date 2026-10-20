# How to unblock what is blocked

Written 20 October 2026. Each item says **who** has to act, **what exactly**
they do, and **what changes** when they do it. Nothing here is a plan to be
approved; it is the set of actions that are not mine to take.

One item has already moved as a result of writing this: the test database was
never an external blocker at all. See §1.

---

## 1. ~~The DB-gated tests and migration 002~~ — DONE, it was self-serviceable

**This was mislabelled.** Ten tests and migration 002's live behaviour were
reported as needing "a disposable `seraph_test_*` database", which reads like
an infrastructure request. The actual requirement, in `tests/conftest.py`, is:

* a database whose name starts with `seraph_test_`, and
* a table `seraph_test_guard(token)` holding the value of
  `SERAPH_TEST_TOKEN`.

Both are creatable on the Postgres that is already running. Done:

```bash
docker compose up -d   # if it is not already running
```

```bash
python -c "
import asyncio, asyncpg, secrets
from urllib.parse import urlparse, urlunparse
from seraph.store.bootstrap import DEFAULT_DSN
TOKEN='local-' + secrets.token_hex(4); NAME='seraph_test_migrations'
async def main():
    p = urlparse(DEFAULT_DSN)
    c = await asyncpg.connect(urlunparse(p._replace(path='/postgres')))
    if not await c.fetchval('select 1 from pg_database where datname=\$1', NAME):
        await c.execute(f'CREATE DATABASE {NAME}')
    await c.close()
    t = await asyncpg.connect(urlunparse(p._replace(path='/'+NAME)))
    await t.execute('CREATE TABLE IF NOT EXISTS seraph_test_guard (token text primary key)')
    await t.execute('DELETE FROM seraph_test_guard')
    await t.execute('INSERT INTO seraph_test_guard (token) VALUES (\$1)', TOKEN)
    await t.close()
    print('SERAPH_TEST_DB_DSN=' + urlunparse(p._replace(path='/'+NAME)))
    print('SERAPH_TEST_TOKEN=' + TOKEN)
asyncio.run(main())"
```

Then export the two values and run the suite. **Result: the ten DB-gated
tests pass, and migration 002 is now verified against a real PostgreSQL** —
a Table C row and an unavailable row with NULL metrics are both accepted, a
half-filled row of either kind is refused, and Table D is still refused. Seven
tests in `TestMigration002OnARealDatabase` pin it.

The guard exists so this is safe: the harness refuses any target not named
`seraph_test_*` and not carrying the token, so it cannot be pointed at the
research or source database by accident.

---

## 2. Fresh Hawkes, sector micro-flags, contagion network (FR10–15, FR14, FR15)

**Who:** you, with money and a daily login.
**Cost:** Kite Connect is a paid subscription, and the historical-candle API
is a separate add-on. Check current pricing with Zerodha; this document
deliberately does not quote a figure it cannot verify.

**What:**

1. Subscribe to Kite Connect and enable historical data for the app.
2. Put the credentials where the code already looks — environment variables
   `KITE_API_KEY` and `KITE_API_SECRET`, or the token file pointed at by
   `SERAPH_KITE_TOKENS`. **Do not put them in the repository root**; W0-B is
   open precisely because a token file is sitting there.
3. Log in once per day: `python scripts/kite_login.py`. The access token
   expires daily — this is Zerodha's design, not a SERAPH limitation.
4. `python scripts/backfill_intraday.py --from 2015-02-02`

`backfill_intraday.py` is written, checkpointed per `(symbol, window)` and
resumable: a run that dies at request 2,000 resumes there. Every write goes
through the idempotent upsert, so re-running is safe.

**What changes:** `intraday_bars` stops being empty, so the Hawkes pillar can
be *computed* rather than read from an archive. That in turn unblocks FR14's
measured sector micro-flags (Lee–Mykland extraction over 5-minute bars) and
FR15's directed contagion network (which needs the Hawkes branching matrix).
Three features, one subscription.

**What does not change:** the daily pillars and the prediction engine already
run on current data via the public bhavcopy archive. Kite is *only* needed for
the intraday cadence. If the subscription is not worth it for a final-year
project, nothing else is waiting on it.

---

## 3. A real FR35 ablation result

**Who:** you, once, in one command.
**Why it is yours:** D5(d) makes a committed design the precondition for any
AUC, and DR-05 step 5 reserved the commit for a person on purpose — a script
writing `preregistration.json` as a build step defeats the thing
pre-registration is for.

```bash
python -c "from seraph.validation.preregistration import commit; print(commit())"
```

`commit()` refuses to overwrite, so it cannot be run twice by accident. Then:

```bash
python scripts/run_experiment.py --dataset fixture --out runs/exp-01.json
```

**What changes:** the runner stops refusing and produces Tables A/B/C. The
machinery, the FR37 transfer, the FR34 sweep and the FR38 archive are all
built and tested; this is the gate, not the work.

**Read the design first.** `python scripts/run_experiment.py --status` prints
what would be committed. Once committed, changing it invalidates every result
produced under it.

**A second, separate limitation:** a real run also needs per-epoch reconciled
states for all six labelled epochs, which the archive does not hold. So
committing the design makes the machinery produce results; producing *the*
result for all six epochs is a further data step.

---

## 4. Counterfactual policy path (FR48, T11)

**Who:** you — a decision, then ordinary engineering.

**The decision:** Hamilton is under a standing research exclusion
(`NOT_PRODUCTION`). Is persisting a fitted Hamilton model acceptable for
*counterfactual scenario* use?

There is a defensible reading in which it is, and it is worth stating because
the blocker has been recorded as if the answer were obviously no. The
exclusion as written concerns the **live composite** — "standing research
decision (NOT_PRODUCTION); not a feed outage" — and the archived ξ series is
labelled "diagnostic only". `project_xi` is neither: it propagates regime
probabilities under a **hypothetical** covariate path, and the console already
labels its output a hypothetical rather than a forecast. Excluding Hamilton
from the score it feeds is not the same as forbidding scenario analysis with
it.

**If you decide yes, the engineering is small and bounded:**

`project_xi` raises `fit the engine before projecting a policy path` because
it needs `engine._res` — the fitted statsmodels result. The existing artefacts
(`causal_xi_NOT_PRODUCTION.npz` in two evidence directories) carry the ξ
series, the LSD and the variance, but **not the fitted coefficients**. So:

1. Run `HamiltonEngine.fit()` on the causal path.
2. Persist `_res.params` plus the model specification, labelled research-only.
3. Reconstruct it for `project_xi`, and keep the existing direct-ξ sensitivity
   available alongside.

**If you decide no:** the macro z→ξ mapping stays unavailable and says so,
which is the current behaviour. The direct regime-path simulator already
works.

---

## 5. Defensive-action drawdown (FR46, T12)

**Who:** you — a contract, because the assumptions are financially material
and I will not invent them.

`playbook()` returns `drawdownReductionPct: None` with
`"awaiting C10 back-test calibration"`. Returning a plausible-looking number
would be inventing a result.

**What must be declared, in writing, before the back-test can be built:**

1. **The action's mechanics.** "Reduce exposure" is not a specification. By
   how much, to what, on what trigger?
2. **The position basis.** Which portfolio is the drawdown measured on? An
   index proxy, an equal-weight universe, a declared holding set?
3. **Execution assumptions.** When does the action execute relative to the
   alert — same close, next open? At what price?
4. **Cost assumptions.** Slippage, brokerage, impact. A defensive action that
   looks free will look better than it is.

**What changes:** with those four fixed, the back-test is ordinary work: run
the alert series, apply the action, measure realised drawdown with and
without, and report both — **including when the action is worse**, which is a
real possible outcome and must not be filtered out.

---

## 6. Institution exposure decomposition (FR42, T13)

**Who:** you — data access plus a schema.

Private institutional positions are **not derivable from public price bars**.
No amount of engineering substitutes for the data. This needs:

1. Authorised submissions from the institutions, or an authorised regulatory
   feed.
2. A submission schema and the legal basis for holding it.

**What changes:** the surface currently reports absence rather than an
inference, which is correct. With authorised data it reports a decomposition.

**What I will not do:** infer institution-level exposure from public data and
present it as a decomposition. That is fabrication with a plausible shape.

---

## 7. News gold corpus (X08)

**Who:** you, or two people you nominate — this is labelling labour, not
engineering.

The evaluator's gold corpus is at **0 of 600 documents and 0 of 2 reviewers**.
`seraph/validation/news_gate.py` declares the requirement:
600 documents across the declared slices, two independent reviewers.

**What changes:** NI17 can establish interpretation accuracy. Until then the
news evaluator reports that it cannot, which is honest and is why the gate
exists.

**Scoping note:** 600 documents double-reviewed is a substantial amount of
work. If the goal is a final-year demonstration rather than a publishable
evaluation, a smaller declared corpus with the reduced power stated honestly
is a legitimate alternative — but that is a change to the declared gate, and
changing it to match what was achieved is exactly what the gate is designed to
prevent. Decide the size *before* labelling, not after.

---

## 8. Housekeeping that needs you

* **W0-B — rotate the Kite token.** `kite_credentials.tokens.json` is still in
  the repository root. The externalised configuration, the warning and the
  invariant check are implemented; `SERAPH_KITE_TOKENS` points the code
  elsewhere. Move the file out of the tree and rotate the credential, because
  being gitignored is not the same as being absent.
* **W0-C — two stale worktrees** pinned at the unreachable commit `f79299d`,
  one locked.
* **W0-D — `DEMO-DELETE-ME.md`** is still in the root.

---

## What is not blocked

For completeness, so this list is not read as the whole backlog: P01
(authentication), D04 (corporate-action adjustment and the hardcoded symbol
limits), U02/U03, V01/V03 and the remaining console integrations are ordinary
engineering with no external dependency. They are simply not done yet.
