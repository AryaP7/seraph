# Database state — 2026-10-18

Written after bringing Docker up to run the 14 tests that had been skipping.

## What happened

The Docker daemon was not running, so 12 of the 14 skipped tests could not
run. I started Docker Desktop and ran `docker compose up -d`, which is
AGENTS.md §7's documented command.

Compose applied the current `docker-compose.yml` — one service,
`seraph-research-timescaledb`, database `seraph_research`, volume
`seraph_research_pgdata`, on `127.0.0.1:5434`. That volume did not exist, so
compose created it empty, and in reconciling the project it removed an older
stopped container named `seraph-timescaledb`.

**Nothing was deleted and nothing running was stopped.** The daemon was down
when I started; `docker compose ps` listed no services. The removed container
was a leftover from a compose file that predates the source/research split, and
OPERATIONS.md §1 is explicit that the source database is "never started or
migrated from here" — so no intentionally-managed service was affected.

## The volumes

| | state |
|---|---|
| `seraphvarya_seraph_pgdata` | **intact**, 9.2 GB, PG_VERSION 16, complete PGDATA. No container attached, so not served on any port. Verified by mounting it **read-only** in a throwaway container. |
| `seraphvarya_seraph_research_pgdata` | new, served on `127.0.0.1:5434` as `seraph_research` |
| test instance | tmpfs inside `seraph-test-timescaledb`, `127.0.0.1:5435` — nothing persistent |

OPERATIONS.md §1 places the source database on **5433**. Nothing serves 5433
now, and by that document's own rule this repo is not where that should be
fixed. The 9.2 GB of data is on the volume above whenever it is wanted; only a
container is missing. I have **not** added one — exposing the read-only source
corpus is your call, and the password must come from outside the repo.

## The test database — use the project's own tooling

Your constraint was: *a separate experimental database for production-like
results, and a guarded disposable `seraph_test_*` database for tests; never
place the test marker into a source or research database.*

That is already built, and better than what I first improvised:

```bash
docker compose -f docker-compose.test.yml up -d
python scripts/provision_test_db.py        # prints the two variables
```

The instance is **tmpfs** — in memory, so a test database cannot survive a
reboot — on its own port, in its own container. `provision_test_db.py` refuses
a name not starting with `seraph_test_`, refuses a non-loopback host, and
refuses a target that already holds rows in any of E1–E14.

Result with it provisioned: **98 passed, 0 skipped** across
`test_ct1_ingestion_idempotency`, `test_c2_macro_ingestion`,
`test_c5_hawkes_writer` and `test_fix06_evaluation_identity`.

I first created `seraph_test_ct` by hand inside the research container before
finding this script. It was a genuine `seraph_test_*` database and the guard
accepted it, but it sat on a persistent volume inside the research instance,
which is worse on both counts. **It has been dropped**; `seraph_research` is
back to being the only database in that container.

### Three guards, verified still refusing

`tests/conftest.py` overwrites `SERAPH_DB_DSN` with a dead address
unconditionally, so a test run can never inherit an application connection.
DB tests enable only when `SERAPH_TEST_DB_DSN` names a `seraph_test_*`
database, `SERAPH_TEST_TOKEN` is set, and `seraph_test_guard(token)` holds it.

| attempt | result |
|---|---|
| DSN pointing at `seraph_research` | refused — "requires a seraph_test_* database" |
| `seraph_test_*` with no token | refused |
| `seraph_test_*` with a wrong token | refused — "Missing disposable database marker" |

### One trap worth knowing

Both compose files share a project name, so
`docker compose -f docker-compose.test.yml up -d` warns that
`seraph-research-timescaledb` is an "orphan container". Running that command
with `--remove-orphans` **would delete the research container**. Don't. The
warning is cosmetic; the flag is not.

Teardown, when you want it:

```bash
docker compose -f docker-compose.test.yml down -v   # tmpfs, so really gone
```

## Two defects this exposed

**1. `DEFAULT_DSN` could never authenticate.** `bootstrap.py` hardcoded
`postgresql://seraph:seraph@localhost:5434/seraph_research` while
`docker-compose.yml` sets `POSTGRES_PASSWORD: ${SERAPH_DB_PASSWORD:-change-me-locally}`.
Two copies of one default in two files, drifted. Anyone following §7 got
`InvalidPasswordError` and a message telling them to run the command they had
just run. The default is now assembled from the same variables compose reads,
so they cannot disagree again — and a password is no longer hardcoded in a
versioned source file, which your own rule asks for even of a placeholder.

**2. The skip reason named a cause it had not established.** The probe caught
every exception and reported "TimescaleDB not reachable — run
`docker compose up -d` first". An auth failure, a wrong port, a missing
database and a stopped container are four different problems and three are not
unreachability. This cost real time: I started Docker, connected by hand, and
still read "not reachable". The reason now carries the actual error and names
the two variables actually required.

A third, smaller: setting `SERAPH_TEST_DB_DSN` to something unusable let the
exception escape `pytest_configure`, which pytest renders as an
`INTERNALERROR` traceback — so a wrong password looked like a broken harness.
It is now a one-line `pytest.UsageError`. The guard's behaviour is unchanged;
only its reporting is.

## The orphan trap is now closed structurally

`docker-compose.test.yml` previously had no project name, so both files
defaulted to the directory name. Compose therefore reported
`seraph-research-timescaledb` as an "orphan container" of the test project and
suggested `--remove-orphans` — a flag that would have **deleted the research
container**.

It now declares `name: seraph-test`, so the two are separate compose projects:
the suggestion never appears and the flag cannot reach across. `container_name`
is explicit and the data volume is tmpfs, so nothing else about the instance
changes.

**This takes effect on the next recreate.** The container currently running
was created under the old project name, so a `up -d` under the new name
conflicts on the container name until the old one is removed. Apply it when
convenient — the test database is tmpfs and holds nothing worth keeping:

```bash
docker compose -f docker-compose.test.yml down -v     # old project
docker compose -f docker-compose.test.yml up -d       # new project name
python scripts/provision_test_db.py
```

I did not do this here because a full-suite run was using the instance, and
pulling it out mid-run would have invalidated a third consecutive run.
