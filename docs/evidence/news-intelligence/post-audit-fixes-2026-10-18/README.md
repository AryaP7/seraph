# Post-fix re-run of the 18 October 2026 news audit probes

The audit's own counterexample scripts, re-run against the remediated code.
See `docs/AMENDMENT-06-news-audit-remediation.md` for what changed and why.

`../full-audit-2026-10-18/` is the audit's original evidence and is **not**
modified by anything here.

| File | What it is |
|---|---|
| `probes.py` | A copy of the audit's `probes.py`. Identical except for one addition: a `linked_repeal` case exercising A11 where the two documents DO cite a shared case number, and where a reviewer supplies the link the documents lack. |
| `findings.json` | Its output. |
| `semantic_probes.py` | The audit's `semantic_probes.py`, unchanged. |
| `semantic-findings.json` | Its output. |

Both scripts read the production store read-only and write only into this
directory, exactly as the originals did.

## What the re-run shows

| Audit case | Original finding | Now |
|---|---|---|
| A01 `class_recall_negative_inflation` | 95% recall on 0/5 supported events found | `class_recall` **0.0**; the 95 negatives score as `negative_specificity` |
| A02 `future_named_month` | `effective_at=null`, `in_force=true` | `2026-12-01T00:00:00+05:30`, stage `adopted`, `decided_not_yet_in_force` |
| A03 `body_exemption` | adverse Indian steel route at medium confidence | **no impacts**; the frame records the named exclusion |
| A04 `denial_in_body` | a confirmed halt with targets, plus a separate denial | **one** event, `denied`, no impacts |
| A05 `repeated_claim_in_body` | two events, repeated estimates | **one** event, keeping the facility named in the repeated sentence |
| A06 `hindi_syndication_collision` | one key for two unrelated headlines | two distinct keys |
| A07 `reverted_document` | B left current after A → B → A | **A** current, recorded as a reversion |
| A08 `document_budget_starvation` | the first URL fetched on every pass; the second never got a body | two calls, **both** documents have bodies |
| A09 `abandoned_job_lease` | zero fetches while the worker reported `running` | zero fetches and the worker reports `failed` / `lock_unavailable`; a provably dead holder is reconciled and the replacement polls |
| A10 `strict_replay_future_operational_data` | a 10:00 heartbeat at an 08:00 replay, age −120 min; a gap observed at 10:00 | `unavailable_at_decision_time`, no age, no gap |
| A11 `unlinked_repeal` | `supersedes=null`, old order silently in force | still unlinked — a similar title is not evidence — but now a **named unresolved-link warning**. `linked_repeal` shows the same pair superseded when a case number is shared, and when a reviewer confirms the link |

A11's unlinked case is the one where the correct output is still "not linked".
The fix is that the consequence — an earlier order left in force — is now
stated as review work instead of being a silent property of the data.

## Browser verification (19 October 2026)

The payload gained fields during remediation (`manifest`, `supersession`,
`corroboration`, per-reference `display_permitted`), so the audit's browser
evidence no longer describes the payload being rendered. Both of the
project's browser scripts were re-run against it, unchanged, plus one new
check for the surface neither of them opens.

| Run | Script | Result |
|---|---|---|
| `browser/` | `scripts/verify_news_browser.py` | 6 globe markers, 1 arc, 2 evidence links, auto-refresh advanced `plan.asOf`, 409 snapshots persisted |
| `browser-roles/` | `scripts/verify_news_roles_browser.py` | all three roles render, portfolio submission accepted, unmapped-holding warning shown, 6 markers, 2 evidence links |
| `browser-method/` | ad-hoc CDP check | the METHOD panel, which neither script opens |

Both scripts work on isolated SQLite copies and drive the ordinary Streamlit
component protocol with no payload injection. The audit's own
`ordinary-flow.json` / `ordinary-flow.png` / `browser-app.log` one directory
up were preserved and restored; this run's copies live in `browser/`.

**What the browser confirmed that the tests could not.**

* The METHOD panel's stale constant is gone. It now reads: *Connected:
  signals, sector_stress, geography, assets · 2/17 feed(s) within their
  declared freshness policy · 0/17 source rights reviewed per use ·
  reconstruction with event-rules/2.1*.
* The regulator panel carries the A11 review queue — `linked: 2` and 18
  unresolved-link warnings, each naming the document and stating that the
  earlier order is still reported as in force — alongside the new `rights`
  and `retention` items.
* No "withheld", "Unavailable", "undefined" or "NaN" anywhere in the
  rendered role panels; no `role news view unavailable`, so no role
  projection threw.

**One defect this found, in the remediation itself.** `newsConnectionLine()`
read `news.manifest`, but `console_backend.news_branch()` forwards an
explicit allow-list and `manifest` was not on it, so that clause could never
render. Fixed by naming `manifest` in the allow-list — the method panel is
exactly where a reader asks what produced the numbers.

**Not covered by any of this.** The institutional panel reports *0 route(s)
carry an accounting scenario* on the pilot corpus: the production caller is
wired and exercised, and all 23 routes refuse, because no stored document
states both duty levels. The refusals render with their reasons. The retail
weight formatter is likewise unexercised in the browser — the submitted
holdings carry no `exposurePct` — and is covered only by a source assertion
and a direct check of the function.
