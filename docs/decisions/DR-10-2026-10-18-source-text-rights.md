# DR-10 — may SERAPH retain source full text? Answered per source

**Date:** 2026-10-18
**Ticket:** `NI08`
**Status:** **Decided for 5 of 11 sources; 6 remain `False`.**

---

## Why this was open

`scripts/run_news.py` set `may_store_full_text=False` for every source, and
said why:

> These are public government feeds and the summaries are short, but "publicly
> reachable" is not "licensed to redistribute", and that question has not been
> answered for any of them. So SERAPH keeps the headline, the link, the times
> and a content hash, and does not retain article bodies. **Changing that needs
> the terms read, not a convenient assumption.**

That was the right default. The cost is real: of 278 stories, ~20 had bodies,
so interpretation ran on titles alone. The Federal Register adapter already
extracts each document's `abstract` and the store was discarding it.

This record answers the question **per source, by reading the terms**. Nothing
here is inferred from "it's a government site".

---

## What each source actually says

### Permitted — US Government works (17 U.S.C. §105)

**`federal_register`, `federal_register_india`**

GPO's policies page, quoting the statute:

> "Copyright protection under this title is not available for any work of the
> United States Government"

A "work of the United States Government" is defined by 17 U.S.C. §101 as one
"prepared by an officer or employee of the United States Government as part of
the person's official duties" — which is what a Federal Register document is.
GPO adds that "public documents can generally be reprinted without legal
restriction."

Source: <https://www.govinfo.gov/about/policies>

**Conditions carried into the Source record.** GPO states two:

- "customary credit should be given to the Government department or agency
  which prepared the material"
- "Government publications may contain copyrighted material which was used
  with permission of the copyright owner" — publication in a Government
  document does not authorise reuse of that embedded material.

*Note:* `federalregister.gov`'s own legal-status page could not be read — it
redirects to a bot-detection "unblock" page, which was not followed. The
determination rests on the statute and GPO's policy, which are the better
authorities anyway.

### Permitted — USGS

> "Most U.S. Geological Survey (USGS) information resides in the Public Domain
> and may be used without restriction. When using information from USGS
> information products, publications, or websites, we ask that proper credit
> be given."

Credit is *requested*, not a licence condition. The same exception applies:
"Some non USGS photographs, images, and/or graphics are used by the USGS with
permission from the copyright holder."

Source: <https://www.usgs.gov/information-policies-and-instructions/acknowledging-or-crediting-usgs>

### Permitted — Press Information Bureau

The PIB Copyright Policy, in full:

> "Material featured on this website may be reproduced free of charge and
> there is no need for any prior approval for using the content. The
> permission to reproduce this material shall not extend to any third-party
> material. Authorisation to reproduce such material must be obtained from the
> departments/copyright holders concerned. The material must be reproduced
> accurately and not used in a derogatory manner or in a misleading context.
> Wherever the material is being published or issued to others, the source
> must be prominently acknowledged."

Source: <https://factcheck.pib.gov.in/Documents/CopyrightPolicy.pdf>

*Provenance caveat, stated because it matters:* `pib.gov.in`'s own copyright
page returned **403** to this fetch. The document quoted above is the same
policy hosted on `factcheck.pib.gov.in`, a PIB-operated domain, titled
"Copyright Policy" and written site-generically ("this website"). It is good
evidence and it is not the primary page. If that distinction ever becomes
load-bearing, re-read `pib.gov.in/content/102_2_Copyright-Policy.aspx`
directly.

### Already permitted

**`fed_press`** — already `may_store_full_text=True`, recorded as
"Board-authored public-domain feed text; attribution required". Unchanged by
this record; consistent with §105.

---

## Refused — and these stay refused

### `rbi_press_releases`, `rbi_notifications`, `rbi_speeches`

The RBI copyright page says, in its entirety:

> "© Reserve Bank of India. All Rights Reserved."

There is no grant. "All Rights Reserved" is the opposite of a licence, and the
disclaimer page redirects to the site root. **`may_store_full_text` stays
`False`.** SERAPH keeps RBI headlines, links, times and hashes, as now.

Source: <https://www.rbi.org.in/Scripts/Copyright.aspx>

### `sebi_press`

SEBI's website policy permits reproduction **only after obtaining permission**:

> material featured on this Website may be reproduced free of charge **after
> taking proper permission by sending a mail to us**

with conditions that the material be accurate, not used misleadingly or
derogatorily, and that the source be credited. Third-party material is
excluded.

That permission has **not been requested or obtained**, so this stays `False`.
It is a one-email action, but it is a human's to take — fabricating a
permission is precisely the failure this record exists to avoid.

Source: <https://www.sebi.gov.in/website-policy.html>

### `tata_kalinganagar_expansion`, `mofcom_*`

A corporate press release and a foreign ministry's listing. Neither has been
read. They stay `False` by the original default.

---

## Decision table

| Source | `may_store_full_text` | Basis |
|---|---|---|
| `federal_register` | **True** | 17 U.S.C. §105 (GPO) |
| `federal_register_india` | **True** | 17 U.S.C. §105 (GPO) |
| `usgs_earthquakes` | **True** | USGS public domain statement |
| `pib_releases` | **True** | PIB Copyright Policy, no prior approval |
| `fed_press` | True (unchanged) | Board-authored, §105 |
| `rbi_press_releases` | False | "All Rights Reserved", no grant |
| `rbi_notifications` | False | as above |
| `rbi_speeches` | False | as above |
| `sebi_press` | False | permission required, not obtained |
| `tata_kalinganagar_expansion` | False | not reviewed |
| `mofcom_*` | False | not reviewed |

Every permitted source carries the same two conditions, and the `rights`
string on each Source record now states them rather than saying terms were
never reviewed:

1. **the source must be acknowledged** — PIB requires it "prominently", GPO
   and USGS request customary credit;
2. **third-party material embedded in a government document is not covered**,
   and SERAPH must not treat a quoted or reproduced excerpt as licensed.

---

## What this does and does not change

**Does:** new stories from the four sources retain the body the fetcher
already extracts — for the Federal Register, the document's `abstract`, which
is a substantive paragraph describing the action rather than a headline.

**Does not:** stories already in the store stay body-less. Rows are immutable
by trigger (`stories are immutable; publish a correction`), and a re-poll of
unchanged items produces `unchanged`, not a new row. Body coverage therefore
grows forward from this date rather than being back-filled — which is the
correct behaviour for an append-only record, and means the coverage figure
will climb gradually rather than jump.

**Still out of scope:** fetching the *full document text* from each
document's own page. These bodies are feed-supplied abstracts. Retrieving and
storing complete documents is a separate question about volume and about each
page's terms, and this record does not answer it.
