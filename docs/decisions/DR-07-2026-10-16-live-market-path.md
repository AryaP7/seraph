# DR-07 — The live market path, and the gap it exposes

**Date:** 2026-10-16
**Raised by:** the owner — *"the SERAPH systems risk score is supposed to be a
real-time market risk score… have you started the development of real-time
data ingestion, where are you getting present market data from"*
**Status:** architecture built; **no live data source connected**

---

## The finding, stated plainly

**SERAPH has no present market data, and until now nothing said so.**

| | |
|---|---|
| Research corpus ends | **2026-08-21** |
| Today | **2026-10-16** |
| Gap | **56 days** |
| `kite_client.py` | REST only — historical candles, daily token. No `KiteTicker`, no websocket |
| Live loop in the codebase | none existed |
| "Fresh source endpoint" | reads source PostgreSQL (unreachable) **and withholds its composite** — a diagnostic, never a live score |

Every CSRS this system has produced — including everything built in the
previous slices — is a replay. That is correct for policy work and historical
segments, which is what the owner uses it for. It is not the product: FR39 and
NFR1 specify a current market risk score with a bar-close-to-view latency
budget.

The deeper problem was not the gap itself but that **the gap was invisible**.
A replayed score and a live score rendered identically. Nothing in the payload,
the UI or the API distinguished them.

## What was built

### `seraph/live/clock.py` — the market clock

Inverts the replay model. Instead of picking a date and deriving a decision
time, the clock decides when a decision happens:

- `state()` → `pre_open` | `open` | `closed_for_day` | `not_a_session`, built
  on the existing session registry, so Muhurat evenings and two-window special
  sessions are already right.
- `current_bar()` is explicitly **incomplete**; `last_closed_bar()` is the
  newest one safe to compute on. Feeding a partial bar to Lee–Mykland produces
  a jump that un-happens five minutes later, and a flickering risk score
  destroys trust faster than a wrong one.
- **`recency()` is the gate the whole path hangs on.** It returns `live`,
  `delayed`, `stale` or `historical_only`, and `may_publish_as_current` is
  False for the last two. Against the current corpus the answer is
  `historical_only` — as a returned value, not a caveat.

### `seraph/live/feed.py` — sources, and their absence

- `MarketDataFeed` protocol; `KiteTickerFeed` is the real websocket adapter.
- **No automatic fallback.** Without credentials `resolve_feed()` returns
  `NullFeed` carrying the reason. A `ReplayFeed` must be handed over
  *deliberately*, reports `is_live=False`, and stamps every tick `replay`.
- `KiteTickerFeed` raises `FeedUnavailable` rather than degrading, and its
  `health().detail` states it has never been exercised against the live
  endpoint in this checkout.

### `seraph/live/bars.py` — ticks to bars

Only emits bars whose window has fully elapsed. Closes on a timer so a thin
symbol cannot hold a bar open. A **late tick is rejected and counted**, never
folded into a closed bar — amending a bar the pillars already consumed would
change a published score. Bar volume is the increment of the broker's
cumulative day figure, not the cumulative figure itself.

### `seraph/live/loop.py` — the bar-close decision loop

`LiveDecision.publishable` is False unless recency permits **and** the feed is
live. A decision that ran but is not publishable is still recorded, with the
reason. `bar_close_to_decision_ms` is measured from the bar's close on every
tick, because NFR1 is about bar-close-to-view latency and an overnight replay
benchmark says nothing about it.

### `scripts/run_live.py` — the scheduler entry point

`--status` reports the clock, feed and recency and changes nothing; `--once`
runs a single pass under the `PIPE03` job lock. Today it prints:

```
[live] NO LIVE MARKET DATA SOURCE.
[live] NOTHING IS PUBLISHABLE AS A CURRENT READING.
[live] recency = historical_only
```

### The banner — the most important change

`console_backend.liveness_of()` computes recency for the displayed point and
the bridge renders it as a **red banner across the console**:

> **HISTORICAL REPLAY — NOT A CURRENT MARKET READING** — the newest
> observation is 2360.1 days old… market closed_for_day · feed: none — no live
> market data source is configured

It turns green and says `CURRENT MARKET READING` only when recency and feed
both permit. A user can no longer mistake a replay for the market.

## What is needed to actually go live

| Need | Unlocks |
|---|---|
| **Kite API key + daily access token**, and `pip install kiteconnect` | `KiteTickerFeed` connects; bars start closing; decisions become publishable |
| **Source PostgreSQL** (5433/5434) | the warm-start history the pillars need — a live bar is meaningless without the trailing window the ECDF and Hawkes windows are fitted on |
| A decision on the live universe | currently a 5-symbol default; the real set is C3's point-in-time snapshot, which needs the source DB |

The first two are the same two blockers that already gate `PIPE01`. Live
execution is not a separate project from the fresh-data path — it is its
endpoint.

## What is explicitly not claimed

- **No live connection has ever been made.** The adapter's failure paths are
  tested; its success path is not.
- **No bar-close-to-view latency has been measured.** The instrumentation
  exists and has never seen a real bar close.
- **The 5-symbol default is a placeholder**, enough to prove the path, not a
  universe.
- Nothing here changes the scientific position: advance-warning skill remains
  unestablished, and a live score would not change that.

## Verification

`tests/test_live_market_path.py` — **30 passed**: session states including
Muhurat and split sessions, partial-bar refusal, late-tick rejection, bar
volume as increment, no-automatic-fallback, replay never claiming live,
recency across live/delayed/stale/historical_only, and the loop computing a
score that is correctly **not publishable**.

Core partition after the change: **843 passed, 14 skipped, 1 xfailed, 0
failures**. Five invariants pass. `git diff --check` clean.
