"""The role ACTIONS: review a link, price a scenario, export an analysis.

A review queue on screen is not a review workflow, and a scenario
function nothing can supply inputs to is not a scenario feature. These
are the three operations the console dispatches, kept here rather than in
the dashboard so they can be tested without a browser and so the rules
about who may do what live in one place.

Each one refuses specifically. "Unavailable" with the missing input named
is the useful answer; a blank panel is not, and a filled one built from
defaults would be worse than both.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

#: Which role may perform which action. Local role switching is a DEMO
#: identity: it is not authentication, it is not a claim about who the
#: person is, and every record written through it says so. A deployment
#: with real users must put the server identity in `reviewer` instead --
#: see `seraph/identity/` -- and these functions take the attribution as
#: an argument precisely so that substitution is a caller's decision.
ROLE_ACTIONS = {
    "regulator": ("review_instrument_link",),
    "institutional": ("scenario", "export"),
    "retail": (),
}

DEMO_PREFIX = "demo-role:"


def attribution(role: str, *, authenticated_subject: str | None = None) -> dict:
    """Who is recorded as acting, and on what basis.

    Never silently promotes a demo role to an identity. A record written
    by the local console says `demo-role:regulator` and carries
    `authenticated=False`, so a reviewed decision can be told apart from
    one made by a person a system actually authenticated.
    """
    if authenticated_subject:
        return dict(reviewer=authenticated_subject, authenticated=True,
                    basis="server-side authenticated session")
    return dict(reviewer=f"{DEMO_PREFIX}{role}", authenticated=False,
                basis=("local role selection in this console. This is a "
                       "demonstration identity, NOT authentication, and the "
                       "decision is recorded as such"))


def _permit(role: str, action: str) -> None:
    if action not in ROLE_ACTIONS.get(role, ()):
        raise PermissionError(
            f"the {role} view does not offer {action!r}. Role selection here "
            f"is a demonstration of distinct projections, not an "
            f"authorisation system")


# ------------------------------------------------- regulator: link review

def review_instrument_link(store, *, role: str, later_event_id: str,
                           earlier_event_id: str, decision: str,
                           reason: str, instrument_id: str | None = None,
                           authenticated_subject: str | None = None,
                           now: str | None = None) -> dict:
    """Accept or reject a proposed supersession link, with a reason.

    The decision is appended, never overwritten, and it changes what
    later projections say WITHOUT touching a single stored observation:
    the documents are evidence and stay exactly as received; the link
    between them is a reviewed judgement and is recorded separately.
    """
    _permit(role, "review_instrument_link")
    if decision not in ("confirmed", "rejected"):
        raise ValueError("a link review is 'confirmed' or 'rejected'")
    if not str(reason or "").strip():
        raise ValueError("a review needs a reason: a decision nobody can "
                         "read the grounds for cannot be audited later")
    who = attribution(role, authenticated_subject=authenticated_subject)
    recorded = store.record_supersession_review(
        later_event_id=later_event_id, earlier_event_id=earlier_event_id,
        decision=decision, reviewer=who["reviewer"],
        reason=f"{reason.strip()} [{who['basis']}]",
        instrument_id=instrument_id, now=now)
    return dict(kind="news_review", decision=decision,
                later=later_event_id, earlier=earlier_event_id,
                reviewer=who["reviewer"], authenticated=who["authenticated"],
                decided_at=recorded["decided_at"],
                review_id=recorded["review_id"],
                effect=("later projections at or after this time apply the "
                        "decision; stored documents and their evidence are "
                        "unchanged"),
                note=who["basis"])


# ------------------------------------- institutional: conditional scenario

def _decimal(value, label: str, *, low=None, high=None):
    if value is None or value == "":
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError(f"{label} must be a number; got {value!r}")
    if not number.is_finite():
        raise ValueError(f"{label} must be finite")
    if low is not None and number < low:
        raise ValueError(f"{label} must be at least {low}")
    if high is not None and number > high:
        raise ValueError(f"{label} must be at most {high}")
    return number


def run_scenario(event, master, *, role: str, edge=None, product=None,
                 cost_base=None, pass_through=None, on=None) -> dict:
    """Price one documented route under explicitly supplied assumptions.

    `cost_base` and `pass_through` are the CALLER'S assumptions and are
    labelled as such in the result. They are not observed company data,
    they are not fitted, and supplying neither is a perfectly good way to
    use this: the landed-cost change comes from the instrument's own
    stated rates and needs no assumption at all.
    """
    _permit(role, "scenario")
    base = _decimal(cost_base, "eligible cost base", low=Decimal(0))
    interval = None
    if pass_through is not None:
        low = _decimal(pass_through[0], "pass-through low",
                       low=Decimal(0), high=Decimal(1))
        high = _decimal(pass_through[1], "pass-through high",
                        low=Decimal(0), high=Decimal(1))
        if low is None or high is None:
            raise ValueError("a pass-through interval needs both endpoints")
        if low > high:
            raise ValueError("the pass-through interval is inverted")
        interval = (low, high)

    from seraph.news.scenarios import scenario_for
    result = scenario_for(event, master, edge=edge, product=product,
                          on=on, eligible_cost_base=base,
                          pass_through=interval)
    result["kind"] = "news_scenario"
    result["event_id"] = event.event_id
    result["headline"] = event.headline
    result["inputs"] = dict(
        cost_base=None if base is None else str(base),
        pass_through=None if interval is None else [str(x) for x in interval],
        product=product, as_of=on,
        supplied_by=("the caller, through this console. These are stated "
                     "assumptions, not observed company data and not an "
                     "estimate produced by this system"))
    if base is None:
        result.setdefault("monetary_basis",
                          "no eligible cost base was supplied, so no "
                          "monetary range is produced")
    return result


# ------------------------------------------- institutional: export

def export_analysis(*, role: str, channel, scenario=None, comparison=None,
                    matrix=None, event_ids=(), now: str | None = None) -> dict:
    """The displayed analysis, with everything needed to check it later.

    An export that carries only conclusions is an assertion. This carries
    the evidence links, the input assumptions, the processing manifest and
    the limitations alongside them, so a reader who disagrees can find the
    documents and the versions that produced it.
    """
    _permit(role, "export")
    from seraph.news.acquisition import _now
    stamp = now or _now()
    wanted = set(event_ids or ())
    events = [e for e in (channel.get("eligible_events") or ())
              if not wanted or e.event_id in wanted]
    references = channel.get("references") or {}
    estimates = [e for e in (channel.get("estimates") or ())
                 if not wanted or e.event_id in wanted]

    return dict(
        kind="news_export",
        schema="news-analysis-export/1",
        exported_at=stamp,
        decision_ts=channel.get("decision_ts"),
        role=role,
        events=[dict(event_id=e.event_id, headline=e.headline,
                     event_type=e.event_type,
                     first_seen_at=(e.timing.first_seen_at if e.timing else None),
                     published_at=(e.timing.published_at if e.timing else None),
                     effective_at=(e.timing.effective_at if e.timing else None),
                     assertion=getattr(getattr(e, "frame", None),
                                       "assertion_status", None),
                     legal_stage=getattr(getattr(e, "frame", None),
                                         "policy_status", None),
                     unknowns=list(getattr(getattr(e, "frame", None),
                                           "unknowns", ()) or ()),
                     evidence=references.get(e.event_id, []))
                for e in events],
        impacts=[e.describe() for e in estimates],
        scenario=scenario, comparison=comparison, matrix=matrix,
        manifest=channel.get("manifest"),
        source_coverage=channel.get("source_coverage"),
        supersession=channel.get("supersession"),
        limitations=[
            "Qualitative mechanism hypotheses. Nothing here is a measured "
            "outcome, a loss, or a probability of loss.",
            "Exposure relationships are documented and mostly UNSIZED; an "
            "unknown size is not a small one.",
            "A scenario's cost base and pass-through are caller assumptions, "
            "labelled in `scenario.inputs`, not observed company data.",
            "Frames are reconstructed from stored text with the rule "
            "versions in `manifest`; that is not a replay of what the "
            "running system emitted at the time.",
            "The independent extraction benchmark has NOT been passed. "
            "These examples support a demonstration, not a general accuracy "
            "claim.",
        ])
