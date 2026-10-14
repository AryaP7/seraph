#!/usr/bin/env python3
# C10 — operational usefulness of the replayed signals (FR29, FR32, NFR12).
"""Would a warning have been early and reliable enough to act on?

`replay_crisis_warnings.py` answers whether an alert fired before each onset.
That is necessary and nowhere near sufficient. An operator needs to know what
the alert *means* when it fires, how often it fires for nothing, and whether the
number attached to it is a probability or a decoration.

Three questions, answered separately because they fail independently:

## 1. Calibration — is the score a probability?

C9 emits `csrs` in [0, 1] and `alert_level` from two provisional constants. It is
documented as uncalibrated pending FR30, and this script measures *how*
uncalibrated rather than repeating the disclaimer. The reliability test bins the
score and compares each bin's mean score against the realised frequency of a
crisis day in that bin, reporting:

* **Brier score** against the FR32 crisis label, with the base-rate Brier as the
  reference. A score no better than the base rate carries no probabilistic
  information at all.
* **ECE** (expected calibration error), the occupancy-weighted mean gap between
  bin mean score and bin realised frequency. A calibrated score has ECE ~ 0.
* The full reliability table, because a single summary hides whether the
  miscalibration is a uniform shift or a sign error.

**The label is the contemporaneous FR32 crisis window `[onset, onset+30]`.** So
calibration here is about detection, not warning. A score well calibrated for
"is today a crisis day" still says nothing about tomorrow.

## 2. Precision and recall — what fraction of alerts are real?

Reported at both resolutions, because they answer different questions and the
day-level number flatters a persistent signal:

* **day level** — of the days flagged, how many are crisis days.
* **episode level** — of the distinct alert episodes (rising edges), how many
  land in a crisis window. This is the operator's number: an alert that stands
  for 40 days is one decision, not 40.

## 3. Actionability — could a decision have been taken?

Alert-episode duration, the share of calendar time under alert, and the mean
number of false alarms between true ones. A signal that alerts a third of the
time is not a warning system, whatever its AUC.

**No economic claim is made or computable here.** Drawdown avoided, hedge cost
and realised risk reduction need a position model, an execution assumption and a
cost model, none of which exist in this repository. FR46's playbook is a separate
piece of work and nothing in this output supports a profit or loss statement.

Run:
  python scripts/replay_operational_value.py --out docs/evidence/replay
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

import replay_crisis_warnings as R  # noqa: E402
from seraph.validation.epochs import CRISIS_WINDOW_DAYS, EPOCH_BREAKS  # noqa: E402

N_BINS = 10


def crisis_label(dates: list[str]) -> np.ndarray:
    """FR32's contemporaneous crisis window: `[onset, onset+30]` trading days."""
    y = np.zeros(len(dates), dtype=bool)
    for onset, _ in EPOCH_BREAKS.values():
        at = [i for i, d in enumerate(dates) if d >= onset]
        if not at:
            continue
        s = at[0]
        y[s:min(len(dates), s + CRISIS_WINDOW_DAYS)] = True
    return y


def reliability(vals: np.ndarray, y: np.ndarray, ok: np.ndarray,
                n_bins: int = N_BINS) -> dict:
    """Brier, ECE and the reliability table over equal-width score bins.

    Only days with a finite score AND an assessable threshold are included, so
    the warm-up period cannot dilute the base rate.
    """
    m = ok & np.isfinite(vals)
    v, yy = vals[m], y[m].astype(float)
    if v.size < 100:
        return {"error": f"only {v.size} usable days"}
    base = float(yy.mean())
    brier = float(np.mean((v - yy) ** 2))
    brier_base = float(np.mean((base - yy) ** 2))
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    rows, ece = [], 0.0
    for b in range(n_bins):
        lo, hi = edges[b], edges[b + 1]
        sel = (v >= lo) & (v < hi) if b < n_bins - 1 else (v >= lo) & (v <= hi)
        n = int(sel.sum())
        if not n:
            rows.append({"bin": f"[{lo:.1f},{hi:.1f})", "n": 0})
            continue
        mean_score = float(v[sel].mean())
        freq = float(yy[sel].mean())
        ece += (n / v.size) * abs(mean_score - freq)
        rows.append({"bin": f"[{lo:.1f},{hi:.1f})", "n": n,
                     "mean_score": round(mean_score, 4),
                     "realised_crisis_freq": round(freq, 4),
                     "gap": round(mean_score - freq, 4)})
    return {
        "usable_days": int(v.size),
        "crisis_base_rate": round(base, 4),
        "brier": round(brier, 5),
        "brier_at_base_rate": round(brier_base, 5),
        "brier_skill_score": round(1.0 - brier / brier_base, 4),
        "ece": round(ece, 4),
        "table": rows,
    }


def episodes(flags: np.ndarray) -> list[tuple[int, int]]:
    """Contiguous alert runs as (start, end_inclusive)."""
    out, i, n = [], 0, flags.size
    while i < n:
        if flags[i]:
            j = i
            while j + 1 < n and flags[j + 1]:
                j += 1
            out.append((i, j))
            i = j + 1
        else:
            i += 1
    return out


def precision_recall(flags: np.ndarray, y: np.ndarray, ok: np.ndarray) -> dict:
    m = ok
    f, yy = flags & m, y & m
    tp = int((f & yy).sum()); fp = int((f & ~yy).sum())
    fn = int((~f & yy).sum()); tn = int((~f & ~yy).sum())
    prec = tp / (tp + fp) if (tp + fp) else None
    rec = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * prec * rec / (prec + rec)) if (prec and rec) else None

    eps = [(a, b) for a, b in episodes(flags) if m[a]]
    hit = [e for e in eps if y[e[0]:e[1] + 1].any()]
    durs = [b - a + 1 for a, b in eps]
    return {
        "day_level": {
            "tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "precision": round(prec, 4) if prec is not None else None,
            "recall": round(rec, 4) if rec is not None else None,
            "f1": round(f1, 4) if f1 is not None else None,
        },
        "episode_level": {
            "n_episodes": len(eps),
            "n_hitting_a_crisis_window": len(hit),
            "precision": (round(len(hit) / len(eps), 4) if eps else None),
            "median_duration_days": (int(np.median(durs)) if durs else None),
            "max_duration_days": (int(max(durs)) if durs else None),
        },
        "share_of_assessable_days_under_alert": (
            round(float(f.sum() / max(1, m.sum())), 4)),
    }


def actionability(flags: np.ndarray, y: np.ndarray, ok: np.ndarray,
                  dates: list[str]) -> dict:
    eps = [(a, b) for a, b in episodes(flags) if ok[a]]
    hit = [e for e in eps if y[e[0]:e[1] + 1].any()]
    miss = [e for e in eps if not y[e[0]:e[1] + 1].any()]
    span_y = max(1e-9, (int(dates[-1][:4]) - int(dates[0][:4])
                        + (int(dates[-1][5:7]) - int(dates[0][5:7])) / 12.0))
    return {
        "alert_episodes_per_year": round(len(eps) / span_y, 3),
        "false_alarm_episodes_per_year": round(len(miss) / span_y, 3),
        "false_alarms_per_true_alarm": (round(len(miss) / len(hit), 2)
                                        if hit else None),
        "n_true_alarm_episodes": len(hit),
        "span_years": round(span_y, 2),
    }


async def main(out_dir: str) -> int:
    signals = await R.build_signals()
    grid = signals["CSRS[rmt]"][0]
    y_full = crisis_label(grid)
    print(f"\n[op] FR32 crisis label: {int(y_full.sum())} crisis days of "
          f"{len(grid):,} ({100*y_full.mean():.2f}%), "
          f"window = [onset, onset+{CRISIS_WINDOW_DAYS}]")
    print(f"[op] calibration is measured against the CONTEMPORANEOUS label — "
          f"it says nothing about advance warning\n", flush=True)

    report = {
        "generated_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "crisis_label": {
            "definition": f"[onset, onset+{CRISIS_WINDOW_DAYS}] trading days, FR32",
            "crisis_days": int(y_full.sum()), "total_days": len(grid),
            "base_rate": round(float(y_full.mean()), 4),
        },
        "economic_claim": ("NONE. No position model, execution assumption or "
                           "cost model exists in this repository, so no "
                           "drawdown-avoided or risk-reduction figure is "
                           "computable and none is stated."),
        "signals": {},
    }

    hdr = (f"{'signal':<24}{'brier':>8}{'BSS':>8}{'ECE':>7}"
           f"{'ep.prec':>9}{'FA/yr':>7}{'FA/TA':>7}{'%alert':>8}")
    print(hdr); print("-" * len(hdr))
    for sig, (d, v, _m) in signals.items():
        fb, ok_b = R.causal_quantile_flags(d, v, with_assessable=True)
        y = crisis_label(d)
        rel = reliability(v, y, ok_b)
        pr = precision_recall(fb, y, ok_b)
        act = actionability(fb, y, ok_b, d)
        report["signals"][sig] = {"reliability": rel, "precision_recall": pr,
                                  "actionability": act,
                                  "assessable_days": int(ok_b.sum())}
        if "error" in rel:
            print(f"{sig:<24}{rel['error']:>48}")
            continue
        ep = pr["episode_level"]["precision"]
        fatas = act["false_alarms_per_true_alarm"]
        print(f"{sig:<24}{rel['brier']:>8.4f}{rel['brier_skill_score']:>8.3f}"
              f"{rel['ece']:>7.3f}"
              f"{(f'{ep:.3f}' if ep is not None else '-'):>9}"
              f"{act['false_alarm_episodes_per_year']:>7.2f}"
              f"{(f'{fatas:.1f}' if fatas is not None else '-'):>7}"
              f"{100*pr['share_of_assessable_days_under_alert']:>7.1f}%")

    print("\nBSS = Brier skill score vs the base rate. BSS <= 0 means the score")
    print("carries no probabilistic information beyond the unconditional rate.")
    print("ECE = occupancy-weighted |mean score - realised frequency|; 0 is")
    print("calibrated. ep.prec = fraction of alert EPISODES touching a crisis")
    print("window. FA/TA = false-alarm episodes per true-alarm episode.")

    outp = Path(out_dir); outp.mkdir(parents=True, exist_ok=True)
    jp = outp / "operational_value.json"
    jp.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    print(f"\n[op] wrote {jp}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="docs/evidence/replay")
    a = ap.parse_args()
    raise SystemExit(asyncio.run(main(a.out)))
