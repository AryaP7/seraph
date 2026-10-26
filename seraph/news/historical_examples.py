"""C13/FR48 — a cited historical accounting case using the existing calculator.

This is a curated worked example, not an extracted live event or current law.
Proclamation 10947 paragraphs 7 and operative clauses 1–2 state both levels.
The UK exception is outside this India-origin covered-steel example.
"""
from decimal import Decimal

from seraph.news.scenarios import TariffMeasure, tariff_cost_scenario

CASE_ID = 'historical:us-steel-10947'
SOURCE = 'https://www.govinfo.gov/content/pkg/DCPD-202500655/html/DCPD-202500655.htm'


def run(*, role, cost_base=None, pass_through=None):
    from seraph.news.workflows import _permit, _decimal
    _permit(role, 'scenario')
    base = _decimal(cost_base, 'old duty-inclusive covered component cost', low=Decimal(0))
    interval = (tuple(_decimal(v, 'pass-through', low=Decimal(0), high=Decimal(1))
                      for v in pass_through) if pass_through else (Decimal(0), Decimal(1)))
    if len(interval) != 2 or any(x is None for x in interval):
        raise ValueError('Supply both pass-through endpoints')
    measure = TariffMeasure('US Proclamation 10947', 'US', 'IN',
        ('covered steel articles',), 'effective', Decimal('.25'), Decimal('.50'),
        '2025-06-04T09:31:00+05:30', evidence=(SOURCE,
            'https://www.federalregister.gov/documents/2025/06/09/2025-10524/adjusting-imports-of-aluminum-and-steel-into-the-united-states'))
    result = tariff_cost_scenario(measure, product='covered steel articles', origin='IN',
        destination='US', on='2025-06-09T15:30:00+05:30',
        eligible_cost_base=base, pass_through=interval)
    result.update(kind='news_scenario', event_id=CASE_ID,
        headline='Historical worked example: covered India-origin steel, June 2025',
        old_rate='.25', new_rate='.50', effective_from=measure.effective_from,
        inputs=dict(cost_base=str(base) if base is not None else None,
            pass_through=[str(v) for v in interval], product='covered steel articles',
            as_of='2025-06-09T15:30:00+05:30',
            cost_basis='Covered component including the OLD 25% Section 232 duty; same currency before/after',
            supplied_by='caller assumptions; not observed company costs'),
        curation=dict(source=SOURCE, instrument='Proclamation 10947',
            retrieved_document_sha256='96936b7771c33e62fa15bee1448674f7646d68821c08af043c2fcb53ac87eac4',
            verified_at='2026-10-21',
            issued_on='2025-06-03', federal_register_published_on='2025-06-09',
            evidence_location='paragraph 7 and operative clauses 1–2; UK exception in clause 7'),
        limitations=['Historical conditional example, not a statement of the tariff applying today.',
            'Only goods actually within the proclamation scope; UK treatment and unrelated duties are excluded.',
            'No FX, customs valuation, volume, substitution or company exposure is inferred.'])
    return result
