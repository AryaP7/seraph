# C12 — the durable-workflow stores behind the console (T05, T08, T09)
"""Where the console gets its `WorkspaceStore`, `ScenarioStore` and `CaseStore`.

The defect this closes is not a bug in any of those three stores. All three
are implemented, tested and sound -- `WorkspaceStore` (portfolios, dated
holdings snapshots, watchlists, preferences), `ScenarioStore` (immutable
assumption revisions, reconstructable runs, bound reviews) and `CaseStore`
(assignment, evidence, decisions, closure, versioned export). The defect is
that **nothing in the dashboard ever called them.** `grep -c` over
`prototype_app.py` and `console_backend.py` for all three store names
returned 0. So the console kept portfolios in `st.session_state`, scenarios
were transient, and the regulator case lifecycle had no user at all: around
1,300 lines of working persistence with no route to a human.

This module is the route. It owns nothing of its own except store
construction and the demo identity.

Identity
--------
Every method on those stores takes a `Principal`, and a `Principal` comes
from `IdentityRegistry` -- never from a literal, because the whole point of
the registry is that authorisation is resolved centrally. There is no
identity provider configured in this checkout, so this module mints a
**local demonstration principal** through the registry's real path
(organisation -> user -> membership -> grant -> session -> resolve) and
labels it as such.

That label is load-bearing and must not be softened. `AGENTS.md` and the
console's own caption both say local role switching is not authentication.
What this gives the demonstration is *durable, owner-scoped state* -- the
same portfolio comes back after a restart, and another organisation's rows
are not visible -- which is what FR42/FR43 are about. What it does not give
is proof of who is sitting at the keyboard. P01 is that work, and it needs a
provider.
"""
from __future__ import annotations

import os
from pathlib import Path

from seraph.decision_support.cases import CaseStore
from seraph.decision_support.scenarios import ScenarioStore
from seraph.decision_support.workspace import WorkspaceStore
from seraph.identity import IdentityRegistry

#: Where the durable workflow stores live. Beside the other prototype stores,
#: so one directory is the whole of this installation's mutable state and
#: O05's backup story has one place to look.
def _runs_dir() -> Path:
    override = os.environ.get("SERAPH_WORKSPACE_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "prototype_runs"


#: The demonstration organisation and subjects. Fixed, so that restarting the
#: console returns the SAME principal and therefore the same saved rows --
#: a per-session random identity would make persistence untestable and would
#: quietly orphan yesterday's portfolios.
DEMO_ORG = "org_demo"
DEMO_ORG_NAME = "Local Demonstration Desk"
DEMO_ISSUER = "local://seraph-demo"

#: ONE SUBJECT PER ROLE, not one user holding all three.
#:
#: The first version granted every role to a single user and re-resolved it
#: per request. That does not work and should not: `IdentityRegistry.resolve`
#: returns one role for a session, so the third grant collided with the first
#: and `CaseStore` refused the case with "only a regulator may open a case".
#:
#: Separate subjects are also the right model rather than a workaround. A
#: retail holder and a market regulator are different people with different
#: data, and a single principal carrying all three roles at once is precisely
#: the privilege confusion role-based access control exists to prevent. The
#: consequence is deliberate: each demonstration role has its OWN portfolios,
#: scenarios and cases, because the stores are owner-scoped.
DEMO_SUBJECTS = {
    "retail": "local-demo-retail",
    "institutional": "local-demo-institutional",
    "regulator": "local-demo-regulator",
}

#: Said on every surface that shows this principal's data.
DEMO_NOTE = ("local demonstration identity, not authenticated. State is "
             "durable and owner-scoped; it does not establish who is using it")


def registry(path: "Path | None" = None) -> IdentityRegistry:
    return IdentityRegistry(Path(path) if path else _runs_dir() / "identity.sqlite")


def demo_principal(role: str = "retail", *, reg: IdentityRegistry | None = None):
    """A real `Principal` for the local demonstration, built the real way.

    One user PER ROLE -- see `DEMO_SUBJECTS`. Idempotent: the organisation,
    user, membership and grant are upserted, so calling this on every page
    render does not accumulate rows. A fresh session is opened each time
    because a session is the thing that expires; the USER and its grants are
    stable, which is what owns the data.
    """
    if role not in DEMO_SUBJECTS:
        raise ValueError(
            f"unknown role {role!r}; this release has "
            f"{', '.join(sorted(DEMO_SUBJECTS))}")
    reg = reg or registry()
    try:
        reg.add_organisation(DEMO_ORG, DEMO_ORG_NAME, "institution")
    except Exception:                                       # noqa: BLE001
        pass                                                # already present
    user = reg.upsert_user(provider_subject=DEMO_SUBJECTS[role],
                           issuer=DEMO_ISSUER)
    try:
        reg.add_membership(user.user_id, DEMO_ORG)
    except Exception:                                       # noqa: BLE001
        pass
    reg.grant(user.user_id, DEMO_ORG, role, granted_by="local-demo")
    return reg.resolve(reg.open_session(user.user_id).session_id)


def stores(*, reg: IdentityRegistry | None = None) -> dict:
    """The three stores, sharing one identity registry.

    One registry instance matters: each store calls `registry.require(...)`
    for every read and write, and two registries over two files would let a
    grant exist for one store and not the other.
    """
    reg = reg or registry()
    root = _runs_dir()
    return dict(
        registry=reg,
        workspace=WorkspaceStore(root / "workspace.sqlite", reg),
        scenarios=ScenarioStore(root / "scenarios.sqlite", reg),
        cases=CaseStore(root / "cases.sqlite", reg),
    )


def describe(role: str = "retail") -> dict:
    """What the console should say about this identity, verbatim."""
    return dict(identity=DEMO_SUBJECTS.get(role, role),
                organisation=DEMO_ORG, role=role,
                authenticated=False, note=DEMO_NOTE,
                directory=str(_runs_dir()))


def active_portfolio(selection: dict, role: str, *, at: str,
                     bundle=None, principal=None, flags=None) -> dict:
    """C12/FR43 — resolve saved holdings and their overlay in one owner scope."""
    from seraph.decision_support.portfolio import portfolio_overlay

    bundle = bundle or stores()
    principal = principal or demo_principal(role, reg=bundle['registry'])
    if selection.get('role') != role:
        raise ValueError('The active portfolio belongs to another role')
    workspace = bundle['workspace']
    pid = selection['portfolio_id']
    historical = selection.get('basis') == 'historical'
    held = (workspace.holdings_as_of(principal, pid, at) if historical else
            workspace.current_holdings(principal, pid))
    # Keep the normalized inputs for news; coverage output is a different shape.
    holdings = [{k: row[k] for k in ('symbol', 'value', 'quantity', 'sector')}
                for row in held['holdings']]
    result = portfolio_overlay(holdings, flags or {})
    overlay = result.value if result.status == 'ok' else None
    return dict(holdings=holdings, overlay=overlay,
                context=dict(portfolio_id=pid, snapshot_id=held['snapshot_id'],
                             basis=held['basis'], effective_at=held.get('effective_at')),
                note=(held.get('note') or
                      'Current holdings overlaid on the selected market decision')
                if not historical else
                held.get('note', 'Historical holdings at the market decision'))
