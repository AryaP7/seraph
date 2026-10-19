# News channel runbook

Launch, shutdown, recovery, troubleshooting. Every command here was run.

---

## Launch

```powershell
.\launch_prototype.ps1
```

This does three things in order, and the order matters:

1. **reconciles source registrations** — on every launch, not only when the
   store is missing. Gating it on a missing file meant an existing database
   never received a source added to the catalogue later.
2. **starts the supervisor**, which starts the worker with `--catch-up`.
   Catch-up records collection gaps *before* polling, then resumes
   backfills, then polls every source once. Polling first would overwrite
   `source_health.last_success_at` and erase the evidence of the outage.
3. **starts Streamlit** against the same store (`SERAPH_NEWS_STORE`).

Worker only, no UI:

```powershell
.\launch_news.ps1
```

`-NoNewsWorker` starts the UI alone. The console then shows **NO WORKER** and
says nothing is fetching, which is true.

## Shutdown

Ctrl+C in the launcher window. The supervisor marks the worker `stopped`
cleanly and does not restart it — a clean exit is the operator's decision.

If a worker is orphaned (its supervisor died but it kept beating):

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'run_news|news_supervisor' } |
  Select-Object ProcessId, CommandLine
Stop-Process -Id <pid> -Force
```

Never `taskkill /IM python.exe` — it kills test runs too.

## Is it working?

```bash
python scripts/run_news.py --status      # per-source health and freshness
python scripts/run_news.py --backfill    # gaps: recoverable and not
python scripts/run_news_gate.py          # extraction accuracy, report-only
```

The console separates **four times** that used to blur into "current":

| | means |
|---|---|
| `projected_for` | what the screen was built for — **not** evidence of freshness |
| `newest_first_seen_at` | when an article last reached us |
| `stale` | a source is past the freshness policy **it declared** |
| `worker.state` | whether anything is fetching at all |

`11/17 feeds fresh` measures per-source fetch health within **three times**
each source's own interval. It is **not** worker liveness and **not**
editorial coverage.

## Worker states

| state | meaning | action |
|---|---|---|
| `never_started` | no worker has ever beaten in this store | start the launcher |
| `running` | beating, within its declared deadline | none |
| `catching_up` | startup backfill and first poll | wait; it declares a deadline |
| `stalled` | beating but past its **own** declared deadline | supervisor terminates/reaps the child and retries within its restart budget |
| `stopped` | silent past the 5-minute threshold, or exited cleanly | restart if unintended |
| `failed` | crashed, or the supervisor gave up | read `detail`; fix the cause |

The 5-minute threshold is deliberately independent of any source's polling
interval: a 240-minute feed must not buy a dead worker four hours of looking
alive.

## Recovery after downtime

Automatic on launch. Manually:

```bash
python scripts/run_news.py --backfill
```

**Only the two Federal Register endpoints can be recovered exactly** — their
API takes a publication-date range and pages through it, and the backfill
preserves the source's own query (including `conditions[term]=India`).

Every other feed exposes its latest ~30 items. Anything that rotated out
during an outage is **permanently missing, not late**, and the gap says so.
Such a gap closes as `unrecoverable`: settled, not filled.

A backfill stopped by the page cap keeps a continuation cursor and the gap
stays **open** — truncation is not completion.

## Troubleshooting

**The screen refreshes but the news never changes.** That is correct: the
30-second timer re-projects stored data and touches no network. To fetch, use
the console's acquire action, or `python scripts/run_news.py --once`. A
request is coalesced across browser tabs and rate-limited to one per minute.

**A refresh says sources were "NOT contacted".** The budget ran out. They were
never contacted and their data is exactly as old as before. `timed_out` is
different: contacted, no answer in time. `failed` is different again: it
answered with an error.

**A source shows `SSL: CERTIFICATE_VERIFY_FAILED`.** CBIC, MOSPI and IMD
present chains this client cannot verify. **Do not disable verification.**
These remain uncovered and are listed in `UNAVAILABLE_SOURCES`.

**Tests skip with "database unusable".** DB tests need a disposable database:

```bash
docker compose -f docker-compose.test.yml up -d
python scripts/provision_test_db.py     # prints the two variables to export
```

`docker compose up -d` alone is not enough. Never point
`SERAPH_TEST_DB_DSN` at the research database — the guard refuses it, and that
refusal is deliberate.

**Both compose files share a project name.** `docker compose -f
docker-compose.test.yml up -d` may warn that the research container is an
"orphan". Do **not** pass `--remove-orphans`: it would delete it.

**A store created by an older build lacks a column.** Opening it migrates
additively — columns are added, nothing is dropped or rewritten.

## What this channel will not tell you

- a financial size: the documented relationships remain **unsized**; station MW is capacity, not loss exposure
- a probability of loss: nothing here is one
- a position: directions are qualitative mechanism hypotheses
- that an unmapped holding is safe: it is one this system cannot speak about

Nothing in the news channel (F2) enters CSRS or the market pillars (F1).

## Documents and crash recovery

Worker startup reconciles the source configuration, including reviewed rights.
Permitted documents deferred by the per-poll budget are reconstructed as pending
work from stored records, including when the next feed response is HTTP 304.
Failed document URLs wait an hour before retry; non-enabled hosts wait a day.
The attempt status is persisted separately from immutable story evidence.
If older rules discarded feed bytes, recovery retains a reference to the old
observation and fetches the document by its stored URL. It does not invent those bytes.

HTML/plain text and text-bearing PDFs are supported on enabled official hosts.
PDF extraction uses `pypdf>=6.21.1` in a disposable child with a timeout. It is
not OCR; blank/scanned pages and truncation remain explicit. The package's
[extraction documentation](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
explains why image-only pages and arbitrary table structure require additional work.

Manual request claims expire after three minutes by default. A replacement
worker can reclaim an expired claim; stale completion tokens are rejected.
Use the launcher/supervisor for the continuing service, not repeated `--once`
commands competing with an existing worker.

## Independent benchmark workflow

Export to a new directory; an existing frozen corpus is never overwritten:

```bash
python scripts/news_benchmark.py export --corpus prototype_runs/review-corpus-v2
```

The export writes a hashed manifest, blank `reviews.jsonl`, and a
`review-template.jsonl` for each reviewer to copy and complete separately.
Review the frozen text, not the extractor's output or a subsequently changed URL.
Unknown fields must be explicitly labelled `unknown`, and absent numeric fields
must be `null`. Empty quantities contribute no numeric-accuracy credit.

```bash
python scripts/news_benchmark.py import-reviews --corpus prototype_runs/review-corpus-v2 --reviews alice.jsonl
python scripts/news_benchmark.py import-reviews --corpus prototype_runs/review-corpus-v2 --reviews bob.jsonl
python scripts/news_benchmark.py evaluate --corpus prototype_runs/review-corpus-v2 --output prototype_runs/review-corpus-v2/gate.json
```

An invalid batch is rejected before writing. Duplicate identities cannot count
twice. Agent reviews remain provisional. Preserve conflicting reviews: a third
human can import a new decision with an `adjudication` object containing `reason`
and `review_hashes` (the `news_corpus.digest` of each original independent review).
The adjudicator must be distinct from both reviewers and must cite the exact
reviews being resolved. The evaluation command exits nonzero unless every
release condition passes. Only the test split is scored.

The 18 October snapshot has 395 documents and no reviews/test documents. It is
ready for curation, not release validation. The current label schema evaluates
single-event documents; multi-event outputs abstain explicitly. See the
[remaining acceptance requirements](NEWS-INTELLIGENCE-LIMITATIONS.md).

Reproduce isolated browser and document checks without changing production data:

```bash
python scripts/verify_news_roles_browser.py --output docs/evidence/news-intelligence/new-browser-run
python scripts/verify_news_document_recovery.py --output docs/evidence/news-intelligence/new-document-run.json
```

The browser check requires Windows Edge and uses ordinary role/portfolio UI
actions. The document check uses real HTTP requests with a simulated unchanged
feed and writes only an isolated copy. Both refuse to overwrite earlier evidence.
