"""C10 — bounded stored-run adapter for FR32–FR36; never fabricates missing modes."""
from datetime import datetime
import hashlib
import json
from pathlib import Path

from seraph.shared_types import PILLAR_ORDER, ReconciledState
from seraph.validation.experiment import LabelledEpoch, Observation
from seraph.validation.epochs import EPOCH_BREAKS


def derive_reconciliation(store, run_id, *, mode, cutoff):
    """Bounded replay of the actual archived pillar inputs through C8.

    The resulting state is computed independently, never copied from Kalman
    and relabelled. No model refit or evaluation is performed here.
    """
    from seraph.orchestration.prototype import InferenceSession
    run = next((r for r in store.runs() if r['id'] == run_id), None)
    if not run or run['status'] != 'complete':
        raise ValueError('Select a complete source run')
    if any(w in str(run['manifest'].get('mode', '')).lower() for w in ('synthetic', 'fixture', 'demo')):
        raise ValueError('Real reconciliation derivation requires real source observations')
    moment = datetime.fromisoformat(cutoff)
    if moment.tzinfo is None:
        raise ValueError('cutoff requires an explicit timezone')
    rows = [p for p in store.points(run_id) if datetime.fromisoformat(p['evaluation_timestamp']) <= moment]
    if not rows:
        raise ValueError('No eligible actual observations at cutoff')
    source_hash = hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest()
    manifest = dict(mode='historical observation reconciliation replay',
        source_run=run_id, source_points_sha256=source_hash, reconciliation_mode=mode,
        cutoff=cutoff, data_available_through=rows[-1]['date'],
        implementation_hashes={name: hashlib.sha256((Path(__file__).resolve().parents[1]/name).read_bytes()).hexdigest()
            for name in ('orchestration/prototype.py', 'reconciliation/kalman.py')},
        semantics='Recomputed from the archived eligible original pillar observations; no new fit or labels')
    target = store.begin(manifest)
    session = InferenceSession([p['date'] for p in rows], reconciliation_mode=mode)
    for point in rows:
        originals = {p:dict(v) for p,v in point['original_pillars'].items()}
        # This named legacy archive predates explicit absence fields. Its
        # standing NOT_PRODUCTION decision is structural, not a feed outage.
        h = originals.get('hamilton', {})
        if not h.get('score_eligible') and 'absence' not in h and h.get('origin') == 'causal research archive NOT_PRODUCTION':
            h.update(absence='structural', absence_reason='no_data_coverage')
        derived = session.step(point['date'], originals,
                               point.get('astra_predictions') or [], run_id=target)
        if derived['evaluation_timestamp'] != point['evaluation_timestamp']:
            raise ValueError('Derived decision clock differs from the archived source clock')
        store.put(target, derived)
    store.finish(target, len(rows))
    return target


def from_run_store(store, run_ids, epoch_definitions, *, cutoff,
                   required_modes=('kalman', 'forward_fill')):
    """Definitions supply explicit session axes and evaluation windows.

    Each definition has start/end, break_date, and sessions (the observed
    exchange axis, including normal sessions). Labels cover the first 30
    sessions at/after the declared break. No score-derived labels or copied
    reconciliation modes are permitted.
    """
    cutoff_ts = datetime.fromisoformat(cutoff)
    if cutoff_ts.tzinfo is None:
        raise ValueError('cutoff must have an explicit offset')
    manifests = {r['id']: r for r in store.runs()}
    points, provenance = {}, []
    for run_id in run_ids:
        run = manifests.get(run_id)
        if not run or run['status'] != 'complete':
            raise ValueError(f'{run_id}: select a complete stored run')
        if any(word in str(run['manifest'].get('mode', '')).lower()
               for word in ('synthetic', 'fixture', 'demo')):
            raise ValueError('synthetic/demo runs cannot enter the real-data adapter')
        rows = store.points(run_id)
        provenance.append(dict(run_id=run_id, manifest=run['manifest'],
                               points_sha256=hashlib.sha256(json.dumps(
                                   rows, sort_keys=True).encode()).hexdigest()))
        for point in rows:
            if datetime.fromisoformat(point['evaluation_timestamp']) > cutoff_ts:
                continue
            if datetime.fromisoformat(point['data_cutoff']) > datetime.fromisoformat(point['evaluation_timestamp']):
                raise ValueError('stored state contains a future data cutoff')
            raw = point.get('reconciled')
            if not raw:
                continue
            state = ReconciledState.model_validate(raw)
            evaluation = datetime.fromisoformat(point['evaluation_timestamp'])
            if datetime.fromisoformat(state.ts) > evaluation or any(
                tau and datetime.fromisoformat(tau) > evaluation
                for tau in state.tau_last_update):
                raise ValueError('stored state contains future observations')
            if state.mode not in required_modes:
                continue
            key = (point['date'], state.mode)
            if key in points and points[key] != point:
                raise ValueError(f'ambiguous duplicate state at {key}; select one run')
            points[key] = point
    dataset, coverage = {}, {}
    for epoch, definition in epoch_definitions.items():
        if epoch not in EPOCH_BREAKS or definition['break_date'] != EPOCH_BREAKS[epoch][0]:
            raise ValueError('epoch break differs from the declared project label')
        sessions = definition['sessions']
        if sessions != sorted(set(sessions)):
            raise ValueError('epoch sessions must be unique and ordered')
        positive = set([s for s in sessions if s >= definition['break_date']][:30])
        modes, missing = {}, {}
        for mode in required_modes:
            observed = []
            missing[mode] = []
            for day in sessions:
                if not definition['start'] <= day <= definition['end']:
                    continue
                point = points.get((day, mode))
                if point is None:
                    missing[mode].append(day)
                    continue
                state = ReconciledState.model_validate(point['reconciled'])
                # Use stored probabilities only; uniform production weighting
                # is not a substitute for a missing Hamilton probability.
                detail = point['original_pillars'].get('hamilton', {}).get('detail') or {}
                xi = detail.get('xi')
                if xi is None and all(k in detail for k in ('xi1', 'xi2', 'xi3')):
                    xi = [detail[k] for k in ('xi1', 'xi2', 'xi3')]
                if xi is None:
                    missing[mode].append(day)
                    continue
                observed.append(Observation(state, tuple(xi), int(day in positive)))
            if observed:
                modes[mode] = tuple(observed)
        observations = [o for rows in modes.values() for o in rows]
        pillars = frozenset(p for i, p in enumerate(PILLAR_ORDER)
                            if observations and all(o.state.mask[i] for o in observations))
        dataset[epoch] = LabelledEpoch(epoch, pillars, modes)
        coverage[epoch] = dict(observations={m: len(v) for m, v in modes.items()},
                               missing=missing, pillar_coverage=sorted(pillars),
                               label_provenance=EPOCH_BREAKS[epoch][1])
    return dict(dataset=dataset, provenance_manifest=dict(
        kind='stored historical observations', cutoff=cutoff, runs=provenance,
        epoch_definitions=epoch_definitions), coverage_report=coverage)
