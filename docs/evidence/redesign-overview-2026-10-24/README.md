# Redesigned OVERVIEW — evidence, 2026-10-24

Captured from `seraph/dashboard/redesign/app.py` on port 8520, viewport
1680×1150, dark scheme, with `SERAPH_NEWS_WORKER=0` so the capture started no
network acquisition. Classic was running on 8512 at the same time.

Archive selection throughout: run `37bccf32974201f0…`, decision
`2020-04-30T15:30:00+05:30`, store `prototype_runs/fix01-covid-window.sqlite`
(resolved from the machine's `SERAPH_PROTOTYPE_STORE`).

| File | Shows | The honesty rule it evidences |
|---|---|---|
| `redesign-01-overview-top-institutional.jpg` | Top bar with basis / role / "NOT A CURRENT MARKET READING" / observed / market state / forecast as-of. Dial at CSRS 0.990 with the FR29 interval arc. FR41 overlay on two axes. | Publication-gate verdict passed through verbatim; two units never share an axis |
| `redesign-08-dial-closeup.jpg` | The dial at reading size: 0–1 scale ticks, `RED` alert, legend naming the point estimate, the FR29 interval and the unfilled scale | Every arc corresponds to a quantity the payload carries |
| `redesign-02-pillars.jpg` | Hawkes 0.1054 (lavender, "excluded from the composite (D2 mask: excluded)"), RMT 0.2415 (cyan, "entered the composite"), Hamilton "DECLARED NOT SCORED" (amber) with its reason and origin | A declared absence is never rendered as zero; one pillar colour table everywhere |
| `redesign-03-breakdown-sectors.jpg` | Contribution tracks — RMT `+0.9899 CSRS score units` filled, Hawkes and Hamilton dashed and `· excluded by mask`. D2 effective weights drawn as shares summing to 1.000. Sector / holdings / flow absences with reasons | Signed contributions are not percentages; 0-by-construction is not 0-by-measurement; weights may be shares and the panel says why |
| `redesign-07-pillar-detail-chart.jpg` | Pillar readings bar chart: hawkes and rmt drawn, **hamilton not drawn** and named — "not drawn, because no value was reported: hamilton" | A missing value stays missing; it is not plotted at zero |
| `redesign-04-timeline-separation.jpg` | Decision timeline across all 81 dates with the selected decision marked and a full legend; channel-separation panel with `F07 directed network PENDING` | A scoreless session is hollow, not zero; F2 never enters F1; F07 still displays as pending |
| `redesign-05-current-unavailable.jpg` | Basis switched to **Current — live runtime**: dial keeps its track and fills none of it, centre reads `—` under `UNAVAILABLE`, "NO COMPOSITE SCORE" with the runtime's own reason, worker health as a separate card, "NO CURRENT HISTORY", "NO PILLAR READINGS — this is an absence of input, not three readings of zero" | **The central rule**: an unavailable composite is never a zero, and Current does not fall back to the archive replay |
| `redesign-09-unfilled-dial-closeup.jpg` | The unfilled dial at reading size — the full 0–1 track drawn, nothing filled over it, `—` and `UNAVAILABLE` in the centre, `basis: live · no fallback to an archive run` beneath | The dial's geometry is identical whether or not there is a number; what differs is that none of it is filled |
| `redesign-06-retail-withheld.jpg` | The same decision at `retail`: the dial still renders (retail may see the CSRS), while the pillar cards read "withheld at this role" citing `gateway.ROLE_FIELDS` | Withheld by the transport boundary is not the same claim as "not emitted" |
| `redesign-10-gap-screen.jpg` | The `Evaluation` entry in the left rail: "SCREEN NOT IMPLEMENTED — this screen exists in the Classic console and has not been rebuilt here. It is listed as an open gap in docs/REDESIGN-FEATURE-PARITY.md, not quietly dropped" | A Classic feature that is not ported says so and points at Classic, rather than rendering a hollow imitation |
| `classic-regression-after-redesign.jpg` | **Classic** on port 8512, re-rendered while the redesign ran on 8520 | Matches `../frontend-baseline-2026-10-24/screenshots/classic-01-prediction-top.jpg`; no restyling leaked and Classic is unchanged |

## Reproducing

```powershell
.\launch_prototype.ps1        # Classic, 8512
.\launch_redesign.ps1         # Redesigned, 8520
```

## Checks run alongside

- `pytest tests/test_redesign_overview.py -q -p no:randomly` → 31 passed
- `python scripts/check_invariants.py` → all `[ok]`
- All seven Classic frontend files re-hashed against
  `../frontend-baseline-2026-10-24/` → byte-identical
