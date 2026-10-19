"""C10 NI17 — frozen documents, independent labels, exact field evaluation.

Export does not invent labels. Test text is hashed, split chronologically and
never changed on import. Agent reviews can aid curation but cannot satisfy the
two-human-reviewer gate. Reviewer identity/independence is an attestation, not
something software can establish about a person.
"""
from collections import Counter
from decimal import Decimal
from datetime import datetime
import hashlib
import json
from pathlib import Path

from seraph.validation.news_gate import REQUIRED_CORPUS, SliceResult, evaluate


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode()).hexdigest()


def export_corpus(store, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    # Current revisions only: a correction must not appear in train while
    # its essentially identical predecessor appears in the test set.
    groups = store.syndication_groups()
    stories = [min(group, key=lambda s: (s.first_seen_at, s.story_id)) for group in groups.values()]
    stories.sort(key=lambda s: (s.first_seen_at, s.story_id))
    unique = {}
    for story in stories:
        unique.setdefault(digest((story.title, story.body)), story)
    stories = list(unique.values())
    documents = []
    for index, story in enumerate(stories[:600]):
        document = dict(document_id=story.story_id, source_id=story.source_id,
                        title=story.title, body=story.body, url=story.url,
                        first_seen_at=story.first_seen_at, published_at=story.timing.published_at,
                        language=story.language, text_scope=story.metadata.get('text_scope',
                         'stored_body' if story.body else 'headline_only'),
                        group_id=story.syndication_group or story.story_id,
                        publication_scheduled=story.timing.publication_scheduled,
                        metadata={key: story.metadata[key] for key in
                                  ('source_kind_hint', 'title_is_filing_entity', 'publication_precision')
                                  if key in story.metadata},
                        split='train' if index < 300 else 'calibration' if index < 400 else 'test')
        document['hash'] = digest(document)
        documents.append(document)
    manifest = dict(schema='news-corpus/1', documents=documents,
                    split_policy='first_seen chronological 300/100/200; no syndicated group crosses splits',
                    required=REQUIRED_CORPUS)
    manifest['hash'] = digest(manifest)
    (directory/'manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding='utf-8')
    (directory/'reviews.jsonl').write_text('', encoding='utf-8')
    templates = [dict(document_id=d['document_id'], document_hash=d['hash'],
                      reviewer_id='', reviewer_kind='human', independent=False,
                      category='', labels=dict(event_type='', policy_status='', action='',
                                               targets=[], quantities=[])) for d in documents]
    (directory/'review-template.jsonl').write_text(
        ''.join(json.dumps(row, ensure_ascii=False)+'\n' for row in templates), encoding='utf-8')
    (directory/'README.md').write_text(
        '# Frozen news benchmark\n\nDo not edit manifest.json. Each reviewer independently appends a JSON '
        'object to reviews.jsonl with document_id, document_hash, reviewer_id, reviewer_kind '
        '(human or agent), independent (true only if reviewed without model outputs or other labels), '
        'category, and labels. Labels require event_type, policy_status, action, targets '
        '(list of sector IDs), quantities (list with measure, old_level, new_level, delta, unit). '
        'Use null for absent numeric values. Record the text actually shown, not a linked body '
        'absent from the manifest. Two distinct independent human reviewers must agree on all '
        'fields, or a third human adjudicates the disagreement. Import completed files with '
        '`scripts/news_benchmark.py import-reviews --corpus THIS_DIRECTORY --reviews FILE`. '
        'An adjudication is a new review with adjudication={review_hashes: [SHA256 of each '
        'independent review using news_corpus.digest], reason: explanation}; it preserves both '
        'original reviews and must use a distinct human identity. No scores are generated '
        'by export. Reviewer independence is an attestation, not proof of independence.\n', encoding='utf-8')
    return manifest


def load_corpus(directory):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
    saved = manifest.pop('hash')
    if digest(manifest) != saved:
        raise ValueError('frozen corpus manifest was modified')
    manifest['hash'] = saved
    ids, groups, texts = set(), set(), set()
    previous = None
    for doc in manifest['documents']:
        fields = {k:v for k,v in doc.items() if k != 'hash'}
        if digest(fields) != doc['hash']:
            raise ValueError('document hash mismatch')
        identity = doc['document_id']
        group = doc.get('group_id', identity)
        text_hash = digest((doc['title'], doc.get('body')))
        if identity in ids or group in groups or text_hash in texts:
            raise ValueError('duplicate document, text or syndication group in frozen corpus')
        ids.add(identity)
        groups.add(group)
        texts.add(text_hash)
        stamp = datetime.fromisoformat(doc['first_seen_at'])
        if stamp.utcoffset() is None:
            raise ValueError('corpus timestamps must have an explicit timezone')
        if previous is not None and stamp < previous:
            raise ValueError('corpus is not chronological')
        previous = stamp
        index = len(ids)-1
        expected = 'train' if index < 300 else 'calibration' if index < 400 else 'test'
        if doc['split'] != expected:
            raise ValueError('corpus split violates frozen 300/100/200 policy')
    if len(ids) > 600:
        raise ValueError('corpus exceeds frozen 600-document policy')
    reviews = [json.loads(line) for line in (directory/'reviews.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    return manifest, reviews


def import_reviews(directory, path):
    """Validate the entire batch before appending; never replace a review."""
    from seraph.news.worker_lock import worker_lock
    directory = Path(directory)
    incoming = [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines()
                if line.strip()]
    with worker_lock(directory/'reviews.jsonl', 'import'):
        manifest, existing = load_corpus(directory)
        agreed_labels(manifest, existing + incoming)
        # Atomic replacement avoids a partially written JSONL batch on crash.
        staged = directory/'reviews.jsonl.pending'
        staged.write_text(''.join(json.dumps(row, ensure_ascii=False)+'\n'
                                  for row in existing + incoming), encoding='utf-8')
        staged.replace(directory/'reviews.jsonl')
    return len(incoming)


def agreed_labels(manifest, reviews):
    docs = {d['document_id']: d for d in manifest['documents']}
    grouped, adjudications, seen = {}, {}, set()
    required = {'event_type', 'policy_status', 'action', 'targets', 'quantities'}
    for review in reviews:
        doc = docs.get(review['document_id'])
        if doc is None or review['document_hash'] != doc['hash']:
            raise ValueError('review does not identify the frozen document')
        key = (review['document_id'], review['reviewer_id'])
        if not isinstance(review['reviewer_id'], str) or not review['reviewer_id'].strip() or key in seen:
            raise ValueError('duplicate or empty reviewer identity')
        seen.add(key)
        if not required.issubset(review['labels']):
            raise ValueError('incomplete gold labels')
        validate_labels(review['labels'])
        if review['category'] not in REQUIRED_CORPUS or review['category'] in ('total','non_english','locked_test','reviewers'):
            raise ValueError('unknown benchmark category')
        if review.get('adjudication'):
            if review.get('reviewer_kind') != 'human':
                raise ValueError('adjudication requires a human reviewer')
            adjudications.setdefault(review['document_id'], []).append(review)
        elif review.get('reviewer_kind') == 'human' and review.get('independent') is True:
            grouped.setdefault(review['document_id'], []).append(review)
    agreed, unresolved = {}, []
    for doc_id in docs:
        rows = grouped.get(doc_id, [])
        answers = {digest({'labels':r['labels'], 'category':r['category']}) for r in rows}
        if len(rows) >= 2 and len(answers) == 1:
            agreed[doc_id] = rows[0]
        else:
            decisions = adjudications.get(doc_id, [])
            for decision in decisions:
                record = decision['adjudication']
                if (len(rows) < 2 or decision['reviewer_id'] in {r['reviewer_id'] for r in rows}
                        or not isinstance(record, dict) or not str(record.get('reason', '')).strip()
                        or set(record.get('review_hashes', [])) != {digest(r) for r in rows}):
                    raise ValueError('adjudication must cite the independent reviews and explain its decision')
            if len(decisions) == 1:
                agreed[doc_id] = decisions[0]
            else:
                unresolved.append(doc_id)
    return agreed, unresolved


def validate_labels(labels):
    """Malformed gold must fail before it can become accuracy evidence."""
    for field in ('event_type', 'policy_status', 'action'):
        if not isinstance(labels[field], str) or not labels[field].strip():
            raise ValueError(f'gold {field} must be a nonempty string; use unknown for abstention')
    targets = labels['targets']
    if not isinstance(targets, list) or any(not isinstance(t, str) or
            not t.startswith('sector:') or t == 'sector:' for t in targets):
        raise ValueError('gold targets must be a list of sector IDs')
    if len(targets) != len(set(targets)):
        raise ValueError('duplicate gold targets')
    if not isinstance(labels['quantities'], list):
        raise ValueError('gold quantities must be a list')
    for q in labels['quantities']:
        required = {'measure', 'unit', 'old_level', 'new_level', 'delta'}
        if not isinstance(q, dict) or not required.issubset(q):
            raise ValueError('incomplete gold quantity')
        if any(not isinstance(q[k], str) or not q[k].strip() for k in ('measure', 'unit')):
            raise ValueError('gold quantity needs a measure and unit')
        for key in ('old_level', 'new_level', 'delta'):
            value = q[key]
            if value is not None:
                try:
                    valid = not isinstance(value, bool) and Decimal(str(value)).is_finite()
                except ArithmeticError:
                    valid = False
                if not valid:
                    raise ValueError('gold numeric values must be finite or null')


def quantity_values(quantities, field):
    out = []
    for q in quantities:
        if field == 'unit':
            out.append((q['measure'], q['unit']))
        else:
            out.append((q['measure'], *(None if q.get(k) is None else
                       str(Decimal(str(q[k])).normalize()) for k in ('old_level','new_level','delta'))))
    return sorted(out, key=str)


def score_gold(slices, predicted, gold, *, per_class=None):
    """Score one document. Negatives may never earn recall credit (A01).

    `class_recall` used to count every document: 95 hard negatives correctly
    left alone and five supported events entirely missed reported **95%
    recall** while the supported-event recall was 0/5. Whole-document
    classification accuracy under a recall name is the single most misleading
    number a gate like this can produce, because recall is exactly the
    statistic a reader consults to ask "would it have found the event?".

    So the two populations are scored apart:

    * gold is a SUPPORTED EVENT -> `class_recall`. Found, confused or
      abstained; nothing else contributes to this denominator.
    * gold is a HARD NEGATIVE -> `negative_specificity`, whose `extra`
      counts the negatives promoted to a supported class (false positives).
    """
    from seraph.validation.news_gate import is_supported_event
    got, want = predicted.get('event_type'), gold['event_type']
    if is_supported_event(want):
        item = slices['class_recall']
        item.relevant += 1
        item.correct += int(got == want)
        item.abstained += int(not got)
        if per_class is not None:
            row = per_class.setdefault(want, dict(
                gold=0, found=0, abstained=0, confused_with={}))
            row['gold'] += 1
            if got == want:
                row['found'] += 1
            elif not got:
                row['abstained'] += 1
            else:
                row['confused_with'][got] = row['confused_with'].get(got, 0) + 1
    else:
        item = slices['negative_specificity']
        # `predicted` is the denominator for a non-recall slice: the number
        # of actual negatives scored. `relevant` carries the same count so a
        # reader of the raw counts is not left guessing which is which.
        item.predicted += 1
        item.relevant += 1
        rejected = not is_supported_event(got)
        item.correct += int(rejected)
        item.abstained += int(not got)
        if not rejected:
            item.extra += 1
        if per_class is not None:
            row = per_class.setdefault('negative:' + (want or 'unknown'),
                                       dict(gold=0, found=0, abstained=0,
                                            confused_with={}))
            row['gold'] += 1
            if rejected:
                row['found'] += 1
            else:
                row['confused_with'][got] = row['confused_with'].get(got, 0) + 1
    links = slices['link_precision']
    actual, wanted = set(predicted.get('targets', [])), set(gold['targets'])
    links.predicted += len(actual)
    links.correct += len(actual & wanted)
    links.extra += len(actual - wanted)
    for name, key in [('action', 'action'), ('legal_stage', 'policy_status')]:
        item = slices['field_'+name]
        item.predicted += 1
        item.correct += int(predicted.get(key) == gold[key])
    for field in ('numeric', 'unit'):
        item = slices['field_'+field]
        actual_q, wanted_q = predicted.get('quantities', []), gold['quantities']
        if not actual_q and not wanted_q:
            continue  # empty/empty is not evidence of numeric accuracy
        item.predicted += 1
        item.correct += int(quantity_values(actual_q, field) == quantity_values(wanted_q, field))


def evaluate_corpus(directory, predictor, checks):
    from seraph.validation.news_gate import REQUIRED_SLICES
    manifest, reviews = load_corpus(directory)
    gold, unresolved = agreed_labels(manifest, reviews)
    counts = Counter()
    slices = {name: SliceResult(name) for name in REQUIRED_SLICES}
    per_class: dict = {}
    for doc in manifest['documents']:
        review = gold.get(doc['document_id'])
        if review is None:
            continue
        counts['total'] += 1
        counts[review['category']] += 1
        counts['non_english'] += int(doc['language'] != 'en')
        if doc['split'] == 'test':
            counts['locked_test'] += 1
            score_gold(slices, predictor(doc), review['labels'],
                       per_class=per_class)
    result = evaluate(list(slices.values()), dict(counts), reviewers=2 if gold else 0,
                      checks=checks, per_class=per_class).describe()
    result.update(corpus_hash=manifest['hash'], unresolved_documents=len(unresolved),
                  frozen_documents=len(manifest['documents']), reviewed_documents=len(gold),
                  scored_split='test',
                  reviewer_independence='attested by reviewers; not established by software')
    if unresolved:
        result['gate_passed'] = False
        result['provisional'] = True
        result['reasons'].append('not every frozen document has two independent human reviews with agreement or adjudication')
    return result
