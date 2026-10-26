"""C5 — measured sector jump intensities and persisted coverage (FR14, FR43).

Uses the adopted C4 detector and FR14 threshold. Intervals are caller-declared;
neither a news tag nor a missing bar is a measured zero.
"""
from dataclasses import asdict
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path

import numpy as np

from seraph.shared_types import IST
from seraph.pillars.hawkes.basket_stream import DETECTOR_VERSION
from seraph.pillars.hawkes.engine import sector_flags, SECTOR_AMBER_MULTIPLE


def root():
    return Path(os.environ.get('SERAPH_SECTOR_ARTIFACTS',
                Path(__file__).resolve().parents[3] / 'prototype_runs/hawkes_sectors'))


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def observe(stream, timeline, sector_members, *, baseline_start, baseline_end,
            observation_start, observation_end, mapping_basis):
    """Fixed-at-cutoff membership, same contributors/units in both intervals."""
    if not baseline_start <= baseline_end < observation_start <= observation_end:
        raise ValueError('Declare disjoint ordered baseline and observation intervals')
    selected = timeline.at(observation_end)
    basket = set(selected.basket if selected else ())
    days = np.asarray(stream.day, dtype=str)
    ranges = [(baseline_start, baseline_end), (observation_start, observation_end)]
    indices = [np.flatnonzero((days >= lo) & (days <= hi)) for lo, hi in ranges]
    result = dict(schema='c5-sector-observations/1', input_end=observation_end,
        baseline=dict(start=baseline_start, end=baseline_end),
        observation=dict(start=observation_start, end=observation_end),
        mapping_basis=mapping_basis, membership_policy='fixed_at_fit_cutoff',
        detector=DETECTOR_VERSION, amber_multiple=SECTOR_AMBER_MULTIPLE,
        units='negative jumps per observed session in the same eligible basket',
        sectors=[], flags={}, limitations=[
            'Intensity flags describe observed jump activity; they are not loss forecasts.',
            'Coverage refers to the supplied native bar grid, not a certified exchange-session archive.'])
    for sector, names in sorted(sector_members.items()):
        members = sorted(set(names) & basket)
        contributors = []
        for symbol in members:
            series = stream.series.get(symbol)
            # One fixed contributor set. Require each supplied bar in both
            # intervals; missing prints must not reduce the apparent intensity.
            if series is not None and all(
                    len(ix) and np.isin(ix, series.bar_index).all() for ix in indices):
                contributors.append(symbol)
        counts, sessions, manifests = [], [], []
        for ix in indices:
            sessions.append(len(set(days[ix])))
            if not len(ix) or not contributors:
                counts.append(None)
                continue
            lo, hi = int(ix[0]), int(ix[-1])
            values, manifest = stream.window(lo, hi,
                segments=[(lo, hi, tuple(contributors))], policy='fixed_at_fit_cutoff',
                declared=members, basket_id=selected.digest,
                basket_basis=mapping_basis, rebalance_date=selected.rebalance_date)
            counts.append(int(values['n_neg'].sum()))
            manifests.append(asdict(manifest))
        baseline = counts[0] / sessions[0] if counts[0] is not None and sessions[0] else None
        covered = baseline is not None and baseline > 0 and counts[1] is not None and sessions[1] > 0
        flag = (sector_flags({sector: counts[1]}, {sector: baseline}, sessions[1])[0]
                if covered else None)
        if flag:
            result['flags'][sector] = flag.flag
        result['sectors'].append(dict(sector=sector, declared_members=members,
            contributors=contributors, excluded_members=sorted(set(members)-set(contributors)),
            baseline_count=counts[0], baseline_sessions=sessions[0], baseline_rate=baseline,
            observed_count=counts[1], observed_sessions=sessions[1],
            covered=bool(covered), ratio=flag.n if flag else None,
            flag=flag.flag if flag else None, manifests=manifests,
            reason=None if covered else 'No complete common bar coverage or positive baseline'))
    result['available'] = bool(result['flags'])
    result['artifact_id'] = digest(result)
    return result


def save(result, *, directory=None):
    folder = Path(directory or root())
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (result['artifact_id'] + '.json')
    if not path.exists():
        value = dict(result, available_at=datetime.now(IST).isoformat())
        # Exclusive creation preserves the first actual availability.
        with path.open('x', encoding='utf-8') as file:
            json.dump(value, file, sort_keys=True, indent=2, allow_nan=False)
    return json.loads(path.read_text(encoding='utf-8'))


def select(as_of, *, directory=None, input_through=None):
    """Read only artifacts actually available by the requested decision."""
    moment = datetime.fromisoformat(as_of)
    if moment.tzinfo is None:
        raise ValueError('Sector decision time requires an explicit offset')
    input_end = min(as_of[:10], input_through or as_of[:10])
    candidates = []
    for path in Path(directory or root()).glob('*.json'):
        value = json.loads(path.read_text(encoding='utf-8'))
        body = {k: v for k, v in value.items() if k not in ('artifact_id', 'available_at')}
        if digest(body) != value['artifact_id']:
            raise ValueError(f'Sector artifact content mismatch: {path.name}')
        if (value['input_end'] <= input_end and
                datetime.fromisoformat(value['available_at']) <= moment):
            candidates.append(value)
    if not candidates:
        return dict(available=False, flags={}, sectors=[],
                    reason='No measured sector observation set was available at this decision',
                    requires='per-sector native intraday jump counts and declared historical baselines',
                    blocked_by='No eligible artifact at the cutoff. Acquire intraday bars via Kite or a supplied supported history, then run write_hawkes_sectors.py.',
                    note='No measured flags means no substitute is used. News mechanisms are a different subsystem.')
    return max(candidates, key=lambda v: (v['input_end'], v['available_at']))
