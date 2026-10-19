"""T04 — a cached Principal is a snapshot, never standing authority (R06).

The audit found that after revoking a grant, an existing `Principal` still
passed `IdentityRegistry.can()` and could read a portfolio. A fresh
`resolve()` correctly denied it, but `can()`/`require()` never revalidated.

Reproducing it here showed it was worse than reported: a revoked **session**
and a **disabled user** also still passed.

Plan §14.1 R06 requires: revoked cached principal; disabled user; revoked
session/membership; cross-org list/read/export/mutate; cache and browser
payload isolation. The first four are here; cross-org and payload isolation
are already covered by `test_auth_identity_and_tenancy.py`.
"""
from __future__ import annotations

import pytest

from seraph.identity import (
    AuthorizationError,
    IdentityRegistry,
    Scope,
    StalePrincipal,
    authorization_revision,
)


@pytest.fixture
def world(tmp_path):
    """One user with one live grant, holding one private portfolio."""
    registry = IdentityRegistry(tmp_path / "identity.sqlite")
    registry.add_organisation("org_a", "Alpha Capital", "institution")
    registry.add_organisation("org_b", "Beta Capital", "institution")
    user = registry.upsert_user(provider_subject="s1", issuer="https://idp.test")
    registry.add_membership(user.user_id, "org_a")
    registry.grant(user.user_id, "org_a", "institutional", granted_by="admin")
    principal = registry.resolve(registry.open_session(user.user_id).session_id)
    registry.register_resource("portfolio", "pf1", org_id="org_a",
                               owner_user_id=user.user_id)
    return registry, user, principal


# ------------------------------------------- the four revocation paths


def test_a_revoked_grant_denies_the_cached_principal(world):
    """The audit's exact reproduction."""
    registry, user, principal = world
    assert registry.can(principal, "read", "portfolio", "pf1") is True
    registry.revoke_grant(user.user_id, "org_a", "institutional")
    assert registry.can(principal, "read", "portfolio", "pf1") is False


def test_a_revoked_session_denies_the_cached_principal(world):
    registry, user, principal = world
    registry.revoke_session(principal.session_id)
    assert registry.can(principal, "read", "portfolio", "pf1") is False


def test_a_revoked_membership_denies_the_cached_principal(world):
    registry, user, principal = world
    registry.revoke_membership(user.user_id, "org_a")
    assert registry.can(principal, "read", "portfolio", "pf1") is False


def test_a_disabled_user_denies_the_cached_principal(world):
    registry, user, principal = world
    with registry.connect() as db:
        db.execute("UPDATE users SET disabled_at=? WHERE user_id=?",
                   ("2026-01-01T00:00:00+05:30", user.user_id))
    assert registry.can(principal, "read", "portfolio", "pf1") is False


def test_an_expired_session_denies_the_cached_principal(world):
    registry, user, principal = world
    assert registry.can(principal, "read", "portfolio", "pf1",
                        ) is True
    with registry.connect() as db:
        db.execute("UPDATE sessions SET expires_at=? WHERE session_id=?",
                   ("2026-01-01T00:00:00+05:30", principal.session_id))
    assert registry.can(principal, "read", "portfolio", "pf1") is False


# ------------------------------------------- every path revalidates


@pytest.mark.parametrize("revoke", [
    pytest.param(lambda r, u, p: r.revoke_grant(u.user_id, "org_a", "institutional"),
                 id="grant"),
    pytest.param(lambda r, u, p: r.revoke_session(p.session_id), id="session"),
    pytest.param(lambda r, u, p: r.revoke_membership(u.user_id, "org_a"),
                 id="membership"),
])
def test_require_raises_after_revocation(world, revoke):
    registry, user, principal = world
    revoke(registry, user, principal)
    with pytest.raises(AuthorizationError):
        registry.require(principal, "read", "portfolio", "pf1")


@pytest.mark.parametrize("revoke", [
    pytest.param(lambda r, u, p: r.revoke_grant(u.user_id, "org_a", "institutional"),
                 id="grant"),
    pytest.param(lambda r, u, p: r.revoke_session(p.session_id), id="session"),
])
def test_listing_is_filtered_after_revocation(world, revoke):
    """A list path must not leak what a read path denies."""
    registry, user, principal = world
    assert registry.visible(principal, "portfolio", ["pf1"]) == ["pf1"]
    revoke(registry, user, principal)
    assert registry.visible(principal, "portfolio", ["pf1"]) == []


def test_export_is_denied_after_revocation(world):
    registry, user, principal = world
    registry.revoke_grant(user.user_id, "org_a", "institutional")
    assert registry.can(principal, "export", "portfolio", "pf1") is False


# ------------------------------------------- the revision, for commits


def test_a_principal_carries_an_authorization_revision(world):
    _, _, principal = world
    assert principal.authorization_revision
    assert principal.resolved_at
    assert principal.describe()["authorization_revision"] == \
        principal.authorization_revision


def test_an_unchanged_state_passes_the_commit_check(world):
    registry, user, principal = world
    fresh = registry.check_revision(principal)
    assert fresh.user_id == user.user_id
    assert fresh.authorization_revision == principal.authorization_revision


def test_narrowing_scope_mid_request_fails_the_commit_check(world):
    """A mutation must not commit under a snapshot that is no longer true."""
    registry, user, principal = world
    registry.grant(user.user_id, "org_a", "institutional", granted_by="admin",
                   scope=Scope(own_org_only=False, institutions=("org_b",)))
    with pytest.raises(StalePrincipal, match="authorization changed"):
        registry.check_revision(principal)


def test_revoking_mid_request_fails_the_commit_check(world):
    registry, user, principal = world
    registry.revoke_grant(user.user_id, "org_a", "institutional")
    with pytest.raises(StalePrincipal, match="no longer valid"):
        registry.check_revision(principal)


def test_the_revision_changes_with_every_authorization_input(world):
    registry, user, principal = world
    grant = registry.grants_for(user.user_id)[0]
    membership = registry._membership(user.user_id, "org_a")
    with registry.connect() as db:
        row = db.execute("SELECT session_id,user_id,issued_at,expires_at,"
                         "revoked_at,issuer FROM sessions WHERE session_id=?",
                         (principal.session_id,)).fetchone()
    from seraph.identity.model import Session
    session = Session(*row)
    base = authorization_revision(user=user, grant=grant, membership=membership,
                                  session=session)
    assert base == principal.authorization_revision

    narrowed = authorization_revision(
        user=user, grant=grant.__class__(**{**grant.__dict__,
                                            "scope": Scope(own_org_only=False)}),
        membership=membership, session=session)
    assert narrowed != base, "a scope change must change the revision"


# ------------------------------------------- recovery and performance


def test_a_regranted_user_works_again(world):
    """Revocation is not a tombstone on the person."""
    registry, user, principal = world
    registry.revoke_grant(user.user_id, "org_a", "institutional")
    assert registry.can(principal, "read", "portfolio", "pf1") is False
    registry.grant(user.user_id, "org_a", "institutional", granted_by="admin")
    assert registry.can(principal, "read", "portfolio", "pf1") is True


def test_require_returns_the_revalidated_principal(world):
    """Callers continue with current grants, including a narrowed scope."""
    registry, user, principal = world
    fresh = registry.require(principal, "read", "portfolio", "pf1")
    assert fresh.user_id == principal.user_id
    assert fresh.resolved_at >= principal.resolved_at


def test_listing_revalidates_once_not_per_resource(world):
    """A list of 500 portfolios must not cost 500 re-resolutions."""
    registry, user, principal = world
    ids = [f"pf{i}" for i in range(50)]
    for resource_id in ids:
        registry.register_resource("portfolio", resource_id, org_id="org_a",
                                   owner_user_id=user.user_id)
    calls = {"n": 0}
    original = registry.revalidate

    def counted(p, **kw):
        calls["n"] += 1
        return original(p, **kw)

    registry.revalidate = counted
    try:
        assert len(registry.visible(principal, "portfolio", ids)) == 50
    finally:
        registry.revalidate = original
    assert calls["n"] == 1


def test_the_unrevalidated_path_is_opt_in_only(world):
    """`revalidate=False` exists for `visible()`; it must be explicit."""
    registry, user, principal = world
    registry.revoke_grant(user.user_id, "org_a", "institutional")
    assert registry.can(principal, "read", "portfolio", "pf1") is False
    assert registry.can(principal, "read", "portfolio", "pf1",
                        revalidate=False) is True, \
        "the opt-out still trusts the snapshot, which is why it is opt-in"
