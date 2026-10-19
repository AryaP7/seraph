"""C13 NI12 legal applicability and dimensional accounting regression."""
from decimal import Decimal as D
from dataclasses import replace
import pytest
from seraph.news.scenarios import TariffMeasure,tariff_cost_scenario

@pytest.fixture
def measure():
    return TariffMeasure('instrument','US','IN',('7208','7209'),'effective',D('.50'),D('.05'),'2026-01-01',excluded_products=('7209',),evidence=('https://example.org/instrument',))

def run(m,**kwargs):
    args=dict(product='7208',origin='IN',destination='US',on='2026-10-17',eligible_cost_base=D('1000'),pass_through=(D('0'),D('1')))
    args.update(kwargs)
    return tariff_cost_scenario(m,**args)

def test_reduction_is_minus_thirty_percent_of_tariff_inclusive_component(measure):
    r=run(measure)
    assert D(r['landed_component_change'])==D('-.30')
    assert [D(x) for x in r['monetary_range']]==[D('-300'),D('0')]

@pytest.mark.parametrize('overrides',[{'product':'7209'},{'origin':'CN'},{'destination':'EU'},{'on':'2025-01-01'}])
def test_exclusions_and_country_date_scope(measure,overrides):
    assert run(measure,**overrides)['status']=='inapplicable'

def test_proposal_is_not_effective_duty(measure):
    assert run(replace(measure,policy_status='proposed'))['status']=='inapplicable'

def test_unknown_base_produces_no_money(measure):
    assert run(measure,eligible_cost_base=None)['monetary_range'] is None
