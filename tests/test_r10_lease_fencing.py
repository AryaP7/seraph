# R10 — job lease fencing (audit section B, DR-14)
"""An expired writer must not be able to write under a lease it has lost.

The audit: "Fence generic job checkpoints/watermarks/completion by current
lease owner and generation; renew bounded long jobs and recover abandoned
locks safely."

Three writes were unfenced -- `checkpoint`, `clear_checkpoint` and
`set_watermark` -- and there was no way to renew. The lease is 30 minutes by
default, so a job legitimately running longer had it taken over WHILE STILL
WORKING, and then both wrote. The consequences differ and each has its own
test below:

* a stale checkpoint overwrites the successor's progress;
* `clear_checkpoint` is called by `run()` on success, so an expired worker
  finishing late wipes the successor's progress and the successor restarts
  from nothing having already done the work;
* a stale watermark advance makes the successor skip input it never read.

`N05` depended on this: the news worker reports blocked polling correctly
now, but its underlying lease was the thing that could be silently stolen.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from seraph.operations.jobs import JobStore, LeaseLost, LockUnavailable


@pytest.fixture
def store(tmp_path):
    return JobStore(tmp_path / "jobs.sqlite")


@pytest.fixture
def t0():
    return datetime.now().astimezone().replace(microsecond=0)


def superseded(store, t0):
    """A lease taken over while its first holder still believes it owns it."""
    first = store.acquire("poll", "run-A", lease_minutes=1, now=t0)
    second = store.acquire("poll", "run-B", lease_minutes=30,
                           now=t0 + timedelta(minutes=2))
    return first, second


class TestTheFencingToken:
    def test_a_lease_carries_a_generation(self, store, t0):
        assert store.acquire("poll", "run-A", now=t0)["generation"] == 1

    def test_a_takeover_increments_it(self, store, t0):
        first, second = superseded(store, t0)
        assert second["generation"] == first["generation"] + 1
        assert second["took_over_expired_lease"] is True

    def test_it_is_not_reused_after_a_clean_release(self, store, t0):
        """Deriving the token from the lock row would reuse a generation
        after release, making a stale writer's token valid again."""
        first = store.acquire("poll", "run-A", now=t0)
        store.release("poll", "run-A")
        second = store.acquire("poll", "run-B", now=t0 + timedelta(seconds=1))
        assert second["generation"] > first["generation"]

    def test_a_live_lease_still_cannot_be_acquired(self, store, t0):
        store.acquire("poll", "run-A", lease_minutes=30, now=t0)
        with pytest.raises(LockUnavailable):
            store.acquire("poll", "run-B", now=t0 + timedelta(minutes=1))


class TestASupersededWriterIsRefused:
    def test_its_checkpoint_is_refused(self, store, t0):
        first, second = superseded(store, t0)
        store.checkpoint("poll", {"at": 99}, run_id="run-B",
                         generation=second["generation"])
        with pytest.raises(LeaseLost, match="held by run run-B"):
            store.checkpoint("poll", {"at": 2}, run_id="run-A",
                             generation=first["generation"])
        assert store.last_checkpoint("poll")["payload"] == {"at": 99}

    def test_its_clear_is_refused(self, store, t0):
        """The worst of the three: `run()` calls this on success, so an
        expired worker finishing late would wipe its successor's progress."""
        first, second = superseded(store, t0)
        store.checkpoint("poll", {"at": 99}, run_id="run-B",
                         generation=second["generation"])
        with pytest.raises(LeaseLost):
            store.clear_checkpoint("poll", run_id="run-A",
                                   generation=first["generation"])
        assert store.last_checkpoint("poll") is not None

    def test_its_watermark_advance_is_refused(self, store, t0):
        """A stale advance makes the successor skip input it never read."""
        first, second = superseded(store, t0)
        store.set_watermark("poll", "nse", "2026-08-21", run_id="run-B",
                            generation=second["generation"])
        with pytest.raises(LeaseLost):
            store.set_watermark("poll", "nse", "2099-01-01", run_id="run-A",
                                generation=first["generation"])
        assert store.watermark("poll", "nse") == "2026-08-21"

    def test_its_renewal_is_refused(self, store, t0):
        """A renewal granted to a superseded writer is worse than none: it
        extends a lease the writer no longer owns."""
        first, _ = superseded(store, t0)
        with pytest.raises(LeaseLost, match="no longer held"):
            store.renew("poll", "run-A", first["generation"])

    def test_the_refusal_says_what_to_do(self, store, t0):
        first, _ = superseded(store, t0)
        with pytest.raises(LeaseLost) as caught:
            store.checkpoint("poll", {}, run_id="run-A",
                             generation=first["generation"])
        assert "re-acquire" in str(caught.value)


class TestTheHolderCanStillWork:
    def test_the_current_holder_checkpoints_normally(self, store, t0):
        lease = store.acquire("poll", "run-A", now=t0)
        store.checkpoint("poll", {"at": 1}, run_id="run-A",
                         generation=lease["generation"])
        assert store.last_checkpoint("poll")["payload"] == {"at": 1}

    def test_the_current_holder_can_renew(self, store, t0):
        lease = store.acquire("poll", "run-A", lease_minutes=5, now=t0)
        renewed = store.renew("poll", "run-A", lease["generation"],
                              lease_minutes=60, now=t0)
        assert renewed["expires_at"] > lease["expires_at"]

    def test_renewing_keeps_the_lease_unacquirable(self, store, t0):
        """The point of renewal: a long job is not taken over mid-run."""
        lease = store.acquire("poll", "run-A", lease_minutes=1, now=t0)
        store.renew("poll", "run-A", lease["generation"], lease_minutes=60,
                    now=t0 + timedelta(seconds=30))
        with pytest.raises(LockUnavailable):
            store.acquire("poll", "run-B", now=t0 + timedelta(minutes=2))

    def test_an_unheld_job_accepts_an_ad_hoc_write(self, store):
        """The operator escape hatch: no lease exists, so nobody is being
        stamped over."""
        store.checkpoint("poll", {"manual": True}, run_id="operator")
        assert store.last_checkpoint("poll")["payload"] == {"manual": True}

    def test_an_unfenced_write_against_a_live_lease_is_refused(self, store, t0):
        """The escape hatch must not become a way around the fence."""
        store.acquire("poll", "run-A", lease_minutes=30, now=t0)
        with pytest.raises(LeaseLost, match="unfenced write"):
            store.checkpoint("poll", {"sneaky": True}, run_id="operator")


class TestRunPassesTheTokenThrough:
    def test_a_job_can_checkpoint_from_its_context(self, store):
        seen = {}

        def work(context):
            context.checkpoint({"step": 1})
            seen["generation"] = context.generation
            return dict(ok=True)

        record = store.run("poll", work)
        assert record.status == "succeeded"
        assert seen["generation"] == 1

    def test_a_context_can_renew(self, store):
        def work(context):
            context.renew(lease_minutes=60)
            return dict(ok=True)

        assert store.run("poll", work).status == "succeeded"

    def test_a_resumed_job_sees_the_previous_checkpoint(self, store):
        def failing(context):
            context.checkpoint({"progress": 7})
            raise RuntimeError("boom")

        store.run("poll", failing, max_attempts=1)
        resumed = {}

        def succeeding(context):
            resumed["from"] = context.resume_from
            return dict(ok=True)

        store.run("poll", succeeding)
        assert resumed["from"] == {"progress": 7}

    def test_success_clears_the_checkpoint_under_its_own_fence(self, store):
        def work(context):
            context.checkpoint({"step": 1})
            return dict(ok=True)

        store.run("poll", work)
        assert store.last_checkpoint("poll") is None

    def test_a_watermark_set_from_the_context_is_fenced(self, store):
        def work(context):
            context.set_watermark("nse", "2026-08-21")
            return dict(ok=True)

        store.run("poll", work)
        assert store.watermark("poll", "nse") == "2026-08-21"


class TestLeaseLostIsDistinctFromLockUnavailable:
    def test_they_are_different_types(self):
        """Different handling: one is a reason to wait, the other a reason to
        stop and re-acquire."""
        assert LeaseLost is not LockUnavailable
        assert not issubclass(LeaseLost, LockUnavailable)
        assert not issubclass(LockUnavailable, LeaseLost)
