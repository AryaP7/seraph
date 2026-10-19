-- 002 — scope a decision to its stream (audit R06, verification X04)
--
-- `runtime_head` was stream-scoped from the start: one head row per
-- `stream_id`, and every read of it filtered on that column. `live_decisions`
-- was not. It had no `stream_id` at all, so `latest_decision()` and
-- `decisions()` queried every row in the database and ordered by `as_of` --
-- which means a replay stream's decision, or a demo's, could be returned as
-- the current live reading. Two different facts about the world, sharing one
-- answer.
--
-- X04 made that reachable rather than theoretical. The decision id was
-- `f"live:{as_of.isoformat()}"`, carrying neither stream nor mode, so a
-- replay pass and a live pass over the same bar end minted the SAME id.
-- Combined with `commit_decision` returning an existing row as a replay
-- before comparing its payload, a replay commit was accepted as the live
-- decision and reported `replayed=True`.
--
-- Both halves are closed: this migration adds the column and the scoped
-- index, `engine_adapter.decision_id()` puts mode and stream in the id, and
-- `commit_decision` compares `payload_hash` before declaring a replay.
--
-- Backfill. Existing rows predate the composite id and are all from the
-- default stream -- they were written by the only writer there was, whose
-- ids are prefixed `live:`. They are assigned 'live' rather than guessed at
-- from the id text, because a wrong stream attribution is worse than a
-- conservative one: it would move a historical decision into a stream that
-- never produced it.

ALTER TABLE live_decisions ADD COLUMN stream_id TEXT NOT NULL DEFAULT 'live';

-- The read path is (stream, recency). The old index was `as_of DESC` alone,
-- which is the index for the query that caused the defect.
CREATE INDEX IF NOT EXISTS live_decisions_by_stream_as_of
    ON live_decisions(stream_id, as_of DESC, computed_at DESC);

-- Outbox events belong to a stream too: a replay must not be able to emit a
-- production alert, and O04's delivery worker reads this table. Without the
-- column it would have no way to tell whose event it is holding.
ALTER TABLE outbox ADD COLUMN stream_id TEXT NOT NULL DEFAULT 'live';

CREATE INDEX IF NOT EXISTS outbox_by_stream
    ON outbox(stream_id, next_attempt_at);
