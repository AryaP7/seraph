# SERAPH — what is left, and what to do next

Written 2026-10-16, after the Phase 1 and Phase 3–9 build-out.
Supersedes the "current slice" section of [DEVELOPMENT-PLAN.md](DEVELOPMENT-PLAN.md);
per-item state stays in [DEVELOPMENT-STATUS.md](DEVELOPMENT-STATUS.md).

---

## 1. Where things stand

| | Count | Meaning |
|---|---|---|
| ✅ verified | 27 | implemented, tested, evidence recorded |
| ⚠ implemented, unverified | 3 | code done, the confirming run has not happened |
| 🔒 blocked on external input | 9 | nothing more can be built until something arrives |
| 🔬 scientifically unresolved | 1 | needs your decision, not more code |
| ◐ partial | 3 | designed or half-built on purpose |
| ✗ not started | 17 | |

Tests: **813 core passed**, **34 expensive model tests passed**, 5 invariants,
research artefacts verified, packaging verified, 0 failures.
Audit findings: **12 of 14 fixed**.

---

## 1b. The live gap — read this first

**SERAPH's CSRS is specified as a current market risk score. It has never had
present market data.** The corpus ends 2026-08-21; today is 2026-10-16. The
Kite client is REST backfill, not streaming. No feed has ever connected.

The architecture now exists
([DR-07](decisions/DR-07-2026-10-16-live-market-path.md)): market clock, feed
adapters, bar aggregation, a bar-close decision loop, and a **red banner on
the console** reading `HISTORICAL REPLAY — NOT A CURRENT MARKET READING` until
recency and feed both permit. What is missing is the data — see 2.1 and 2.1b.

## 2. The things only you can unblock

Everything in section 3 is gated behind these. Ranked by how much they release.

### 2.1 Source PostgreSQL — biggest single unlock

Ports 5433 and 5434 refuse connections. **Releases:** `DATA02`, `DATA09`,
`PIPE01`, `PIPE02`, `VAL01` — the entire fresh-data path, and with it the only
route to new predictive evidence. It is also half of what the **live** path
needs: a live bar means nothing without the trailing history the ECDF and
Hawkes windows are fitted on.

```bash
pg_isready -h 127.0.0.1 -p 5433 && pg_isready -h 127.0.0.1 -p 5434
```

If the database lives elsewhere, set `SERAPH_SOURCE_DB_DSN` and say so; the
read path already opens it read-only and will not write.

### 2.1b Kite credentials — the other half of going live

`KITE_API_KEY` + a daily access token, and `pip install kiteconnect`.
**Releases:** `LIVE02` — and with 2.1, a genuinely current CSRS rather than a
replay.

```bash
python scripts/run_live.py --status
```

Prints the clock, the feed and the recency verdict, and changes nothing. It is
the fastest way to see which world you are in before trusting a number on
screen.

### 2.2 Docker's Linux engine

`npipe:////./pipe/dockerDesktopLinuxEngine` does not exist. **Releases:**
`DATA01`, the 13 skipped DB tests, and `FIX06`'s verification. Start Docker
Desktop, then:

```bash
docker compose -f docker-compose.test.yml up -d && python scripts/provision_test_db.py
```

### 2.3 FR35 Table B — two epochs or six

**This is a decision, not a task.** `docs/decisions/DR-05-2026-10-16-fr35-table-b-scope.md`
lays out both readings and recommends **two epochs**, keeping the six-epoch
RMT/Hamilton run as a separate Table C. **Releases:** `FIX05` → `FIX06`,
`VAL03`. Nothing was changed to make the failing test pass, because the fold
count gets hashed into the pre-registration and a design nobody chose is worse
than a failing test.

### 2.4 Deployment audience

Private use, institutional pilot, or regulator demo? Each sets a different bar
for TLS, retention, backup and audit. **Releases:** `OPS03` acceptance, and the
measurable criteria for the undefined NFRs.

Lower-priority inputs: an OIDC issuer + client id (`AUTH01` round trip only);
authorized news-source rights (`NEWS01` live fetch); cited tariff announcements
(`DATA06`); the Nifty 500 benchmark (`DATA04`); authorized institution
submissions (`CASE02`).

---

## 3. What to do next, in order

### Now — needs nothing from you (≈2–3 slices)

| # | Item | Why it is next | Done when |
|---|---|---|---|
| 1 | **`NEWS07`** analyst review + evaluation set | The news chain is built but its *accuracy* is unmeasured. Without a review set, extraction quality is an opinion. | A labelled set exists; extraction/linking accuracy, duplicate handling and source-to-display latency are numbers; analyst corrections are versioned and audited |
| 2 | **`QA01`** canonical browser tests | Nothing has been checked in a real browser this whole build. `AppTest` and the Node bridge harness cover behaviour, not rendering. | Globe renders; role switch, tools round trip, stale-context and preserved drafts pass in a browser; a before/after capture exists |
| 3 | **`PORT03`** measured sector flags → portfolio | `FIX07` made fit artefacts persistable; this is what makes coverage stop being 100% uncovered. | A measured flag reaches `portfolio_overlay`; covered/uncovered reconcile; unknown stays distinct from quiet |
| 4 | **`QA02`** accessibility + WebGL fallback | Independent of data. Keyboard, non-colour status cues, reduced motion, fallback. | Criteria stated and measured — propose them, don't invent a pass |

### Then — the moment a blocker clears

| Trigger | Do immediately |
|---|---|
| Docker up | `DATA01` → run the 13 DB tests → verify `FIX06`'s migration on a real database |
| Source DB up | `DATA02` read-only census → `DATA09` regenerate corrected features → `PIPE01` full chronological run → `PIPE02` fresh forecasts → **start `VAL01`'s shadow ledger the same day** |
| FR35 decided | `FIX05` implement the chosen scope → commit `preregistration.json` **before any AUC** → `FIX06` → `VAL03` |
| Audience decided | `OPS03` TLS/retention/backup acceptance → `OPS02` restore exercise |

### Later — needs data that does not exist yet

`DATA04`–`DATA08`, `DATA10`, `PIPE04`, `NEWS08`, `PORT05`, `SCEN02`, `POL01`,
`POL02`, `VAL02`, `CASE02`.

---

## 4. Standing rules for whoever picks this up

- `seraph/shared_types/` is frozen — ask before touching it. Nothing in this
  build did.
- Curated registries (`seraph/news/curated/*.csv`,
  `seraph/ingestion/tariff_events.curated.csv`) ship **empty on purpose**. The
  loaders refuse uncited rows. Do not fill them to make a panel look alive.
- Blocked means blocked. Never substitute an archive or a mock and label it
  fresh.
- Evidence is append-only. New results get new artefacts; old hashes are never
  rewritten to bless changed code.
- Nothing here establishes predictive skill. The original advance-warning claim
  is still unestablished and the Astra future-loss result still sits inside its
  descriptive interval of the volatility baseline.
