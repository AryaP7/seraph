# ⚠ DEMO SCAFFOLDING — DELETE BEFORE ANY REAL USE

**Added 2026-08-24 for a presentation. Every number it produces is fabricated.**

The dashboard can be made to look like a fully working SERAPH risk engine with
all three pillars reporting. **It is not.** As of this commit the real pipeline
state is:

| Table | Rows | Status |
|---|---|---|
| `rmt_output` | 5,363 | real, validated (Pillar 2 PASS) |
| `hamilton_output` | 5,365 | real, but **smoothed / non-causal** |
| `hawkes_output` | **0** | no production writer exists |
| `reconciled_state` | **0** | C8 is never called |
| `csrs` | **0** | C9 is never called |

So the demo's CSRS, confidence interval, Shapley decomposition, full
`(True, True, True)` availability mask and trend strips **do not come from the
pipeline**. No CSRS has ever been computed from real data.

## What to delete

1. `seraph/dashboard/demo_data.py` — the whole file.
2. In `seraph/dashboard/datasource.py`: the block between
   `# --- DEMO SCAFFOLDING` and `# --- END DEMO SCAFFOLDING`, plus the
   `SERAPH_DEMO` branch at the top of `latest_state()`.
3. In `seraph/dashboard/app.py`: the block between
   `# --- DEMO SCAFFOLDING` and `# --- END DEMO SCAFFOLDING`
   (`render_sparkline`, `render_trends`), and the `if state.get("history"):`
   call inside `main()`.
4. This file.

Nothing else imports any of it. The real fetch path in `latest_state()` is
untouched, so removal cannot break production.

## Guard rails already in place

- Reachable **only** with `SERAPH_DEMO=1`. Never a fallback for a failed fetch —
  without the flag the dashboard shows an explicit "no scored output yet" gap.
- A permanent red **DEMO MODE — synthetic T0 data, not a market reading** banner
  renders while it is active.
- The trend strip keys off a `history` field the real fetch layer never returns,
  so it disappears on its own once `demo_data.py` is gone.
- The 3D geospatial stage carries its own banner: it is not wired to the
  pipeline and its tickers/markers are internal to the asset.

## Also still outstanding (unrelated to the demo)

- Pillar 3's causal behaviour is unresolved — see
  `docs/AMENDMENT-04-rmt-readout.md` for Pillar 2 and the session notes on the
  Hamilton TVTP diagnostic (decision C pending: multi-start the transition
  block, assert the nesting invariant, raise the minimum causal window).
- Do not describe SERAPH as an operational or calibrated risk engine until real
  emissions flow C5/C6/C7 → C8 → C9 end to end.
