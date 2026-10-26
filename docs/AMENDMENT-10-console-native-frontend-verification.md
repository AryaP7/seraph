# Amendment 10 — the console-native frontend, verified end to end

**Date:** 2026-10-25
**Scope:** `seraph/dashboard/redesign/**`, `tests/test_redesign_*.py`.
No scientific model, prediction algorithm or validation standard was touched.
Classic (`launch_prototype.ps1`, port 8512) is unchanged and remains the
fallback.

This amendment records what was *measured* about the reworked frontend, and
three regressions the measurement found. It does not restate the design —
`docs/REDESIGN-FRONTEND.md` owns that.

---

## 1. The architecture that was verified

The console **is** the application. SERAPH's interface is the full-screen 3D
console component, and the redesigned screens are entries in *its* navigation
rather than a Streamlit shell wrapped around it. There is no sidebar and no
second navigation.

Thirteen nav entries, counted in the fork's own markup and in the running app:

| | | |
|---|---|---|
| RISK MAP | OVERVIEW | CONSOLE |
| SIGNAL FEED | PILLARS | EXPOSURE |
| FORECASTS | EARLY WARNING | WORKSPACE |
| EVALUATION | HEALTH | TOOLS |
| METHOD | | |

Eight are the console's own views; five (OVERVIEW, EARLY WARNING, WORKSPACE,
EVALUATION, HEALTH) are built in Python and carried in the payload as markup,
so the dial, the contribution tracks and the timeline have one implementation
rather than two.

The component is **forked** into `seraph/dashboard/redesign/console_component/`.
That is what makes the nav additions safe: Classic's own component keeps
exactly its original eight views, which `test_classic_component_has_only_its_original_views`
asserts structurally.

---

## 2. What was measured, not assumed

`tests/test_redesign_console_e2e.py` (new, 57 tests) drives the real backends
rather than reading files. It covers:

* **All thirteen views, all three roles.** Every field the eight
  console-rendered views read is present in a real `project_run` payload at
  `regulator`; the five redesigned views each render non-empty markup for
  every role.
* **Role gating as a declared decision.** The fields withheld per role are
  pinned exactly — `retail` loses `limitations`, `pillars`, `mask`,
  `predictions`, `manifest`; `institutional` loses `manifest`; `regulator`
  loses nothing. A gate that is added *or* lifted fails the test, because
  showing a retail user the model internals is as much a decision as hiding
  them.
* **Workspace, through `console_backend.dispatch`.** The portfolio round trip
  (`ws_create` → `ws_preview` → `ws_commit` → `ws_holdings`) completes for all
  three roles; scenarios (`sc_save` → `sc_list` → `sc_run`) for institutional
  and regulator; regulator cases (`case_open` → `case_evidence` →
  `case_decision`), including the assertion that attaching evidence advances
  the case version.
* **Every refusal in `WORKFLOW_ROLES`.** Parametrised off the table itself:
  each (operation, role) pair outside it must raise, and the refusal must say
  why. 39 pairs.
* **Evaluation is read-only** for every role — it emits no operations at all,
  because D5(d) makes committing a pre-registered design a person's act and a
  full ablation on page render would make every refresh a cliff.
* **Early warning keeps measured, predicted and warning apart**, and the
  prediction surface is read rather than fitted (two reads return the same
  `generated_at`).
* **The freshness gate** labels an archived decision a replay for every role,
  with `publishable_as_current` false and a checkable reason.

Writes go to a disposable store: the fixture points `SERAPH_WORKSPACE_DIR` at
`tmp_path`, so the suite adds no rows to `prototype_runs/`.

---

## 3. Three regressions the verification found, and fixed

### 3.1 A removed panel left live code behind — and it disabled the globe

`INPUT COMMODITIES` and `METEOROLOGICAL INPUTS` were removed from the fork
because nothing in SERAPH produces either. The *script that filled them* was
not removed, so `el("commod").innerHTML = ...` ran against a null node and
threw on every load:

```
Uncaught TypeError: Cannot set properties of null (setting 'innerHTML')
  at index.html:1865
```

An uncaught throw at that level stops every statement after it in the same
script. Everything below line 1865 — the signals board, the exposure board,
the asset dataset and **the globe initialisation** — therefore never ran. The
3D console, which is the whole point of this architecture, was dead on the
redesigned frontend and the failure was visible only in the browser console.

Fixed by removing the two data arrays and the two render blocks.
`test_no_script_fills_a_panel_the_fork_removed` compares the fork's `el(...)`
references against its own markup, excluding the references Classic also has,
so the next removed panel cannot repeat this.

**Confirmed by measurement, not inspection:** after the fix the globe renders,
and `#ticker` and `#signals` populate (2,436 and 78,974 characters) where
before they were empty.

### 3.2 The FABRICATED tag sat above real measured flow

`flowHTML()` has read real E14 prints since FR45/FR51 landed, and renders an
explicit reason when none is available. The `FABRICATED PREVIEW` tag that was
put there for the three invented numbers (`FII net (example) -1200` and its
two companions) outlived them, so it was stamped above real published prints
and above an honest statement of absence.

A tag that appears over true things is one a reader learns to ignore, and
that habit is the only thing protecting the panels that genuinely *are*
previews. Removed, with `test_the_flow_panel_is_not_tagged_fabricated`.

The static fallback banner was also still naming `COMMODITIES` and `WEATHER`
— two surfaces this fork no longer has. Corrected.

### 3.3 HEALTH drew a dead fetcher as a neutral chip

The news acquisition panel reported the worker as a one-word `state` chip with
no tone and dropped the worker's own `detail` and `note`. A dead fetcher is
the single most misleading thing this screen can under-report, because the
store answers every read at full depth whether or not anything is arriving —
so a news channel receiving nothing looks identical to a healthy one on every
other surface.

`owner` and `state` are now treated as the two different facts they are:
`owner` is what *this dashboard* did about starting a worker, `state` is the
store's heartbeat, which any process may have written. They can disagree, and
when they do the screen says so rather than resolving it in favour of the
cheerful one. Both cases render the worker's recorded detail.

---

## 4. The news channel is real

Measured against `prototype_runs/news-intelligence-pilot.sqlite`:

| | |
|---|---|
| sources registered | 22 |
| sources healthy at last poll | 21 of 22 |
| stories | 5,512+ |
| newest story first seen | 2026-10-25T18:14 IST, then 21:50 IST after a manual pass |
| surfaces reported connected | `signals`, `sector_stress`, `geography`, `assets` |
| surfaces reported preview | none |

With the channel attached, `preview_surfaces` is empty and the console's news
status line reads `CONNECTED: SIGNALS, SECTOR_STRESS, GEOGRAPHY, ASSETS` with
no fabricated list. The news layer is therefore **on by default** — detached,
those four surfaces fall back to the console's illustrative layer and are
correctly labelled FABRICATED, which is true of that view but is not what this
installation has.

What remains genuinely fabricated, and still tagged: the NIFTY ticker strip,
the illustrative map geography kept behind a `<details>`, and the original
design-preview exposure board.

### The acquisition worker had died, and it is not a code defect

`prototype_runs/news-worker.log`:

```
[supervisor] worker exited 3221225794; gave up after 5 restarts. Nothing is fetching
```

`3221225794` is `0xC0000142`, `STATUS_DLL_INIT_FAILED`, preceded by two plain
`exited 1`. That is process/resource exhaustion on the host, not a fault in
`run_news.py`: a hand-run `run_news.py --once` completed clean in 34 s with 61
new stories, zero failures, and `federal_register` / `federal_register_india`
both recovering from what had looked like a persistent parse error.

The host was measured at **0.9 GB free of 15.8 GB**, commit 23.4 GB of 31.8 GB.
A day-old Classic Streamlit server had accumulated 16.5 CPU-hours; the owner
approved stopping it, which returned free memory to 1.3 GB. The remaining
pressure is ordinary desktop oversubscription and is not attributable to
SERAPH.

---

## 5. The staleness banner is correct, and is not a defect

```
NOT A CURRENT MARKET READING — the newest observation is 2369.1 days old.
```

This is `SessionClock.recency` (`seraph/live/clock.py`) reporting through the
publication gate (`seraph/live/publication.py`), and it is the gate working.

The cause is **which archive is selected**, not a bug:

| archive | newest decision |
|---|---|
| `fix01-covid-window.sqlite` *(the configured default)* | 2020-04-30 |
| `fix01-full-replay.sqlite` | 2026-08-21 |

`SERAPH_PROTOTYPE_STORE` resolves to the COVID-window study, whose single
complete run spans 2020-01-01 → 2020-04-30. 2020-04-30 → 2026-10-25 is 2,369
days, exactly what the banner states. `market not_a_session` is correct
(2026-10-25 is a Sunday) and `feed: none` is correct (no authenticated Kite
session is attached).

Pointing `SERAPH_PROTOTYPE_STORE` at `fix01-full-replay.sqlite` yields a
newest decision of 2026-08-21. That is still 65 days old and still labelled
`historical_only` — correctly, because the market corpus ends there. A run
over the fresher corpus (which reaches 2026-10-19) would close most of that
gap, and is a data-pipeline task, not a frontend one.

**The default archive was deliberately left as it is.** Changing it is a
demonstration decision for the owner, not an engineering one, and the
COVID window is presumably chosen on purpose.

---

## 6. Standing items not addressed here

* `scripts/check_invariants.py` passes, with its standing informational
  finding: `kite_credentials.tokens.json` sits in the repository root. Being
  gitignored is not the same as being absent — it travels with any copy of
  this folder. `.env` likewise holds a Kite API secret in plain text. Moving
  both outside the tree and pointing `SERAPH_KITE_TOKENS` at the new location
  is the documented remedy and is the owner's call.
* `mofcom_rare_earth_18_2025` has 27 consecutive acquisition failures and is
  correctly reported `degraded` rather than silently dropped.
