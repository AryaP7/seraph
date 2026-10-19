# C14 — Identity registry and authorization (PRODUCT-CONTRACTS §4, AUTH01-AUTH03)
"""Server-held users, organisations, grants, sessions and resource ACLs.

Everything here answers one of two questions:

    resolve(session_id, requested_role) -> Principal     who is acting?
    can(principal, action, resource)    -> bool          may they?

Both are answered from stored state at a stated time. Nothing a client sends
can widen them: `resolve` ignores a requested role the user has no live grant
for, and `can` reads the resource's own ACL rather than any claim travelling
with the request.

Storage is SQLite, in the same local-prototype spirit as `RunStore` — a
single-user demonstration store, not authenticated regulatory infrastructure.
The schema is written so the same statements port to PostgreSQL.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from seraph.identity.model import (
    RESOURCE_KINDS,
    ROLES,
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
from seraph.shared_types import IST, ist_timestamp

#: Actions the authorization layer understands. An unknown action is denied.
ACTIONS = ("read", "list", "write", "delete", "export")

#: Which roles may ever perform an action on a resource kind, before scope is
#: even considered. Scope then narrows it to specific resources.
ROLE_CAPABILITY: dict[str, dict[str, tuple[Role, ...]]] = {
    "run":               {"read": ROLES, "list": ROLES, "write": (), "delete": (), "export": ("institutional", "regulator")},
    "portfolio":         {"read": ROLES, "list": ROLES, "write": ROLES, "delete": ROLES, "export": ROLES},
    "holdings_snapshot": {"read": ROLES, "list": ROLES, "write": ROLES, "delete": ROLES, "export": ROLES},
    "scenario":          {"read": ("institutional", "regulator"), "list": ("institutional", "regulator"),
                          "write": ("institutional", "regulator"), "delete": ("institutional", "regulator"),
                          "export": ("institutional", "regulator")},
    "case":              {"read": ("regulator",), "list": ("regulator",), "write": ("regulator",),
                          "delete": (), "export": ("regulator",)},
    "news_annotation":   {"read": ROLES, "list": ROLES, "write": ("institutional", "regulator"),
                          "delete": (), "export": ("institutional", "regulator")},
    "export":            {"read": ("institutional", "regulator"), "list": ("institutional", "regulator"),
                          "write": ("institutional", "regulator"), "delete": (), "export": ()},
    "watchlist":         {"read": ROLES, "list": ROLES, "write": ROLES, "delete": ROLES, "export": ()},
    "preference":        {"read": ROLES, "list": ROLES, "write": ROLES, "delete": ROLES, "export": ()},
}

DEFAULT_SESSION_HOURS = 12


def _now() -> str:
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


class IdentityRegistry:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id TEXT PRIMARY KEY, provider_subject TEXT NOT NULL,
                    issuer TEXT NOT NULL, display_name TEXT, email TEXT,
                    created_at TEXT NOT NULL, disabled_at TEXT,
                    UNIQUE(issuer, provider_subject));
                CREATE TABLE IF NOT EXISTS organisations (
                    org_id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS memberships (
                    user_id TEXT NOT NULL REFERENCES users(user_id),
                    org_id TEXT NOT NULL REFERENCES organisations(org_id),
                    granted_at TEXT NOT NULL, revoked_at TEXT,
                    PRIMARY KEY(user_id, org_id));
                CREATE TABLE IF NOT EXISTS grants (
                    user_id TEXT NOT NULL REFERENCES users(user_id),
                    org_id TEXT NOT NULL REFERENCES organisations(org_id),
                    role TEXT NOT NULL, scope TEXT NOT NULL,
                    granted_by TEXT NOT NULL, granted_at TEXT NOT NULL, revoked_at TEXT,
                    PRIMARY KEY(user_id, org_id, role));
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES users(user_id),
                    issued_at TEXT NOT NULL, expires_at TEXT NOT NULL,
                    revoked_at TEXT, issuer TEXT);
                CREATE TABLE IF NOT EXISTS resource_acl (
                    resource_kind TEXT NOT NULL, resource_id TEXT NOT NULL,
                    org_id TEXT NOT NULL, owner_user_id TEXT,
                    visibility TEXT NOT NULL DEFAULT 'private',
                    PRIMARY KEY(resource_kind, resource_id));
                CREATE INDEX IF NOT EXISTS acl_by_org ON resource_acl(org_id);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.execute('PRAGMA foreign_keys=ON')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:
                yield db
        finally:
            db.close()

    # ------------------------------------------------------------ writes

    def upsert_user(self, *, provider_subject: str, issuer: str,
                    display_name: str | None = None, email: str | None = None) -> User:
        """Bind a verified provider subject to a local user.

        The `(issuer, provider_subject)` pair is the identity. An email is a
        label that can change hands and is never the key.
        """
        with self.connect() as db:
            row = db.execute(
                'SELECT user_id,created_at,disabled_at FROM users WHERE issuer=? '
                'AND provider_subject=?', (issuer, provider_subject)).fetchone()
            if row:
                db.execute('UPDATE users SET display_name=COALESCE(?,display_name),'
                           'email=COALESCE(?,email) WHERE user_id=?',
                           (display_name, email, row[0]))
                return self.user(row[0])
            user_id = 'usr_' + uuid.uuid4().hex[:16]
            created = _now()
            db.execute('INSERT INTO users VALUES (?,?,?,?,?,?,NULL)',
                       (user_id, provider_subject, issuer, display_name, email, created))
        return self.user(user_id)

    def add_organisation(self, org_id: str, name: str, kind: str) -> Organisation:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO organisations VALUES (?,?,?)',
                       (org_id, name, kind))
        return Organisation(org_id=org_id, name=name, kind=kind)

    def add_membership(self, user_id: str, org_id: str, *, at: str | None = None) -> None:
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO memberships VALUES (?,?,?,NULL)',
                       (user_id, org_id, at or _now()))

    def grant(self, user_id: str, org_id: str, role: Role, *, granted_by: str,
              scope: Scope | None = None, at: str | None = None) -> Grant:
        if role not in ROLES:
            raise ValueError(f'unknown role {role!r}')
        scope = scope or Scope()
        with self.connect() as db:
            if not db.execute('SELECT 1 FROM memberships WHERE user_id=? AND org_id=? '
                              'AND revoked_at IS NULL', (user_id, org_id)).fetchone():
                raise ValueError('grant requires a live membership in that organisation')
            db.execute('INSERT OR REPLACE INTO grants VALUES (?,?,?,?,?,?,NULL)',
                       (user_id, org_id, role, json.dumps(scope.describe()),
                        granted_by, at or _now()))
        return Grant(user_id=user_id, org_id=org_id, role=role, scope=scope,
                     granted_by=granted_by, granted_at=at or _now())

    def revoke_grant(self, user_id: str, org_id: str, role: Role,
                     *, at: str | None = None) -> None:
        """Revoke by timestamp, never by delete: the audit trail keeps the fact."""
        with self.connect() as db:
            db.execute('UPDATE grants SET revoked_at=? WHERE user_id=? AND org_id=? '
                       'AND role=? AND revoked_at IS NULL',
                       (at or _now(), user_id, org_id, role))

    def revoke_membership(self, user_id: str, org_id: str, *, at: str | None = None) -> None:
        stamp = at or _now()
        with self.connect() as db:
            db.execute('UPDATE memberships SET revoked_at=? WHERE user_id=? AND org_id=? '
                       'AND revoked_at IS NULL', (stamp, user_id, org_id))
            # Losing the membership loses every grant that depended on it.
            db.execute('UPDATE grants SET revoked_at=? WHERE user_id=? AND org_id=? '
                       'AND revoked_at IS NULL', (stamp, user_id, org_id))

    def open_session(self, user_id: str, *, hours: int = DEFAULT_SESSION_HOURS,
                     issuer: str | None = None, at: str | None = None) -> Session:
        issued = at or _now()
        expires = ist_timestamp(
            datetime.fromisoformat(issued) + timedelta(hours=hours))
        session = Session(session_id='ses_' + uuid.uuid4().hex[:20], user_id=user_id,
                          issued_at=issued, expires_at=expires, issuer=issuer)
        with self.connect() as db:
            db.execute('INSERT INTO sessions VALUES (?,?,?,?,NULL,?)',
                       (session.session_id, user_id, issued, expires, issuer))
        return session

    def revoke_session(self, session_id: str, *, at: str | None = None) -> None:
        with self.connect() as db:
            db.execute('UPDATE sessions SET revoked_at=? WHERE session_id=? '
                       'AND revoked_at IS NULL', (at or _now(), session_id))

    def register_resource(self, kind: str, resource_id: str, *, org_id: str,
                          owner_user_id: str | None = None,
                          visibility: Visibility = 'private') -> ResourceACL:
        if kind not in RESOURCE_KINDS:
            raise ValueError(f'unknown resource kind {kind!r}')
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO resource_acl VALUES (?,?,?,?,?)',
                       (kind, resource_id, org_id, owner_user_id, visibility))
        return ResourceACL(resource_kind=kind, resource_id=resource_id, org_id=org_id,
                           owner_user_id=owner_user_id, visibility=visibility)

    # ------------------------------------------------------------- reads

    def user(self, user_id: str) -> User:
        with self.connect() as db:
            row = db.execute('SELECT user_id,provider_subject,issuer,display_name,'
                             'email,created_at,disabled_at FROM users WHERE user_id=?',
                             (user_id,)).fetchone()
        if not row:
            raise AuthorizationError('unknown user')
        return User(*row)

    def organisation(self, org_id: str) -> Organisation:
        with self.connect() as db:
            row = db.execute('SELECT org_id,name,kind FROM organisations WHERE org_id=?',
                             (org_id,)).fetchone()
        if not row:
            raise AuthorizationError('unknown organisation')
        return Organisation(*row)

    def grants_for(self, user_id: str, *, at: str | None = None) -> list[Grant]:
        stamp = at or _now()
        with self.connect() as db:
            rows = db.execute(
                'SELECT g.user_id,g.org_id,g.role,g.scope,g.granted_by,g.granted_at,'
                'g.revoked_at FROM grants g JOIN memberships m '
                'ON m.user_id=g.user_id AND m.org_id=g.org_id '
                'WHERE g.user_id=? ORDER BY g.org_id, g.role', (user_id,)).fetchall()
            members = {r[0]: Membership(user_id, r[0], r[1], r[2]) for r in db.execute(
                'SELECT org_id,granted_at,revoked_at FROM memberships WHERE user_id=?',
                (user_id,))}
        out = []
        for uid, org, role, scope_json, by, at_, revoked in rows:
            scope_raw = json.loads(scope_json)
            grant = Grant(user_id=uid, org_id=org, role=role, granted_by=by,
                          granted_at=at_, revoked_at=revoked,
                          scope=Scope(own_org_only=scope_raw.get('own_org_only', True),
                                      institutions=tuple(scope_raw.get('institutions') or ()),
                                      note=scope_raw.get('note')))
            membership = members.get(org)
            if grant.active_at(stamp) and membership and membership.active_at(stamp):
                out.append(grant)
        return out

    def acl(self, kind: str, resource_id: str) -> ResourceACL | None:
        with self.connect() as db:
            row = db.execute('SELECT resource_kind,resource_id,org_id,owner_user_id,'
                             'visibility FROM resource_acl WHERE resource_kind=? '
                             'AND resource_id=?', (kind, resource_id)).fetchone()
        return ResourceACL(*row) if row else None

    # --------------------------------------------------------- resolution

    def resolve(self, session_id: str, *, requested_role: Role | None = None,
                requested_org: str | None = None, at: str | None = None) -> Principal:
        """Who is acting? Fails closed on anything unexpected.

        A requested role the user has no live grant for is refused outright —
        not downgraded silently — so a forged request is visible rather than
        quietly tolerated.
        """
        stamp = at or _now()
        with self.connect() as db:
            row = db.execute('SELECT session_id,user_id,issued_at,expires_at,revoked_at,'
                             'issuer FROM sessions WHERE session_id=?',
                             (session_id,)).fetchone()
        if not row:
            raise AuthorizationError('unknown session')
        session = Session(*row)
        if not session.active_at(stamp):
            raise AuthorizationError('session expired or revoked')
        user = self.user(session.user_id)
        if not user.active:
            raise AuthorizationError('user disabled')
        grants = self.grants_for(user.user_id, at=stamp)
        if not grants:
            raise AuthorizationError('no live grants')
        available = tuple((g.org_id, g.role) for g in grants)
        chosen = None
        if requested_role is None and requested_org is None:
            chosen = grants[0]
        else:
            for g in grants:
                if (requested_role is None or g.role == requested_role) and \
                   (requested_org is None or g.org_id == requested_org):
                    chosen = g
                    break
        if chosen is None:
            raise AuthorizationError(
                f'no live grant for role={requested_role!r} org={requested_org!r}')
        membership = self._membership(user.user_id, chosen.org_id)
        return Principal(
            user=user, org=self.organisation(chosen.org_id), role=chosen.role,
            scope=chosen.scope, session_id=session.session_id,
            available_roles=available, resolved_at=stamp,
            authorization_revision=authorization_revision(
                user=user, grant=chosen, membership=membership, session=session))

    def _membership(self, user_id: str, org_id: str) -> Membership:
        with self.connect() as db:
            row = db.execute(
                'SELECT user_id,org_id,granted_at,revoked_at FROM memberships '
                'WHERE user_id=? AND org_id=?', (user_id, org_id)).fetchone()
        if not row:
            raise AuthorizationError('no membership')
        return Membership(*row)

    # ------------------------------------------------ freshness (T04/R06)

    def revalidate(self, principal: Principal, *, at: str | None = None
                   ) -> Principal:
        """Re-read the authorization state behind a principal.

        Returns a principal reflecting CURRENT state, or raises
        `StalePrincipal`. This is what makes a cached principal safe to hold:
        it is a snapshot, and every authorization decision re-reads.
        """
        stamp = at or _now()
        try:
            fresh = self.resolve(principal.session_id,
                                 requested_role=principal.role,
                                 requested_org=principal.org_id, at=stamp)
        except AuthorizationError as exc:
            raise StalePrincipal(
                f'authorization for {principal.user_id} in {principal.org_id} '
                f'is no longer valid: {exc}') from exc
        if fresh.user_id != principal.user_id:
            raise StalePrincipal('the session now resolves to a different user')
        return fresh

    def check_revision(self, principal: Principal, *, at: str | None = None
                       ) -> Principal:
        """Assert the authorization state has not changed since resolution.

        Mutations call this inside their commit boundary. A scope narrowed or
        a grant revoked mid-request changes the revision, so the commit is
        refused rather than applied under a snapshot that is no longer true.
        """
        fresh = self.revalidate(principal, at=at)
        if (principal.authorization_revision
                and fresh.authorization_revision != principal.authorization_revision):
            raise StalePrincipal(
                'authorization changed during this request '
                f'({principal.authorization_revision} -> '
                f'{fresh.authorization_revision}); the operation was not applied')
        return fresh

    # ------------------------------------------------------ authorization

    def can(self, principal: Principal, action: str, kind: str,
            resource_id: str, *, revalidate: bool = True) -> bool:
        """May this principal do this to this resource? Unknown means no.

        T04 / audit finding R06: this re-resolves the principal by default.
        A revoked grant, a revoked or expired session, a revoked membership or
        a disabled user all deny here, not only at the next `resolve()`.

        `revalidate=False` exists ONLY for callers that have just revalidated
        and are checking many resources in one request (`visible()`); it must
        never be reachable from a request boundary.
        """
        if action not in ACTIONS or kind not in ROLE_CAPABILITY:
            return False
        if revalidate:
            try:
                principal = self.revalidate(principal)
            except StalePrincipal:
                return False
        if principal.role not in ROLE_CAPABILITY[kind].get(action, ()):
            return False
        acl = self.acl(kind, resource_id)
        if acl is None:
            # An unregistered resource has no owner, so nothing can vouch for
            # it. Denying is the only safe answer.
            return False
        if acl.visibility == 'public':
            return action in ('read', 'list')
        if not principal.scope.reaches(acl.org_id, principal.org_id):
            return False
        if acl.visibility == 'private' and acl.owner_user_id not in (
                None, principal.user_id):
            # Private means the owner's own. A regulator with an explicit
            # cross-institution scope still does not get another USER's
            # personal holdings through this path.
            return False
        return True

    def require(self, principal: Principal, action: str, kind: str,
                resource_id: str) -> Principal:
        """Authorize, or raise. Returns the REVALIDATED principal.

        Callers should use the returned principal for the rest of the
        operation: it reflects current grants, including a narrowed scope.
        """
        fresh = self.revalidate(principal)          # raises StalePrincipal
        if not self.can(fresh, action, kind, resource_id, revalidate=False):
            raise AuthorizationError(
                f'{fresh.role} in {fresh.org_id} may not {action} '
                f'{kind} {resource_id}')
        return fresh

    def visible(self, principal: Principal, kind: str,
                resource_ids) -> list[str]:
        """Filter a list down to what the principal may actually see.

        Listing goes through the same check as a direct read, so a resource
        cannot leak through an index that forgot to filter.
        """
        # Revalidate ONCE, then check each resource against the fresh
        # principal: a list of 500 portfolios must not cost 500 re-resolutions.
        try:
            fresh = self.revalidate(principal)
        except StalePrincipal:
            return []
        return [r for r in resource_ids
                if self.can(fresh, 'list', kind, r, revalidate=False)]
