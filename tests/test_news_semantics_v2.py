"""C13 NI01 semantic falsification and dimensional contracts."""
from decimal import Decimal
import pytest
from seraph.news.model import Story, ExposureEdge, Event, ImpactEstimate
from seraph.news.registry import MasterData
from seraph.news.extraction import extract
from seraph.news.estimation import direction_of, reachable, aggregate_by
from seraph.product_types import Timing, SourceRef

TS = '2026-10-17T12:00:00+05:30'

def story(title, **kwargs):
    return Story(story_id='s1', source_id='official', observation_id='o1',
                 title=title, url='https://example.org/1', timing=Timing(first_seen_at=TS), **kwargs)

def event(title):
    return extract([story(title)], MasterData()).event

@pytest.mark.parametrize('title,action,assertion,policy', [
 ('RBI cuts repo rate by 25 basis points', 'decrease', 'confirmed_statement', 'unknown'),
 ('RBI holds repo rate unchanged', 'unchanged', 'confirmed_statement', 'unknown'),
 ('Government withdraws subsidy for solar manufacturers', 'withdraw', 'confirmed_statement', 'unknown'),
 ('Factory denies reports of production halt', 'stop', 'denied', 'unknown'),
 ('Government proposes 50% tariff; consultation opens', 'announce', 'confirmed_statement', 'consultation'),
 ('Company cancels planned capacity expansion', 'cancel', 'confirmed_statement', 'unknown'),
 ('Government reduces import duty from 50% to 5%', 'decrease', 'confirmed_statement', 'unknown'),
])
def test_semantic_counterexamples(title, action, assertion, policy):
    result = event(title)
    assert result.frame.action == action
    assert result.frame.assertion_status == assertion
    assert result.frame.policy_status == policy
    assert result.timing.occurred_at is None


def test_signed_bps_and_levels():
    q = event('RBI cuts repo rate by 25 basis points').frame.quantities[0]
    assert q.delta == Decimal('-25') and q.unit == 'basis_points'
    q = event('Government reduces import duty from 50% to 5%').frame.quantities[0]
    assert (q.old_level, q.new_level, q.delta, q.unit) == (Decimal('50'), Decimal('5'), Decimal('-45'), 'percentage_points')

@pytest.mark.parametrize('title', ['RBI holds repo rate unchanged', 'Factory denies reports of production halt', 'Company cancels planned capacity expansion', 'RBI publishes weekly statistical supplement', 'RBI cuts repo rate by 25 basis points'])
def test_no_category_only_sign(title):
    assert direction_of(event(title)) in ('ambiguous', 'neutral', 'unknown')


def test_syndicated_copies_are_one_origin():
    from dataclasses import replace
    one = story('Factory reports production halt', syndication_group='wire')
    copies = [replace(one, story_id=f's{i}', source_id=f'outlet{i}') for i in range(10)]
    assert extract(copies, MasterData()).event.confirmations == 1


def edge(id, a, b, confidence='high'):
    return ExposureEdge(id,a,b,'supplier',confidence=confidence,
                        evidence=(SourceRef(source_id='filing',reference='https://example.org/filing'),))


def test_graph_cycle_diamond_order():
    edges = [edge('ab','a','b','low'),edge('ac','a','c'),edge('cb','c','b'),edge('bd','b','d'),edge('dc','d','c')]
    results=[]
    for values in (edges,list(reversed(edges))):
        paths=reachable(MasterData(edges=values),('a',),max_depth=5)
        assert paths['d'].confidence == 'high'
        assert paths['d'].edges == ('ac','cb','bd')
        results.append(paths)
    assert results[0] == results[1]


def test_overlapping_and_incompatible_exposure_not_summed():
    def estimate(id, unit):
        return ImpactEstimate(id,id,'company','entity','minor','low',30,unit,'adverse',30,'export','test','1')
    for units in [('share_of_revenue','share_of_revenue'),('tonnes','MW')]:
        row=aggregate_by([estimate(str(i),u) for i,u in enumerate(units)])['company']
        assert row['exposure_magnitude'] is None
        assert row['exposure_components']


def test_later_registry_edge_not_in_earlier_replay():
    from dataclasses import replace
    e=replace(edge('ab','a','b'), known_from=TS)
    master=MasterData(edges=[e])
    assert reachable(master,('a',),known_at='2026-10-16T12:00:00+05:30') == {}
    assert 'b' in reachable(master,('a',),known_at=TS)


def test_multiple_events_keep_original_evidence_offsets():
    from seraph.news.extraction import extract_events
    s=story('RBI cuts repo rate by 25 bps. Government proposes a tariff of 5%.')
    results=extract_events([s],MasterData())
    assert len(results)==2
    text=f'{s.title}. '
    for result in results:
        for span in result.event.frame.evidence:
            assert text[span.start:span.end]==span.text
    assert results[0].event.frame.action=='decrease'
    assert results[1].event.frame.policy_status=='proposed'
