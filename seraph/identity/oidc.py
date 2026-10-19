# C14 — OIDC subject verification (PRODUCT-CONTRACTS §4, AUTH01)
"""Turn an identity-provider assertion into a verified subject, or fail closed.

Scope, deliberately narrow: this module **verifies a subject**. It does not
authorize anything — `IdentityRegistry` does that from server-held grants, and
no claim in a token grants a role. A provider could assert
`"role": "regulator"` all day and it would change nothing.

Streamlit's native OIDC support (`st.user`, `st.login`) hands the application
an already-authenticated subject, so the normal production path is
`VerifiedSubject.from_streamlit_user()`. `OidcVerifier.verify()` exists for the
case where SERAPH holds the token itself.

**Unverified against a real provider.** No issuer, client id or secret is
configured in this checkout, so the round trip has never been exercised. The
code fails closed on every missing piece rather than pretending; see
`docs/DEVELOPMENT-STATUS.md` for the state this leaves `AUTH01` in.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass


class IdentityProviderUnavailable(RuntimeError):
    """The provider is not configured or not reachable.

    This is never a reason to fall back to privileged access. Local
    demonstration mode is a separate, explicitly labelled mode (see
    `seraph.identity.demo`), not what happens when auth breaks.
    """


@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    #: Leeway for clock skew between SERAPH and the provider.
    leeway_seconds: int = 60

    @classmethod
    def from_env(cls) -> "OidcConfig":
        """Read configuration from the environment, or fail closed.

        Credentials live in the environment, never in a versioned file and
        never in a log line.
        """
        issuer = os.environ.get("SERAPH_OIDC_ISSUER")
        client_id = os.environ.get("SERAPH_OIDC_CLIENT_ID")
        if not issuer or not client_id:
            raise IdentityProviderUnavailable(
                "SERAPH_OIDC_ISSUER and SERAPH_OIDC_CLIENT_ID are not set. "
                "Identity is unavailable; there is no fallback to privileged access")
        return cls(issuer=issuer, client_id=client_id)

    @classmethod
    def configured(cls) -> bool:
        return bool(os.environ.get("SERAPH_OIDC_ISSUER")
                    and os.environ.get("SERAPH_OIDC_CLIENT_ID"))


@dataclass(frozen=True)
class VerifiedSubject:
    """A subject SERAPH is willing to bind to a local user.

    Only `issuer` and `subject` are identity. Everything else is a label.
    """

    issuer: str
    subject: str
    email: str | None = None
    display_name: str | None = None
    email_verified: bool = False

    @classmethod
    def from_streamlit_user(cls, user) -> "VerifiedSubject":
        """Build from Streamlit's `st.user` after `st.login()`.

        Streamlit verifies the token and exposes the claims; it explicitly
        does not do authorization, which is exactly the split this module
        assumes.
        """
        get = (user.get if hasattr(user, "get")
               else lambda k, d=None: getattr(user, k, d))
        if not get("is_logged_in", False):
            raise IdentityProviderUnavailable("no authenticated Streamlit user")
        issuer, subject = get("iss"), get("sub")
        if not issuer or not subject:
            raise IdentityProviderUnavailable(
                "the provider returned no issuer/subject pair; refusing to invent one")
        return cls(issuer=str(issuer), subject=str(subject),
                   email=get("email"), display_name=get("name"),
                   email_verified=bool(get("email_verified", False)))


class OidcVerifier:
    """Validates claims SERAPH holds itself.

    Signature verification is the provider library's job (Streamlit's, or an
    OIDC client's). What this adds is the set of checks that are easy to skip
    and dangerous to skip: issuer match, audience match, expiry, not-before,
    and the presence of a stable subject.
    """

    def __init__(self, config: OidcConfig):
        self.config = config

    def verify(self, claims: dict, *, now: float | None = None) -> VerifiedSubject:
        now = time.time() if now is None else now
        leeway = self.config.leeway_seconds
        issuer = claims.get("iss")
        if issuer != self.config.issuer:
            raise IdentityProviderUnavailable(
                f"token issuer {issuer!r} is not the configured issuer")
        audience = claims.get("aud")
        audiences = audience if isinstance(audience, (list, tuple)) else [audience]
        if self.config.client_id not in audiences:
            raise IdentityProviderUnavailable("token audience does not include this client")
        exp = claims.get("exp")
        if exp is None or float(exp) + leeway < now:
            raise IdentityProviderUnavailable("token is expired or has no expiry")
        nbf = claims.get("nbf")
        if nbf is not None and float(nbf) - leeway > now:
            raise IdentityProviderUnavailable("token is not valid yet")
        subject = claims.get("sub")
        if not subject:
            raise IdentityProviderUnavailable("token carries no subject")
        return VerifiedSubject(
            issuer=str(issuer), subject=str(subject), email=claims.get("email"),
            display_name=claims.get("name"),
            email_verified=bool(claims.get("email_verified", False)))
