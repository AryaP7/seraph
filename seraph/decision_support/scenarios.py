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

ENGINE_VERSION = "c11.scenario/2026-10-16.1"

ScenarioKind = Literal["rank_shock", "regime_path", "economic"]

#: Kinds whose results mean something today. `economic` needs a documented
#: propagation and portfolio-valuation model, which does not exist.
SUPPORTED_KINDS = ("rank_shock", "regime_path")


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
                    executed_by TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS scenario_reviews (
                    scenario_id TEXT NOT NULL REFERENCES scenarios(scenario_id),
                    seq INTEGER NOT NULL, reviewer TEXT NOT NULL, verdict TEXT NOT NULL,
                    comment TEXT, at TEXT NOT NULL, PRIMARY KEY(scenario_id, seq));
                CREATE TRIGGER IF NOT EXISTS scenario_runs_no_update
                    BEFORE UPDATE ON scenario_runs
                    BEGIN SELECT RAISE(ABORT,'a scenario run is a record, not a draft'); END;
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
            db.execute('INSERT INTO scenarios VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                       (scenario_id, principal.user_id, principal.org_id, name, kind,
                        json.dumps(baseline.describe()),
                        json.dumps([asdict(a) for a in assumptions]),
                        json.dumps(steps), 1, created, principal.user_id))
        self.registry.register_resource('scenario', scenario_id,
                                        org_id=principal.org_id,
                                        owner_user_id=principal.user_id,
                                        visibility=visibility)
        return self.scenario(principal, scenario_id)

    def revise_assumptions(self, principal: Principal, scenario_id: str,
                           assumptions: list[Assumption]) -> dict:
        """A new assumption version. The old runs keep pointing at the old set."""
        self.registry.require(principal, 'write', 'scenario', scenario_id)
        with self.connect() as db:
            db.execute('UPDATE scenarios SET assumptions=?, '
                       'assumption_version=assumption_version+1 WHERE scenario_id=?',
                       (json.dumps([asdict(a) for a in assumptions]), scenario_id))
        return self.scenario(principal, scenario_id)

    def record_run(self, principal: Principal, scenario_id: str, *, results: list,
                   inputs: dict) -> dict:
        """Store an execution against the exact inputs that produced it."""
        self.registry.require(principal, 'write', 'scenario', scenario_id)
        scenario = self.scenario(principal, scenario_id)
        inputs_hash = hashlib.sha256(
            json.dumps(dict(inputs=inputs,
                            baseline=scenario["baseline"]["artefact_id"],
                            assumption_version=scenario["assumption_version"],
                            engine=ENGINE_VERSION),
                       sort_keys=True, default=str).encode()).hexdigest()
        run_key = f"{scenario_id}:{inputs_hash[:16]}"
        executed = _now()
        with self.connect() as db:
            existing = db.execute(
                'SELECT results FROM scenario_runs WHERE run_key=?',
                (run_key,)).fetchone()
            if existing:
                # Same scenario, same inputs, same engine: the same record.
                return dict(run_key=run_key, reused=True,
                            results=json.loads(existing[0]),
                            inputs_hash=inputs_hash)
            db.execute('INSERT INTO scenario_runs VALUES (?,?,?,?,?,?,?)',
                       (run_key, scenario_id, executed, ENGINE_VERSION,
                        json.dumps(results, default=str), inputs_hash,
                        principal.user_id))
        return dict(run_key=run_key, reused=False, results=results,
                    executed_at=executed, engine_version=ENGINE_VERSION,
                    inputs_hash=inputs_hash)

    def review(self, principal: Principal, scenario_id: str, *,
               verdict: Literal["approved", "changes_requested", "rejected"],
               comment: str | None = None) -> dict:
        self.registry.require(principal, 'write', 'scenario', scenario_id)
        with self.connect() as db:
            seq = (db.execute('SELECT COALESCE(MAX(seq),0) FROM scenario_reviews '
                              'WHERE scenario_id=?', (scenario_id,)).fetchone()[0]) + 1
            db.execute('INSERT INTO scenario_reviews VALUES (?,?,?,?,?,?)',
                       (scenario_id, seq, principal.user_id, verdict, comment, _now()))
        return dict(scenario_id=scenario_id, seq=seq, verdict=verdict,
                    reviewer=principal.user_id)

    # ------------------------------------------------------------- read

    def scenario(self, principal: Principal, scenario_id: str) -> dict:
        self.registry.require(principal, 'read', 'scenario', scenario_id)
        with self.connect() as db:
            row = db.execute(
                'SELECT scenario_id,owner_user_id,org_id,name,kind,baseline,'
                'assumptions,steps,assumption_version,created_at,created_by '
                'FROM scenarios WHERE scenario_id=?', (scenario_id,)).fetchone()
            reviews = db.execute(
                'SELECT seq,reviewer,verdict,comment,at FROM scenario_reviews '
                'WHERE scenario_id=? ORDER BY seq', (scenario_id,)).fetchall()
        if not row:
            raise AuthorizationError('unknown scenario')
        return dict(
            scenario_id=row[0], owner_user_id=row[1], org_id=row[2], name=row[3],
            kind=row[4], baseline=json.loads(row[5]),
            assumptions=json.loads(row[6]), steps=json.loads(row[7]),
            assumption_version=row[8], created_at=row[9], created_by=row[10],
            reviews=[dict(seq=r[0], reviewer=r[1], verdict=r[2], comment=r[3],
                          at=r[4]) for r in reviews],
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
