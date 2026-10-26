# C11 — Saved scenarios (PRODUCT-CONTRACTS §7; SCEN01)
"""Reusable, owned, reproducible scenarios around the existing simulators.

This does **not** write a second simulator. `simulate_shock` and
`simulate_policy` keep doing the arithmetic; this adds the things that make a
scenario a work product rather than a slider:

* a stable identity and an owner, scoped like every other resource;
* the **baseline artefact id** — run, date, weights and reconciled state — so
  "reproduce this" means something. A scenario whose baseline is "whatever is
  on screen" cannot be reproduced;
* an assumption set with units and justifications, versioned, so a comparison
  between two runs can say what actually differed;
* reviewer history.

What a rank shock is and is not
-------------------------------
The existing tool shifts an ECDF-ranked pillar value. `+0.1` is a tenth of the
rank distribution — it is **not** a 10% price move, and nothing here converts
one into the other. `kind="rank_shock"` says so in the saved record, and
`kind="economic"` is refused until a propagation and valuation model exists,
rather than being quietly approximated.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

from seraph.identity import AuthorizationError, IdentityRegistry, Principal
from seraph.shared_types import IST, ist_timestamp

ENGINE_VERSION = "c11.scenario/2026-10-21.1"

ScenarioKind = Literal["rank_shock", "regime_path", "macro_path", "defensive", "economic"]

#: Kinds whose results mean something today. `economic` needs a documented
#: propagation and portfolio-valuation model, which does not exist.
SUPPORTED_KINDS = ("rank_shock", "regime_path", "macro_path", "defensive")


def _now() -> str:
    return ist_timestamp(datetime.now(IST).replace(microsecond=0))


@dataclass(frozen=True)
class Assumption:
    key: str
    value: object
    unit: str
    justification: str
    source: str | None = None

    def __post_init__(self) -> None:
        if not self.unit.strip():
            raise ValueError(f"{self.key}: an assumption needs a unit; a bare "
                             f"number is not a quantity")
        if not self.justification.strip():
            raise ValueError(f"{self.key}: an assumption needs a justification, "
                             f"so a reviewer can disagree with it")


@dataclass(frozen=True)
class Baseline:
    """Exactly what the scenario departs from."""

    run_id: str
    date: str
    weights_artefact_id: str
    reconciled_hash: str

    @property
    def artefact_id(self) -> str:
        return hashlib.sha256(
            f"{self.run_id}|{self.date}|{self.weights_artefact_id}|"
            f"{self.reconciled_hash}".encode()).hexdigest()

    def describe(self) -> dict:
        return dict(**asdict(self), artefact_id=self.artefact_id)


def baseline_from_point(point: dict) -> Baseline:
    """Pin a baseline from a persisted run point."""
    composite = point.get("composite") or {}
    reconciled = json.dumps(point.get("reconciled") or {}, sort_keys=True)
    return Baseline(run_id=point["run_id"], date=point["date"],
                    weights_artefact_id=composite.get("weights_artefact_id", ""),
                    reconciled_hash=hashlib.sha256(reconciled.encode()).hexdigest())


class ScenarioStore:
    def __init__(self, path, registry: IdentityRegistry):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = registry
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS scenarios (
                    scenario_id TEXT PRIMARY KEY, owner_user_id TEXT NOT NULL,
                    org_id TEXT NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL,
                    baseline TEXT NOT NULL, assumptions TEXT NOT NULL,
                    steps TEXT NOT NULL, assumption_version INTEGER NOT NULL,
                    created_at TEXT NOT NULL, created_by TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scenario_runs (
                    run_key TEXT PRIMARY KEY,
                    scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                    executed_at TEXT NOT NULL, engine_version TEXT NOT NULL,
                    results TEXT NOT NULL, inputs_hash TEXT NOT NULL,
                    executed_by TEXT NOT NULL,
                    -- P05: a hash tells you two runs differ, not what either
                    -- of them was. The inputs themselves are stored so an old
                    -- run can be RECONSTRUCTED and not merely compared.
                    inputs_json TEXT,
                    assumption_version INTEGER);
                CREATE TABLE IF NOT EXISTS scenario_reviews (
                    scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                    seq INTEGER NOT NULL, reviewer TEXT NOT NULL, verdict TEXT NOT NULL,
                    comment TEXT, at TEXT NOT NULL,
                    -- P05: a verdict used to be bound to the SCENARIO only,
                    -- so approving revision 1 silently approved revision 2
                    -- the moment the assumptions changed under it. A review
                    -- is of a specific revision, and of a specific run when
                    -- one was examined.
                    assumption_version INTEGER,
                    run_key TEXT,
                    PRIMARY KEY(scenario_id, seq));
                CREATE TRIGGER IF NOT EXISTS scenario_runs_no_update
                    BEFORE UPDATE ON scenario_runs
                    BEGIN SELECT RAISE(ABORT,'a scenario run is a record, not a draft'); END;

                -- P05. `revise_assumptions` used to run
                --     UPDATE scenarios SET assumptions=?, ...
                -- which DESTROYED the previous assumption text while only
                -- incrementing a version counter. Its docstring claimed "the
                -- old runs keep pointing at the old set"; they pointed at a
                -- number whose content no longer existed, so an old run could
                -- not be reconstructed and a reviewer could not see what they
                -- had approved. Revisions are append-only rows now.
                CREATE TABLE IF NOT EXISTS scenario_assumptions (
                    scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                    version INTEGER NOT NULL,
                    assumptions TEXT NOT NULL,
                    revised_at TEXT NOT NULL,
                    revised_by TEXT NOT NULL,
                    PRIMARY KEY(scenario_id, version));
                CREATE TRIGGER IF NOT EXISTS scenario_assumptions_no_update
                    BEFORE UPDATE ON scenario_assumptions
                    BEGIN SELECT RAISE(ABORT,'an assumption revision is immutable; add a new version'); END;
                CREATE TRIGGER IF NOT EXISTS scenario_assumptions_no_delete
                    BEFORE DELETE ON scenario_assumptions
                    BEGIN SELECT RAISE(ABORT,'an assumption revision is the record of what was reviewed; it cannot be deleted'); END;
            ''')
            # Backfill: a scenario created before this table existed has its
            # current assumptions as version 1. That is the only version whose
            # content survives -- earlier ones were overwritten in place and
            # are genuinely unrecoverable, which is the defect, and inventing
            # them would be worse than recording the gap.
            for row in db.execute(
                    'SELECT scenario_id, assumptions, assumption_version, '
                    'created_at, created_by FROM scenarios').fetchall():
                db.execute(
                    'INSERT OR IGNORE INTO scenario_assumptions '
                    '(scenario_id, version, assumptions, revised_at, revised_by) '
                    'VALUES (?,?,?,?,?)',
                    (row[0], row[2], row[1], row[3], row[4]))

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

    # ------------------------------------------------------------ write

    def save(self, principal: Principal, *, name: str, kind: ScenarioKind,
             baseline: Baseline, steps: list, assumptions: list[Assumption],
             visibility: str = "org") -> dict:
        if kind not in SUPPORTED_KINDS:
            raise ValueError(
                f"{kind!r} scenarios are not supported. An economic scenario needs "
                f"a documented propagation and portfolio-valuation model; a pillar "
                f"rank shock is not one and will not be relabelled as one")
        if principal.role == "retail":
            raise AuthorizationError("scenarios are an institutional/regulator tool")
        scenario_id = "sc_" + uuid.uuid4().hex[:16]
        created = _now()
        with self.connect() as db:
            body = json.dumps([asdict(a) for a in assumptions])
            db.execute('INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (scenario_id, principal.user_id, principal.org_id, name, kind,
                        json.dumps(baseline.describe()),
                        body, json.dumps(steps), 1, created, principal.user_id))
            # Version 1 is a revision like any other (P05).
            db.execute(
                'INSERT INTO scenario_assumptions (scenario_id, version, '
                'assumptions, revised_at, revised_by) VALUES (?,1,?,?,?)',
                (scenario_id, body, created, principal.user_id))
        self.registry.register_resource('scenario', scenario_id,
                                        org_id=principal.org_id,
                                        owner_user_id=principal.user_id,
                                        visibility=visibility)
        return self.scenario(principal, scenario_id)

    def revise_assumptions(self, principal: Principal, scenario_id: str,
                           assumptions: list[Assumption]) -> dict:
        """Append a new assumption version. Earlier versions are preserved.

        P05: this used to `UPDATE scenarios SET assumptions=?`, destroying
        the previous text and keeping only a counter. The old docstring
        claimed the old runs kept pointing at the old set -- they pointed at
        a version NUMBER whose content had been overwritten, so an old run
        could not be reconstructed and a reviewer could not see what they
        had approved. Now every version is a row, the triggers refuse to
        update or delete one, and `scenarios.assumptions` is maintained as a
        cache of the newest for the existing read path.
        """
        self.registry.require(principal, 'write', 'scenario', scenario_id)
        body = json.dumps([asdict(a) for a in assumptions])
        with self.connect() as db:
            current = db.execute(
                'SELECT assumption_version FROM scenarios WHERE scenario_id=?',
                (scenario_id,)).fetchone()
            if current is None:
                raise ValueError(f'no scenario {scenario_id}')
            version = int(current[0]) + 1
            db.execute(
                'INSERT INTO scenario_assumptions (scenario_id, version, '
                'assumptions, revised_at, revised_by) VALUES (?,?,?,?,?)',
                (scenario_id, version, body, _now(), principal.user_id))
            db.execute('UPDATE scenarios SET assumptions=?, '
                       'assumption_version=? WHERE scenario_id=?',
                       (body, version, scenario_id))
        return self.scenario(principal, scenario_id)

    def assumptions_at(self, principal: Principal, scenario_id: str,
                       version: int) -> dict:
        """The exact assumption set a given version held.

        This is what makes an old run reconstructable, and what a reviewer's
        verdict is bound to.
        """
        self.registry.require(principal, 'read', 'scenario', scenario_id)
        with self.connect() as db:
            row = db.execute(
                'SELECT assumptions, revised_at, revised_by FROM '
                'scenario_assumptions WHERE scenario_id=? AND version=?',
                (scenario_id, version)).fetchone()
        if row is None:
            raise ValueError(
                f'scenario {scenario_id} has no assumption version {version}. '
                f'Versions written before revisions were append-only were '
                f'overwritten in place and are unrecoverable; this is recorded '
                f'rather than reconstructed')
        return dict(scenario_id=scenario_id, version=version,
                    assumptions=json.loads(row[0]),
                    revised_at=row[1], revised_by=row[2])

    def assumption_history(self, principal: Principal,
                           scenario_id: str) -> list[dict]:
        """Every assumption version, oldest first."""
        self.registry.require(principal, 'read', 'scenario', scenario_id)
        with self.connect() as db:
            rows = db.execute(
                'SELECT version, assumptions, revised_at, revised_by FROM '
                'scenario_assumptions WHERE scenario_id=? ORDER BY version',
                (scenario_id,)).fetchall()
        return [dict(version=r[0], assumptions=json.loads(r[1]),
                     revised_at=r[2], revised_by=r[3]) for r in rows]

    def record_run(self, principal: Principal, scenario_id: str, *, results: list,
                   inputs: dict) -> dict:
        """Store an execution against the exact inputs that produced it.

        P05: the row stored `inputs_hash` and not the inputs, so a run could
        be CHECKED for sameness and never RECONSTRUCTED -- a hash tells you
        two runs differ, not what either of them was. The inputs, the
        baseline and the assumption version in force are now stored
        alongside it.
        """
        self.registry.require(principal, 'write', 'scenario', scenario_id)
        scenario = self.scenario(principal, scenario_id)
        version = scenario["assumption_version"]
        identity = dict(inputs=inputs,
                        baseline=scenario["baseline"]["artefact_id"],
                        assumption_version=version,
                        engine=ENGINE_VERSION)
        inputs_hash = hashlib.sha256(
            json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
        run_key = f"{scenario_id}:{inputs_hash[:16]}"
        executed = _now()
        with self.connect() as db:
            existing = db.execute(
                'SELECT results, inputs_json, assumption_version FROM '
                'scenario_runs WHERE run_key=?', (run_key,)).fetchone()
            if existing:
                # Same scenario, same inputs, same assumptions, same engine:
                # the same record.
                return dict(run_key=run_key, reused=True,
                            results=json.loads(existing[0]),
                            inputs=json.loads(existing[1] or '{}'),
                            assumption_version=existing[2],
                            inputs_hash=inputs_hash)
            db.execute(
                'INSERT INTO scenario_runs (run_key, scenario_id, executed_at, '
                'engine_version, results, inputs_hash, executed_by, '
                'inputs_json, assumption_version) VALUES (?,?,?,?,?,?,?,?,?)',
                (run_key, scenario_id, executed, ENGINE_VERSION,
                 json.dumps(results, default=str), inputs_hash,
                 principal.user_id,
                 json.dumps(identity, sort_keys=True, default=str), version))
        return dict(run_key=run_key, reused=False, results=results,
                    executed_at=executed, engine_version=ENGINE_VERSION,
                    inputs_hash=inputs_hash, inputs=identity,
                    assumption_version=version)

    def review(self, principal: Principal, scenario_id: str, *,
               verdict: Literal["approved", "changes_requested", "rejected"],
               comment: str | None = None,
               assumption_version: int | None = None,
               run_key: str | None = None) -> dict:
        """Record a verdict on a SPECIFIC assumption revision.

        P05: a verdict used to be bound to the scenario id and a sequence
        number only, so approving revision 1 silently became approval of
        revision 2 the moment somebody revised the assumptions underneath it.
        A reviewer's name then stood behind a set of numbers they had never
        seen.

        `assumption_version` defaults to the version in force now -- the one
        the reviewer is looking at. Passing it explicitly is how a caller
        reviewing an older revision says so, and a version that does not
        exist is refused rather than recorded.
        """
        self.registry.require(principal, 'write', 'scenario', scenario_id)
        if assumption_version is None:
            assumption_version = self.scenario(
                principal, scenario_id)["assumption_version"]
        else:
            # Refuse a verdict on a revision that does not exist.
            self.assumptions_at(principal, scenario_id, assumption_version)
        with self.connect() as db:
            if run_key is not None and not db.execute(
                    'SELECT 1 FROM scenario_runs WHERE run_key=? AND '
                    'scenario_id=?', (run_key, scenario_id)).fetchone():
                raise ValueError(
                    f'run {run_key} does not belong to scenario {scenario_id}; '
                    f'a review cannot cite a run it did not examine')
            seq = (db.execute('SELECT COALESCE(MAX(seq),0) FROM scenario_reviews '
                              'WHERE scenario_id=?', (scenario_id,)).fetchone()[0]) + 1
            db.execute(
                'INSERT INTO scenario_reviews (scenario_id, seq, reviewer, '
                'verdict, comment, at, assumption_version, run_key) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (scenario_id, seq, principal.user_id, verdict, comment,
                 _now(), assumption_version, run_key))
        return dict(scenario_id=scenario_id, seq=seq, verdict=verdict,
                    reviewer=principal.user_id,
                    assumption_version=assumption_version, run_key=run_key)

    # ------------------------------------------------------------- read

    def scenario(self, principal: Principal, scenario_id: str) -> dict:
        self.registry.require(principal, 'read', 'scenario', scenario_id)
        with self.connect() as db:
            row = db.execute(
                'SELECT scenario_id,owner_user_id,org_id,name,kind,baseline,'
                'assumptions,steps,assumption_version,created_at,created_by '
                'FROM scenarios WHERE scenario_id=?', (scenario_id,)).fetchone()
            reviews = db.execute(
                'SELECT seq,reviewer,verdict,comment,at,assumption_version,'
                'run_key FROM scenario_reviews '
                'WHERE scenario_id=? ORDER BY seq', (scenario_id,)).fetchall()
        if not row:
            raise AuthorizationError('unknown scenario')
        return dict(
            scenario_id=row[0], owner_user_id=row[1], org_id=row[2], name=row[3],
            kind=row[4], baseline=json.loads(row[5]),
            assumptions=json.loads(row[6]), steps=json.loads(row[7]),
            assumption_version=row[8], created_at=row[9], created_by=row[10],
            # P05: a verdict reads with the revision it was given on, so a
            # later revision cannot inherit it.
            reviews=[dict(seq=r[0], reviewer=r[1], verdict=r[2], comment=r[3],
                          at=r[4], assumption_version=r[5], run_key=r[6])
                     for r in reviews],
            semantics=_SEMANTICS[row[4]])

    def scenarios(self, principal: Principal) -> list[dict]:
        with self.connect() as db:
            ids = [r[0] for r in db.execute(
                'SELECT scenario_id FROM scenarios ORDER BY created_at')]
        return [self.scenario(principal, i)
                for i in self.registry.visible(principal, 'scenario', ids)]

    def runs(self, principal: Principal, scenario_id: str) -> list[dict]:
        self.registry.require(principal, 'read', 'scenario', scenario_id)
        with self.connect() as db:
            rows = db.execute(
                'SELECT run_key,executed_at,engine_version,results,inputs_hash,'
                'executed_by FROM scenario_runs WHERE scenario_id=? '
                'ORDER BY executed_at', (scenario_id,)).fetchall()
        return [dict(run_key=r[0], executed_at=r[1], engine_version=r[2],
                     results=json.loads(r[3]), inputs_hash=r[4], executed_by=r[5])
                for r in rows]

    # -------------------------------------------------------- comparison

    def compare(self, principal: Principal, left_id: str, right_id: str) -> dict:
        """What actually differs between two scenarios.

        Comparing results across different baselines is meaningless, so a
        baseline mismatch is reported as the headline difference rather than
        buried under a diff of the numbers.
        """
        left = self.scenario(principal, left_id)
        right = self.scenario(principal, right_id)
        same_baseline = (left["baseline"]["artefact_id"]
                         == right["baseline"]["artefact_id"])
        left_assumptions = {a["key"]: a for a in left["assumptions"]}
        right_assumptions = {a["key"]: a for a in right["assumptions"]}
        changed = []
        for key in sorted(set(left_assumptions) | set(right_assumptions)):
            a, b = left_assumptions.get(key), right_assumptions.get(key)
            if a is None or b is None or a["value"] != b["value"] or a["unit"] != b["unit"]:
                changed.append(dict(key=key, left=a, right=b))
        return dict(
            left=left_id, right=right_id, comparable=same_baseline,
            baseline_left=left["baseline"]["artefact_id"],
            baseline_right=right["baseline"]["artefact_id"],
            same_kind=left["kind"] == right["kind"],
            assumption_differences=changed,
            step_differences=left["steps"] != right["steps"],
            note=("results are comparable" if same_baseline else
                  "DIFFERENT BASELINES: these scenarios start from different run "
                  "states, so their results are not directly comparable. Re-run "
                  "one against the other's baseline first"))


_SEMANTICS = {
    "macro_path": "Hypothetical named covariates through a persisted fitted TVTP mapping; Hamilton production exclusion remains in force.",
    "defensive": "Ex-post wealth comparison under supplied executable prices, timing and costs; not a prospective trading recommendation.",
    "rank_shock": (
        "shifts a pillar's ECDF rank. +0.1 is a tenth of the rank distribution, "
        "NOT a 10% price move. It is an expert sensitivity diagnostic, not a "
        "forecast and not an economic shock"),
    "regime_path": (
        "propagates an explicitly supplied regime probability path. It is "
        "hypothetical: no fitted macro-to-regime mapping is applied. Identical "
        "regime weights can legitimately leave the score unchanged"),
    "economic": (
        "unsupported: needs a documented propagation and portfolio-valuation model"),
}
