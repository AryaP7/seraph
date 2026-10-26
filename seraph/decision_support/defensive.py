"""C11 — declared historical defensive-action wealth comparisons (FR46).

Buy-and-hold positions with one declared execution. Linear hedges use daily
cash settlement; puts require supplied option premiums. No prices are imputed.
"""
from datetime import datetime
import hashlib
import json
import math

import numpy as np

ACTIONS = ('none', 'reduce_to_cash', 'sector_rotation', 'hedge_ratio', 'index_put')


def finite(value, name, *, minimum=None, maximum=None):
    number = float(value)
    if (not math.isfinite(number) or (minimum is not None and number < minimum)
            or (maximum is not None and number > maximum)):
        raise ValueError(f'{name} is outside its finite supported range')
    return number


def instant(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError('Decision and valuation times require explicit offsets')
    return moment


def drawdowns(wealth):
    values = np.asarray(wealth, dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError('Nonpositive wealth is outside this unlevered comparison model')
    path = 1-values/np.maximum.accumulate(values)
    return path.tolist(), float(path.max())


def compare(request):
    """Return all supported action paths and explicit per-action refusals."""
    if not request.get('epoch') or not request.get('currency'):
        raise ValueError('An epoch and valuation currency are required')
    dates = request['valuation_times']
    moments = [instant(t) for t in dates]
    if len(moments) < 2 or moments != sorted(set(moments)):
        raise ValueError('At least two unique ordered valuation times are required')
    decision = instant(request['decision_at'])
    if decision < moments[0]:
        raise ValueError('Include a baseline valuation at or before the decision')
    cash = finite(request['initial_cash'], 'initial_cash', minimum=0)
    cash_rate = finite(request['cash_rate_per_session'], 'cash rate', minimum=-.99)
    series = request['series']
    positions = {}
    for row in request['positions']:
        symbol = row['instrument']
        if symbol in positions:
            raise ValueError('Duplicate positions must be consolidated explicitly')
        positions[symbol] = finite(row['quantity'], 'position quantity', minimum=0)
    if not positions:
        raise ValueError('At least one baseline position is required')
    prices, multipliers = {}, {}

    def load(symbol, expected=None):
        if symbol not in series:
            raise ValueError(f'Missing supplied price history for {symbol}')
        item = series[symbol]
        if item['currency'] != request['currency']:
            raise ValueError('Mixed currencies require dated FX conversion before comparison')
        if expected and item['kind'] not in expected:
            raise ValueError(f'{symbol} needs instrument kind {expected}; an index is not an option or a futures contract')
        if not item.get('source') or not item.get('price_basis') or item.get('mode') not in (
                'historical_observation', 'user_supplied', 'synthetic_test'):
            raise ValueError(f'{symbol} needs source, price basis and evidence mode')
        stamps = [p['at'] for p in item['prices']]
        if stamps != dates:
            raise ValueError(f'{symbol} has missing or misaligned prices; no filling is performed')
        values = np.asarray([finite(p['price'], 'price', minimum=0) for p in item['prices']])
        if item['kind'] != 'index_put' and (values <= 0).any():
            raise ValueError('Non-option prices must be strictly positive')
        multiplier = finite(item['multiplier'], 'contract multiplier', minimum=1e-12)
        prices[symbol], multipliers[symbol] = values, multiplier
        return values

    for symbol in positions:
        load(symbol, ('equity', 'sector_index', 'index'))
    baseline = []
    running_cash = cash
    for i in range(len(dates)):
        if i:
            running_cash *= 1+cash_rate
        baseline.append(running_cash+sum(q*prices[s][i]*multipliers[s] for s,q in positions.items()))
    base_dd, base_mdd = drawdowns(baseline)
    results = []
    ids = [a['id'] for a in request['actions']]
    if len(set(ids)) != len(ids):
        raise ValueError('Action IDs must be unique')
    for action in request['actions']:
        try:
            kind = action['type']
            if kind not in ACTIONS:
                raise ValueError(f'Unsupported action {kind}')
            execution = instant(action['execution_at'])
            if execution <= decision or execution not in moments:
                raise ValueError('Execution must be a supplied executable price strictly after the decision')
            start = moments.index(execution)
            if start == 0:
                raise ValueError('Include a pre-execution valuation so transaction costs enter drawdown')
            cost_bps = finite(action['transaction_cost_bps'], 'cost bps', minimum=0)
            fixed = finite(action['fixed_cost'], 'fixed cost', minimum=0)
            carry = finite(action['carry_per_session'], 'carry per session', minimum=0)
            held, available_cash = dict(positions), cash
            hedge_symbol, hedge_units, margin = None, 0., 0.
            turnover, costs, carry_total = 0., 0., 0.
            wealth, cash_path, transactions = [], [], []
            if kind in ('sector_rotation', 'hedge_ratio', 'index_put'):
                instrument = action['instrument']
                expected = {'sector_rotation': ('equity', 'sector_index'),
                            'hedge_ratio': ('linear_hedge',), 'index_put': ('index_put',)}[kind]
                load(instrument, expected)
                if kind == 'index_put':
                    option = series[instrument]
                    finite(option['strike'], 'put strike', minimum=1e-12)
                    if not option.get('underlying') or instant(option['expiry_at']) < moments[-1]:
                        raise ValueError('Put window must end by expiry; post-expiry settlement requires a separate cash-settlement history')
                    if option['price_basis'] != 'observed_option_premium':
                        raise ValueError('Put overlay requires observed option premium history')
            for i, at in enumerate(dates):
                if i:
                    available_cash *= 1+cash_rate
                if i > start:
                    if hedge_symbol:
                        available_cash -= hedge_units*(prices[hedge_symbol][i]-prices[hedge_symbol][i-1])*multipliers[hedge_symbol]
                    available_cash -= carry
                    carry_total += carry
                if i == start:
                    if kind in ('reduce_to_cash', 'sector_rotation'):
                        fraction = finite(action['fraction'], 'sale fraction', minimum=0, maximum=1)
                        proceeds = 0.
                        for symbol, quantity in list(held.items()):
                            sold = fraction*quantity
                            amount = sold*prices[symbol][i]*multipliers[symbol]
                            held[symbol] -= sold
                            proceeds += amount
                            transactions.append(dict(at=at, instrument=symbol, quantity=-sold, amount=amount))
                        available_cash += proceeds
                        turnover += proceeds
                        if kind == 'sector_rotation':
                            purchased = proceeds/(prices[instrument][i]*multipliers[instrument])
                            held[instrument] = held.get(instrument, 0.)+purchased
                            available_cash -= proceeds
                            turnover += proceeds
                            transactions.append(dict(at=at, instrument=instrument, quantity=purchased, amount=-proceeds))
                    elif kind == 'hedge_ratio':
                        ratio = finite(action['hedge_ratio'], 'hedge ratio', minimum=0, maximum=1)
                        notional = ratio*sum(q*prices[s][i]*multipliers[s] for s,q in held.items())
                        hedge_symbol = instrument
                        hedge_units = notional/(prices[instrument][i]*multipliers[instrument])
                        margin = notional*finite(action['margin_fraction'], 'margin fraction', minimum=0, maximum=1)
                        turnover += notional
                        transactions.append(dict(at=at, instrument=instrument, quantity=-hedge_units,
                                                 notional=notional, convention='short linear contract; daily cash settlement'))
                    elif kind == 'index_put':
                        quantity = finite(action['quantity'], 'put contracts', minimum=0)
                        amount = quantity*prices[instrument][i]*multipliers[instrument]
                        held[instrument] = held.get(instrument, 0.)+quantity
                        available_cash -= amount
                        turnover += amount
                        transactions.append(dict(at=at, instrument=instrument, quantity=quantity, amount=-amount))
                    if kind == 'none' and (cost_bps or fixed or carry):
                        raise ValueError('No-op must have zero action costs and carry')
                    costs = turnover*cost_bps/10000 + (fixed if turnover else 0.)
                    available_cash -= costs
                if available_cash < margin-1e-8:
                    raise ValueError('Insufficient cash for costs, premium, carry or declared hedge margin; borrowing is not assumed')
                wealth.append(available_cash+sum(q*prices[s][i]*multipliers[s] for s,q in held.items()))
                cash_path.append(available_cash)
            dd, mdd = drawdowns(wealth)
            reduction = 100*(base_mdd-mdd)
            results.append(dict(id=action['id'], type=kind, status='available', wealth=wealth,
                cash=cash_path, drawdown=dd, maximum_drawdown=mdd,
                reduction_percentage_points=reduction,
                relative_reduction_pct=100*(base_mdd-mdd)/base_mdd if base_mdd else None,
                transactions=transactions, transaction_cost=costs, carry_cost=carry_total,
                ending_positions=held, hedge_units=hedge_units, required_cash_margin=margin))
        except (ValueError, KeyError, TypeError) as exc:
            results.append(dict(id=action.get('id'), type=action.get('type'), status='unsupported', reason=str(exc)))
    ranked = sorted((r for r in results if r['status']=='available'), key=lambda r:r['maximum_drawdown'])
    raw = json.dumps(request, sort_keys=True, allow_nan=False)
    return dict(schema='defensive-comparison/1', epoch=request['epoch'],
        currency=request['currency'], valuation_times=dates, input_sha256=hashlib.sha256(raw.encode()).hexdigest(),
        baseline=dict(wealth=baseline, drawdown=base_dd, maximum_drawdown=base_mdd),
        actions=results, ex_post_ranking=[r['id'] for r in ranked],
        evidence_modes=sorted({v['mode'] for v in series.values()}),
        limitations=['Ex-post comparison among supplied actions, not a prospective recommendation.',
            'Buy-and-hold baseline, one execution, supplied prices, no inferred dividends or financing.',
            'Sector/index paths are conditional notional exposures unless an executable instrument is supplied.',
            'Declared cash rate accrues per supplied valuation interval; hedge margin is held constant and cash-settled.'])
