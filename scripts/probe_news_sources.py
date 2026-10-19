"""NEWS01 — verify which candidate news sources are actually usable.

`Source.accessibility_verified` ships False, and this is the only thing that
earns a True: a real fetch, a real parse, and a check that items carry usable
publication times. The audit listed RBI and GDELT as *candidates*; a candidate
is not an integration.

    python scripts/probe_news_sources.py

Writes `docs/evidence/NEWS-SOURCE-PROBE-<date>.json`. Read-only: it fetches
and parses, and registers nothing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.news.http_feed import probe  # noqa: E402
from seraph.news.json_feed import probe_json  # noqa: E402

#: Candidates, with why each is a candidate. Official policy announcements
#: first — decision D-A's starting scope.
CANDIDATES = [
    ("rbi_press_releases", "https://rbi.org.in/pressreleases_rss.xml",
     "Reserve Bank of India press releases — official monetary and regulatory "
     "announcements"),
    ("rbi_notifications", "https://rbi.org.in/notifications_rss.xml",
     "RBI notifications — binding circulars to regulated entities"),
    ("rbi_speeches", "https://rbi.org.in/speeches_rss.xml",
     "RBI speeches — forward guidance, not binding"),
    ("pib_releases", "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
     "Press Information Bureau — Government of India press releases"),
    ("rbi_index_page", "https://www.rbi.org.in/Scripts/rss.aspx",
     "the RBI feed INDEX, listed by the audit as 'RBI RSS'. Included to show "
     "it is a landing page, not a feed"),
    # T09: three RBI feeds are not world coverage. These are the sources the
    # plan names, probed rather than assumed — a URL in a plan is a
    # hypothesis until something has fetched and parsed it.
    ("sebi_press", "https://www.sebi.gov.in/sebirss.xml",
     "Securities and Exchange Board of India — market regulator announcements"),
    ("pib_all", "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=0",
     "Press Information Bureau, all ministries — the first PIB endpoint "
     "returned nothing usable, so a second is tried"),
    ("pib_finance", "https://pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=3",
     "PIB without the www host, finance regions"),
]

#: Sources that do not publish a feed at all. Each needs a named adapter;
#: there is no generic shape-guessing path.
JSON_CANDIDATES = [
    ("federal_register", "federal_register",
     "https://www.federalregister.gov/api/v1/documents.json"
     "?per_page=20&order=newest"
     "&fields[]=title&fields[]=html_url&fields[]=publication_date"
     "&fields[]=abstract&fields[]=document_number",
     "US Federal Register — tariff and trade actions reach India through "
     "import parity; this is the primary record of them"),
    ("usgs_earthquakes", "usgs_earthquakes",
     "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
     "4.5_day.geojson",
     "USGS — a physical hazard with its OWN coordinate, which is the one "
     "case where geography comes from the source and not the registry"),
    ("gdelt_doc", "gdelt_doc",
     "https://api.gdeltproject.org/api/v2/doc/doc"
     "?query=india%20tariff&mode=artlist&format=json&maxrecords=20",
     "GDELT — breadth. It aggregates other outlets, so its rows are pointers "
     "and must not be counted as independent confirmations"),
]


def main() -> int:
    results = []
    for source_id, url, why in CANDIDATES:
        outcome = probe(url)
        outcome.update(source_id=source_id, why_a_candidate=why)
        results.append(outcome)
        status = ("USABLE" if outcome["usable"]
                  else "REACHABLE, NOT USABLE" if outcome["reachable"]
                  else "UNREACHABLE")
        print(f"[{status:>22}] {source_id}")
        print(f"{'':25} items={outcome.get('items', '-')} "
              f"dated={outcome.get('dated_items', '-')} "
              f"newest={outcome.get('newest_published')} "
              f"{outcome.get('latency_ms', '-')}ms")
        if outcome.get("error"):
            print(f"{'':25} {outcome['error'][:150]}")
        elif not outcome.get("dated_items"):
            print(f"{'':25} {outcome['note']}")

    for source_id, adapter, url, why in JSON_CANDIDATES:
        outcome = probe_json(url, adapter)
        outcome.update(source_id=source_id, why_a_candidate=why, kind="json")
        results.append(outcome)
        status = ("USABLE" if outcome["usable"]
                  else "REACHABLE, NOT USABLE" if outcome["reachable"]
                  else "UNREACHABLE")
        print(f"[{status:>22}] {source_id} (json/{adapter})")
        print(f"{'':25} items={outcome.get('items', '-')} "
              f"dated={outcome.get('dated_items', '-')} "
              f"newest={outcome.get('newest_published')} "
              f"{outcome.get('latency_ms', '-')}ms")
        if outcome.get("error"):
            print(f"{'':25} {outcome['error'][:150]}")

    usable = [r for r in results if r["usable"]]
    record = dict(
        checked_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        candidates=len(results), usable=len(usable),
        usable_source_ids=[r["source_id"] for r in usable],
        results=results,
        note=("`usable` means: fetched, parsed as RSS/Atom, and at least one "
              "item carries a publication time this parser can read. A feed "
              "with no usable dates still cannot order evidence, so it is not "
              "promoted to accessibility_verified. Rights and permitted use "
              "are a SEPARATE question this probe does not answer"))
    target = ROOT / "docs" / "evidence" / f"NEWS-SOURCE-PROBE-{time.strftime('%Y-%m-%d')}.json"
    target.write_text(json.dumps(record, indent=2), encoding="utf-8")
    print(f"\n{len(usable)} of {len(results)} candidates are usable.")
    print(f"evidence: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
