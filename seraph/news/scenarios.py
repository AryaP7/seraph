"""C13 NI12 — explicit ad-valorem accounting scenarios, never return forecasts.

The arithmetic below was written, tested and then never called: the audit of
18 October 2026 found `tariff_cost_scenario()` with no production caller, so
a reader looking at a duty change on screen saw a direction and a severity
band and nothing that said how much the landed cost of the covered article
moves. `measure_from_event` and `scenario_for` are that caller's half of the
bridge — they turn an EVENT and a documented exposure edge into the
instrument this module already knows how to price, or say exactly which
input is missing.

What the bridge will not do:

* **Invent a rate.** Both levels must come from the document's own stated
  quantities, in compatible units. One level with no predecessor prices
  nothing.
* **Invent a product scope.** The covered articles come from the exposure
  edge's `products`, which carry their own evidence, and the frame's parsed
  carve-outs are passed through as exclusions.
* **Invent a size.** With no eligible cost base there is no monetary range,
  only the landed-component change — which is arithmetic on the instrument
  itself and needs no assumption about anybody's balance sheet.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

@dataclass(frozen=True)
class TariffMeasure:
    instrument_id: str
    jurisdiction: str
    origin: str
    products: tuple[str, ...]
    policy_status: str
    old_rate: Decimal
    new_rate: Decimal
    effective_from: str
    effective_to: str | None = None
    excluded_products: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()

    def __post_init__(self):
        if not self.evidence or not self.products:
            raise ValueError('instrument needs evidence and explicit product scope')
        if any(not r.is_finite() or r < 0 for r in (self.old_rate,self.new_rate)):
            raise ValueError('rates must be finite nonnegative fractions')

    def applies(self, *, product, origin, destination, on):
        return (self.policy_status == 'effective' and self.jurisdiction == destination
                and self.origin == origin and product in self.products
                and product not in self.excluded_products
                and self.effective_from <= on
                and (not self.effective_to or on < self.effective_to))


def tariff_cost_scenario(measure, *, product, origin, destination, on,
                         eligible_cost_base: Decimal | None,
                         pass_through: tuple[Decimal, Decimal]):
    """Pass-through endpoints are caller assumptions, not fitted probabilities."""
    if not measure.applies(product=product,origin=origin,destination=destination,on=on):
        return dict(status='inapplicable', monetary_range=None)
    low,high=pass_through
    if not all(x.is_finite() for x in (low,high)) or not Decimal(0)<=low<=high<=Decimal(1):
        raise ValueError('pass-through interval must lie in [0,1]')
    price_change=(1+measure.new_rate)/(1+measure.old_rate)-1
    if eligible_cost_base is not None and (not eligible_cost_base.is_finite() or eligible_cost_base<0):
        raise ValueError('eligible cost base must be finite and nonnegative')
    values=sorted([eligible_cost_base*price_change*x for x in (low,high)]) if eligible_cost_base is not None else None
    return dict(status='conditional_scenario',landed_component_change=str(price_change),
                monetary_range=[str(v) for v in values] if values else None,
                assumption='unchanged tax base, exchange rate, freight and other taxes; pass-through supplied by caller',
                prediction_status='not_a_return_forecast',evidence=list(measure.evidence))


#: Quantity measures that name an ad-valorem duty rate, and the units they
#: may arrive in. A rate in basis points with no level, or a tonnage, is not
#: an ad-valorem rate and must not be read as one.
RATE_MEASURES = frozenset({'tariff_rate', 'import_duty'})
RATE_UNITS = {'percentage_points': Decimal(100), 'percent': Decimal(100),
              'fraction': Decimal(1)}

#: Legal stages at which an instrument has rates worth pricing. A proposal
#: prices nothing, and the scenario's own `applies()` refuses anything but
#: `effective` — an adopted measure returns `inapplicable`, which is the
#: correct answer and a different one from "we could not build it".
PRICEABLE_STAGES = frozenset({'effective', 'adopted'})


def _rate_pair(frame):
    """The old and new ad-valorem rates as fractions, or a reason there are none."""
    for quantity in getattr(frame, 'quantities', ()) or ():
        if quantity.measure not in RATE_MEASURES:
            continue
        scale = RATE_UNITS.get(quantity.unit)
        if scale is None:
            return None, (f'the stated rate is in {quantity.unit!r}, which is '
                          f'not an ad-valorem unit this scenario can price')
        if quantity.old_level is None or quantity.new_level is None:
            return None, ('the document states one rate level and not the '
                          'other, so the change in landed cost cannot be '
                          'computed from it')
        try:
            return (Decimal(quantity.old_level) / scale,
                    Decimal(quantity.new_level) / scale), None
        except (InvalidOperation, ArithmeticError):
            return None, 'the stated rates are not finite numbers'
    return None, 'the document states no ad-valorem duty rate'


def measure_from_event(event, master, *, edge=None):
    """Build the instrument this module prices, or say what is missing.

    Returns `{status: 'available', measure: TariffMeasure}` or
    `{status: 'unavailable', reasons: [...]}`. Never a partially invented
    instrument: `TariffMeasure` itself refuses one without evidence and an
    explicit product scope, and that refusal is the point.
    """
    frame = getattr(event, 'frame', None)
    reasons = []
    if frame is None or frame.assertion_status != 'confirmed_statement':
        reasons.append('the document does not confirm the measure')
    if frame is not None and frame.policy_status not in PRICEABLE_STAGES:
        reasons.append(f'legal stage is {frame.policy_status!r}: nothing is '
                       f'decided that could change a landed cost')
    rates, why = _rate_pair(frame) if frame is not None else (None, 'no frame')
    if rates is None:
        reasons.append(why)

    jurisdiction = next((node for node, role in event.locations
                         if role == 'issuer_jurisdiction'), None)
    origin = next((node for node, role in event.locations
                   if role == 'subject_origin'), None)
    if origin is None:
        origin = next((o for o in event.exposure_origins if o != jurisdiction), None)
    if edge is not None and origin is None:
        origin = edge.from_id
    if jurisdiction is None:
        reasons.append('the issuing jurisdiction is not established, so the '
                       'destination market of the duty is unknown')
    if origin is None:
        reasons.append('the origin of the covered goods is not established')

    products = tuple(getattr(edge, 'products', ()) or ())
    if not products:
        reasons.append('no documented relationship names the covered '
                       'products, and a product scope is not inferred from a '
                       'headline')
    evidence = tuple(sorted({span.text for span in getattr(frame, 'evidence', ())
                             if span.field in ('old_new_rate', 'rate_level',
                                               'instrument_id', 'effective_at')})) \
        or (event.event_id,)
    effective_from = (event.timing.effective_at
                      or (frame.effective_at if frame is not None else None)
                      or event.timing.first_seen_at)
    if not effective_from:
        reasons.append('no date from which the measure applies')
    if reasons:
        return dict(status='unavailable', reasons=reasons)
    return dict(status='available', measure=TariffMeasure(
        instrument_id=(event.instrument_ids[0] if event.instrument_ids
                       else event.event_id),
        jurisdiction=jurisdiction, origin=origin, products=products,
        policy_status=frame.policy_status,
        old_rate=rates[0], new_rate=rates[1],
        effective_from=effective_from,
        excluded_products=tuple(frame.excluded_products),
        evidence=evidence))


#: With no assumption supplied, the admissible interval is the whole of it.
#: Stated as bounds rather than a midpoint on purpose: a pass-through of
#: "somewhere between none and all of it" is honest, and a fitted-looking
#: 0.6 would not be.
UNASSUMED_PASS_THROUGH = (Decimal(0), Decimal(1))


def scenario_for(event, master, *, edge=None, on=None,
                 eligible_cost_base=None, pass_through=None,
                 product=None):
    """Price one documented route, with every input named.

    This is the production path the audit found missing. It is deliberately
    forthcoming about refusing: a reader who sees `unavailable` with its
    reasons learns more than one who sees a number assembled from defaults.
    """
    built = measure_from_event(event, master, edge=edge)
    if built['status'] != 'available':
        return dict(status='unavailable', reasons=built['reasons'],
                    note=('a scenario needs a stated rate change, a product '
                          'scope from a documented relationship, an origin '
                          'and a destination. None of them is inferred'))
    measure = built['measure']
    product = product or measure.products[0]
    assumed = pass_through or UNASSUMED_PASS_THROUGH
    result = tariff_cost_scenario(
        measure, product=product, origin=measure.origin,
        destination=measure.jurisdiction,
        on=on or event.timing.first_seen_at,
        eligible_cost_base=eligible_cost_base, pass_through=assumed)
    result.update(
        instrument_id=measure.instrument_id, product=product,
        origin=measure.origin, destination=measure.jurisdiction,
        old_rate=str(measure.old_rate), new_rate=str(measure.new_rate),
        effective_from=measure.effective_from,
        excluded_products=list(measure.excluded_products),
        pass_through=[str(x) for x in assumed],
        pass_through_basis=('caller assumption' if pass_through else
                            'no assumption supplied: the full admissible '
                            '[0,1] interval, which is bounds rather than an '
                            'estimate'),
        monetary_basis=('eligible cost base supplied by the caller'
                        if eligible_cost_base is not None else
                        'no monetary range: the exposure is unsized, and an '
                        'unsized relationship produces no money'))
    if result['status'] == 'inapplicable':
        result['reasons'] = [
            f'the instrument does not apply to {product!r} from '
            f'{measure.origin} into {measure.jurisdiction} at '
            f'{on or event.timing.first_seen_at}: its stage is '
            f'{measure.policy_status!r}, it runs from '
            f'{measure.effective_from}, and its exclusions are '
            f'{list(measure.excluded_products)}']
    return result
