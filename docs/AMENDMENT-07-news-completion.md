# Amendment 07 — news feature completion

19 October 2026. Implementation, not an audit. This records what was built
against the seven-part completion brief, what it was verified with, and what
is genuinely blocked.

Reconciled against, not taken on trust: [the full audit](NEWS-FULL-AUDIT-2026-10-18.md),
[the academic-freeze assessment](NEWS-ACADEMIC-FREEZE-ASSESSMENT-2026-10-18.md)
and [Amendment 06](AMENDMENT-06-news-audit-remediation.md). Hawkes, RMT,
Hamilton and the preregistered evaluation are untouched. Nothing was
committed.

**Canonical launch command — there is no separate news command:**

```powershell
.\launch_prototype.ps1
```

---

## 1. Requirement by requirement

| # | Requirement | State | Where |
|---|---|---|---|
| 1 | Ordinary and IDE launches both start frontend + one supervised worker | **Done** | `news_service.py`, `launch_prototype.ps1`, `.claude/launch.json` |
| 1 | Current news fetched promptly; backfill does not block startup | **Done** | backfill moved into the loop after pass 1 |
| 1 | Startup acquisition progress and per-source outcomes visible | **Done** | NEWS ACQUISITION panel |
| 1 | Tabs and reruns do not spawn duplicates | **Done** | process-wide memo + OS lock |
| 1 | Shutdown manages only owned processes; no orphans | **Done** | `--owner-pid`, tree stop; rehearsal ends with 0 |
| 2 | A failing source does not terminate a healthy worker | **Done** | `degraded` state; supervisor reads `ALIVE_STATUSES` |
| 2 | Failed sources stay visibly degraded and retry | **Done** | source health, per-source panel |
| 2 | Crashes, missing progress, exceeded deadlines still recover | **Done** | 3 consecutive job failures exit; deadline/stall checks kept |
| 3 | Obtain permitted substantive document text | **Done** | govinfo route; 40/40 retrieved, median 16.7 KB |
| 3 | Extract stage, jurisdiction, dates, scope, rates, exceptions, relationships | **Mostly done** | instrument ids now on 40/40; rates present but never as an old→new pair |
| 3 | Preserve evidence, text scope, provenance, uncertainty | **Done** | `text_scope`, representation hashes, manifest |
| 4 | Add reliable sources closing concrete gaps | **Partly** | `federal_register_ita` added and verified by acquisition |
| 4 | DGFT/CBIC or suitable alternatives | **Blocked** | 403 / SSL failures; not worked around |
| 4 | Expand exposure mappings | **Not done** | would require inventing sectors without evidence |
| 5 | Retail portfolio relevance, unmapped holdings, weight ≠ loss | **Done** (pre-existing, re-verified) | browser |
| 5 | Institutional document comparison | **Done** | `comparison.py`, COMPARE INSTRUMENTS |
| 5 | Product–country exposure matrix | **Done** | `product_country_matrix`, rendered |
| 5 | Scenario inputs/results with assumptions and unavailable reasons | **Done** | `workflows.run_scenario`, CONDITIONAL SCENARIO |
| 5 | Export of displayed analysis with evidence and limitations | **Done** | `export_analysis`, EXPORT ANALYSIS |
| 5 | Regulator accept/reject review persisting reviewer, reason, time | **Done** | `review_instrument_link`, INSTRUMENT LINK REVIEW |
| 5 | Demo identity distinguished from authenticated identity | **Done** | `demo-role:<role>`, `authenticated: false` |
| 6 | Scenario usable end to end on a real instrument | **Path done, evidence blocked** | refuses with named reasons on all 22 routes |
| 7 | Events reach feed, sectors, roles, globe, evidence links | **Done** | rehearsal: 7 markers, 1 arc, signals populated |

## 2. Defects found and fixed while building

Four, none of which were in the prior reports:

1. **A partial source outage killed acquisition.** `work()` raised on any
   failed source, the loop wrote heartbeat `failed`, and the supervisor
   terminated its own healthy child — a recurring publisher error could
   exhaust the restart budget and stop every good feed. *This was
   introduced by Amendment 06's A09 fix.* The freeze assessment found it;
   this closes it with `degraded` as an alive state.
2. **Catch-up killed the worker on a real roster.** The historical
   backfill ran under the same 300-second deadline as the startup poll;
   on 19 sources that deadline expired, `worker_state` reported `stalled`,
   and the supervisor replaced a working process. Backfill now runs after
   the first steady pass with its own deadline.
3. **Registration outran the first heartbeat.** `register()` contacts
   unregistered sources before the worker beat; with unreachable hosts
   that took minutes, during which the store still held the previous run's
   `stopped` row, so the supervisor killed the new worker. The worker now
   beats first, with a declared deadline.
4. **The console reported refusals as successes.** The status bar tested
   `answered` before `error`, and a refusal carries the same
   `context.request_id` as a success — so a failed operation displayed
   "DONE" with an empty detail. Found because it hid a fifth defect: the
   dashboard passed an open `NewsStore` where a path was expected, which
   broke every role action **and the console's own acquisition button**.

## 3. Verification

Evidence: `docs/evidence/news-intelligence/news-completion-2026-10-19/`.

**End-to-end rehearsal through the ordinary launcher** (`rehearsal/`),
seven steps as specified:

| Step | Result |
|---|---|
| 1 no separate news command | `streamlit run prototype_app.py` only |
| 2 startup acquisition and heartbeat visible | 4 processes; `catching_up` → `running` |
| 3 two worker passes complete | sequence 2, state `running` |
| 4 manual acquisition truthful | 5 fetched, 13 unchanged, 0 failed, 1 timed out, 0 skipped; 938 → 1186 stories |
| 5 one source fails, healthy acquisition continues | worker `degraded` and alive; **18 healthy sources still covered** |
| 6 evidence reaches frontend and globe | 7 markers, 1 arc, signals populated |
| 7 shutdown leaves nothing | 0 news processes |

**Browser, driving the new controls** (`browser-workflows/`, via the new
`scripts/verify_news_workflows_browser.py`): matrix rendered, scenario form
and export present and both returning `DONE`, the result rendered with its
limitations, the review queue present with 100 controls, a decision refused
without a reason, accepted with one, and **recorded in the store** as
`demo-role:regulator` / `authenticated: false`.

**Other evidence in the same directory:** `source-reachability.json`,
`new-source-acquisition.json` (40 documents, 6 routed),
`document-depth.json` (40/40 retrieved, median 16.7 KB),
`partial-failure-result.json` (0 restarts on a partial outage; 2 on a
stopped worker), `role-workflows.json`, `scenario-on-real-data.json`.

**Tests.** 846 passing across the news, role, dashboard, operations and
globe selection; both JavaScript harnesses clean. New files:
`test_news_source_failure_isolation.py`, `test_news_unified_startup.py`,
`test_news_role_workflows.py`, plus document-depth cases added to
`test_news_completion_2026_10_18.py`.

Three pre-existing tests were re-pointed, each because the behaviour they
asserted deliberately changed; all three now assert the property at the
place it actually lives rather than a mechanism that moved. One of them
had been passing on a word inside a COMMENT.

## 4. Genuinely blocked, with causes

* **Indian trade instruments (DGFT, CBIC), statistics (MOSPI), weather
  (IMD), gazette, grid.** HTTP 403 and SSL certificate verification
  failures. Certificate verification was not disabled and no access
  control was bypassed. Probed and recorded.
* **A real priceable scenario.** No instrument currently held states an
  old→new ad-valorem rate pair, even in the full retrieved notices;
  determinations state dumping margins. The computation path is complete
  and exercised; the evidence is not available. Supplying `old_rate = 0`
  to fill the panel was refused as an invented input.
* **Balanced exposure coverage.** Six issuers still have no sector.
  Assigning one requires evidence this work did not have, so none was
  invented and the consequence stays visible as an unmapped holding.

## 5. What this does not claim

The independent 600-document extraction benchmark, the 150-case impact
benchmark, two independent human reviewers and the prospective shadow
operation remain unpassed and untouched. No threshold was relaxed. A few
checked examples support a demonstration; they are not a general accuracy
claim. Nothing here is a measured outcome, a loss, or a probability of
loss.
