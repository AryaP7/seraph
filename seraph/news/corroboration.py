"""C13 — is this event corroborated, or just repeated?

`Event.confirmations` counts distinct reporting origins, and a syndication
group carries ONE of them however many outlets ran the copy. That is right:
ten papers carrying one agency wire are one piece of evidence with ten
witnesses, and counting them as ten confirmations is the single easiest way
to manufacture confidence out of a press distribution list.

What was wrong is what the system said about it. `reporting_origins` held a
single group token, so every event reported `confirmations = 1` and nothing
distinguished the four genuinely different situations behind that number:

* **Document duplication** — the same bytes fetched twice.
* **Copied reporting** — different publishers, the same text. More outlets,
  no more evidence.
* **Same-event identity** — different publishers, different text, one event.
  This is the only one that could be corroboration.
* **Event revision** — a correction or an update to something already held.

This module reports which of those the group looks like, and refuses the
last step: **independence is not established here.** Two outlets writing
different sentences may still be reading the same handout, and nothing in
this corpus records wire relationships or newsroom sourcing. So the output
is an observation about the documents, never a claim about their sources,
and it does not raise `confirmations`.
"""
from __future__ import annotations

import hashlib
import re

from seraph.news.model import syndication_tokens

#: Below this Jaccard overlap of content tokens, two headlines are treated
#: as differently written. Deliberately high: the question is whether the
#: text was COPIED, and a rewritten lead usually keeps most of the nouns.
COPY_OVERLAP = 0.8


def _digest(story) -> str:
    return hashlib.sha256(
        f"{story.title}\u0000{story.body or ''}".encode()).hexdigest()


def _overlap(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def assess(stories) -> dict:
    """What a syndication group's documents establish, and what they do not."""
    stories = list(stories)
    if not stories:
        return dict(documents=0, publishers=[], distinct_texts=0,
                    duplicates=0, copied_reporting=0, differently_written=0,
                    independence_verified=False,
                    corroboration="none",
                    note="no documents")

    publishers = sorted({s.source_id for s in stories})
    digests = {}
    for story in stories:
        digests.setdefault(_digest(story), []).append(story)
    duplicates = sum(len(group) - 1 for group in digests.values())

    tokens = [set(syndication_tokens(s.title)) for s in digests.values()
              for s in [s[0]]]
    copied = differently_written = 0
    for index, left in enumerate(tokens):
        for right in tokens[index + 1:]:
            if _overlap(left, right) >= COPY_OVERLAP:
                copied += 1
            else:
                differently_written += 1

    if len(publishers) <= 1:
        kind = "single_publisher"
    elif differently_written:
        kind = "independently_written"
    else:
        kind = "copied_reporting"

    return dict(
        documents=len(stories),
        publishers=publishers,
        distinct_texts=len(digests),
        duplicates=duplicates,
        copied_reporting=copied,
        differently_written=differently_written,
        corroboration=kind,
        # The load-bearing field. `independently_written` is an observation
        # about the TEXT; two newsrooms rewriting one handout produce it
        # just as readily as two reporters who each made a phone call.
        independence_verified=False,
        note=("`corroboration` describes the documents, not their sources. "
              "Independent origin is NOT established by this system and does "
              "not raise `confirmations`: a syndication group is one "
              "reporting origin however many outlets carry it, and "
              "differently written copy is evidence of two keyboards, not of "
              "two sources"))


def describe_event(event, stories) -> dict:
    """Corroboration for one event, with its revision history attached."""
    found = assess(stories)
    corrections = [s.story_id for s in stories if getattr(s, "corrects", None)]
    retractions = [s.story_id for s in stories if getattr(s, "retracts", None)]
    return dict(found, event_id=getattr(event, "event_id", None),
                confirmations=getattr(event, "confirmations", None),
                revisions=len(corrections), retractions=len(retractions),
                revision_note=("a correction is a new state of the same "
                               "document, not a second report of the event"))
