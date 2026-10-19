# C14 — Identity model (PRODUCT-CONTRACTS §4)
"""Users, organisations, memberships, grants, sessions and resource ACLs.

Design notes that are not obvious:

* A **grant** is `(user, org, role, scope)`. The role says what kind of view
  the user gets; the scope says which resources that view may reach. They are
  deliberately not one field, because "regulator" is not a synonym for "may
  read every institution's book".
* Revocation is a **timestamp, not a delete**. An audit trail that loses the
  fact a grant once existed cannot reconstruct a past decision.
* `Principal` is the resolved answer to "who is acting right now" — a user,
  the organisation they are acting for, the active role, and the scope that
  role carries. Authorization asks the principal, never the request.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from seraph.shared_types import ISOTimestamp

Role = Literal["retail", "institutional", "regulator"]
ROLES: tuple[Role, ...] = ("retail", "institutional", "regulator")

OrgKind = Literal["retail_household", "institution", "regulator_body"]

Visibility = Literal["private", "org", "shared", "public"]

#: Resource kinds the ACL understands. A kind not listed here is unknown, and
#: `IdentityRegistry.can` denies unknown kinds rather than guessing.
RESOURCE_KINDS = (
    "run", "portfolio", "holdings_snapshot", "scenario", "case",
    "news_annotation", "export", "watchlist", "preference",
)


class AuthorizationError(PermissionError):
    """The principal may not do this. Carries no detail about what exists."""


@dataclass(frozen=True)
class Scope:
    """What a role's reach actually is.

    `own_org_only` is the default and the safe one. A regulator grant may name
    `institutions` explicitly; an empty tuple with `own_org_only=False` means
    the scope was never configured, which `IdentityRegistry` treats as reaching
    nothing rather than everything.
    """

    own_org_only: bool = True
    institutions: tuple[str, ...] = ()
    note: str | None = None

    def reaches(self, org_id: str, acting_org: str) -> bool:
        if self.own_org_only:
            return org_id == acting_org
        return org_id == acting_org or org_id in self.institutions

    def describe(self) -> dict:
        return dict(own_org_only=self.own_org_only,
                    institutions=list(self.institutions), note=self.note)


@dataclass(frozen=True)
class User:
    user_id: str
    provider_subject: str          # the OIDC `sub`; stable for the lifetime of the account
    issuer: str                    # the OIDC issuer that vouched for it
    display_name: str | None = None
    email: str | None = None
    created_at: ISOTimestamp | None = None
    disabled_at: ISOTimestamp | None = None

    @property
    def active(self) -> bool:
        return self.disabled_at is None


@dataclass(frozen=True)
class Organisation:
    org_id: str
    name: str
    kind: OrgKind


@dataclass(frozen=True)
class Membership:
    user_id: str
    org_id: str
    granted_at: ISOTimestamp
    revoked_at: ISOTimestamp | None = None

    def active_at(self, ts: ISOTimestamp) -> bool:
        return self.granted_at <= ts and (self.revoked_at is None or ts < self.revoked_at)


@dataclass(frozen=True)
class Grant:
    user_id: str
    org_id: str
    role: Role
    granted_by: str
    granted_at: ISOTimestamp
    scope: Scope = field(default_factory=Scope)
    revoked_at: ISOTimestamp | None = None

    def active_at(self, ts: ISOTimestamp) -> bool:
        return self.granted_at <= ts and (self.revoked_at is None or ts < self.revoked_at)

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.user_id, self.org_id, self.role)


@dataclass(frozen=True)
class Session:
    session_id: str
    user_id: str
    issued_at: ISOTimestamp
    expires_at: ISOTimestamp
    revoked_at: ISOTimestamp | None = None
    issuer: str | None = None

    def active_at(self, ts: ISOTimestamp) -> bool:
        return (self.issued_at <= ts < self.expires_at
                and (self.revoked_at is None or ts < self.revoked_at))


@dataclass(frozen=True)
class ResourceACL:
    resource_kind: str
    resource_id: str
    org_id: str
    owner_user_id: str | None = None
    visibility: Visibility = "private"


class StalePrincipal(AuthorizationError):
    """The principal was valid when resolved and is not valid now.

    Audit finding R06: `can()` trusted a cached `Principal`, so a revoked
    grant, a revoked session and even a disabled user all still passed. A
    principal is a *snapshot of a past resolution*, never standing authority.
    """


@dataclass(frozen=True)
class Principal:
    """The resolved actor. Authorization asks this, never the HTTP request.

    It carries an `authorization_revision` — a digest of the exact grant,
    membership, session and user state it was resolved from. Authorization
    re-reads that state and compares; a mutation re-checks the revision inside
    its commit boundary, so a grant revoked mid-request cannot be committed
    under the stale snapshot.
    """

    user: User
    org: Organisation
    role: Role
    scope: Scope
    session_id: str
    available_roles: tuple[tuple[str, Role], ...] = ()   # (org_id, role) pairs
    #: Digest of the authorization state this principal was resolved from.
    authorization_revision: str = ""
    resolved_at: ISOTimestamp | None = None

    @property
    def user_id(self) -> str:
        return self.user.user_id

    @property
    def org_id(self) -> str:
        return self.org.org_id

    def describe(self) -> dict:
        """What is safe to show the client. No other user's data, ever."""
        return dict(
            user_id=self.user_id, display_name=self.user.display_name,
            org_id=self.org_id, org_name=self.org.name, org_kind=self.org.kind,
            role=self.role, scope=self.scope.describe(),
            available_roles=[dict(org_id=o, role=r) for o, r in self.available_roles],
            authorization_revision=self.authorization_revision,
            resolved_at=self.resolved_at,
        )


def authorization_revision(*, user: User, grant: Grant, membership: Membership,
                           session: Session) -> str:
    """Digest the exact authorization state a principal was resolved from.

    Any change to the user's enabled state, the grant (including its scope),
    the membership or the session produces a different revision, so a stale
    principal is detectable without comparing a dozen fields by hand.
    """
    payload = json.dumps(dict(
        user=user.user_id, disabled=user.disabled_at,
        grant=list(grant.key), grant_granted=grant.granted_at,
        grant_revoked=grant.revoked_at, scope=grant.scope.describe(),
        membership=[membership.user_id, membership.org_id,
                    membership.granted_at, membership.revoked_at],
        session=session.session_id, session_expires=session.expires_at,
        session_revoked=session.revoked_at,
    ), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode()).hexdigest()[:32]
