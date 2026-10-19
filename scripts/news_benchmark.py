"""NI17 export/review/evaluate a frozen, chronological news benchmark."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from seraph.validation.news_corpus import export_corpus, evaluate_corpus, import_reviews
from seraph.validation.news_gate import Checks
from seraph.news.acquisition import NewsStore
from seraph.news.registry import load_master_data
from seraph.news.extraction import extract_events
from seraph.news.estimation import estimate_impacts
from seraph.news.model import Story
from seraph.product_types import Timing


def predict_document(document, master):
    """Run the same extractor on the frozen text and its historical registry."""
    stamp = document['first_seen_at']
    registry = master.as_of(stamp, strict=True)
    story = Story(story_id=document['document_id'], source_id=document['source_id'],
                  observation_id=document['hash'], title=document['title'], url=document['url'],
                  body=document['body'],
                  timing=Timing(first_seen_at=stamp, published_at=document['published_at'],
                                publication_scheduled=document.get('publication_scheduled', False)),
                  language=document['language'], metadata=document.get('metadata', {}))
    events = [r.event for r in extract_events([story], registry) if r.event]
    if len(events) != 1:
        return {}  # this single-event benchmark cannot silently choose one
    event = events[0]
    frame = event.frame.describe() if event.frame else {}
    return dict(event_type=event.event_type, action=frame.get('action'),
                policy_status=frame.get('policy_status'), quantities=frame.get('quantities', []),
                targets=sorted({i.target_id for i in estimate_impacts(event, registry,
                    on=stamp[:10], known_at=stamp) if i.target_id.startswith('sector:')}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['export','import-reviews','evaluate'])
    parser.add_argument('--corpus', type=Path, required=True)
    parser.add_argument('--store', type=Path, default=ROOT/'prototype_runs/news-intelligence-pilot.sqlite')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--reviews', type=Path, help='independently completed review JSONL to import')
    args = parser.parse_args()
    if args.operation == 'import-reviews':
        if args.reviews is None:
            parser.error('--reviews is required for import-reviews')
        print(json.dumps(dict(imported=import_reviews(args.corpus, args.reviews))))
        return 0
    if args.operation == 'export':
        manifest = export_corpus(NewsStore(args.store), args.corpus)
        print(json.dumps(dict(documents=len(manifest['documents']), hash=manifest['hash'],
                              labels_created=0, path=str(args.corpus))))
        return 0
    master, _ = load_master_data()
    def predictor(document):
        return predict_document(document, master)
    spec = importlib.util.spec_from_file_location('news_gate_checks', ROOT/'scripts/run_news_gate.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lookahead_ran, breaches = module.run_lookahead_check(master)
    adv_ran, adv_total, adv_out = module.run_adversarial_check(master)
    report = evaluate_corpus(args.corpus, predictor,
        Checks(lookahead_ran=lookahead_ran, lookahead_breaches=breaches,
               adversarial_ran=adv_ran, adversarial_total=adv_total, adversarial_outstanding=adv_out))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['gate_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
