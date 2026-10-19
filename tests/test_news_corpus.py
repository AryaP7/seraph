from seraph.validation.news_corpus import score_gold, agreed_labels, digest, load_corpus
from seraph.validation.news_gate import REQUIRED_SLICES, SliceResult
import json
import pytest
from types import SimpleNamespace
from seraph.validation.news_corpus import export_corpus, import_reviews, evaluate_corpus
from seraph.validation.news_gate import Checks


def test_wrong_numeric_value_and_action_are_not_credited_for_existing():
    slices = {name:SliceResult(name) for name in REQUIRED_SLICES}
    gold = dict(event_type='import_duty_change', policy_status='effective', action='decrease',
                targets=['sector:steel'], quantities=[dict(measure='duty', old_level=50, new_level=5, delta=-45, unit='percent')])
    prediction = dict(gold, action='increase', quantities=[dict(measure='duty', old_level=50, new_level=15, delta=-35, unit='bps')])
    score_gold(slices, prediction, gold)
    assert slices['field_action'].correct == 0
    assert slices['field_numeric'].correct == 0
    assert slices['field_unit'].correct == 0
    assert slices['class_recall'].correct == 1


def test_empty_quantities_do_not_inflate_numeric_score():
    slices = {name:SliceResult(name) for name in REQUIRED_SLICES}
    gold = dict(event_type='other', policy_status='unknown', action='unknown', targets=[], quantities=[])
    score_gold(slices, gold, gold)
    assert slices['field_numeric'].predicted == 0
    assert slices['link_precision'].predicted == 0


def test_two_agent_reviewers_do_not_satisfy_human_review_requirement():
    manifest = {'documents':[{'document_id':'d','hash':'h'}]}
    labels = dict(event_type='other', policy_status='unknown', action='unknown', targets=[], quantities=[])
    reviews = [dict(document_id='d', document_hash='h', reviewer_id=r, reviewer_kind='agent',
                    independent=True, category='hard_negatives', labels=labels) for r in ('one','two')]
    assert agreed_labels(manifest, reviews) == ({}, ['d'])
    for review in reviews:
        review['reviewer_kind'] = 'human'
    assert agreed_labels(manifest, reviews)[1] == []
    reviews[1] = dict(reviews[1], labels=dict(labels, action='start'))
    assert agreed_labels(manifest, reviews)[1] == ['d']


def test_modified_frozen_manifest_is_rejected(tmp_path):
    manifest = dict(documents=[])
    manifest['hash'] = digest(manifest)
    manifest['documents'] = [{'document_id':'altered'}]
    (tmp_path/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match='modified'):
        load_corpus(tmp_path)


def corpus(tmp_path, count=1):
    stories = [SimpleNamespace(story_id=f'd{i:03}', source_id='source', title=f'Unique {i}',
                body=None, url=f'https://example.invalid/{i}', language='en',
                first_seen_at='2026-10-18T09:00:00+05:30',
                timing=SimpleNamespace(published_at=None, publication_scheduled=False),
                syndication_group=f'g{i}', metadata={'source_kind_hint':'hazard_agency'})
               for i in range(count)]
    store = SimpleNamespace(syndication_groups=lambda: {s.story_id:[s] for s in stories})
    directory = tmp_path/'corpus'
    manifest = export_corpus(store, directory)
    return directory, manifest


def review(doc, reviewer='alice', **labels):
    gold = dict(event_type='other', policy_status='unknown', action='unknown', targets=[], quantities=[])
    gold.update(labels)
    return dict(document_id=doc['document_id'], document_hash=doc['hash'], reviewer_id=reviewer,
                reviewer_kind='human', independent=True, category='hard_negatives', labels=gold)


@pytest.mark.parametrize('labels', [dict(action=''), dict(targets='sector:steel'),
    dict(quantities=[dict(measure='rate', unit='percent', old_level=None, new_level='NaN', delta=None)]),
    dict(quantities=[dict(measure='rate', unit='percent')])])
def test_malformed_gold_is_rejected(tmp_path, labels):
    _, manifest = corpus(tmp_path)
    with pytest.raises(ValueError):
        agreed_labels(manifest, [review(manifest['documents'][0], **labels)])


def test_import_is_all_or_nothing_and_rejects_duplicate_identity(tmp_path):
    directory, manifest = corpus(tmp_path)
    batch = tmp_path/'review.jsonl'
    batch.write_text(json.dumps(review(manifest['documents'][0]))+'\n')
    assert import_reviews(directory, batch) == 1
    before = (directory/'reviews.jsonl').read_bytes()
    with pytest.raises(ValueError, match='duplicate'):
        import_reviews(directory, batch)
    assert (directory/'reviews.jsonl').read_bytes() == before


def test_adjudication_preserves_two_disagreeing_reviews_and_cites_them(tmp_path):
    _, manifest = corpus(tmp_path)
    doc = manifest['documents'][0]
    rows = [review(doc, 'alice'), review(doc, 'bob', action='start')]
    assert agreed_labels(manifest, rows)[1] == [doc['document_id']]
    decision = review(doc, 'carol')
    decision.update(independent=False, adjudication=dict(review_hashes=[digest(r) for r in rows],
                                                       reason='The text states no operational action.'))
    assert agreed_labels(manifest, rows+[decision])[1] == []
    rows[1]['labels']['action'] = 'stop'
    with pytest.raises(ValueError, match='cite'):
        agreed_labels(manifest, rows+[decision])


def test_only_frozen_test_documents_are_scored(tmp_path):
    directory, manifest = corpus(tmp_path, 401)
    reviews = [review(d, r) for d in manifest['documents'] for r in ('alice','bob')]
    (directory/'reviews.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in reviews))
    visited = []
    def predict(doc):
        visited.append(doc['document_id'])
        assert doc['metadata']['source_kind_hint'] == 'hazard_agency'
        return review(doc)['labels']
    report = evaluate_corpus(directory, predict, Checks())
    assert visited == ['d400']
    assert report['corpus']['locked_test'] == 1
    assert report['reviewed_documents'] == 401
    assert not report['gate_passed']


def test_real_benchmark_predictor_consumes_frozen_story_contract(tmp_path):
    from scripts.news_benchmark import predict_document
    from seraph.news.registry import MasterData
    _, manifest = corpus(tmp_path)
    document = dict(manifest['documents'][0], title='M 5.7 - 48 km WNW of Khuzdar, Pakistan')
    result = predict_document(document, MasterData())
    assert result['event_type'] == 'physical_hazard'
    assert 'action' in result and 'quantities' in result


@pytest.mark.parametrize('mutation', ['split', 'duplicate', 'naive'])
def test_valid_hash_cannot_hide_invalid_corpus_structure(tmp_path, mutation):
    directory, manifest = corpus(tmp_path, 2)
    if mutation == 'split':
        manifest['documents'][0]['split'] = 'test'
    elif mutation == 'duplicate':
        manifest['documents'][1]['group_id'] = manifest['documents'][0]['group_id']
    else:
        manifest['documents'][0]['first_seen_at'] = '2026-10-18T09:00:00'
    for doc in manifest['documents']:
        doc['hash'] = digest({k:v for k,v in doc.items() if k != 'hash'})
    manifest['hash'] = digest({k:v for k,v in manifest.items() if k != 'hash'})
    (directory/'manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        load_corpus(directory)
