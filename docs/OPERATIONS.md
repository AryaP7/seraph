# SERAPH operations and deployment posture

Created 2026-10-16 (`OPS01`, `OPS02`, `OPS03`).

**Audience decision (D-F) is still open**, and it is the decision this whole
document waits on: private personal use, an institutional pilot and a
regulator demonstration have different acceptance bars for every row below.
What follows is the posture that holds **today**, which is *local, single-user,
localhost only* — stated plainly so nobody mistakes it for a deployment
standard.

---

## 1. The three databases

They are separate on purpose, and conflating them is the worst available
mistake.

| Role | Where | Port | Writable? |
|---|---|---|---|
| **source** | the original SERAPH database | 5433 | **read-only.** Opened in a read-only repeatable-read transaction; never migrated, never started from this repo |
| **research** | `docker-compose.yml` | 127.0.0.1:5434 | yes — new production-like results |
| **test** | `docker-compose.test.yml` | 127.0.0.1:5435 | yes — disposable, tmpfs, destroyed with `down -v` |

The test guard is enforced in three independent places, because one is not
enough:

1. `tests/conftest.py` refuses a DSN whose database name does not start with
   `seraph_test_`, and requires `seraph_test_guard(token)` to hold the token
   in `SERAPH_TEST_TOKEN`.
2. `scripts/provision_test_db.py` refuses a non-loopback host, refuses a
   non-`seraph_test_` name, and refuses to provision a database where any
   E1–E14 table already holds rows.
3. The marker is never committed to any file; the token is generated per
   provisioning run and printed once.

```bash
docker compose -f docker-compose.test.yml up -d && python scripts/provision_test_db.py
```

**Current status: blocked.** Docker's Linux engine is unavailable on this
machine (`npipe:////./pipe/dockerDesktopLinuxEngine` does not exist), so the
test database has never been started and the 13 database-dependent tests have
never run. The provisioning path is complete and its guards are tested; the
execution is not done and is not claimed.

## 2. Configuration and secrets

| Rule | Where it holds |
|---|---|
| Credentials come from the environment, never a versioned file | `docker-compose*.yml` read `${SERAPH_DB_USER}` etc. with throwaway local defaults |
| `.env` is gitignored | already true; confirmed |
| Ports bind to loopback explicitly | `127.0.0.1:5434`, `127.0.0.1:5435`. The previous `"5434:5432"` published on **every** interface |
| Images are pinned | `timescale/timescaledb:2.17.2-pg16`. `latest-pg16` changes the engine under a database whose results must reproduce |
| `scram-sha-256` password auth | `POSTGRES_INITDB_ARGS` |
| No credential reaches a log line | `provision_test_db.py` prints the token once, to the terminal, and writes it nowhere |

**Not done:** TLS. Everything is loopback today, so there is no transport to
protect; NFR23/24 acceptance cannot be claimed and is not. The moment the
audience decision makes this reachable over a network, TLS termination, at-rest
encryption and a secrets store stop being optional and none of them exist yet.

## 3. Scheduling and recovery (`PIPE03`)

`seraph/operations/jobs.py`. Cron (or Task Scheduler) invokes the entry point;
the store supplies the guarantees:

- **a lease-based lock** — two overlapping ticks cannot both run, and an
  expired lease is taken over with the takeover recorded, so a crashed run
  does not wedge the job until a human notices;
- **checkpoints** — an interrupted backfill resumes from where it stopped. A
  failed run **keeps** its checkpoint; a successful one clears it;
- **bounded retries** — exhaustion is a recorded `failed` row, not an infinite
  loop and not silence;
- **watermarks** per `(job, stream)` for incremental sources.

Suggested cron shape, once a fresh pipeline exists (`PIPE01`):

| Job | Cadence | Freshness budget |
|---|---|---|
| `news.ingest` | every 30 min | 90 min |
| `eod.ingest` | 18:00 IST on session days | 26 h |
| `features.rebuild` | after `eod.ingest` | 26 h |
| `pillars.refit` | weekly | 8 days |
| `forecast.refresh` | after `features.rebuild` | 26 h |

Those budgets are **proposed defaults**, not measured requirements. They feed
`job_checks()` and should be revised once the real cadence is observed.

## 4. Monitoring (`OPS01`)

`seraph/operations/monitoring.py`.

- `source_checks()` / `job_checks()` → `ok` | `degraded` | `stale` | `failing`
  | `never_succeeded` | `never_run`. **A thing with no data never reads `ok`.**
  An empty dashboard with a green banner is the specific failure this prevents.
- `overall()` reports the worst check, with every name grouped by health.
- `AlertLedger` separates **issued** from **delivered**:
  `issued → delivered → acknowledged → resolved`, with `snoozed`, `escalated`
  and `delivery_failed` as real states. `undelivered()` lists alerts that were
  raised and never reached anyone, so they can be retried or escalated rather
  than lost. The trail is append-only and SQL-trigger protected.
- Issuing is idempotent by dedupe key.

**Not done:** an actual delivery transport. Nothing sends email or messages;
the ledger records what a transport would have been asked to do. Wiring one is
small, and claiming delivery without it would not be.

## 5. Audit coverage (NFR26)

| Covered now | Where |
|---|---|
| Regulator annotations: create, update, retract, revisions | `action_log.py`, `RunStore.action()` |
| Case lifecycle: every assignment, comment, evidence attach, review, decision, closure, reopen, with the real actor and organisation | `cases.py::case_events`, append-only |
| Identity: grants and memberships revoked by timestamp, never deleted | `identity/registry.py` |
| Alerts: issue and every delivery state change | `AlertLedger` |
| Scenario reviews | `scenarios.py::scenario_reviews` |

**Not covered:** view and export audit for ordinary reads. NFR26 asks for
dashboard-view events; nothing records who looked at what. That is a gap, and
the retention/access policy for such a log is an audience-decision question —
a view log is itself sensitive.

## 6. Backup and restore (`OPS02`)

**Migrations** (`seraph/store/migrations/`) apply in filename order, once
each, recorded with the SHA-256 of the file that ran. A migration whose file
changed after it was applied is an error, not a silent re-run. Every migration
runs in its own transaction.

What must be backed up, and why each one matters:

| Store | Holds | Loss means |
|---|---|---|
| research PostgreSQL | E1–E14, fitted artefacts, evaluation results | the corpus and every result |
| `prototype_runs/*.sqlite` | run manifests, points, reports, action journal | the audit trail of every decision |
| identity SQLite | users, orgs, grants, sessions | nobody can sign in; grant history gone |
| workspace SQLite | portfolios, holdings snapshots, imports | users' own data, irreplaceable |
| cases SQLite | case history, pinned evidence | the regulatory record |
| news SQLite | observations, stories, source health | re-fetchable in principle, but `first_seen_at` is **not** — restoring from the source would rewrite the replay bound |

That last row is the one to notice: news observations are not safely
re-derivable, because re-fetching assigns a new first-seen time and quietly
changes what a past replay is allowed to see.

**Not done:** no backup job, no restore procedure, no recovery exercise, and
therefore no recovery objective. `OPS02` is designed, not demonstrated.

## 7. What is explicitly not claimed

- **NFR9's 99.9% uptime** is a hypothetical deployment target. Nothing here
  has been measured against it and it is not a project result.
- **NFR23/24** transport and at-rest protection: not implemented, not
  measured, localhost only.
- **Load and concurrency** (NFR3, the 100-user figure): never run. No
  concurrency measurement of any kind exists.
- **Bar-close-to-view latency** (NFR1): never measured. An overnight archive
  replay is not that measurement, and it will not be used as one.
- **Disaster recovery**: untested.
