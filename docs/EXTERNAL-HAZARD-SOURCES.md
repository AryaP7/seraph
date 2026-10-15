# External public-health hazard source register

Verified on 2026-10-14 for the market-data cutoff **2026-08-21**. This register
contains **nine new or initial WHO PHEIC declarations**, each checked against a
dated WHO primary publication. It is a source register and a hypothetical
scenario design, not evidence of a successful financial predictor.

## Uniform inclusion rule

Include the first WHO declaration for a distinct emergency, including a new
declaration after a prior emergency ended. Include every qualifying event,
whether or not an equity-market crisis followed. Exclude continuations,
renewals, emergency terminations, national/continental declarations, and
committee meetings that did not declare a WHO PHEIC. This distinguishes the two
mpox declarations and the three separate Ebola declarations.

The machine-readable register is `research_data/public_health_events.json`.
Its `title` fields are short descriptive source labels, not verbatim article
titles. Each `evidence_excerpt` is a direct source fragment under 25 words.

| Displayed publication date | Included event | WHO primary evidence |
|---|---|---|
| 2009-04-25 | H1N1 influenza | [Initial committee statement](https://www.who.int/news/item/25-04-2009-first-meeting-of-the-ihr-emergency-committee) |
| 2014-05-05 | International spread of wild poliovirus | [Polio declaration](https://www.who.int/news/item/05-05-2014-who-statement-on-the-meeting-of-the-international-health-regulations-emergency-committee-concerning-the-international-spread-of-wild-poliovirus) |
| 2014-08-08 | Ebola in West Africa | [Initial Ebola statement](https://www.who.int/news/item/08-08-2014-statement-on-the-1st-meeting-of-the-ihr-emergency-committee-on-the-2014-ebola-outbreak-in-west-africa) |
| 2016-02-01 | Microcephaly and neurological clusters associated with Zika | [Director-General statement](https://www.who.int/news-room/detail/01-02-2016-who-director-general-summarizes-the-outcome-of-the-emergency-committee-regarding-clusters-of-microcephaly-and-guillain-barr%C3%A9-syndrome) |
| 2019-07-17 | Ebola in eastern DRC, Kivu/Ituri outbreak | [DRC declaration](https://www.who.int/news-room/detail/17-07-2019-ebola-outbreak-in-the-democratic-republic-of-the-congo-declared-a-public-health-emergency-of-international-concern) |
| 2020-01-30 | Novel coronavirus, subsequently named COVID-19 | [Second committee statement](https://www.who.int/news/item/30-01-2020-statement-on-the-second-meeting-of-the-international-health-regulations-(2005)-emergency-committee-regarding-the-outbreak-of-novel-coronavirus-(2019-ncov)) |
| 2022-07-23 | First multicountry mpox emergency | [Director-General announcement](https://www.who.int/news-room/speeches/item/who-director-general-s-statement-on-the-press-conference-following-IHR-emergency-committee-regarding-the-multi--country-outbreak-of-monkeypox--23-july-2022) |
| 2024-08-14 | New mpox emergency | [Renewed mpox declaration](https://www.who.int/news/item/14-08-2024-who-director-general-declares-mpox-outbreak-a-public-health-emergency-of-international-concern) |
| 2026-05-17 | Bundibugyo Ebola in DRC/Uganda | [New Ebola declaration](https://www.who.int/news/item/17-05-2026-epidemic-of-ebola-disease-in-the-democratic-republic-of-the-congo-and-uganda-determined-a-public-health-emergency-of-international-concern) |

The ninth declaration matters: a register stopping at the eight events through
2024 would omit a qualifying event inside this project's 2026 data coverage.

## Completeness checks and limits

The disease families were cross-checked against WHO's current
[IHR committee index](https://www.who.int/teams/ihr/ihr-emergency-committees).
The other listed committees are not additional positive declarations:
[MERS](https://www.who.int/groups/mers-cov-ihr-emergency-committee),
[yellow fever](https://www.who.int/groups/yellow-fever-ihr-emergency-committee),
and [2018 Equateur Ebola](https://www.who.int/news-room/detail/18-05-2018-statement-on-the-1st-meeting-of-the-ihr-emergency-committee-regarding-the-ebola-outbreak-in-2018)
did not produce PHEIC declarations. They are excluded by the same rule, not
because of their market outcomes.

Targeted WHO searches for 2025 and 2026 found no further new declaration before
2026-08-21. The 2025 mpox material includes continuation and the
[September termination](https://www.who.int/news-room/speeches/item/who-director-general-s-opening-remarks-at-the-media-briefing---5-september-2025),
not a new initial event. The 2026 Ebola committee record identifies
[May and August follow-up meetings](https://www.who.int/groups/ihr-emergency-committee-regarding-the-epidemic-of-ebola-bundibugyo-virus-disease-in-the-drc-and-uganda);
its August 24 recommendations are both a continuation and later than the
market cutoff. No such later publication is an input to this replay.

This is a documented, manually cross-checked inventory, **not a certified audit
of an immutable WHO historical archive**. Search indexing and live-page
revision can affect completeness. The 2026 May declaration page explicitly
records a later correction to a case detail; none of those revised case counts
are features. The declaration itself and its displayed date are the facts used.

## Hypothetical fixed watch rule

This is a rule declared for the new scenario replay before calculating that
scenario's results. It was **not preregistered before COVID**. Both the choice of
health declarations and the 20-session duration are hindsight-informed research
choices, not parameters proven to have been selected without knowledge of 2020.

1. For every new declaration, activate a health-hazard watch on the first
   observed market session whose calendar date is **strictly after** the
   displayed WHO publication date. Use an after-close decision.
2. Keep the watch active for exactly 20 observed sessions including that first
   session. Take the union if watches overlap. Do not extend a watch because
   its market outcome looks promising or because a continuation meeting occurs.
3. Do not fit a coefficient, optimize duration against COVID, or assign a crisis
   probability to the binary watch. It represents an external hazard deserving
   review, not a known causal market-crash forecast.
4. Retain every watch, including watches without a subsequent crisis. Report
   publication date, first usable session, last watched session, data coverage,
   total warning time, and the market outcomes under the same frozen targets.
5. Report external-only, pillar-only, and combined policies separately. If the
   external channel creates a warning and the three pillars do not contribute,
   credit the external channel. Keep Hawkes, RMT, and Hamilton as visible
   measurements; do not present the overlay as proof of their predictive skill.

**Availability limitation:** the source pages establish calendar dates but do
not establish exact first-publication timestamps for this entire register.
`publication_timestamp` is therefore null. The next-observed-session convention
reduces same-day timing leakage, but is an approximation and **does not prove
that a historical feed delivered each event by the assumed decision time**.
Publication time zones, initial delays, page revisions, and acquisition latency
would require timestamped historical feeds or archived snapshots for a stronger
claim. No initial-publication hour has been invented.

Observed sessions must come from the actual market-data calendar, including
holidays and special sessions, rather than a generic weekday calendar. If
source data are absent around an event, mark the watch coverage incomplete;
mapping a declaration across a long data gap does not establish timely warning.

The January 30, 2020 declaration is an example of potentially relevant public
information before the project's COVID onset label. Whether this uniform rule
would yield useful warnings at an acceptable false-alarm cost is a **separate
retrospective calculation**; this source register makes no performance claim.
