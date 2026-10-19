"""AUTH01-AUTH04 — identity, tenancy, revocation and durable owned state.

Audit finding A10: any local user could select regulator, the journal actor
was a role string, run selection was global, and holdings could ride inside a
run manifest. The contract's required integration check is explicit — two
users in one organisation, two different organisations, a scoped regulator, a
revoked user and a forged role request — so those are the tests.

The identity-provider round trip is NOT exercised here: no issuer or client id
is configured in this checkout. What is tested is that the verifier fails
closed on every malformed or missing piece, and that nothing anywhere falls
back to privileged access when it does.
"""
from __future__ import annotations

import time

import pytest

from seraph.decision_support.workspace import WorkspaceStore
from seraph.identity import (
    AuthorizationError,
    IdentityProviderUnavailable,
    IdentityRegistry,
    OidcConfig,
    OidcVerifier,
    Scope,
    VerifiedSubject,
)


@pytest.fixture
def world(tmp_path):
    """Two institutions, a retail household, a regulator, and their people."""
    registry = IdentityRegistry(tmp_path / "identity.sqlite")
    workspace = WorkspaceStore(tmp_path / "workspace.sqlite", registry)
    registry.add_organisation("org_alpha", "Alpha Capital", "institution")
    registry.add_organisation("org_beta", "Beta Capital", "institution")
    registry.add_organisation("org_home", "A Household", "retail_household")
    registry.add_organisation("org_reg", "Market Regulator", "regulator_body")

    people = {}
    for key, sub, org, role, scope in [
        ("alpha_one", "s-a1", "org_alpha", "institutional", Scope()),
        ("alpha_two", "s-a2", "org_alpha", "institutional", Scope()),
        ("beta_one", "s-b1", "org_beta", "institutional", Scope()),
        ("retail", "s-r1", "org_home", "retail", Scope()),
        ("regulator", "s-g1", "org_reg", "regulator",
         Scope(own_org_only=False, institutions=("org_alpha",),
               note="supervises Alpha only")),
    ]:
        user = registry.upsert_user(provider_subject=sub,
                                    issuer="https://idp.test", display_name=key)
        registry.add_membership(user.user_id, org)
        registry.grant(user.user_id, org, role, granted_by="admin", scope=scope)
        session = registry.open_session(user.user_id)
        people[key] = registry.resolve(session.session_id)
    return registry, workspace, people


# --------------------------------------------------- AUTH01: resolution


def test_a_role_is_resolved_from_a_grant_not_from_the_request(world):
    registry, _, people = world
    assert people["retail"].role == "retail"
    with pytest.raises(AuthorizationError, match="no live grant"):
        registry.resolve(people["retail"].session_id, requested_role="regulator")


def test_a_user_may_switch_only_among_grants_they_hold(world):
    registry, _, people = world
    user_id = people["alpha_one"].user_id
    registry.add_membership(user_id, "org_beta")
    registry.grant(user_id, "org_beta", "institutional", granted_by="admin")
    principal = registry.resolve(people["alpha_one"].session_id,
                                 requested_org="org_beta")
    assert principal.org_id == "org_beta"
    assert set(principal.available_roles) == {("org_alpha", "institutional"),
                                              ("org_beta", "institutional")}
    with pytest.raises(AuthorizationError):
        registry.resolve(people["alpha_one"].session_id, requested_org="org_reg")


def test_the_same_provider_subject_maps_to_one_stable_user(world):
    registry, _, _ = world
    first = registry.upsert_user(provider_subject="s-a1", issuer="https://idp.test")
    second = registry.upsert_user(provider_subject="s-a1", issuer="https://idp.test",
                                  email="a@example.test")
    assert first.user_id == second.user_id
    # The same subject at a DIFFERENT issuer is a different person.
    other = registry.upsert_user(provider_subject="s-a1", issuer="https://other.test")
    assert other.user_id != first.user_id


# ------------------------------------------- AUTH02: tenancy isolation


def test_two_users_in_one_organisation_share_org_scope_but_not_private_data(world):
    registry, workspace, people = world
    alpha_one, alpha_two = people["alpha_one"], people["alpha_two"]
    book = workspace.create_portfolio(alpha_one, name="Alpha Book")
    # Same org, but the portfolio is private to its owner.
    assert registry.can(alpha_one, "read", "portfolio", book["portfolio_id"])
    assert not registry.can(alpha_two, "read", "portfolio", book["portfolio_id"])
    registry.register_resource("scenario", "sc_shared", org_id="org_alpha",
                               owner_user_id=alpha_one.user_id, visibility="org")
    assert registry.can(alpha_two, "read", "scenario", "sc_shared")


def test_two_institutions_cannot_read_each_others_books(world):
    registry, workspace, people = world
    alpha_book = workspace.create_portfolio(people["alpha_one"], name="Alpha")
    beta_book = workspace.create_portfolio(people["beta_one"], name="Beta")
    assert not registry.can(people["beta_one"], "read", "portfolio",
                            alpha_book["portfolio_id"])
    assert not registry.can(people["alpha_one"], "read", "portfolio",
                            beta_book["portfolio_id"])
    with pytest.raises(AuthorizationError):
        workspace.portfolio(people["beta_one"], alpha_book["portfolio_id"])


def test_listing_is_filtered_by_the_same_rule_as_reading(world):
    _, workspace, people = world
    workspace.create_portfolio(people["alpha_one"], name="Alpha")
    workspace.create_portfolio(people["beta_one"], name="Beta")
    assert [p["name"] for p in workspace.portfolios(people["alpha_one"])] == ["Alpha"]
    assert [p["name"] for p in workspace.portfolios(people["beta_one"])] == ["Beta"]


def test_a_regulators_scope_is_a_grant_not_a_wildcard(world):
    registry, _, people = world
    regulator = people["regulator"]
    registry.register_resource("case", "case_alpha", org_id="org_alpha")
    registry.register_resource("case", "case_beta", org_id="org_beta")
    assert registry.can(regulator, "read", "case", "case_alpha")
    assert not registry.can(regulator, "read", "case", "case_beta")


def test_a_regulator_does_not_get_a_users_private_holdings_through_scope(world):
    registry, workspace, people = world
    book = workspace.create_portfolio(people["alpha_one"], name="Alpha Book")
    # Alpha is inside the regulator's scope, yet the book is the user's own.
    assert not registry.can(people["regulator"], "read", "portfolio",
                            book["portfolio_id"])


def test_an_unregistered_resource_is_denied_rather_than_assumed_open(world):
    registry, _, people = world
    assert not registry.can(people["alpha_one"], "read", "portfolio", "pf_ghost")
    assert not registry.can(people["alpha_one"], "read", "unknown_kind", "x")
    assert not registry.can(people["alpha_one"], "incinerate", "portfolio", "x")


def test_a_role_without_the_capability_is_denied_before_scope_is_consulted(world):
    registry, _, people = world
    registry.register_resource("case", "c1", org_id="org_home",
                               owner_user_id=people["retail"].user_id)
    assert not registry.can(people["retail"], "read", "case", "c1")


# ------------------------------------- AUTH03: revocation and sessions


def test_revoking_a_grant_stops_access_immediately(world):
    registry, _, people = world
    principal = people["alpha_one"]
    registry.revoke_grant(principal.user_id, "org_alpha", "institutional")
    with pytest.raises(AuthorizationError, match="no live grants"):
        registry.resolve(principal.session_id)


def test_revoking_a_membership_also_revokes_its_grants(world):
    registry, _, people = world
    principal = people["alpha_one"]
    registry.revoke_membership(principal.user_id, "org_alpha")
    assert registry.grants_for(principal.user_id) == []


def test_revocation_is_recorded_not_deleted(world):
    registry, _, people = world
    principal = people["alpha_one"]
    registry.revoke_grant(principal.user_id, "org_alpha", "institutional")
    with registry.connect() as db:
        row = db.execute("SELECT revoked_at FROM grants WHERE user_id=?",
                         (principal.user_id,)).fetchone()
    assert row is not None and row[0] is not None, \
        "an audit trail must keep the fact the grant existed"


def test_a_revoked_session_stops_working(world):
    registry, _, people = world
    registry.revoke_session(people["alpha_one"].session_id)
    with pytest.raises(AuthorizationError, match="expired or revoked"):
        registry.resolve(people["alpha_one"].session_id)


def test_an_expired_session_stops_working(world):
    registry, _, people = world
    user_id = people["retail"].user_id
    session = registry.open_session(user_id, hours=1)
    assert registry.resolve(session.session_id).user_id == user_id
    with pytest.raises(AuthorizationError, match="expired or revoked"):
        registry.resolve(session.session_id, at="2099-01-01T00:00:00+05:30")


def test_an_unknown_session_is_refused(world):
    registry, _, _ = world
    with pytest.raises(AuthorizationError, match="unknown session"):
        registry.resolve("ses_forged")


def test_a_grant_requires_a_live_membership(world):
    registry, _, people = world
    user_id = people["retail"].user_id
    with pytest.raises(ValueError, match="live membership"):
        registry.grant(user_id, "org_alpha", "institutional", granted_by="admin")


# ------------------------------------------- AUTH01: provider failure


def test_an_unconfigured_provider_fails_closed(monkeypatch):
    monkeypatch.delenv("SERAPH_OIDC_ISSUER", raising=False)
    monkeypatch.delenv("SERAPH_OIDC_CLIENT_ID", raising=False)
    assert OidcConfig.configured() is False
    with pytest.raises(IdentityProviderUnavailable, match="no fallback"):
        OidcConfig.from_env()


@pytest.mark.parametrize("broken,match", [
    ({"iss": "https://evil.test"}, "not the configured issuer"),
    ({"aud": "someone-else"}, "audience"),
    ({"exp": 0}, "expired"),
    ({"nbf": 4102444800}, "not valid yet"),
    ({"sub": None}, "no subject"),
])
def test_the_verifier_rejects_every_broken_claim(broken, match):
    verifier = OidcVerifier(OidcConfig(issuer="https://idp.test", client_id="seraph"))
    claims = {"iss": "https://idp.test", "aud": "seraph", "sub": "s-1",
              "exp": time.time() + 3600}
    claims.update(broken)
    with pytest.raises(IdentityProviderUnavailable, match=match):
        verifier.verify(claims)


def test_a_good_token_yields_a_subject_and_no_authority():
    verifier = OidcVerifier(OidcConfig(issuer="https://idp.test", client_id="seraph"))
    subject = verifier.verify({"iss": "https://idp.test", "aud": ["seraph"],
                               "sub": "s-1", "exp": time.time() + 3600,
                               "email": "a@example.test", "name": "A",
                               "role": "regulator"})
    assert isinstance(subject, VerifiedSubject) and subject.subject == "s-1"
    # A role claimed in the token grants nothing: authority comes from grants.
    assert not hasattr(subject, "role")


def test_a_streamlit_user_who_is_not_logged_in_is_refused():
    with pytest.raises(IdentityProviderUnavailable, match="no authenticated"):
        VerifiedSubject.from_streamlit_user({"is_logged_in": False})
    with pytest.raises(IdentityProviderUnavailable, match="refusing to invent"):
        VerifiedSubject.from_streamlit_user({"is_logged_in": True, "sub": None})


# --------------------------------------- AUTH04: durable owned state


def test_owned_state_survives_a_restart_and_stays_isolated(tmp_path, world):
    registry, workspace, people = world
    alpha = people["alpha_one"]
    workspace.save_watchlist(alpha, "Energy", ["reliance", "ONGC", "reliance"])
    workspace.set_preference(alpha, "default_view", "console")
    reopened = WorkspaceStore(workspace.path, registry)
    lists = reopened.watchlists(alpha)
    assert lists[0]["items"] == ["ONGC", "RELIANCE"], "deduplicated and normalised"
    assert reopened.preferences(alpha)["default_view"] == "console"
    # Another organisation's user sees none of it.
    assert reopened.watchlists(people["beta_one"]) == []
    assert reopened.preferences(people["beta_one"]) == {}


def test_a_portfolio_is_registered_for_authorization_when_created(world):
    registry, workspace, people = world
    book = workspace.create_portfolio(people["alpha_one"], name="Alpha")
    acl = registry.acl("portfolio", book["portfolio_id"])
    assert acl.org_id == "org_alpha"
    assert acl.owner_user_id == people["alpha_one"].user_id
    assert acl.visibility == "private"
