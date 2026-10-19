# C14 — Identity, organisations and grants (PRODUCT-CONTRACTS §4)
"""Who is asking, which organisation they act for, and what they may reach.

Role and resource scope are separate. A user with the `institutional` role in
Org A still cannot read Org B's books; a regulator's reach is an explicit grant
scope, not "sees everything". Every grant is server-held: a browser may ask to
switch among grants the user already has, and nothing more.
"""
from seraph.identity.model import (
    AuthorizationError,
    Grant,
    Membership,
    Organisation,
    Principal,
    ResourceACL,
    Role,
    Scope,
    Session,
    StalePrincipal,
    User,
    Visibility,
    authorization_revision,
)
from seraph.identity.registry import IdentityRegistry
from seraph.identity.oidc import (
    IdentityProviderUnavailable,
    OidcConfig,
    OidcVerifier,
    VerifiedSubject,
)

__all__ = [
    "AuthorizationError",
    "Grant",
    "IdentityProviderUnavailable",
    "IdentityRegistry",
    "Membership",
    "OidcConfig",
    "OidcVerifier",
    "Organisation",
    "Principal",
    "ResourceACL",
    "Role",
    "Scope",
    "Session",
    "StalePrincipal",
    "User",
    "VerifiedSubject",
    "Visibility",
    "authorization_revision",
]
