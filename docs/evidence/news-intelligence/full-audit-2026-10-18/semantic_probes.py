"""Audit counterexamples only; writes evidence, never the production store."""
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
from seraph.news.model import Story
from seraph.news.registry import load_master_data
from seraph.news.extraction import extract_events
from seraph.news.lifecycle import applicability
from seraph.news.estimation import estimate_impacts
from seraph.product_types import Timing

STAMP = '2026-10-18T10:00:00+05:30'
master, _ = load_master_data()
cases = {
    'future_named_month': ('Import duty on steel increased effective from 1 December 2026', None),
    'denial_in_body': ('Tata Steel halts production', 'Tata Steel denies production halt. Operations continue normally.'),
    'repeated_claim_in_body': ('Tata Steel halts production', 'Tata Steel halts production at Kalinganagar.'),
    'body_exemption': ('Certain Hot-Rolled Steel From India: Antidumping Duty Order', 'This order does not apply to products from India.'),
}
report = {}
for key, (title, body) in cases.items():
    story = Story(key, 'federal_register_india', key, title, 'https://example.invalid/audit',
                  Timing(first_seen_at=STAMP), body=body)
    rows = []
    for result in extract_events([story], master):
        event = result.event
        if event is None:
            continue
        rows.append(dict(headline=event.headline, event_type=event.event_type,
                         assertion=event.frame.assertion_status,
                         action=event.frame.action, stage=event.frame.policy_status,
                         effective_at=event.timing.effective_at,
                         applicability=applicability(event, STAMP),
                         impacts=[dict(target=i.target_id, direction=i.direction,
                                       confidence=i.evidence_confidence,
                                       limitations=list(i.limitations))
                                  for i in estimate_impacts(event, master)]))
    report[key] = dict(input=dict(title=title, body=body), events=rows)
Path(__file__).with_name('semantic-findings.json').write_text(
    json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(report, indent=2))
