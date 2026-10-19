# C5 — Hawkes Engine (FR10–FR15): per-window basket construction of the pooled
# count stream. T05 / audit finding R11.
"""Make the basket the metadata declares the basket the counts actually came from.

**The defect (R11).** `scripts/write_hawkes_production.py` resolved the universe
*once*, at the end of the corpus, loaded one pooled jump stream from those
symbols, and then sliced that single stream for every refit window. Separately
and correctly, it resolved a point-in-time basket per window and wrote it into
the artefact. So the artefact declared a 2016 membership while the counts it
described were pooled over the 2026 membership. The metadata was not a
description of the input; it was a description of a different input.

Two directions of error follow, and they are not symmetric:

* **Survivorship.** A symbol that left the universe before the corpus end is
  never loaded at all, so its events are missing from the windows in which it
  *was* a member. In this corpus that set happens to be empty — every symbol
  with intraday bars is in the terminal basket — but that is a property of how
  the intraday pull was scoped, not a property the code may assume.
* **Composition inflation.** A symbol that joined the universe late is loaded
  for every window, including windows long before it was a member. This one is
  large here: of the 91 intraday-covered symbols in the terminal basket, 52
  were not in the 2005 basket, so an early window's pooled stream carried
  substantially more contributors than its declared basket had.

**What this module provides.** `PooledStream` holds each symbol's events once,
indexed against a single global bar grid, and pools them *per window* from that
window's own member set. `WindowManifest` records what was actually used —
basket digest, membership policy, contributing symbols, a content hash of the
underlying input rows, a hash of the pooled counts handed to the estimator, the
detector version and the window bounds — so input/metadata agreement is a
checkable claim rather than an assurance.

**Membership policy is explicit, never implied.** Three are distinguished:

``fixed_at_fit_cutoff``
    the snapshot in force at the window's last session, applied across the
    whole window. This is the adopted policy (see
    `docs/decisions/DR-08-2026-10-16-hawkes-membership-policy.md`): it is what
    an operator standing at the cutoff can actually know, it matches the
    `point_in_time_members(pool, window_end)` basket the artefact already
    recorded, and it keeps composition constant within a window so the pooled
    count series stays comparable across its own length.
``fixed_at_window_start``
    the snapshot in force at the window's first session. Causally safe, but it
    scores today using a basket up to `window_days` sessions out of date.
``day_varying``
    each session uses the snapshot in force on that session. Historically the
    most faithful, and the reason it is not the default is that it makes the
    exposure denominator move inside a window, so a change in `n` cannot be
    separated from a change in who was being counted.

The content hashes use an order-independent XOR accumulation over per-session
digests, so a window's hash depends on exactly the rows inside it: changing a
price inside the window changes the hash, and changing one outside it does not.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Literal, Sequence

import numpy as np

from seraph.features.jump_extraction import (
    LM_ALPHA,
    LM_TEST_BLOCK_SIZE,
    LM_WINDOW_K,
    extract_jumps,
)

STREAM_VERSION = "c5.basket_stream/2026-10-16.1"

#: Identifies the jump detector that produced the events, including the
#: constants that change its output. Derived from C4's own constants rather
#: than restated here, so the two cannot drift apart.
DETECTOR_VERSION = (f"lee_mykland/k={LM_WINDOW_K},alpha={LM_ALPHA:g},"
                    f"block={LM_TEST_BLOCK_SIZE}")

MembershipPolicy = Literal["fixed_at_fit_cutoff", "fixed_at_window_start",
                           "day_varying"]
MEMBERSHIP_POLICIES: tuple[MembershipPolicy, ...] = (
    "fixed_at_fit_cutoff", "fixed_at_window_start", "day_varying")

#: A symbol needs a full bipower window (k bars) plus a margin before any jump
#: can be flagged at all; below this it contributes nothing but noise to the
#: active-symbol denominator.
MIN_SYMBOL_BARS = 200

_LANES = 4          # a 256-bit digest held as four uint64 lanes


def _digest_lanes(payload: bytes) -> np.ndarray:
    raw = hashlib.sha256(payload).digest()
    return np.frombuffer(raw, dtype=">u8").astype(np.uint64)


def _lanes_bytes(lanes: np.ndarray) -> bytes:
    return lanes.astype(">u8").tobytes()


# --------------------------------------------------------------- symbol series


@dataclass(frozen=True)
class SymbolSeries:
    """One symbol's contribution to the pooled stream, indexed on the grid.

    `bar_index`, `neg_index` and `pos_index` are positions in the global bar
    grid, so pooling any member set is a gather rather than a re-read.
    `session_xor` is the cumulative XOR of this symbol's per-session content
    digests, giving a sliceable content hash for any window.
    """

    symbol: str
    bar_index: np.ndarray
    neg_index: np.ndarray
    pos_index: np.ndarray
    bars_kept: int
    session_xor: np.ndarray          # (n_sessions + 1, _LANES) uint64

    def bars_in(self, lo: int, hi: int) -> int:
        a, b = np.searchsorted(self.bar_index, (lo, hi + 1))
        return int(b - a)

    def content_digest(self, lo_session: int, hi_session: int) -> np.ndarray:
        """XOR of this symbol's session digests over `[lo_session, hi_session]`."""
        return np.bitwise_xor(self.session_xor[hi_session + 1],
                              self.session_xor[lo_session])


# ------------------------------------------------------------------- manifest


@dataclass(frozen=True)
class WindowManifest:
    """What a refit window actually consumed. Checkable, not merely asserted."""

    as_of: str
    training_start: str
    start_index: int
    end_index: int
    n_bars: int
    n_sessions: int
    membership_policy: MembershipPolicy
    basket_id: str
    basket_basis: str
    rebalance_date: str | None
    members_declared: int
    members_contributing: int
    members_without_data: tuple[str, ...]
    n_neg: int
    n_pos: int
    input_row_hash: str
    event_hash: str
    detector_version: str = DETECTOR_VERSION
    stream_version: str = STREAM_VERSION
    segments: tuple[dict, ...] = ()

    @property
    def coverage(self) -> float:
        """Share of the declared basket that had any bar inside the window."""
        if not self.members_declared:
            return 0.0
        return self.members_contributing / self.members_declared

    def describe(self) -> dict:
        return dict(
            as_of=self.as_of, training_start=self.training_start,
            window=dict(start_index=self.start_index, end_index=self.end_index,
                        n_bars=self.n_bars, n_sessions=self.n_sessions),
            membership=dict(
                policy=self.membership_policy, basket_id=self.basket_id,
                basis=self.basket_basis, rebalance_date=self.rebalance_date,
                declared=self.members_declared,
                contributing=self.members_contributing,
                coverage=round(self.coverage, 6),
                without_data=list(self.members_without_data),
                segments=[dict(s) for s in self.segments] or None),
            events=dict(n_neg=self.n_neg, n_pos=self.n_pos),
            hashes=dict(input_row_hash=self.input_row_hash,
                        event_hash=self.event_hash),
            versions=dict(detector=self.detector_version,
                          stream=self.stream_version),
        )


def basket_digest(members) -> str:
    """Order-independent digest of a member set."""
    return hashlib.sha256("|".join(sorted(set(members))).encode()).hexdigest()


def segments_digest(segments) -> str:
    """Digest of a whole membership schedule, bounds included.

    A single-segment schedule digests to the same value as its member set, so
    a fixed policy's basket id is the basket's own digest and nothing has to
    special-case it. A `day_varying` window has no single basket, and this is
    what stands in for one rather than a cutoff digest that would misdescribe
    most of the window.
    """
    ordered = sorted(segments)
    if len(ordered) == 1:
        return basket_digest(ordered[0][2])
    payload = "|".join(f"{lo}:{hi}:{basket_digest(members)}"
                       for lo, hi, members in ordered)
    return hashlib.sha256(payload.encode()).hexdigest()


def event_hash_of(n_neg, n_pos, active) -> str:
    """Hash the exact count vectors handed to the estimator."""
    h = hashlib.sha256()
    for name, arr in (("neg", n_neg), ("pos", n_pos), ("active", active)):
        h.update(name.encode())
        h.update(np.asarray(arr, dtype=np.int64).tobytes())
    return h.hexdigest()


def verify_manifest(manifest: WindowManifest, *, n_neg, n_pos, active) -> list[str]:
    """Does this manifest describe these inputs? Returns the disagreements."""
    problems: list[str] = []
    recomputed = event_hash_of(n_neg, n_pos, active)
    if recomputed != manifest.event_hash:
        problems.append(
            f"event hash disagrees: the manifest records {manifest.event_hash[:12]} "
            f"and these counts hash to {recomputed[:12]}")
    if int(np.asarray(n_neg).sum()) != manifest.n_neg:
        problems.append(
            f"negative-jump total disagrees: manifest {manifest.n_neg}, "
            f"counts {int(np.asarray(n_neg).sum())}")
    if int(np.asarray(n_pos).sum()) != manifest.n_pos:
        problems.append(
            f"positive-jump total disagrees: manifest {manifest.n_pos}, "
            f"counts {int(np.asarray(n_pos).sum())}")
    if len(np.asarray(n_neg)) != manifest.n_bars:
        problems.append(
            f"length disagrees: manifest {manifest.n_bars} bars, "
            f"counts {len(np.asarray(n_neg))}")
    return problems


# ---------------------------------------------------------------- the stream


@dataclass(frozen=True)
class StreamQuality:
    symbols_requested: int
    symbols_used: int
    symbols_too_short: tuple[str, ...]
    symbols_absent: tuple[str, ...]
    bars_read: int
    bars_dropped_nonpositive: int

    def describe(self) -> dict:
        return dict(symbols_requested=self.symbols_requested,
                    symbols_used=self.symbols_used,
                    symbols_too_short=list(self.symbols_too_short),
                    symbols_absent=list(self.symbols_absent),
                    bars_read=self.bars_read,
                    bars_dropped_nonpositive=self.bars_dropped_nonpositive)


class PooledStream:
    """Per-symbol events on one grid, pooled on demand for a member set.

    Construct with `build()`. Nothing here reads a database: the caller hands
    over `(symbol, timestamps, closes)` triples, which keeps the window logic
    unit-testable against a fixture with no corpus at all.
    """

    def __init__(self, bars: list, series: "dict[str, SymbolSeries]",
                 quality: StreamQuality) -> None:
        self.bars = bars
        self.series = series
        self.quality = quality
        self.day = np.array([t.date() for t in bars])
        tod = np.array([t.hour * 60 + t.minute for t in bars], dtype=np.int64)
        slots = np.unique(tod) if len(bars) else np.zeros(0, dtype=np.int64)
        self.tod_index = np.searchsorted(slots, tod)
        self.n_slots = int(slots.size)
        self.new_sess = (np.r_[True, self.day[1:] != self.day[:-1]]
                         if len(bars) else np.zeros(0, dtype=bool))
        self.session_index = (np.cumsum(self.new_sess) - 1
                              if len(bars) else np.zeros(0, dtype=np.int64))
        self.n_sessions = int(self.new_sess.sum())
        self.session_start_index = np.flatnonzero(self.new_sess)
        self._cache: "dict[str, dict]" = {}

    # ---------------------------------------------------------------- build

    @classmethod
    def build(cls, symbol_rows: "Iterable[tuple[str, Sequence, Sequence]]", *,
              requested: "Sequence[str] | None" = None,
              min_symbol_bars: int = MIN_SYMBOL_BARS) -> "PooledStream":
        """Build from an iterable of `(symbol, timestamps, closes)`.

        Convenience over `StreamBuilder` for tests and small inputs. A corpus
        read should use the builder directly and drop each symbol's rows as it
        goes — holding nineteen million `Record`s to assemble one grid is how
        the previous loader made its memory footprint the size of the corpus.
        """
        builder = StreamBuilder(requested=requested,
                                min_symbol_bars=min_symbol_bars)
        for symbol, timestamps, closes in symbol_rows:
            builder.add(symbol, timestamps, closes)
        return builder.finish()


    # --------------------------------------------------------------- pooling

    def _full(self, members: "tuple[str, ...]") -> dict:
        """Full-grid pooled counts for a member set, cached by basket digest.

        Refit windows run in date order and the member set only changes at a
        rebalance, so a small cache turns one pass per window into one pass per
        basket.
        """
        key = hashlib.sha256("|".join(sorted(set(members))).encode()).hexdigest()
        hit = self._cache.get(key)
        if hit is not None:
            return hit
        n = len(self.bars)
        active = np.zeros(n, dtype=np.int64)
        neg = np.zeros(n, dtype=np.int64)
        pos = np.zeros(n, dtype=np.int64)
        used: "list[str]" = []
        for symbol in sorted(set(members)):
            s = self.series.get(symbol)
            if s is None:
                continue
            used.append(symbol)
            active += np.bincount(s.bar_index, minlength=n)
            if s.neg_index.size:
                neg += np.bincount(s.neg_index, minlength=n)
            if s.pos_index.size:
                pos += np.bincount(s.pos_index, minlength=n)
        value = dict(active=active, neg=neg, pos=pos, used=tuple(used))
        if len(self._cache) >= 6:
            self._cache.pop(next(iter(self._cache)))
        self._cache[key] = value
        return value

    def window(self, lo: int, hi: int, *,
               segments: "Sequence[tuple[int, int, tuple[str, ...]]]",
               policy: MembershipPolicy, declared: "Sequence[str]",
               basket_id: str, basket_basis: str,
               rebalance_date: "str | None") -> "tuple[dict, WindowManifest]":
        """Pool `[lo, hi]` from the given membership segments and describe it.

        `segments` are `(seg_lo, seg_hi, members)` triples that must tile the
        window exactly. A fixed policy passes one segment; `day_varying` passes
        one per rebalance interval the window overlaps.
        """
        if hi < lo:
            raise ValueError(f"empty window [{lo}, {hi}]")
        ordered = sorted(segments)
        covered = [(a, b) for a, b, _ in ordered]
        if not covered or covered[0][0] != lo or covered[-1][1] != hi:
            raise ValueError(
                f"the membership segments do not tile the window: they span "
                f"{covered[0][0] if covered else None}..."
                f"{covered[-1][1] if covered else None}, "
                f"the window is {lo}...{hi}")
        for (_, b1), (a2, _) in zip(covered, covered[1:]):
            if a2 != b1 + 1:
                raise ValueError(
                    f"the membership segments leave a gap or overlap between "
                    f"bar {b1} and bar {a2}")

        n = hi - lo + 1
        active = np.zeros(n, dtype=np.int64)
        neg = np.zeros(n, dtype=np.int64)
        pos = np.zeros(n, dtype=np.int64)
        contributing: set = set()
        content = np.zeros(_LANES, dtype=np.uint64)
        described: "list[dict]" = []

        for seg_lo, seg_hi, members in ordered:
            full = self._full(tuple(members))
            a, b = seg_lo - lo, seg_hi - lo + 1
            active[a:b] = full["active"][seg_lo:seg_hi + 1]
            neg[a:b] = full["neg"][seg_lo:seg_hi + 1]
            pos[a:b] = full["pos"][seg_lo:seg_hi + 1]
            lo_sess = int(self.session_index[seg_lo])
            hi_sess = int(self.session_index[seg_hi])
            seg_contrib = []
            for symbol in full["used"]:
                s = self.series[symbol]
                if not s.bars_in(seg_lo, seg_hi):
                    continue
                seg_contrib.append(symbol)
                contributing.add(symbol)
                content = np.bitwise_xor(content,
                                         s.content_digest(lo_sess, hi_sess))
            described.append(dict(
                start=str(self.day[seg_lo]), end=str(self.day[seg_hi]),
                declared=len(set(members)), contributing=len(seg_contrib)))

        declared_set = tuple(sorted(set(declared)))
        without = tuple(s for s in declared_set if s not in contributing)
        structural = json.dumps(dict(
            detector=DETECTOR_VERSION, stream=STREAM_VERSION, policy=policy,
            basket=basket_id, start=self.bars[lo].isoformat(),
            end=self.bars[hi].isoformat(), n_bars=n,
            contributors=sorted(
                [s, self.series[s].bars_in(lo, hi)] for s in contributing),
        ), sort_keys=True, separators=(",", ":"))
        input_row_hash = hashlib.sha256(
            structural.encode() + _lanes_bytes(content)).hexdigest()

        inputs = dict(
            n_neg=neg.astype(float), n_pos=pos.astype(float),
            active=active.astype(float),
            session_starts=self.new_sess[lo:hi + 1],
            tod_index=self.tod_index[lo:hi + 1], n_slots=self.n_slots,
            bars=self.bars[lo:hi + 1], day=self.day[lo:hi + 1])
        manifest = WindowManifest(
            as_of=str(self.day[hi]), training_start=str(self.day[lo]),
            start_index=lo, end_index=hi, n_bars=n,
            n_sessions=int(self.new_sess[lo:hi + 1].sum()),
            membership_policy=policy, basket_id=basket_id,
            basket_basis=basket_basis, rebalance_date=rebalance_date,
            members_declared=len(declared_set),
            members_contributing=len(contributing),
            members_without_data=without,
            n_neg=int(neg.sum()), n_pos=int(pos.sum()),
            input_row_hash=input_row_hash,
            event_hash=event_hash_of(neg, pos, active),
            segments=tuple(described))
        return inputs, manifest


class StreamBuilder:
    """Accumulate per-symbol series, then assemble one grid.

    The point of the two-phase shape is memory: a symbol's rows are reduced to
    two numpy arrays (epoch seconds and closes) and the caller's `Record` list
    can be dropped immediately. Across 91 symbols and 18.7M intraday bars that
    is a few hundred megabytes rather than several gigabytes of Python objects.
    """

    def __init__(self, *, requested: "Sequence[str] | None" = None,
                 min_symbol_bars: int = MIN_SYMBOL_BARS) -> None:
        self.requested = list(requested) if requested is not None else None
        self.min_symbol_bars = min_symbol_bars
        self._epoch: "dict[str, np.ndarray]" = {}
        self._close: "dict[str, np.ndarray]" = {}
        self._jump_sign: "dict[str, np.ndarray]" = {}
        self._moment: "dict[int, object]" = {}
        self._too_short: "list[str]" = []
        self._no_rows: "list[str]" = []
        self._seen: "list[str]" = []
        self.bars_read = 0
        self.bars_dropped_nonpositive = 0

    def add(self, symbol: str, timestamps: "Sequence", closes: "Sequence") -> None:
        """Extract this symbol's jumps once. Order of calls does not matter."""
        if symbol in self._seen:
            raise ValueError(f"{symbol} was added twice")
        self._seen.append(symbol)
        ts = list(timestamps)
        close = np.asarray(closes, dtype=float)
        self.bars_read += int(close.size)
        if close.size:
            good = close > 0.0
            dropped = int((~good).sum())
            if dropped:
                self.bars_dropped_nonpositive += dropped
                ts = [t for t, g in zip(ts, good) if g]
                close = close[good]
        if close.size == 0:
            # No intraday rows at all is a coverage gap, not a short series.
            # Reporting 221 universe members as "too short" would read as a
            # detector problem when it is really the intraday backfill never
            # having covered them.
            self._no_rows.append(symbol)
            return
        if close.size < self.min_symbol_bars:
            self._too_short.append(symbol)
            return
        epoch = np.fromiter((int(t.timestamp()) for t in ts), dtype=np.int64,
                            count=len(ts))
        for key, moment in zip(epoch.tolist(), ts):
            if key not in self._moment:
                self._moment[key] = moment
        self._epoch[symbol] = epoch
        self._close[symbol] = close
        self._jump_sign[symbol] = np.asarray(extract_jumps(close)["jump_sign"])

    def finish(self) -> "PooledStream":
        keys = np.array(sorted(self._moment), dtype=np.int64)
        bars = [self._moment[int(k)] for k in keys]
        day = np.array([t.date() for t in bars])
        new_sess = (np.r_[True, day[1:] != day[:-1]] if bars
                    else np.zeros(0, dtype=bool))
        session_index = (np.cumsum(new_sess) - 1 if bars
                         else np.zeros(0, dtype=np.int64))
        n_sessions = int(new_sess.sum())

        series: "dict[str, SymbolSeries]" = {}
        for symbol, epoch in self._epoch.items():
            close = self._close[symbol]
            sign = self._jump_sign[symbol]
            idx = np.searchsorted(keys, epoch)
            order = np.argsort(idx, kind="stable")
            idx, close, sign = idx[order], close[order], sign[order]
            series[symbol] = SymbolSeries(
                symbol=symbol, bar_index=idx,
                neg_index=idx[sign == -1], pos_index=idx[sign == 1],
                bars_kept=int(idx.size),
                session_xor=_session_xor(symbol, idx, close, session_index,
                                         n_sessions))

        requested = self.requested if self.requested is not None else list(series)
        absent = tuple(sorted(set(self._no_rows) | {
            s for s in requested
            if s not in series and s not in self._too_short
            and s not in self._no_rows}))
        quality = StreamQuality(
            symbols_requested=len(requested), symbols_used=len(series),
            symbols_too_short=tuple(sorted(self._too_short)),
            symbols_absent=absent,
            bars_read=self.bars_read,
            bars_dropped_nonpositive=self.bars_dropped_nonpositive)
        return PooledStream(bars, series, quality)


def membership_segments(stream: PooledStream, lo: int, hi: int, *,
                        policy: MembershipPolicy,
                        resolve) -> "list[tuple[int, int, tuple[str, ...]]]":
    """Split `[lo, hi]` into contiguous runs of constant membership.

    `resolve(date_str)` returns the member tuple in force on that session; it
    is a callable rather than a table so this stays free of any database.
    A fixed policy yields one segment. `day_varying` yields one per run of
    consecutive sessions whose member set is unchanged, which for a half-yearly
    rebalance is at most a handful even for a multi-year window.
    """
    if policy not in MEMBERSHIP_POLICIES:
        raise ValueError(
            f"unknown membership policy {policy!r}; the three distinguished "
            f"policies are {', '.join(MEMBERSHIP_POLICIES)}")
    if policy == "fixed_at_fit_cutoff":
        return [(lo, hi, tuple(resolve(str(stream.day[hi]))))]
    if policy == "fixed_at_window_start":
        return [(lo, hi, tuple(resolve(str(stream.day[lo]))))]

    segments: "list[tuple[int, int, tuple[str, ...]]]" = []
    seg_lo = lo
    current = tuple(resolve(str(stream.day[lo])))
    for i in range(lo + 1, hi + 1):
        if not stream.new_sess[i]:
            continue
        members = tuple(resolve(str(stream.day[i])))
        if members != current:
            segments.append((seg_lo, i - 1, current))
            seg_lo, current = i, members
    segments.append((seg_lo, hi, current))
    return segments


def _session_xor(symbol: str, bar_index: np.ndarray, close: np.ndarray,
                 session_index: np.ndarray, n_sessions: int) -> np.ndarray:
    """Cumulative XOR of per-session content digests, for sliceable hashing.

    XOR is order-independent, which is what makes a window's digest the
    difference of two prefixes. Order is not thereby left unpinned: the
    structural identity hashed alongside it carries the window bounds and each
    contributor's bar count.
    """
    prefix = np.zeros((n_sessions + 1, _LANES), dtype=np.uint64)
    if bar_index.size == 0:
        return prefix
    sess = session_index[bar_index]
    starts = np.flatnonzero(np.r_[True, sess[1:] != sess[:-1]])
    edges = np.r_[starts, sess.size]
    running = np.zeros(_LANES, dtype=np.uint64)
    cursor = 0
    for a, b in zip(edges[:-1], edges[1:]):
        j = int(sess[a])
        while cursor <= j:
            prefix[cursor] = running
            cursor += 1
        running = np.bitwise_xor(running, _digest_lanes(
            symbol.encode() + b"|" + str(j).encode() + b"|"
            + np.ascontiguousarray(close[a:b]).tobytes()))
    while cursor <= n_sessions:
        prefix[cursor] = running
        cursor += 1
    return prefix
