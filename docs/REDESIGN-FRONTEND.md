# The redesigned frontend — how to run it, and what it is

**Classic is the default and is unchanged.** This is a second frontend over
the same backends, added as new files only.

## Running

```powershell
.\launch_prototype.ps1        # Classic — port 8512 — THE DEFAULT
.\launch_redesign.ps1         # Redesigned — port 8520
```

Both at once is supported and is the intended way to compare them. Start
Classic first: it owns the market jobs, the owned market runtime and the news
supervisor. The redesigned launcher starts none of those, and the app's own
`news_service.ensure_worker()` probes the OS lock and stands aside when
Classic already holds it — the screen says which of the two owns the worker.

Running the redesigned frontend **alone** and wanting the background work too:

```powershell
.\launch_redesign.ps1 -WithMarketJobs -WithLiveRuntime
```

Do not pass those while Classic is running. Nothing locks the market jobs
across processes, so two copies would write the same vintages.

Other switches: `-Port`, `-Store`, `-NewsStore`, `-LiveStore`,
`-NoNewsWorker`. An unset `-Store` leaves `SERAPH_PROTOTYPE_STORE` exactly as
the machine has it, so both frontends read the same archive.

**Returning to Classic is running `.\launch_prototype.ps1`.** There is no code
to revert and no database to restore.

## What is in it

Six screens, all built from SERAPH's actual outputs. None is a placeholder.
`docs/REDESIGN-FEATURE-PARITY.md` is the full checklist.

| Screen | What it answers |
|---|---|
| **Overview** | What is the composite risk, which pillars produced it, and what does it touch |
| **Risk console** | The original instrument panel, embedded: risk map/globe, signal feed, pillars, exposure, forecasts, tools and method — plus the FR49 action journal and the shock/policy simulators |
| **Forecast & early warning** | What does the engine predict, is there a warning, and has it ever been right |
| **News intelligence** | What is happening in the news, and which documented exposure routes does it touch (F2 — never an input to the CSRS) |
| **Workspace** | Portfolios, scenarios and regulator cases — durable state scoped to a decision |
| **Evaluation** | What has this instrument been shown to do (FR35 ablation, read-only) |
| **Health** | What is stale, what is broken, who is fetching, did the daily jobs run |

**Superseded by the console-native rework (2026-10-25).** These six screens
are no longer a Streamlit shell with the console embedded in it: the console
*is* the application, and the screens above are entries in its own thirteen-item
navigation. `Overview` sits second, after `Risk map`, because it is the screen
a reader reaches for once they have the globe. There is no left rail and no
sidebar. See `docs/AMENDMENT-10-console-native-frontend-verification.md`.

The Overview, in reading order:

1. **Top bar** — page identity, what is selected, and the freshness/mode
   statement (the publication gate's own headline, the observed timestamp,
   the market state, the forecast's as-of).
2. **Composite dial + market-state history.** The dial is the CSRS with the
   FR29 interval as a separate arc. The history is the FR41 overlay on two
   independent axes.
3. **Three pillar cards** — Hawkes lavender, RMT cyan, Hamilton amber, from
   one colour table keyed by `PILLAR_ORDER`.
4. **Pillar readings** — signed Shapley contributions on a symmetric axis in
   score units, beside D2 effective weights drawn as shares.
5. **Measured sector activity, holdings, market flow.**
6. **Decision timeline.**
7. **Channel separation** — F1 market pillars against F2 news intelligence.

## Structure

```
seraph/dashboard/redesign/
├── __init__.py       version marker
├── tokens.py         colours, radii, type — PILLAR_COLOUR is a contract
├── theme.py          the one scoped stylesheet (all rules .rd-* or :root)
├── components.py     panel / card / chip / table / unavailable / pillar_card
├── instruments.py    pure SVG: composite_dial, contribution_tracks,
│                     weight_tracks, timeline
├── charts.py         Altair: market_state_history, forecast_against_threshold
├── data.py           the read adapter over the EXISTING backends
├── overview.py       the OVERVIEW screen
└── app.py            the Streamlit entry point
launch_redesign.ps1
tests/test_redesign_overview.py
```

**No new pipeline and no second engine.** Every number comes from a call
Classic already makes: `console_backend.project_run`,
`current_reader.read_current`, `console_backend.prediction_surface`,
`console_backend.health_surface`, and `prototype_app.store_paths` — the last
imported rather than reimplemented, so the two frontends cannot drift about
where the stores are.

**The dependency runs one way.** `redesign` → `console_backend` /
`current_reader` / `gateway` / `prototype_app.store_paths`. Nothing Classic
loads imports this package; `test_no_classic_module_imports_the_redesign`
asserts it structurally.

**No global CSS.** Every rule in `theme.py` is a `:root` custom property, an
`.rd-*` class, or a Streamlit structural selector. Classic runs in a different
process and never loads it.

## The honesty rules this screen is written against

They are not style preferences — each is a thing the layout would otherwise
invite, and each has a test in `tests/test_redesign_overview.py`.

1. **An unavailable composite keeps the dial and fills none of it.**
   `instruments.composite_dial` has no branch that substitutes zero. The
   centre is an em dash under `UNAVAILABLE`, and the reason is rendered
   beside it.
2. **Declared absences stay absences.** Hamilton's
   `score_eligible: false` renders as "DECLARED NOT SCORED" with the engine's
   own reason. A declared absence is an `Ok` emission carrying a reason, not
   an error, and never a 0.
3. **No arc without a named quantity.** With no confidence interval in the
   payload, no interval arc is drawn. Every arc is in the legend.
4. **Signed contributions are not shares.** Shapley values sum to the CSRS,
   not to 1, so they are drawn on a symmetric axis in score units and the
   panel says they do not sum to 100%. The one widget that draws shares —
   `weight_tracks` — draws D2 effective weights, which are normalised by
   construction, and says so.
5. **0 by construction ≠ 0 by measurement.** A pillar the D2 mask excluded
   gets an empty dashed track; its Shapley is exactly 0 because it was not
   consulted. A real but tiny contribution gets a hairline bar instead, so the
   two never share a shape.
6. **Withheld ≠ not emitted.** At `retail`, `gateway.ROLE_FIELDS` omits
   `pillarScores`, so the field is absent from the payload. The card says
   "withheld at this role" — calling it "not emitted" would be a false
   statement about the model. The flag is derived from `ROLE_FIELDS` so the
   two cannot drift.
7. **Missing values stay missing.** A session with no CSRS breaks the chart
   line and draws a hollow tick on the timeline; it is never interpolated,
   dropped or zero-filled.
8. **Two units never share an axis.** The FR41 overlay resolves its y scale
   independently and names both units.
9. **Every absence carries a reason.** `components.unavailable` is the one
   way this frontend claims absence, and an absence with no reason reports
   *that* on screen as a defect.
10. **F2 does not enter F1.** The overview module imports no news payload
    builder; the separation is stated on screen and asserted structurally.

## Screens beyond the Overview

**Forecast & early warning** separates *measured* (observations), *predicted*
(one model's probability) and *warning* (a policy decision against a
calibrated threshold), because running them together is how a research
instrument starts sounding like an oracle. It adds a calibration chart —
predicted against realised frequency with the perfect-calibration diagonal —
which is the honest substitute for an interval this model does not yield.
Empty reliability bins are dropped rather than plotted at zero.

**News intelligence** is F2 and uses its own palette. The pillar colours are
reserved for measured market pillars, so a documented exposure route can
never be mistaken at a glance for a measured Hawkes edge. Two clocks,
`current_news` and `historical_decision`, are chosen and never swapped.

**Workspace** drives `console_backend.dispatch` with the same event shape the
regression suite already covers. No second permission table, no second
persistence path: `WORKFLOW_ROLES` in the backend decides who may invoke
what, and a refused operation renders as a readable result rather than
replacing the page.

**Evaluation** is read-only in two specific places — no commit control (D5(d)
makes committing a pre-registered design a person's act) and no run control
(a full ablation on page render would make every refresh a cliff).

**Health** merges Classic's HEALTH, NEWS ACQUISITION and MARKET JOBS panels.
Nothing maps silence to health: a check with no data reads `never_run` or
`never_succeeded`, never `ok`.

**Risk console** embeds the existing custom component rather than
reimplementing it. Several workflows live only there — the FR49 regulator
action journal, the pillar shock simulator, the counterfactual policy
simulator, ad-hoc portfolio coverage from pasted holdings, and the news role
actions — and a second implementation of them would be exactly the
duplication this package avoids. It is declared against the same
`console_component/` directory, fed the same `project_run` payload, and
driven through the same `dispatch` and `_news_action`. It therefore keeps its
own visual language inside its frame, because it *is* the original
instrument; the screen says so rather than disguising it.

Its F2 news layer is **opt-in**, for a measured reason: the branch takes about
50 seconds to build on a store holding 2,100+ eligible events, against 0.2
seconds without it, because the aggregates describe every eligible event by
design so that a documented exposure cannot disappear by being on another
page. With the layer off the console opens immediately and its news surfaces
read NOT CONNECTED — true of that view, and said as such rather than implying
the channel is unavailable. The cached branch is not dropped when the
component's 30-second timer asks for a re-projection: clearing it there would
leave the console rebuilding something it never finishes before the next
tick, so the cache TTL is the re-projection interval instead, and a test pins
it to the timer read out of `bridge.js`.

## A Classic defect found while building this — now fixed

`build_news_payload()` returns `surfaces`, never `channel`. Classic's
`news_only_panel()` read `payload['channel']` and so reported zero events and
zero sources however full the store was — measured against the live store,
2,000+ eligible events across 21 feeds. That branch is only reachable when no
archive store exists, which is why it had gone unnoticed.

The session that owns `prototype_app.py` has since fixed it, and the contract
is now pinned from both sides: `test_news_adapter_reads_surfaces_not_a_channel_key`
here, and `test_the_payload_has_no_channel_key_and_counts_live_on_surfaces` in
`tests/test_news06_overlays.py`. Nothing in this package writes to Classic;
the fix was made by its owner.

## Live polling and the sector basis

The live panel polls `revision()` every `LIVE_POLL_SECONDS` inside a Streamlit
**fragment**, so it reruns itself and not the page. That distinction is the
whole point: Classic declares the same constant but never uses it, because
rebuilding the page when the revision moves would silently rebase a half-typed
form and lose it. A fragment refreshes the reading without that cost. With
nothing committed the dial keeps its track and fills none of it — polling an
absence more often does not make it a number.

The FR14 sector analysis basis is a choice, decision-time by default. The
retrospective archive answers a different question — what was measured later —
and the engine's own note travels with it: it does not change the historical
score and does not prove advance warning. Its cutoff is always later than the
decision, never backdated onto it, and the basis is part of the cached
decision's scope so one basis's payload can never be served for the other.

## Evidence

- `docs/evidence/frontend-baseline-2026-10-24/` — the Classic baseline:
  the frontend files copied, the revision, the uncommitted diff, launch
  instructions, and four annotated screenshots.
- `docs/evidence/redesign-overview-2026-10-24/` — the redesigned Overview in
  its institutional, retail-withheld and live-unavailable states, plus
  Classic re-rendered on 8512 while the redesign ran on 8520.
- `docs/evidence/redesign-complete-2026-10-25/` — the five further screens,
  including the portfolio and regulator case created end-to-end through the
  real backend.
