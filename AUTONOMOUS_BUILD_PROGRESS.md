# Autonomous build progress — SERAPH news intelligence

Started 2026-10-18. Updated at each milestone. **Recovery instructions are at
the bottom**: if this session ends, that section is what resumes the work.

## Definition of done — live status

| # | Item | State |
|---|---|---|
| 1 | Worker supervision and automatic recovery | **done** — supervisor with bounded backoff; gives up loudly |
| 2 | Downtime backfill within source capabilities | **done** — 436 stories recovered in a live run; unrecoverable gaps reported |
| 3 | Manual refresh end to end | **done** — budgeted fetch; names sources it could not reach |
| 4 | Freshness and liveness accurately displayed | **done** — browser-verified both ways |
| 5 | News interpretation / regulatory lifecycle defects | **done** — stage, finality, boilerplate, future-effective, proposed rulemaking, `previously approved` |
| 6 | Event expiry and impact decay | **done** — declared horizons; in-force instruments never expire |
| 7 | Hindi processing and coverage gaps | **done** — narrow corpus-grounded rule set; never claims comprehension |
| 8 | Exposure relationships expanded and validated | **done** — 10 edges, 8 sectors, 24 impacts, each cited + containment-tested |
| 9 | Replay versioning | **done** — source_places versioned; dangling mappings impossible |
| 10 | NI17 accuracy gate against its actual spec | **done** — gate executed; correctly FAILS on corpus size + single labeller |
| 11 | Tests pass, limitations documented | 600 news-side passed; full suite running |
| 12 | No unresolved critical defects in scope | continuous |

## Completed before this autonomous run

- NI11/NI12 — 3 curated sector edges, impacts 5 → 20 across five sectors
- Forthcoming-publication `Timing` fix (channel was fully down on real data)
- NI03/NI16 — relevance split from classification; SEBI enforcement class
- NI08 / DR-10 — per-source text rights read and applied; 5 sources permitted
- FIX05 / DR-05 — Table B two-epoch decision, Table C, xfail retired
- Worker heartbeat, `--catch-up`, launcher registration reconciliation
- Future-effective-date fix; one definition of the EFFECTIVE pattern

Suite at last full run: **1433 passed, 4 skipped** (4 = intraday backfill).

## Section 2 (confirmed defects) — all seven done

| | fix |
|---|---|
| 2A display vs acquisition | three ops: `news_project` (no network) / `news_acquire` (queued, coalesced, rate-limited) / progress. The 30s timer forced ALL sources per tab before this. |
| 2B bounded refresh | deadline reaches the socket and the retry loop; five outcomes (fetched/unchanged/failed/timed_out/skipped); demonstrated on a deliberately slow source |
| 2C downtime recovery | gaps persisted BEFORE polling erases them; resumable cursors; page-cap truncation keeps the gap open; **India filter preserved** |
| 2D temporal semantics | `adopted` != in force; 2099 effective date not in force; evaluated at the requested decision time; supersession; late-discovery vs new development |
| 2E gate hardening | missing/empty slices FAIL; precision over predictions with extras counted; recall counts abstentions; per-field gates; checks must actually RUN; `--release-check` exits nonzero |
| 2F replay versioning | undated rows counted and reported, never silently "always known"; version manifest pins source/mapping/exposure/interpretation |
| 2G supervision | stall detection via sequence+deadline; independent supervisor heartbeat; single-worker ownership with handover; additive column migration |

## Section 3 (coverage) — in progress

Probed 13 candidate endpoints live; **6 registered**, 6 recorded uncovered
with the reason (403, SSL verify failures, 502, not-a-feed). SSL verification
is NOT disabled to gain coverage.

New: `nse_corporate_announcements`, `nse_circulars`, `bse_notices`,
`ustr_press`, `federalreserve_speeches`, `ec_news`.
Sources 11 -> 17, stories 280 -> 453, entities 2 -> 16.

**Indian exchange filings were the largest gap and are now covered.** NSE
titles are the filing entity only; the subject is in the body, which is not
retained. So a filing resolves to its issuer and produces NO impact and no
direction — stating that an announcement exists, not what it said.

Still uncovered: DGFT, CBIC, MOSPI, IMD, POSOCO, CEA.

## Sections 4 and 5

**4 — interpretation and exposure.** `beneficiaries` and `constrained_parties`
had existed on the frame since it was written and were never populated, so
every impact showed one signed direction and the reader never saw the other
side. A duty now reports that it constrains the exporter and the downstream
buyer while benefiting the domestic producer, with the net **not computed**.

Product scope: an exclusion detected in the text lowers confidence to `low`;
silence about scope is reported as `unknown`, never as "no exclusions". Both
corpus false friends ("Exclusively listed", "Exclusive Economic Zone") are
rejected.

Issuers reached **20** (target met, all cited to the exchange feed that named
them). Facilities 1 of 20 and relationships 10 of 50 — short, and deliberately
not padded.

**5 — role workflows.** Three projections of the SAME channel. Retail reports
which holdings have a documented route AND which do not, distinguishing a
holding that does not resolve from one that resolves to an issuer with no
sector. Institutional shows opposing mechanisms, unsized counts and
limitations. Regulator sees coverage, acquisition health, scope split,
unresolved references and open collection gaps.

Verified in the browser on the ordinary route: opposing sides render, eight
sectors, worker warning correct, evidence resolves to its publisher.

## Current action

Final full suite running. Then: completion record.

Remaining and NOT done: facilities to 20 and relationships to 50 (needs cited
sources this corpus does not contain); the NI17 corpus to 600 with two
reviewers (needs human review); DGFT/CBIC/MOSPI/IMD/POSOCO/CEA coverage.

## Recovery instructions

Environment:
```bash
cd "C:/Users/Arlop/Downloads/SERAPH VARYA/SERAPH Varya"
docker compose up -d                                   # research DB, 5434
docker compose -f docker-compose.test.yml up -d        # disposable test DB, 5435
./.venv/Scripts/python.exe scripts/provision_test_db.py  # prints 2 env vars
export SERAPH_TEST_DB_DSN=... SERAPH_TEST_TOKEN=...
./.venv/Scripts/python.exe -I -m pytest tests/ -q -p no:randomly   # ~15 min
node tests/js/news_layer_harness.mjs
./.venv/Scripts/python.exe scripts/verify_news_sectors_browser.py [--simulate-dead-worker]
```

Environment gotchas that cost time before:
- Bash heredocs mangle backslashes/quotes here; write patch scripts to the
  scratchpad and run with `-I`. `$TMPDIR` is NOT the scratchpad.
- The suite takes ~15–20 min and buffers its progress line. It is not hung.
- Never `taskkill //IM python.exe` — it kills the running suite.
- `console_backend.py` returns an explicit allow-list: a new payload field
  reaches the UI only by being named there.
