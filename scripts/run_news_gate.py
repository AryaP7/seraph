"""NI17 — run the news extraction release gate and report it honestly.

    python scripts/run_news_gate.py                 # report only, exits 0
    python scripts/run_news_gate.py --release-check # exits NONZERO if it fails
    python scripts/run_news_gate.py --json out.json

Thresholds are frozen in `seraph/validation/news_gate.py` before any
evaluation runs. This script measures the extractor against the hand-labelled
benchmark and **expects to fail the corpus check**: the plan asks for 600
documents and two reviewers, and this repository has neither. Failing for that
reason is the correct outcome.

Two modes on purpose. `--release-check` is the one a pipeline runs: a failing
gate must fail the command. The default is report-only, because printing the
numbers is useful even while the corpus is known to be short.
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.news.estimation import estimate_impacts                # noqa: E402
from seraph.news.extraction import extract_events                  # noqa: E402
from seraph.news.model import Place, Story, Timing                 # noqa: E402
from seraph.news.registry import load_master_data                  # noqa: E402
from seraph.validation.news_benchmark_labels import (              # noqa: E402
    GROUP_TO_REQUIREMENT, LABELLED, LABELLER_COUNT, LABELLER_NOTE)
from seraph.validation.news_gate import (                          # noqa: E402
    Checks, SliceResult, evaluate, is_supported_event)

SEEN = "2026-10-18T09:00:00+05:30"


def _event(headline: str, master):
    language = "hi" if any(0x900 <= ord(c) <= 0x97F for c in headline) else "en"
    hazard = headline.startswith("M ") and " - " in headline
    story = Story(story_id="bench", source_id="federal_register",
                  observation_id="o", title=headline,
                  url="https://example.invalid/b", body=None,
                  timing=Timing(first_seen_at=SEEN), syndication_group="g",
                  language=language,
                  metadata={"source_kind_hint": "hazard_agency"} if hazard else {})
    results = list(extract_events([story], master))
    return results[0].event if results and results[0].event else None


def run_lookahead_check(master) -> tuple[bool, int]:
    """Does any event carry evidence it could not have had at first sighting?

    An actually executed check, so the gate is not trusting a literal zero.
    An event whose frame was built from text the pipeline had not yet received
    would be a context breach; the construction here makes that observable by
    asserting the frame's `available_at` never precedes `first_seen_at`.
    """
    breaches = 0
    for headline, *_rest in LABELLED:
        event = _event(headline, master)
        if event is None or event.frame is None:
            continue
        available = getattr(event.frame, "available_at", None)
        seen = event.timing.first_seen_at if event.timing else None
        if available and seen and available < seen:
            breaches += 1
    return True, breaches


def run_adversarial_check(master) -> tuple[bool, int, int]:
    """Re-run every adversarial case and count those still wrong."""
    total = outstanding = 0
    for headline, want_class, want_stage, want_sector, group, _why in LABELLED:
        if group != "adversarial":
            continue
        total += 1
        event = _event(headline, master)
        if event is None:
            outstanding += 1
            continue
        stage = event.frame.policy_status if event.frame else None
        sectors = {i.target_id for i in estimate_impacts(event, master)
                   if i.target_id.startswith("sector:")}
        wrong = (event.event_type != want_class or stage != want_stage
                 or (want_sector is None and sectors)
                 or (want_sector is not None and want_sector not in sectors))
        outstanding += int(bool(wrong))
    return True, total, outstanding


def main(out: Path | None, release_check: bool) -> int:
    master, _ = load_master_data()
    for place_id, name, iso in (("in", "India", "IND"),
                                ("us", "United States", "USA")):
        if place_id not in master.places:
            master.add_place(Place(place_id, name, "country", iso_code=iso))

    links = SliceResult("link_precision")
    klass = SliceResult("class_recall")
    # Audit A01: this runner had the same defect as the corpus evaluator —
    # every labelled headline entered the recall denominator, so agreeing
    # that a hard negative is `other` was scored as a found event. Negatives
    # are now their own slice and earn no recall credit.
    negatives = SliceResult("negative_specificity")
    fields = {name: SliceResult(f"field_{name}")
              for name in ("numeric", "unit", "action", "legal_stage")}
    groups = collections.Counter()
    per_class: dict = {}
    misses = []

    for headline, want_class, want_stage, want_sector, group, why in LABELLED:
        groups[GROUP_TO_REQUIREMENT.get(group, group)] += 1
        event = _event(headline, master)
        got_class = event.event_type if event is not None else None

        if is_supported_event(want_class):
            # --- class recall: over events that SHOULD be found --------
            klass.relevant += 1
            row = per_class.setdefault(want_class, dict(
                gold=0, found=0, abstained=0, confused_with={}))
            row["gold"] += 1
            if got_class is None:
                klass.abstained += 1
                row["abstained"] += 1
            elif got_class == want_class:
                klass.correct += 1
                row["found"] += 1
            else:
                row["confused_with"][got_class] = (
                    row["confused_with"].get(got_class, 0) + 1)
                misses.append(dict(field="class", headline=headline[:80],
                                   expected=want_class, got=got_class))
        else:
            # --- negative specificity: a hard negative left alone ------
            negatives.predicted += 1
            negatives.relevant += 1
            rejected = not is_supported_event(got_class)
            negatives.correct += int(rejected)
            negatives.abstained += int(got_class is None)
            if not rejected:
                negatives.extra += 1
                misses.append(dict(field="false_positive",
                                   headline=headline[:80],
                                   expected=want_class, got=got_class))
        if event is None:
            continue

        # --- link precision: over PREDICTED links only -----------------
        predicted = {i.target_id for i in estimate_impacts(event, master)
                     if i.target_id.startswith("sector:")}
        links.predicted += len(predicted)
        if want_sector is None:
            # Every predicted link here is wrong. A document with no link to
            # make contributes nothing to the denominator -- counting it as a
            # success is how precision rises by adding irrelevant documents.
            links.extra += len(predicted)
            if predicted:
                misses.append(dict(field="link", headline=headline[:80],
                                   expected="no sector",
                                   got=sorted(predicted)))
        else:
            if want_sector in predicted:
                links.correct += 1
            else:
                misses.append(dict(field="link", headline=headline[:80],
                                   expected=want_sector,
                                   got=sorted(predicted) or "none"))
            wrong = predicted - {want_sector}
            links.extra += len(wrong)
            if wrong:
                misses.append(dict(field="link", headline=headline[:80],
                                   expected=f"only {want_sector}",
                                   got=sorted(wrong)))

        frame = event.frame
        hindi = any(0x900 <= ord(c) <= 0x97F for c in headline)

        # --- each field scored SEPARATELY -------------------------------
        stage_slice = fields["legal_stage"]
        if hindi:
            stage_slice.abstained += 1          # abstains by design
        else:
            stage_slice.predicted += 1
            if frame and frame.policy_status == want_stage:
                stage_slice.correct += 1
            else:
                misses.append(dict(
                    field="legal_stage", headline=headline[:80],
                    expected=want_stage,
                    got=frame.policy_status if frame else None))

        # This legacy title corpus labels class/stage/sector only. Having an
        # action, a number or a unit is NOT evidence that it is correct.
        # These slices stay unevaluated until independent gold fields exist.
        for name in ("action", "numeric", "unit"):
            fields[name].abstained += 1
            fields[name].note = 'legacy corpus has no gold labels for this field'

    lookahead_ran, breaches = run_lookahead_check(master)
    adversarial_ran, adv_total, adv_out = run_adversarial_check(master)

    counts = dict(groups)
    counts["total"] = sum(groups.values())
    counts["non_english"] = sum(
        1 for h, *_ in LABELLED if any(0x900 <= ord(c) <= 0x97F for c in h))
    counts["locked_test"] = 0          # no chronological lock has been cut

    result = evaluate([links, klass, negatives, *fields.values()], counts,
                      reviewers=LABELLER_COUNT,
                      per_class=per_class,
                      checks=Checks(lookahead_ran=lookahead_ran,
                                    lookahead_breaches=breaches,
                                    adversarial_ran=adversarial_ran,
                                    adversarial_total=adv_total,
                                    adversarial_outstanding=adv_out))
    report = result.describe()
    report["labeller_note"] = LABELLER_NOTE
    report["misses"] = misses

    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("required_corpus", "misses")}, indent=2))
    if misses:
        print(f"\n{len(misses)} disagreement(s):")
        for miss in misses:
            print(f"  [{miss['field']}] {miss['headline']}")
            print(f"      expected {miss['expected']!r}, got {miss['got']!r}")

    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        print(f"\nwritten to {out}")

    if release_check and not result.gate_passed:
        print("\nRELEASE CHECK FAILED: the gate did not pass. "
              "See `reasons` above.")
        return 1
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", type=Path, default=None)
    ap.add_argument("--release-check", action="store_true",
                    help="exit nonzero when the gate does not pass. The "
                         "default is report-only, which exits 0 so the "
                         "numbers can be read while the corpus is short")
    args = ap.parse_args()
    raise SystemExit(main(args.json, args.release_check))
