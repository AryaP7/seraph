# SERAPH product contracts

Created 2026-10-16 (Phase 0 / `DOC01`). Defines the shared product metadata and
the news, identity, portfolio, scenario, case and UI-transport contracts.

Every section is marked **ADOPTED** (implemented and in force) or **PROPOSAL**
(design of record for a future slice, not yet binding on code). A proposal
becomes adopted only through a dated decision record in `docs/decisions/` plus
the implementing slice.

## Contract-ownership rule

`seraph/shared_types/` is the **frozen mathematical seam** (ARCHITECTURE §0/§2):
`Result`, `PillarEmission`, `ReconciledState`, `CsrsPoint`, `FusionWeights`,
`PILLAR_ORDER`, `SeraphWarning`, `SeraphError`. Product extensions are **not**
added there. They live in the owning component's own package and reuse the
existing `Ok`/`Err` and `WarningCode` conventions at established seams:

| Contract family | Owning package | State |
|---|---|---|
| Market/session calendar | `seraph/market_calendar/` | **ADOPTED** (§2) |
| Pillar input envelope (orchestration adapters) | `seraph/orchestration/` | **ADOPTED** (§3) |
| Product metadata envelope | `seraph/product_types/` | PROPOSAL (§1) |
| Identity, organisation, grants | `seraph/identity/` (new, "C14") | PROPOSAL (§4) |
| News sources, events, entities, exposure, estimates | `seraph/news/` (new, "C13") | PROPOSAL (§5) |
| Portfolio, holdings, valuation | `seraph/decision_support/` (C11) | PROPOSAL (§6) |
| Scenario identity and assumptions | `seraph/decision_support/` (C11) | PROPOSAL (§7) |
| Case workflow | `seraph/decision_support/` (C11) | PROPOSAL (§8) |
| UI transport envelope | `seraph/dashboard/` (C12) | PARTLY ADOPTED (§9) |

Any change inside `seraph/shared_types/` is confirmed with the human first
(`CLAUDE.md`). No such change has been made.

---

## 1. Shared product metadata envelope — PROPOSAL

Every product datum crossing a component or transport boundary carries:

| Field | Meaning | Required |
|---|---|---|
| `id` | Stable identifier for this entity/result, unique within its kind | yes |
| `kind` | Entity kind (`news_event`, `exposure_edge`, `holding`, `scenario`, `case`, …) | yes |
| `schema_version` | Integer version of the payload shape | yes |
| `producer` / `producer_version` | Which component and code/model version produced it | yes for `derived`/`estimate` |
| `status` | `observed` \| `derived` \| `estimate` \| `scenario` \| `preview` \| `unavailable` \| `stale` | yes |
| `absence` | When `status=unavailable`: `structural` \| `transient`, plus a reason code | when unavailable |
| `observed_at` / `effective_at` | When the fact occurred / when it takes effect | when meaningful |
| `first_received_at` | When SERAPH could first have known it — **the replay bound** | yes for externally sourced data |
| `evaluated_at` | Decision time this datum was produced for | yes |
| `revision` / `supersedes` | Revision identity and the revision it replaces | when revisable |
| `sources` | List of `{source_id, reference, content_hash, retrieved_at}` | yes for externally sourced data |
| `coverage` | What population the datum covers, and what it does not | yes for aggregates |
| `unit` | Explicit unit; never a bare number | yes for quantities |
| `uncertainty` | `{kind, value, meaning}` — what the interval actually means | yes for `estimate` |
| `limitations` | Free-text constraints that must travel with the number | optional |
| `run_id` / `model_id` / `scenario_id` | Run, model and scenario identity | when applicable |
| `owner` / `org` | Owning user and organisation scope | for private data |

Rules:

1. `unknown` is never rendered as `0`, and never as measured quiet.
2. A replay at decision time `T` may only read data with `first_received_at ≤ T`.
3. `preview` data may never be an input to any calculation.
4. Status is attached to the datum, not only to the panel.

---

## 2. Market/session calendar — ADOPTED (2026-10-16, `FIX01`)

Module: `seraph/market_calendar/sessions.py`. Owner: new shared calendar package;
read by C8's clock (as a plain mapping, no package coupling) and by the
orchestration layer.

```python
@dataclass(frozen=True)
class TradingSession:
    date: str                      # "YYYY-MM-DD"
    open: str                      # "HH:MM:SS" IST
    close: str                     # "HH:MM:SS" IST
    kind: Literal["regular", "muhurat", "special_live", "short"]
    evidence: str                  # why this session's hours are what they are
    evidence_status: Literal["declared", "verified_against_exchange_notice"]
```

- The default regular NSE equity session is `09:15:00`–`15:30:00` IST.
- `SPECIAL_SESSIONS` is an explicit registry of deviations. Each entry states
  its evidence and its `evidence_status`.
- **Every current entry is `declared`.** No official exchange calendar file has
  been ingested into this repository. Replacing the registry with ingested
  official calendar data is Phase 5 work (`DATA03` neighbourhood).

**Decision clock policies** (`decision_timestamp(date, policy)`):

| Policy | Decision time | Use |
|---|---|---|
| `session_close` (default) | the session's declared close | normal end-of-session evaluation, including an authorised special-session close |
| `standard_1530` | always `15:30:00` | "what did a desk know at the regular close?", and for auditing that the later vintage is correctly withheld |

**Safety property (the future-information guard is not weakened).** A pillar
observation whose `tau` is after the decision timestamp is **withheld** — it is
treated as not yet available, recorded as a `transient` absence with reason
`not_yet_available`, and the most recent earlier vintage is used instead. It is
never silently accepted, and it no longer aborts the replay. Consequently a
registry entry that declares a close *too early* is safe (it only withholds
information); a registry entry that declares a close *too late* is the risk the
`evidence_status` field exists to track.

## 3. Pillar input envelope — ADOPTED (2026-10-16, `FIX01`/`FIX02`)

The `originals` mapping passed to `InferenceSession.step()` is the adapter seam
between any input source (archive, fresh source DB, future live feed) and
C8/C9. It is an orchestration-owned dict contract, deliberately **not** a
`shared_types` model, because it also carries provider-specific `detail`.

| Key | Required | Meaning |
|---|---|---|
| `score_eligible` | yes | may this value enter the CSRS at this decision time |
| `value` | when eligible | the pillar quantity, finite |
| `information_timestamp` | when eligible | `tau` — when the value was actually computed, IST, explicit offset |
| `absence` | **when not eligible** | `structural` \| `transient` — declared explicitly, never inferred |
| `absence_reason` | when not eligible | `no_data_coverage` \| `estimation_failed` \| `insufficient_history` |
| `reason` | when not eligible | human-readable explanation shown in `limitations` |
| `variance` | optional | FR23 estimation variance |
| `model`, `origin`, `detail` | optional | provenance and per-pillar diagnostics |

Rules:

1. An ineligible pillar **must** declare `absence`. Omitting it raises
   `ValueError`; the adapter does not guess. Guessing `structural` was the
   `A02` defect: it dropped a temporarily-unavailable pillar out of the D2 mask.
2. `structural` means the pillar cannot exist for this period (no historical
   coverage, or a standing research-exclusion decision such as original
   Hamilton's `NOT_PRODUCTION` status). It leaves the mask (`false`).
3. `transient` means this update failed or has not arrived (feed outage,
   estimation failure, vintage not yet available). It **stays** in the mask and
   D4 age-inflation grows its uncertainty.
4. A repeated identical vintage is stale, not new information — C8 already
   rejects re-assimilation by `tau`.

## 4. Identity, organisation and grants — PROPOSAL

```
User          : user_id, provider_subject (stable OIDC sub), issuer, email?, created_at, disabled_at?
Organisation  : org_id, name, kind (retail_household | institution | regulator_body)
Membership    : (user_id, org_id), granted_at, revoked_at?
Grant         : (user_id, org_id, role in {retail, institutional, regulator}, scope, granted_by, granted_at, revoked_at?)
Session       : session_id, user_id, issued_at, expires_at, revoked_at?
ResourceACL   : (resource_kind, resource_id, org_id, owner_user_id, visibility)
```

Rules:

1. Roles are **resolved on the server** from live grants. A browser request may
   only ask to switch among grants the user already holds.
2. Role and resource scope are separate: a portfolio manager with the
   `institutional` role still cannot read another organisation's books.
   Regulator scope is an explicit grant scope, not "sees everything".
3. Every private path is checked: lists, direct reads, mutations, exports,
   cached payloads and component responses.
4. Private holdings are never embedded in a globally visible run manifest.
5. An unavailable identity provider **fails closed**. It never falls back to
   privileged demo access. Local demonstration mode is a separate, explicitly
   labelled mode.
6. Audit events record the real actor identity and organisation and preserve
   both alert time and operation time.

## 5. News subsystem — PROPOSAL

Pipeline (each stage a separate persisted contract):

```
Source → RawObservation → Story → Event → (Entity, Place, Asset) → ExposureEdge
       → ImpactEstimate → Aggregate → Overlay / role workflow
```

| Contract | Key fields |
|---|---|
| `Source` | `source_id`, provider, feed URL, topic coverage, language, rights/retention, polling policy, failure behaviour |
| `RawObservation` | `source_id`, fetched_at, `content_hash`, raw reference, cursor position, http/parse status |
| `Story` | canonical URL/content identity, publication_at, first_seen_at, update_at, correction_of?, syndication_group |
| `Event` | event_type, actors, action, quantities+units, occurrence_at, policy_effective_at, lifecycle (`active`/`developing`/`resolved`/`superseded`/`retracted`), evidence spans |
| `Entity`/`Place`/`Asset` | stable issuer/security IDs, parent/subsidiary/operator links, facility location, versioned sector + geographic taxonomy, validity dates |
| `ExposureEdge` | from→to, mechanism (revenue, import, export, input, logistics, supplier), magnitude + unit, validity dates, confidence, evidence |
| `ImpactEstimate` | **separate** `evidence_confidence`, `severity`, `exposure_magnitude`, `direction`, `horizon`, `mechanism`; method id + version; reproducible |
| `Aggregate` | roll-up with path deduplication; `unknown` distinct from measured quiet |

Rules:

1. Publication, first-seen, correction, occurrence and policy-effective times
   are five distinct fields. Replay at `T` sees only `first_seen_at ≤ T`.
2. Ten syndicated copies are one confirmation, not ten, and never ten times the
   estimated stress. Overlapping graph paths do not multiply exposure.
3. Sentiment is never used as a calibrated financial-loss percentage. A loss
   probability requires a declared, calibrated target.
4. Article text is **untrusted input**. It cannot issue application commands,
   change grants or write regulator actions. A language model used for
   extraction requires schema validation, evidence references, versioned
   prompts/models, an evaluation set and explicit abstention.
5. News sector stress and Hawkes sector stress are different series with
   different units, coverage and uncertainty, and are never merged.

## 6. Portfolio — PROPOSAL

```
Portfolio      : portfolio_id, owner_user_id, org_id, name, base_currency, asset_scope
Account        : account_id, portfolio_id, custodian?, kind
HoldingSnapshot: (portfolio_id, effective_at), rows[], import_id, valuation_at?
HoldingRow     : instrument_ref (symbol/ISIN), resolved_security_id?, quantity?, value?, currency, cash_flag, source_row
Import         : import_id, uploaded_at, raw_file_hash, accepted_rows, rejected_rows + reasons, preserved original
```

Rules:

1. First release scope is **long-only equities and cash**, stated explicitly.
   Shorts, derivatives, look-through funds and multi-currency need additional
   exposure conventions, not merely negative values.
2. A historical view uses historical holdings, or prominently states that
   current holdings are being evaluated against past conditions.
3. Portfolio totals, covered share, uncovered share and overlapping exposure
   must reconcile without inflation.
4. Coverage percentage is **not** loss probability and **not** value-at-risk.
   Measured risk requires actual valuation/return history with explicit units,
   horizon, methodology and validation.

## 7. Scenario — PROPOSAL

```
Scenario    : scenario_id, owner, org_id, name, baseline_artefact_id (run + weights + state),
              assumption_set_version, steps[], created_at, reviewer history
Assumption  : key, value, unit, justification, source?
ScenarioRun : (scenario_id, executed_at, engine_version) → results[] + provenance
```

Rules:

1. Zero shock reproduces the baseline exactly (identity test).
2. A `+0.1` pillar-rank shock is **not** a 10% price move. Economic scenarios
   require a documented propagation and portfolio-valuation model.
3. The existing rank-shock tool is retained as an explicit expert diagnostic
   alongside economic scenarios.
4. Identical regime-weight vectors legitimately produce no score change. Weights
   are never altered to make a control appear responsive.
5. A fitted conditional association is not an identified causal effect of
   intervention; the label must say which it is.

## 8. Case workflow — PROPOSAL

```
Case        : case_id, org_id (regulator scope), title, priority, status, deadlines,
              related_alerts[], related_events[], related_institutions[]
Assignment  : case_id, assignee_user_id, team, assigned_by, assigned_at
CaseEvent   : append-only (comment, evidence_attached, info_requested, review, approval,
              decision, closure, reopen), actor, at, request_id
EvidenceRef : immutable pointer (article revision, model fit, position snapshot,
              scenario assumption version) — resolved, never "latest"
```

Rules:

1. Extends the existing journal; its event history is preserved, not replaced.
2. State transitions are validated; concurrent updates are detected.
3. Delivery side effects are idempotent.
4. **Information-as-known replay**: a past decision reopens exactly the
   revisions available then. Exports resolve immutable references.
5. A source correction notifies affected cases and scenarios **without**
   rewriting old decisions.
6. The `circuit_breaker` annotation records an action *category*. It does not
   authorise or execute a real market intervention.

## 8b. Run and command persistence — ADOPTED (2026-10-16, `FIX03`/`FIX08`)

See [DR-02](decisions/DR-02-2026-10-16-run-sealing-and-command-results.md).

```
Run lifecycle:   running -> inference_complete -> complete
Report:          immutable revisions; identical rewrite is a no-op
Command:         action_commands(run_id, request_id, ...) -> event_seq | NULL
Journal:         action_events(run_id, seq, ...) append-only, trigger-protected
```

| Rule | Meaning |
|---|---|
| Sealed means sealed | a completed run accepts no new point; only a byte-identical retry of an existing point |
| Declared range is enforced | a point outside the manifest's `start..end` is rejected even while running |
| Dates, not counts | `finish()` verifies the exact expected date set, records it and a content digest |
| Completion requires the report | a run declaring `requires_report` stays `inference_complete` until its report exists |
| Reports never overwrite | a different report appends a revision; the previous one is preserved |
| One command, at most one event | a no-op command consumes no journal sequence and still returns an idempotent result |
| Unavailable classification fails closed | `MISSING_DEPENDENCY`, or an opt-in degraded mode that says so in a `PARTIAL_COVERAGE` warning |

## 9. UI transport — PARTLY ADOPTED

**Adopted today:** request envelope `{op, id (idempotency key), run_id, date, …}`;
Python re-validates run/date context and role before any computation or write;
`gateway.build_view()` omits restricted fields rather than dimming them; role
changes clear previous view content; journal writes are idempotent and durable.

**Proposed (`FIX10`, `FIX11`, `AUTH02`):**

| Addition | Requirement |
|---|---|
| Request status | `idle` \| `pending` \| `succeeded` \| `failed` \| `timed_out`, visible in the UI |
| Bounded recovery | explicit timeout, bounded retry of the same idempotency key, no permanent `pending` latch |
| Draft preservation | tool form inputs survive a re-render and a failed request |
| Result context binding | every result carries `(run_id, date, role, request_id)`; a result whose context no longer matches the selection is discarded, never displayed |
| Coherent reads | every supported view consumes one run/as-of bundle; no independent-latest-row mixing on any supported route |
| Scoped caching | cache keys include identity/organisation and result context |

---

## Open decisions

Recorded here so they are visible; each needs a dated decision record before
its implementing slice.

| # | Decision | Recommended starting position | Needed before |
|---|---|---|---|
| D-A | First news domain | one official policy/event family + one UI-represented sector (provisionally steel), subject to verified source accessibility and exposure evidence | `NEWS01` |
| D-B | First portfolio scope | long-only equities + cash, current holdings; point-in-time history next | `PORT01` |
| D-C | Role grants model | server-managed grants and organisation scope | `AUTH01` |
| D-D | News estimate semantics | explainable event/exposure/severity/confidence dimensions first; loss probabilities only against a specified calibrated target | `NEWS05` |
| D-E | Policy semantics | distinguish fitted conditional projection, hypothetical regime sensitivity and causal intervention claims | `POL01` |
| D-F | First deployment audience | undecided — fixes operational/security acceptance | `OPS03` |
| D-G | FR35 Table B fold definition | **scientifically unresolved**; two-epoch (FR35 text) vs six-epoch (`configuration_list()`) | `FIX05` |
| D-H | Undefined NFR acceptance quantities (NFR3/18/19/20/22/27/29) | propose measurable criteria; never invent a measured pass | `QA02` |
| D-I | Official session-calendar source | replace the `declared` session registry with ingested exchange calendar data | Phase 5 |
