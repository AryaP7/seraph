"""Live news acquisition — register verified sources and poll them.

    python scripts/run_news.py --register      # register the probed sources
    python scripts/run_news.py --once          # one poll of every source
    python scripts/run_news.py                 # poll on the registered interval
    python scripts/run_news.py --status        # what is stored, how fresh

Only sources that `scripts/probe_news_sources.py` found usable are registered,
and `accessibility_verified` is set from that probe rather than asserted.

Rights
------
"Publicly reachable" is not "licensed to redistribute", so `may_store_full_text`
started **False** everywhere. The terms have now been read per source and the
answer differs by source — see
`docs/decisions/DR-10-2026-10-18-source-text-rights.md`:

* **permitted** — `federal_register`, `federal_register_india` and
  `fed_press` are US Government works (17 U.S.C. 105); `usgs_earthquakes` is
  USGS public domain; `pib_releases` is granted by PIB's own copyright policy,
  which needs no prior approval.
* **refused** — the three RBI feeds say only "(c) Reserve Bank of India. All
  Rights Reserved", which is the opposite of a licence. `sebi_press` permits
  reproduction only after permission is obtained by email, and that email has
  not been sent. These keep headline, link, times and a content hash only.

Every permitted source carries two conditions, stated in its `rights` string:
the source must be acknowledged, and third-party material embedded in a
government document is not covered by the government's own licence.

Bodies accrue **forward only**. Rows are immutable, and a re-poll of an
unchanged item yields `unchanged` rather than a new row, so stories already
stored stay body-less.
"""
from __future__ import annotations

import argparse
import os
import urllib.request
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from seraph.news.acquisition import _now
from seraph.news import NewsStore, Source                      # noqa: E402
from seraph.news.http_feed import HttpFeedFetcher, probe
from seraph.news.json_feed import (                # noqa: E402
    JsonSourceFetcher,
    probe_json,
)
from seraph.news.refresh import acquire
from seraph.operations import JobStore                          # noqa: E402

DEFAULT_STORE = ROOT / "prototype_runs" / "news-intelligence-pilot.sqlite"
JOB = "news.poll"

#: Verified by scripts/probe_news_sources.py on 2026-10-16. Each was fetched,
#: parsed as RSS, and carries usable publication times.
VERIFIED_SOURCES = (
    Source(
        source_id="rbi_press_releases", provider="Reserve Bank of India",
        kind="official_policy", url="https://rbi.org.in/pressreleases_rss.xml",
        topic_coverage=("monetary_policy", "banking_regulation", "forex",
                        "government_securities"),
        language="en",
        rights="RBI reserves all rights: its copyright page says only '(c) Reserve Bank of India. All Rights Reserved' with no grant (https://www.rbi.org.in/Scripts/Copyright.aspx). Terms REVIEWED and full-text retention REFUSED. Headline, link, times and hash only. See docs/decisions/DR-10-2026-10-18-source-text-rights.md",
        may_store_full_text=False, retention_days=None,
        poll_interval_minutes=30, failure_behaviour="retry_then_report",
        max_retries=3, accessibility_verified=True,
        notes="official RBI announcements; the primary policy channel"),
    Source(
        source_id="rbi_notifications", provider="Reserve Bank of India",
        kind="regulator", url="https://rbi.org.in/notifications_rss.xml",
        topic_coverage=("banking_regulation", "compliance", "prudential_norms"),
        language="en",
        rights="RBI reserves all rights: its copyright page says only '(c) Reserve Bank of India. All Rights Reserved' with no grant (https://www.rbi.org.in/Scripts/Copyright.aspx). Terms REVIEWED and full-text retention REFUSED. Headline, link, times and hash only. See docs/decisions/DR-10-2026-10-18-source-text-rights.md",
        may_store_full_text=False, poll_interval_minutes=60,
        accessibility_verified=True,
        notes="binding circulars to regulated entities"),
    Source(
        source_id="rbi_speeches", provider="Reserve Bank of India",
        kind="official_policy", url="https://rbi.org.in/speeches_rss.xml",
        topic_coverage=("forward_guidance", "monetary_policy"),
        language="en",
        rights="RBI reserves all rights: its copyright page says only '(c) Reserve Bank of India. All Rights Reserved' with no grant (https://www.rbi.org.in/Scripts/Copyright.aspx). Terms REVIEWED and full-text retention REFUSED. Headline, link, times and hash only. See docs/decisions/DR-10-2026-10-18-source-text-rights.md",
        may_store_full_text=False, poll_interval_minutes=240,
        accessibility_verified=True,
        notes="speeches are guidance, not binding instruments — weighted "
              "accordingly downstream"),
    # T09. Probed on 2026-10-17 (docs/evidence/NEWS-SOURCE-PROBE-2026-10-17.json).
    # SEBI parsed 30 items with ZERO usable dates until the parser learned its
    # "16 Oct, 2026 +0530" format — a comma was discarding a whole regulator.
    # Its timestamps are DAY granular: the source states a date and no time,
    # and nothing downstream may order within a day from them.
    Source(
        source_id="sebi_press", provider="Securities and Exchange Board of India",
        kind="regulator", url="https://www.sebi.gov.in/sebirss.xml",
        topic_coverage=("market_regulation", "enforcement", "listing_rules",
                        "appeals"),
        language="en",
        rights='SEBI permits reproduction only AFTER permission is obtained by email (https://www.sebi.gov.in/website-policy.html). That email has not been sent, so full-text retention is REFUSED - not because the terms are unknown, but because the permission they require is not held. One email would change this. See docs/decisions/DR-10-2026-10-18-source-text-rights.md',
        may_store_full_text=False, poll_interval_minutes=60,
        accessibility_verified=True,
        notes="day-granular publication dates only; ordering WITHIN a day "
              "cannot be derived from this source"),
)

#: Sources that publish JSON rather than a feed. Each names the adapter that
#: reads its shape; there is no shape-guessing path.
VERIFIED_JSON_SOURCES = (
    (Source('federal_register_india', 'US Federal Register', 'official_policy',
       'https://www.federalregister.gov/api/v1/documents.json?per_page=40&order=newest&conditions[term]=India&fields[]=title&fields[]=html_url&fields[]=publication_date&fields[]=abstract&fields[]=document_number',
       ('india_trade', 'tariffs'), rights='US Government work, not copyrightable: 17 U.S.C. 105 (https://www.govinfo.gov/about/policies). Credit the issuing agency; third-party material embedded in a government document is NOT covered. See docs/decisions/DR-10-2026-10-18-source-text-rights.md',
       may_store_full_text=True,
       poll_interval_minutes=120, accessibility_verified=True), 'federal_register'),
    # The same register, filtered by ISSUING AGENCY rather than by the word
    # "India". The International Trade Administration is the body that
    # actually issues antidumping and countervailing determinations, and a
    # determination reaches an Indian exporter through the PRODUCT it
    # covers -- "Certain Corrosion-Resistant Steel Products" -- without
    # necessarily saying India anywhere a term search can see. The
    # term-filtered feed above therefore misses exactly the instruments
    # the exposure registry exists to route.
    #
    # Reachability was probed before registration, not assumed:
    # docs/evidence/news-intelligence/news-completion-2026-10-19/source-reachability.json
    (Source('federal_register_ita', 'US Federal Register', 'official_policy',
       'https://www.federalregister.gov/api/v1/documents.json?per_page=40&order=newest'
       '&conditions[agencies][]=international-trade-administration'
       '&fields[]=title&fields[]=html_url&fields[]=publication_date'
       '&fields[]=abstract&fields[]=document_number',
       ('india_trade', 'tariffs', 'trade_remedy'),
       rights='US Government work, not copyrightable: 17 U.S.C. 105 (https://www.govinfo.gov/about/policies). Credit the issuing agency; third-party material embedded in a government document is NOT covered. See docs/decisions/DR-10-2026-10-18-source-text-rights.md',
       may_store_full_text=True,
       poll_interval_minutes=120, accessibility_verified=True,
       notes='Trade-remedy determinations by issuing agency. Most carry no '
             'Indian subject at all; relevance scoring and the exposure '
             'registry decide which do, and an unmatched determination is '
             'carried as out of scope rather than dropped.'),
     'federal_register'),
    (Source(
        source_id="federal_register", provider="US Federal Register",
        kind="official_policy",
        url=("https://www.federalregister.gov/api/v1/documents.json"
             "?per_page=40&order=newest"
             "&fields[]=title&fields[]=html_url&fields[]=publication_date"
             "&fields[]=abstract&fields[]=document_number"),
        topic_coverage=("trade_policy", "tariffs", "sanctions", "rulemaking"),
        language="en",
        rights='US Government work, not copyrightable: 17 U.S.C. 105 (https://www.govinfo.gov/about/policies). Credit the issuing agency; third-party material embedded in a government document is NOT covered. See docs/decisions/DR-10-2026-10-18-source-text-rights.md',
        may_store_full_text=True, poll_interval_minutes=120,
        accessibility_verified=True,
        notes="day-granular publication dates. US trade actions reach Indian "
              "exposure through import parity, which is why a US register is "
              "in an Indian market-risk system at all"),
     "federal_register"),
    (Source(
        source_id="usgs_earthquakes", provider="US Geological Survey",
        kind="weather_advisory",
        url=("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
             "4.5_day.geojson"),
        topic_coverage=("physical_hazard", "seismic"),
        language="en",
        rights='US Government work in the public domain; USGS asks that proper credit be given (https://www.usgs.gov/information-policies-and-instructions/acknowledging-or-crediting-usgs). Third-party images used by USGS with permission are NOT covered. See docs/decisions/DR-10-2026-10-18-source-text-rights.md',
        may_store_full_text=True, poll_interval_minutes=30,
        accessibility_verified=True,
        notes="the one source that supplies its OWN coordinate. Its events "
              "are physical facts, not market claims, and nothing here "
              "converts a magnitude into a risk score"),
     "usgs_earthquakes"),
)

#: Probed and NOT registered, with the reason. Keeping this list is the point:
#: a source that silently vanished from a plan looks like one nobody tried.
REJECTED_SOURCES = (
    ("pib_all", "https://www.pib.gov.in/RssMain.aspx?ModId=6&Lang=1&Regid=0",
     "returns zero items"),
    ("rbi_index_page", "https://www.rbi.org.in/Scripts/rss.aspx",
     "an HTML landing page, not a feed"),
    ("gdelt_doc",
     "https://api.gdeltproject.org/api/v2/doc/doc?query=india%20tariff"
     "&mode=artlist&format=json&maxrecords=20",
     "HTTP 429 at probe time. Rate limiting is not a permanent failure; the "
     "adapter exists and is tested, and this needs a politeness budget and a "
     "retry schedule before it is registered"),
)

# Local reading scope only; source evidence and access probes are in
# docs/evidence/news-intelligence/pilot-probes.json. Missing dates stay null.
PILOT_SOURCES = (
    Source('pib_releases', 'Press Information Bureau', 'official_policy',
        'https://pib.gov.in/RssMain.aspx?ModId=6&Lang=2&Regid=3',
        ('ministry_policy', 'industry', 'health'), language='hi',
        rights='PIB Copyright Policy: may be reproduced free of charge, no prior approval; source must be PROMINENTLY acknowledged; must be accurate and not used in a derogatory or misleading context; third-party material NOT covered (https://factcheck.pib.gov.in/Documents/CopyrightPolicy.pdf). See docs/decisions/DR-10-2026-10-18-source-text-rights.md',
        may_store_full_text=True,
        poll_interval_minutes=60, accessibility_verified=True,
        notes='Probe returned Hindi and no dates. First-seen-only; English semantic rules abstain.'),
    Source('fed_press', 'Federal Reserve Board', 'official_policy',
        'https://www.federalreserve.gov/feeds/press_all.xml',
        ('monetary_policy', 'banking_regulation'),
        rights='Board-authored public-domain feed text; attribution required: https://www.federalreserve.gov/disclaimer.htm',
        may_store_full_text=True, poll_interval_minutes=60, accessibility_verified=True),
)
#: Probed 2026-10-25 for NI17's two short quotas: `logistics_hazards` needs
#: 80 against the 40 `usgs_earthquakes` supplies, and `non_english` needs 100
#: against the 29 `pib_releases` supplies.
#:
#: GDACS is not independent corroboration of anything -- it aggregates other
#: agencies' alerts.
#:
#: A SECOND PIB entry was registered here and has been WITHDRAWN. PIB's `Lang`
#: query parameter is inert: `Lang=1` through `Lang=20` at `Regid=3` all return
#: the SAME twenty Devanagari items, in the same order, with the same links as
#: the `Lang=2` URL `pib_releases` already polls (measured 2026-10-25; every
#: `Regid` other than 3 returns zero items). So PIB exposes exactly one feed,
#: `pib_releases` is already it, and a second source_id over the same URL only
#: polls a government endpoint twice an hour for no new information. The twenty
#: rows it acquired were collapsed by `export_corpus`'s (title, body) digest,
#: so the corpus was never affected -- but the duplicate rows are still in the
#: store under `pib_hindi_lang3`.
#:
#: Registering ANY new source cannot move either short quota, which is a
#: property of the corpus rule and not of source availability. `export_corpus`
#: takes the OLDEST 600 documents by `first_seen_at`, and that window closed at
#: 2026-10-19T22:12:32+05:30. `gdacs_alerts` first-saw its 328 items on
#: 2026-10-25, so it contributes ZERO documents to a freeze. See
#: docs/AMENDMENT-08-ni17-corpus-window.md; the remedy is an owner decision.
#:
#: Probed and REJECTED in the same pass, so they are not re-tried blindly:
#: ReliefWeb India (HTTP 202, no items), EMSC (404), UN News Hindi (404),
#: DW Hindi (no items), NDMA and IMD (SSL CERTIFICATE_VERIFY_FAILED --
#: certificate verification is NOT disabled to reach a source).
NI17_COVERAGE_SOURCES = (
    Source('gdacs_alerts', 'Global Disaster Alert and Coordination System',
        'weather_advisory', 'https://www.gdacs.org/xml/rss.xml',
        ('hazard', 'earthquake', 'cyclone', 'flood'),
        language='en', rights='publicly reachable feed; redistribution terms NOT reviewed, so headline, link, times and a content hash only. Reading them is the DR-10 procedure, not an assumption',
        may_store_full_text=False, poll_interval_minutes=120,
        accessibility_verified=True,
        notes='European Commission JRC alerting service; 325 dated items at '
              'probe. An alert is a hazard notification, not a measured '
              'market effect, and carries no exposure of its own.'),
)

#: Probed 2026-10-24 against the live endpoints: both answered HTTP 200
#: with ten dated entries. Registered because 27 NTPC stations and 54
#: exposure edges were curated with NO energy source at all, so that whole
#: set was structurally unable to fire -- the only NTPC news in the corpus
#: was two NSE filings titled "NTPC Limited", and a filing's subject is
#: deliberately not retained, so it produces no impact.
#:
#: These are TRADE PRESS, not primary instruments. A report of a Ministry or
#: regulator decision is reporting, NOT a second independent confirmation of
#: that instrument, and must never be counted as corroboration of it.
#:
#: Registering a source makes the curated edges REACHABLE, not firing: an
#: edge starts at a facility, so it still needs a station named in a
#: headline. None of the twenty headlines in the 2026-10-24 probe named one.
ENERGY_SOURCES = (
    Source('et_energyworld', 'ET EnergyWorld', 'news_agency',
        'https://energy.economictimes.indiatimes.com/rss/topstories',
        ('power', 'energy', 'oil_gas', 'renewables', 'grid'),
        language='en', rights='publicly reachable feed; redistribution terms NOT reviewed, so headline, link, times and a content hash only. Reading them is the DR-10 procedure, not an assumption',
        may_store_full_text=False, poll_interval_minutes=60,
        accessibility_verified=True,
        notes='Indian power/energy trade press, IST timestamps. Names '
              'issuers and facilities, which is what the curated station '
              'edges need. Probe carried earnings and policy items; only '
              'three issuers (ntpc, oil_india, kpi_green_energy) are '
              'registered with sector=energy, so a story about an '
              'unregistered power issuer resolves to no issuer.'),
    Source('mercom_india', 'Mercom India', 'news_agency',
        'https://www.mercomindia.com/feed',
        ('renewables', 'solar', 'power_policy', 'grid'),
        language='en', rights='publicly reachable feed; redistribution terms NOT reviewed, so headline, link, times and a content hash only. Reading them is the DR-10 procedure, not an assumption',
        may_store_full_text=False, poll_interval_minutes=120,
        accessibility_verified=True,
        notes='Renewables and power policy. The probe also returned China '
              'and Rwanda items; relevance is expected to place those out '
              'of scope rather than hide them.'),
)
#: Probed 2026-10-18 against the live endpoints. Each returned parseable,
#: dated entries; those that did not are in UNAVAILABLE_SOURCES with the
#: reason, because an adapter in code is not an active source.
EXCHANGE_AND_POLICY_SOURCES = (
    Source('nse_corporate_announcements', 'National Stock Exchange of India',
        'company_filing',
        'https://nsearchives.nseindia.com/content/RSS/Online_announcements.xml',
        ('issuer_announcement', 'corporate_action', 'disclosure'),
        language='en', rights='publicly reachable feed; redistribution terms NOT reviewed, so headline, link, times and a content hash only. Reading them is the DR-10 procedure, not an assumption',
        may_store_full_text=False, poll_interval_minutes=30,
        accessibility_verified=True,
        notes='Indian ISSUER-level announcements, the primary channel for '
              'company events in this market and previously absent entirely.'),
    Source('nse_circulars', 'National Stock Exchange of India', 'exchange_notice',
        'https://nsearchives.nseindia.com/content/RSS/Circulars.xml',
        ('market_structure', 'compliance', 'enforcement'),
        language='en', rights='publicly reachable feed; redistribution terms NOT reviewed, so headline, link, times and a content hash only. Reading them is the DR-10 procedure, not an assumption',
        may_store_full_text=False, poll_interval_minutes=60,
        accessibility_verified=True,
        notes='Exchange circulars: market structure and member compliance, '
              'distinct from issuer announcements.'),
    Source('bse_notices', 'BSE Limited', 'exchange_notice',
        'https://www.bseindia.com/data/xml/notices.xml',
        ('issuer_announcement', 'corporate_action', 'market_structure'),
        language='en', rights='publicly reachable feed; redistribution terms NOT reviewed, so headline, link, times and a content hash only. Reading them is the DR-10 procedure, not an assumption',
        may_store_full_text=False, poll_interval_minutes=30,
        accessibility_verified=True,
        notes='Overlaps NSE for dually listed issuers, so one event may arrive '
              'twice. Two exchanges reporting one filing is NOT independent '
              'corroboration.'),
    Source('ustr_press', 'Office of the US Trade Representative',
        'official_policy', 'https://ustr.gov/rss.xml',
        ('trade_policy', 'tariffs', 'trade_negotiation'),
        language='en', rights='publicly reachable feed; redistribution terms NOT reviewed, so headline, link, times and a content hash only. Reading them is the DR-10 procedure, not an assumption',
        may_store_full_text=False, poll_interval_minutes=180,
        accessibility_verified=True,
        notes='USTR announces the policy; the Federal Register carries the '
              'instrument. Related, not duplicates.'),
    Source('federalreserve_speeches', 'Federal Reserve Board', 'official_policy',
        'https://www.federalreserve.gov/feeds/speeches.xml',
        ('forward_guidance', 'monetary_policy', 'banking_regulation'),
        language='en', rights='Federal Reserve Board disclaimer permits copying Board information unless otherwise indicated, with Board attribution. Third-party copyrighted material is excluded. https://www.federalreserve.gov/disclaimer.htm (reviewed 2026-10-18)',
        may_store_full_text=True, poll_interval_minutes=240,
        accessibility_verified=True,
        notes='A speech is a signal about intent, not an instrument.'),
    Source('wto_news', 'World Trade Organization', 'official_policy',
        'https://www.wto.org/library/rss/latest_news_e.xml',
        ('trade_policy', 'trade_disputes', 'supply_chain_finance'), language='en',
        rights='Official RSS headlines and links only; no full-text reuse permission established.',
        may_store_full_text=False, poll_interval_minutes=120,
        accessibility_verified=True,
        notes='Probed 2026-10-18: 10 dated items. Multilateral trade developments; '
              'India exposure must be established separately, never inferred from global relevance.'),
    Source('ec_news', 'European Commission', 'official_policy',
        'https://ec.europa.eu/commission/presscorner/api/rss?language=en',
        ('trade_policy', 'export_controls', 'eu_regulation'),
        language='en', rights='publicly reachable feed; redistribution terms NOT reviewed, so headline, link, times and a content hash only. Reading them is the DR-10 procedure, not an assumption',
        may_store_full_text=False, poll_interval_minutes=240,
        accessibility_verified=True,
        notes='Broad feed: most items are out of scope and the relevance '
              'filter is what keeps that honest.'),
)

#: Probed and NOT usable. Recorded rather than dropped: a gap nobody wrote
#: down becomes a gap nobody remembers.
UNAVAILABLE_SOURCES = (
    ('dgft_notifications', 'https://content.dgft.gov.in/Website/RSSFeed',
     'HTTP 403. Indian trade instruments remain UNCOVERED.'),
    ('cbic_whats_new', 'https://www.cbic.gov.in/entities/view-rss-feed',
     'SSL CERTIFICATE_VERIFY_FAILED. Customs duty changes remain UNCOVERED. '
     'Certificate verification is NOT disabled to work around this.'),
    ('mospi_releases', 'https://www.mospi.gov.in/rss.xml',
     'SSL CERTIFICATE_VERIFY_FAILED. Official statistics remain UNCOVERED.'),
    ('imd_warnings', 'https://mausam.imd.gov.in/responsive/rss/ALL.xml',
     'SSL CERTIFICATE_VERIFY_FAILED. Weather warnings remain UNCOVERED.'),
    ('posoco_grid', 'https://posoco.in/feed/',
     'HTTP 502. Grid operations remain UNCOVERED.'),
    ('cea_reports', 'https://cea.nic.in/feed/',
     'not a feed this parser understands. Power reporting remains UNCOVERED.'),
)

LISTING_SOURCES = (
    Source('mofcom_policy_listing', 'China Ministry of Commerce', 'official_policy',
        'https://english.mofcom.gov.cn/Policies/AnnouncementsOrders/index.html',
        ('export_controls', 'trade_policy'), rights='official listing title/link only; no article text retained',
        poll_interval_minutes=240, notes='English listing can lag Chinese instruments; current legal status requires review.'),
)
DOCUMENT_SOURCES = (
    Source('mofcom_rare_earth_18_2025', 'China Ministry of Commerce', 'official_policy',
        'https://english.mofcom.gov.cn/Policies/AnnouncementsOrders/art/2025/art_0dd87cbee7b045bf93fabe6ab2faceee.html',
        ('export_controls', 'rare_earths'), rights='official document title/link only; no full text redistribution',
        poll_interval_minutes=1440, notes='Historical instrument monitored for title changes; does not establish current legal status or monitor replacement instruments.'),
    Source('tata_kalinganagar_expansion', 'Tata Steel', 'company_filing',
        'https://www.tatasteel.com/media/newsroom/press-releases/india/2025/tata-steel-inaugurates-phase-ii-expansion-of-kalinganagar-operations/',
        ('steel', 'capacity'), rights='issuer release title/link only; no full text redistribution',
        poll_interval_minutes=1440, notes='Historical corporate release; first-seen is acquisition now, not the 2025 event date.'),
)


def register(store: NewsStore, *, reprobe: bool, probe_documents: bool = True) -> int:
    for source, adapter in VERIFIED_JSON_SOURCES:
        verified = source.accessibility_verified
        if reprobe:
            outcome = probe_json(source.url, adapter)
            verified = bool(outcome["usable"])
            print(f"[news] probe {source.source_id} (json/{adapter}): "
                  f"usable={verified} items={outcome.get('items')} "
                  f"newest={outcome.get('newest_published')}")
        if not verified:
            print(f"[news] NOT registering {source.source_id}: it did not "
                  f"probe as a usable JSON source")
            continue
        store.register(source)
        print(f"[news] registered {source.source_id} ({source.provider}, "
              f"json/{adapter}, every {source.poll_interval_minutes}min)")
    for source_id, url, why in REJECTED_SOURCES:
        print(f"[news] NOT registered: {source_id} — {why}")
    for source in EXCHANGE_AND_POLICY_SOURCES:
        registered = store.register(source)
        print(f"[news] registered {registered.source_id} "
              f"({registered.provider}, every "
              f"{registered.poll_interval_minutes}min, "
              f"store_full_text={registered.may_store_full_text})")
    for source_id, url, why in UNAVAILABLE_SOURCES:
        print(f"[news] NOT registered: {source_id} - {why}")

    for source in (VERIFIED_SOURCES + PILOT_SOURCES + ENERGY_SOURCES
                   + NI17_COVERAGE_SOURCES):
        verified = source.accessibility_verified
        if reprobe:
            outcome = probe(source.url)
            verified = bool(outcome["usable"])
            print(f"[news] probe {source.source_id}: usable={verified} "
                  f"items={outcome.get('items')} "
                  f"newest={outcome.get('newest_published')}")
        if not verified:
            print(f"[news] NOT registering {source.source_id}: it did not probe "
                  f"as a usable feed")
            continue
        store.register(source)
        print(f"[news] registered {source.source_id} "
              f"({source.provider}, every {source.poll_interval_minutes}min, "
              f"store_full_text={source.may_store_full_text})")
    from dataclasses import replace
    from seraph.news.documents import DocumentFetcher
    fetcher = build_fetcher()
    existing = {s.source_id for s in store.sources()}
    for source in DOCUMENT_SOURCES + LISTING_SOURCES:
        try:
            if source.source_id in existing and not reprobe:
                store.register(replace(source, accessibility_verified=True))
                continue
            if not probe_documents:
                continue
            result = fetcher(source, None)
            if not result.items: raise ValueError('no document metadata')
            store.register(replace(source, accessibility_verified=True))
            print(f'[news] registered document monitor {source.source_id}')
        except Exception as exc:
            print(f'[news] document monitor unavailable {source.source_id}: {exc}')
    return 0


def build_fetcher(store=None) -> "JsonSourceFetcher":
    """One router over both parsers.

    A JSON source gets its named adapter; everything else falls through to
    the feed fetcher unchanged, so the two kinds share the throttle, the
    conditional GET and the item-identity rule rather than diverging.
    """
    from seraph.news.documents import DocumentFetcher, ListingFetcher
    from seraph.news.enrichment import EnrichingFetcher
    return EnrichingFetcher(ListingFetcher(DocumentFetcher(JsonSourceFetcher({source.source_id: adapter
                              for source, adapter in VERIFIED_JSON_SOURCES}),
                           [s.source_id for s in DOCUMENT_SOURCES]),
                          {"mofcom_policy_listing": "/Policies/AnnouncementsOrders/art/"}), store=store)


def backfill_fetcher(url_builder, since, until):
    """A fetcher that pulls an explicit date range instead of the latest items.

    Returns `FetchedItem`s like any other fetcher, so the whole ingest path --
    dedup, hashing, idempotency, the rights gate, immutability -- applies
    unchanged. Backfill must not become a second write path.
    """
    def fetch(source, cursor=None):
        from seraph.news.json_feed import _published, parse_json_source
        from seraph.news.acquisition import FetchedItem, FetchResult
        items, seen = [], set()
        pages_walked, exhausted = 0, False
        urls = list(url_builder(source.url, since, until))
        for page_url in urls:
            request = urllib.request.Request(
                page_url, headers={"User-Agent": "SERAPH-research/1.0"})
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
            entries = parse_json_source("federal_register", payload,
                                        base_url=page_url)
            pages_walked += 1
            if not entries:
                exhausted = True
                break                      # the range really is exhausted
            for entry in entries:
                ref = entry["guid"] or entry["url"]
                if ref in seen:
                    continue
                seen.add(ref)
                raw = (f"{entry['guid']}|{entry['title']}|"
                       f"{entry['published_raw']}|{entry.get('summary','')}"
                       ).encode("utf-8")
                items.append(FetchedItem(
                    reference=ref, title=entry["title"], url=entry["url"],
                    raw=raw, published_at=_published(entry["published_raw"]),
                    body=entry.get("summary") or None, language="en",
                    metadata=dict(
                        publication_precision=(
                            "day" if len(entry.get("published_raw") or "") == 10
                            else "timestamp"),
                        source_kind_hint=entry.get("source_kind_hint"),
                        acquired_by="backfill")))
        # Truncation is NOT completion. Walking every page the builder
        # offered without the range running out means the cap was hit, and
        # the caller must keep the gap open with a continuation cursor
        # instead of reporting the interval covered.
        backfill_fetcher.last_run_truncated = (not exhausted
                                               and pages_walked >= len(urls))
        return FetchResult(items=tuple(items), cursor=None, http_status=200)
    return fetch


#: How far back to go for a source that has never been fetched. Bounded on
#: purpose: "recover everything ever published" is a different operation with
#: different volume and politeness implications, and conflating the two would
#: make a routine restart issue hundreds of requests.
DEFAULT_BACKFILL_DAYS = 7


def resume_backfills(store: NewsStore, decision_ts: str, fetcher_for) -> dict:
    """Work every OPEN gap, resuming from its stored cursor.

    Bounded: `MAX_PAGES_PER_RUN` pages per gap per run. Hitting the bound
    leaves the gap open with a continuation cursor rather than closing it,
    because truncation is not completion.
    """
    from seraph.news.backfill import federal_register_backfill_urls

    worked, still_open = {}, []
    for gap in store.open_gaps():
        if not gap["recoverable"]:
            # Settled, not filled: the feed cannot reach back that far, and
            # the corpus has a known hole. Closing it as `unrecoverable`
            # records that rather than leaving it to look pending forever.
            store.close_gap(gap["gap_id"], state="unrecoverable",
                            note="this feed exposes only its latest items; "
                                 "the interval cannot be recovered by polling")
            continue

        since = gap["covered_until"] or gap["since"]
        if since is None:
            from datetime import datetime, timedelta
            start = (datetime.strptime(decision_ts, "%Y-%m-%dT%H:%M:%S%z")
                     - timedelta(days=DEFAULT_BACKFILL_DAYS))
            since = start.strftime("%Y-%m-%dT%H:%M:%S%z")

        start_page = gap["next_page"] or 1
        def pages(base, a, b, _p=start_page):
            return federal_register_backfill_urls(
                base, a, b, max_pages=MAX_PAGES_PER_RUN, start_page=_p)

        report = store.ingest(gap["source_id"],
                              backfill_fetcher(pages, since, gap["until"]))
        worked[gap["source_id"]] = report.new_stories
        if not report.ok:
            store.advance_gap(gap["gap_id"])
            still_open.append(gap["source_id"])
            print(f"[news] backfill {gap['source_id']}: FAILED — "
                  f"{report.error}. The gap stays OPEN")
            continue

        truncated = getattr(backfill_fetcher, "last_run_truncated", False)
        if truncated:
            store.advance_gap(gap["gap_id"],
                              next_page=start_page + MAX_PAGES_PER_RUN,
                              recovered=report.new_stories)
            still_open.append(gap["source_id"])
            print(f"[news] backfill {gap['source_id']}: page cap reached after "
                  f"{report.new_stories} stories; the gap stays OPEN and will "
                  f"resume at page {start_page + MAX_PAGES_PER_RUN}")
        else:
            store.advance_gap(gap["gap_id"], covered_until=gap["until"],
                              recovered=report.new_stories)
            store.close_gap(gap["gap_id"], state="recovered")
            print(f"[news] backfill {gap['source_id']}: interval covered, "
                  f"{report.new_stories} stories recovered")
    return dict(recovered=worked, still_open=still_open)


#: Pages per gap per run. A bound makes startup predictable; the continuation
#: cursor makes it eventually complete.
MAX_PAGES_PER_RUN = 10


def run_backfill(store: NewsStore, decision_ts: str) -> dict:
    """Recover what can be recovered; report what cannot.

    The second half is not a consolation prize. A source whose feed exposes
    only its latest items has lost whatever rotated out during the gap, and a
    console that resumes without saying so presents an incomplete corpus as a
    complete one.
    """
    from seraph.news.backfill import federal_register_backfill_urls, plan_backfill
    plan = plan_backfill(store, decision_ts)
    recovered, failures = {}, {}
    for gap in plan["gaps"]:
        if not gap["recoverable"]:
            continue
        # A source that has NEVER been fetched has no `since`, and
        # backfilling from `decision_ts` to `decision_ts` covers a zero-width
        # window and silently recovers nothing. A bounded default is used
        # instead, and named in the result so nobody reads it as "everything
        # this source ever published".
        since = gap["since"]
        if since is None:
            from datetime import datetime, timedelta
            start = (datetime.strptime(decision_ts, "%Y-%m-%dT%H:%M:%S%z")
                     - timedelta(days=DEFAULT_BACKFILL_DAYS))
            since = start.strftime("%Y-%m-%dT%H:%M:%S%z")
            print(f"[news] backfill {gap['source_id']}: never fetched; using "
                  f"a bounded {DEFAULT_BACKFILL_DAYS}-day window, NOT the "
                  f"source's full history")
        report = store.ingest(
            gap["source_id"],
            backfill_fetcher(federal_register_backfill_urls, since, decision_ts))
        recovered[gap["source_id"]] = report.new_stories
        if not report.ok:
            # "0 recovered" reads as "nothing to recover". A failed fetch is a
            # different fact and must not wear the same words.
            failures[gap["source_id"]] = report.error
            print(f"[news] backfill {gap['source_id']}: FAILED — "
                  f"{report.error}. The gap is NOT recovered")
        else:
            print(f"[news] backfill {gap['source_id']}: "
                  f"{report.new_stories} recovered story/stories")
    for gap in plan["gaps"]:
        if gap["recoverable"]:
            continue
        print(f"[news] GAP {gap['source_id']}: {gap['note']}")
    plan["recovered_stories"] = recovered
    plan["failed_backfills"] = failures
    plan["recovered_cleanly"] = not failures
    return plan


def _deadline_in(*, seconds: float) -> str:
    """An explicit deadline for the operation about to start.

    Declared up front so that overrunning it is observable. An operation that
    does not say when it should finish cannot be told apart from one that
    will never finish.
    """
    from datetime import datetime, timedelta
    moment = datetime.strptime(_now(), "%Y-%m-%dT%H:%M:%S%z") + timedelta(seconds=seconds)
    return moment.strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":" + moment.strftime("%z")[-2:]


def _work_forced(store: NewsStore, fetcher):
    """A job body for one catch-up pass: every source, due or not.

    Unlike the steady-state pass this does NOT raise on a partial failure. A
    catch-up runs at startup, and one unreachable source must not stop the
    server coming up with everything else refreshed -- the failure is recorded
    in source health and shows as uncovered, which is where it belongs.
    """
    def run(context):
        reports = poll_once(store, fetcher, force=True)
        context.checkpoint({"last_catch_up": _now()})
        failed = [r["source_id"] for r in reports if not r["ok"]]
        if failed:
            print("[news] catch-up: these sources failed and are reported as "
                  "uncovered, not as a quiet market: " + ", ".join(failed))
        return {"sources": len(reports), "forced": True,
                "failed": failed,
                "new_stories": sum(r["new_stories"] for r in reports)}
    return run


def poll_once(store: NewsStore, fetcher, *, now=None, force=False) -> list[dict]:
    reports = []
    now = now or _now()
    def observed(report):
        reports.append(report.describe())
        line = (f"[news] {report.source_id}: ok={report.ok} "
                f"new={report.new_observations} unchanged={report.unchanged} "
                f"stories={report.new_stories} corrections={report.corrections}")
        if report.error:
            line += f" — {report.error}"
        print(line, flush=True)
    outcome = acquire(store, fetcher, now=now, force=force,
                      budget_seconds=90, on_report=observed)
    for source_id in outcome.skipped_for_budget:
        reports.append(dict(source_id=source_id, ok=False, new_stories=0,
                            error='not contacted: acquisition budget exhausted'))
    print('[news] pass: ' + str(outcome.describe()), flush=True)
    return reports


def show_status(store: NewsStore) -> int:
    now = _now()
    sources = store.sources()
    if not sources:
        print("[news] NO SOURCES REGISTERED. Run with --register first.")
        return 1
    coverage = store.coverage_at(now)
    print(json.dumps(dict(
        now=now,
        sources=[dict(id=s.source_id, provider=s.provider,
                      verified=s.accessibility_verified,
                      every_minutes=s.poll_interval_minutes,
                      health=store.health(s.source_id).status,
                      last_success=store.health(s.source_id).last_success_at)
                 for s in sources],
        coverage=dict(covered=coverage.covered, total=coverage.total,
                      complete=coverage.is_complete,
                      uncovered=list(coverage.uncovered)),
        stories=len(store.stories()),
        newest_story=max((s.first_seen_at for s in store.stories()), default=None),
    ), indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", type=Path, default=DEFAULT_STORE)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--reprobe", action="store_true",
                        help="re-verify accessibility while registering")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--backfill", action="store_true",
                        help="recover the gap since each source's last "
                             "successful fetch, where the source supports a "
                             "date range, and report explicitly where it does "
                             "not. A feed exposing only its latest items has "
                             "PERMANENTLY lost what rotated out")
    parser.add_argument("--catch-up", action="store_true",
                        help="before entering the loop, poll EVERY source "
                             "once regardless of whether it is due. A worker "
                             "restarted shortly after a poll would otherwise "
                             "wait out the remaining interval while the "
                             "server shows hours-old data")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--retention", action="store_true",
                        help="apply each source's declared retention window "
                             "to stored text and exit. Removes the TEXT and "
                             "keeps the observation, its content hash and an "
                             "immutable redaction record, so enforcing "
                             "retention cannot rewrite the audit trail")
    parser.add_argument("--dry-run", action="store_true",
                        help="with --retention, report what would be removed")
    parser.add_argument("--interval", type=float, default=300.0)
    parser.add_argument("--jobs", type=Path,
                        default=ROOT / "prototype_runs" / "jobs.sqlite")
    args = parser.parse_args(argv)

    store = NewsStore(args.store)
    if args.register:
        return register(store, reprobe=args.reprobe)
    if args.status:
        return show_status(store)
    if args.retention:
        import json as _json
        print(_json.dumps(store.apply_retention(dry_run=args.dry_run), indent=2))
        return 0
    from seraph.news.worker_lock import worker_lock, WorkerAlreadyRunning
    try:
        with worker_lock(args.store):
            return _run_worker(args, store)
    except WorkerAlreadyRunning as exc:
        print(f"[news] {exc}")
        return 2


def _run_worker(args, store):
    # BEAT FIRST. Registration contacts every unregistered source, and a
    # roster with unreachable hosts spends minutes in connection timeouts
    # before the old first beat was reached. During that window the store
    # still held the PREVIOUS run's heartbeat -- typically `stopped` --
    # so the supervisor's startup grace expired, it read a stale row that
    # did not belong to its child, and it killed a worker that was busy
    # doing exactly what it was told. The deadline is declared here so a
    # slow registration is distinguishable from a hung one.
    store.beat(status="catching_up" if args.catch_up else "running",
               pid=os.getpid(), activity="reconciling source registrations",
               deadline=_deadline_in(seconds=600),
               detail="contacting unregistered sources; no polling yet")
    # Reconcile reviewed configuration in the background worker. Serving the
    # cached frontend never waits for source probes or registration requests.
    register(store, reprobe=False, probe_documents=False)
    fetcher = build_fetcher(store)
    jobs = JobStore(args.jobs)

    def work(context):
        """One steady-state pass.

        A source that fails is NOT a failed pass. This used to raise on any
        partial failure, the loop wrote heartbeat `failed`, and the
        supervisor -- which restarts anything that is not alive -- killed a
        perfectly healthy worker. A publisher returning 503 could therefore
        exhaust the restart budget and stop every working feed with it.

        The failure is not hidden: it is recorded against that source's
        health, reported as uncovered by `coverage_at`, named in the
        returned detail, and the heartbeat says `degraded`.
        """
        reports = poll_once(store, fetcher)
        context.checkpoint({"last_poll": _now()})
        failed = [r['source_id'] for r in reports if not r['ok']]
        if failed:
            print('[news] degraded sources this pass (healthy feeds '
                  'continue): ' + ', '.join(failed), flush=True)
        return {"sources": len(reports), "degraded": failed,
                "new_stories": sum(r["new_stories"] for r in reports)}

    if args.backfill:
        import json as _json
        print(_json.dumps(run_backfill(store, _now()), indent=2)[:2000])
        return 0

    if args.once:
        outcome = jobs.run(JOB, work, max_attempts=1)
        if outcome.status == "lock_unavailable":
            print(f"[news] {outcome.error}")
            return 1
        return 0 if outcome.status == "succeeded" else 1

    # The OS lock is authoritative: a stale heartbeat alone cannot establish
    # that a previous owner is dead. Ownership precedes all startup I/O.
    store.beat(status="running", pid=os.getpid(), activity="starting",
               deadline=_deadline_in(seconds=180))
    if args.catch_up:
        store.beat(status="catching_up", pid=os.getpid(),
                   activity="startup recovery", deadline=_deadline_in(seconds=300))
        # ORDER MATTERS. Polling first overwrites source_health.last_success_at
        # and erases the evidence of the outage, so startup used to destroy
        # the record of the gap it existed to recover from.
        from seraph.news.backfill import record_gaps
        opened = record_gaps(store, _now())
        if opened:
            print(f"[news] catch-up: recorded {len(opened)} collection gap(s) "
                  f"before polling could hide them")
        # Latest news comes first; a historical backfill must not hold up
        # current acquisition. The persisted gaps survive this forced poll.
        jobs.run(JOB, _work_forced(store, fetcher), max_attempts=1)
        # Current news is now in. The HISTORICAL backfill does NOT run here.
        #
        # It used to, under a single 300-second catch-up deadline covering
        # both. On a real roster that deadline expires while the backfill
        # is still working, `worker_state` then reports `stalled` -- which
        # is what the deadline is for -- and the supervisor terminates a
        # worker that was doing exactly what it was asked to. Startup is
        # also the worst possible place for it: nothing on the screen can
        # update until an unbounded recovery of old pages finishes.
        #
        # It is resumed inside the loop instead, after the first steady
        # pass, where it is bounded, re-declares its own deadline, and
        # cannot delay current acquisition.
        print("[news] catch-up: current news fetched; historical backfill "
              "runs after the first steady pass, not before it")

    # One owner per store. A second worker doubles every fetch and races on
    # the same acquisition requests.
    owned = store.claim_worker_ownership("news.poll", os.getpid())
    if not owned["granted"]:
        print(f"[news] not starting: {owned['reason']}")
        return 1

    # We hold the exclusive OS lock on this store, so no other live local
    # worker can legitimately be mid-run. A lease left behind by a process
    # that is gone would otherwise block every poll for its full term while
    # the heartbeat kept reporting `running`.
    reconciled = jobs.reconcile_lock(JOB, reason="replacement worker holds "
                                                 "the OS lock on this store")
    if reconciled["cleared"]:
        print(f"[news] cleared an abandoned {JOB} lease: {reconciled['reason']}")
        store.beat(status="running", pid=os.getpid(), activity="starting",
                   detail=reconciled["reason"],
                   deadline=_deadline_in(seconds=180))
    elif reconciled.get("held") and not reconciled.get("expired"):
        print(f"[news] {JOB} lease held: {reconciled['reason']}")

    retention = store.apply_retention()
    if retention["redacted"]:
        print(f"[news] retention removed stored text from "
              f"{retention['redacted']} observation(s); the rows, hashes and "
              f"redaction records remain")

    print(f"[news] polling every {args.interval:.0f}s; Ctrl+C to stop")
    beat_detail = f"interval={args.interval:.0f}s"
    passes = 0
    # JOB-level failures only. A source returning an error never increments
    # this; it is degraded coverage, not a broken worker.
    job_failures = 0
    try:
        while True:
            # Beat BEFORE the work: the heartbeat answers "is the worker
            # alive", and a worker stuck inside a slow fetch is alive. Beating
            # only after a successful pass would report a hung fetch as death
            # and a dead process as neither.
            # A deadline declared BEFORE the work makes a long operation
            # distinguishable from a deadlock: a pass that blows through its
            # own stated deadline is stalled, one that has not is simply
            # still running.
            passes += 1
            store.beat(status="running", pid=os.getpid(), detail=beat_detail,
                       sequence=passes, activity="polling due sources",
                       deadline=_deadline_in(seconds=180))
            # A console asking for acquisition queues a request rather than
            # fetching inside a web request. The worker is the one process
            # that already owns the sources, so it serves it here -- which is
            # also what makes two browser tabs produce one acquisition.
            claimed = store.claim_acquisition(worker="news.poll")
            if claimed is not None:
                store.beat(status="running", pid=os.getpid(),
                           sequence=passes,
                           activity=f"serving acquisition request "
                                    f"{claimed['request_id']}",
                           deadline=_deadline_in(seconds=120),
                           detail=f"serving acquisition request "
                                  f"{claimed['request_id']}")
                outcome = acquire(store, fetcher, now=_now(),
                                  budget_seconds=60.0, force=True)
                store.finish_acquisition(claimed["request_id"],
                                         claim_token=claimed["claim_token"],
                                         progress=outcome.describe())
                print(f"[news] served acquisition request "
                      f"{claimed['request_id']}: "
                      f"{outcome.new_stories} new story/stories")
            store.beat(status="running", pid=os.getpid(), sequence=passes,
                       activity="polling due sources", deadline=_deadline_in(seconds=180))
            outcome = jobs.run(JOB, work, max_attempts=1)
            # The outcome used to be discarded, so a pass that fetched
            # NOTHING beat "running / waiting for next poll" exactly like a
            # successful one. Reporting it is right; reporting it as a dead
            # PROCESS was not -- the supervisor restarts anything that is
            # not alive, so a publisher's 503 terminated a healthy worker
            # and could exhaust the restart budget. Three states, apart:
            #
            #   pass ran, every source ok                    -> running
            #   pass ran with failed sources, or no pass ran
            #     because the lease was held                 -> degraded
            #   the pass machinery itself raised, repeatedly -> failed,
            #     the one case a supervisor should act on
            idle = _deadline_in(seconds=max(30.0, args.interval) + 60)
            degraded = list((outcome.detail or {}).get("degraded") or ())
            if outcome.status == "lock_unavailable":
                job_failures = 0
                print(f"[news] pass {passes} did NOT poll: {outcome.error}")
                store.beat(status="degraded", pid=os.getpid(), sequence=passes,
                           activity="lock_unavailable", deadline=idle,
                           detail=(f"no acquisition this pass: {outcome.error}. "
                                   f"A heartbeat is not evidence of polling"))
            elif outcome.status != "succeeded":
                job_failures += 1
                limit = store.MAX_CONSECUTIVE_JOB_FAILURES
                print(f"[news] pass {passes} failed "
                      f"({job_failures}/{limit}): {outcome.error}")
                terminal = job_failures >= limit
                store.beat(status="failed" if terminal else "degraded",
                           pid=os.getpid(), sequence=passes,
                           activity="poll failed", deadline=idle,
                           detail=(f"{outcome.status}: {outcome.error} "
                                   f"({job_failures} consecutive)"))
                if terminal:
                    # The pass machinery is broken, not a publisher. Exit so
                    # the supervisor can replace the process: staying up and
                    # reporting `degraded` for ever would be exactly the
                    # quiet failure a supervisor exists to prevent.
                    print(f"[news] {job_failures} consecutive job failures; "
                          f"exiting for the supervisor to replace this worker")
                    return 1
            elif degraded:
                job_failures = 0
                store.beat(status="degraded", pid=os.getpid(), sequence=passes,
                           activity="waiting for next poll", deadline=idle,
                           detail=(f"{len(degraded)} source(s) degraded, "
                                   f"healthy feeds continuing: "
                                   f"{', '.join(degraded)}"))
            else:
                job_failures = 0
                store.beat(status="running", pid=os.getpid(), sequence=passes,
                           activity="waiting for next poll", deadline=idle)
            if args.catch_up and passes == 1:
                # Deferred off the startup path on purpose: current news is
                # already in, the screen is already serving it, and this
                # declares its OWN deadline so a long recovery of old pages
                # is distinguishable from a hung worker instead of being
                # mistaken for one.
                store.beat(status="catching_up", pid=os.getpid(),
                           sequence=passes, activity="historical backfill",
                           deadline=_deadline_in(seconds=900))
                try:
                    resumed = resume_backfills(store, _now(), fetcher)
                    if resumed["recovered"]:
                        print(f"[news] backfill recovered {resumed['recovered']}")
                    if resumed["still_open"]:
                        print(f"[news] gaps still OPEN (truncated or failed): "
                              f"{', '.join(resumed['still_open'])}")
                except Exception as exc:            # noqa: BLE001 - recorded
                    # Recovering history must never stop current news.
                    print(f"[news] backfill failed, current acquisition "
                          f"continues: {type(exc).__name__}: {exc}")
                store.beat(status="running", pid=os.getpid(), sequence=passes,
                           activity="waiting for next poll", deadline=idle)
            if passes % 100 == 0:
                # Idempotent and bounded. A worker that runs for a week must
                # not be the reason a 30-day window is never enforced.
                store.apply_retention()
            time.sleep(max(30.0, args.interval))
    except KeyboardInterrupt:
        print("\n[news] stopped")
        store.beat(status="stopped", pid=os.getpid(),
                   detail="stopped cleanly by operator")
    except Exception as exc:                        # noqa: BLE001 - recorded
        # A worker that dies of an exception must say so in the store, because
        # the UI cannot otherwise distinguish it from a quiet market.
        store.beat(status="failed", pid=os.getpid(),
                   detail=f"{type(exc).__name__}: {exc}")
        raise
    return show_status(store)


if __name__ == "__main__":
    raise SystemExit(main())
