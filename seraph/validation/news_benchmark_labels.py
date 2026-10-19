"""NI17 — hand-labelled benchmark examples. **Provisional: one labeller.**

Every label here was assigned by reading the document title and deciding what
it says, *before* comparing against the extractor. That ordering is the only
thing that makes the evaluation non-circular: labelling by running the
extractor and calling its output the truth would report 100% and mean nothing.

**Provenance and its limits.** One labeller, and not a human one. The plan
requires two independent reviewers with adjudication, so this corpus is marked
`provisional` and no inter-annotator reliability is claimed. It is a
regression and sanity instrument, not evidence of accuracy.

**Hard negatives are over-represented on purpose.** The `adversarial` group is
every semantic defect actually found during development — each one a case
where the extractor confidently produced a wrong answer. They are the examples
most likely to regress, so they are pinned here rather than left to memory.

Fields:
  `stage`   the legal status the document asserts about ITSELF
  `klass`   the event class
  `sector`  the sector a documented exposure should reach, or None
"""
from __future__ import annotations

#: (headline, klass, stage, sector, group, why this label)
LABELLED: tuple[tuple, ...] = (
    # ---------------------------------------------- foreign trade/regulation
    ("Chromium Trioxide From India: Final Affirmative Determination of Sales "
     "at Less Than Fair Value",
     "trade_remedy_determination", "adopted", "sector:chemicals",
     "foreign_trade_regulation",
     "a FINAL affirmative determination is a decided measure"),
    ("Chromium Trioxide From India: Final Affirmative Countervailing Duty "
     "Determination",
     "trade_remedy_determination", "adopted", "sector:chemicals",
     "foreign_trade_regulation", "as above, countervailing"),
    ("Oleoresin Paprika From India: Antidumping Duty Order and Countervailing "
     "Duty Order",
     "trade_remedy_determination", "effective", "sector:agriculture",
     "foreign_trade_regulation",
     "an issued ORDER is in force, not merely decided"),
    ("Certain Freight Rail Couplers and Parts Thereof From India: Final "
     "Affirmative Countervailing Duty Determination",
     "trade_remedy_determination", "adopted", "sector:steel",
     "foreign_trade_regulation", "rail couplers are a steel article"),
    ("Oil Country Tubular Goods From India, South Korea, Turkey, Ukraine, and "
     "Vietnam; Determinations",
     "trade_remedy_determination", "unknown", "sector:steel",
     "foreign_trade_regulation",
     "USITC bare form states no stage; OCTG is steel pipe"),
    ("Fine Denier Polyester Staple Fiber From India: Preliminary Results of "
     "Antidumping Duty Administrative Review",
     "trade_remedy_determination", "announced", "sector:textiles",
     "foreign_trade_regulation", "preliminary results establish nothing yet"),
    ("Certain Paper Shopping Bags From India: Final Affirmative Determination",
     "trade_remedy_determination", "adopted", "sector:paper_packaging",
     "foreign_trade_regulation", "final determination on paper packaging"),
    ("Large Diameter Graphite Electrodes From India: Final Affirmative "
     "Determination of Sales at Less Than Fair Value",
     "trade_remedy_determination", "adopted", "sector:industrial_materials",
     "foreign_trade_regulation",
     "electrodes are a steelmaking INPUT, not a steel article"),
    ("Common Alloy Aluminum Sheet From Bahrain, Brazil, Germany, India, and "
     "Turkey: Antidumping Duty Order",
     "trade_remedy_determination", "effective", "sector:aluminium",
     "foreign_trade_regulation", "an issued order is in force"),

    # --------------------------------------------------------- adversarial
    ("Certain Steel Nails From India: Preliminary Affirmative Determination "
     "of Sales at Less Than Fair Value, Postponement of Final Determination",
     "trade_remedy_determination", "announced", "sector:steel", "adversarial",
     "names the final stage it is DEFERRING; read as adopted, it invented a "
     "duty that does not exist"),
    ("Common Alloy Aluminum Sheet From Bahrain, Brazil, Croatia, Egypt, "
     "Germany, India, Indonesia, Italy, Oman, Romania, Serbia, Slovenia, "
     "South Africa, Spain, Taiwan, and Turkey; Scheduling of Full Five-Year "
     "Reviews",
     "trade_remedy_determination", "consultation", "sector:aluminium",
     "adversarial",
     "a review being SCHEDULED is a proceeding opening; read as expired, it "
     "reported a live duty as lapsed"),
    ("Certain Hot-Rolled Steel From India: Revocation of the Antidumping Duty "
     "Order",
     "trade_remedy_determination", "repealed", "sector:steel", "adversarial",
     "a revocation is relief; it carried no direction at all"),
    ("Certain Frozen Warmwater Shrimp From India: Rescission of Antidumping "
     "Duty Administrative Review, In Part",
     "trade_remedy_determination", "unknown", "sector:agriculture",
     "adversarial",
     "rescinding a REVIEW leaves the duty in place; reading it as a "
     "revocation would invent relief"),
    ("Jeffrey Thies: Final Debarment Order",
     "regulatory_action", "adopted", None, "adversarial",
     "the title states the status; the body narrates the preceding proposal"),
    ("Advance Traveler Information for Rail",
     "other", "unknown", None, "adversarial",
     "a passenger-rail rulemaking, not a logistics disruption"),
    ("Renewal of Agency Information Collections of Previously Approved "
     "Collections",
     "other", "unknown", None, "adversarial",
     "Paperwork Reduction Act boilerplate is not an economic action"),
    ("Marine Mammals; Incidental Take of Polar Bears and Pacific Walruses in "
     "the Beaufort Sea",
     "other", "unknown", None, "adversarial",
     "out of scope entirely; must not acquire a sector"),

    # ------------------------------------------------- company / operations
    ("Notice of attachment dated October 13,2026 issued against Solomon Y "
     "under RC No. 7706 of 2024",
     "securities_enforcement_action", "effective", None,
     "company_operations", "property attached: the constraint is in force"),
    ("Prohibitory Order no. 1575/2026 issued against Venkatachari Suresh in "
     "the matter of Securekloud Technologies Ltd",
     "securities_enforcement_action", "effective", None,
     "company_operations", "a prohibitory order applies on issue"),
    ("Release Order dated October 15, 2026 for RC 8924 of 2025 issued against "
     "Yuvika Tradewing LLP",
     "securities_enforcement_action", "repealed", None, "company_operations",
     "a release LIFTS the constraint; it shares the certificate vocabulary "
     "with an attachment and must not be read as one"),
    ("Notice of Demand under Recovery Certificate number 9303 of 2026",
     "securities_enforcement_action", "announced", None, "company_operations",
     "a demand precedes enforcement"),
    ("Completion of Recovery Certificate No. 3965 of 2021",
     "securities_enforcement_action", "expired", None, "company_operations",
     "the proceeding has ended"),
    ("Confirmatory order in the matter of Rajesh Exports Limited",
     "securities_enforcement_action", "adopted", None, "company_operations",
     "a confirmatory order confirms an earlier interim order"),
    ("Tata Steel inaugurates Phase II expansion of Kalinganagar operations",
     "capacity_expansion", "unknown", "sector:steel", "company_operations",
     "a commissioned expansion at a registered facility"),

    # --------------------------------------------------- macro / monetary
    ("RBI approves amalgamation of Indian branches of Emirates NBD Bank "
     "P.J.S.C. with RBL Bank",
     "bank_resolution", "unknown", None, "macro_monetary",
     "a resolution/amalgamation approval"),
    ("Premature redemption under Sovereign Gold Bond (SGB) Scheme - "
     "Redemption Price",
     "debt_instrument_event", "unknown", None, "macro_monetary",
     "an instrument lifecycle event"),
    ("FOMC statement on the federal funds target range",
     "policy_rate_decision", "unknown", None, "macro_monetary",
     "a central bank rate decision, in Fed vocabulary"),
    ("Investment Company Cross Trading. The Securities and Exchange "
     "Commission is proposing to amend the rule under the Investment Company "
     "Act of 1940.",
     "regulatory_action", "proposed", None, "macro_monetary",
     "the TITLE alone is a topic and carries neither class nor stage; the "
     "abstract is included because that is what the pipeline reads, and "
     "labelling the title from a body I had read would score the wrong text"),

    # ------------------------------------------------- logistics / hazards
    ("M 5.7 - 48 km WNW of Khuzdar, Pakistan",
     "physical_hazard", "unknown", None, "logistics_hazards",
     "a hazard-agency report"),
    ("Port of Mumbai reports severe congestion",
     "logistics_disruption", "unknown", None, "logistics_hazards",
     "congestion is a disruption in itself"),
    ("Container backlog strands cargo at JNPT terminal",
     "logistics_disruption", "unknown", None, "logistics_hazards",
     "backlog plus a transport noun"),

    # -------------------------------------------------- Indian policy (hi)
    ("137 कैंसर रोधी "
     "दवाओं पर व्या"
     "पार मार्जिन "
     "का युक्तिकरण",
     "price_control", "unknown", None, "indian_policy",
     "trade margin rationalisation on anti-cancer drugs"),
    ("आईडीबीआई में "
     "सरकार की हिस्"
     "सेदारी से संब"
     "ंधित विधायी "
     "घटनाक्रमों "
     "पर स्पष्टीकर"
     "ण",
     "ownership_change", "unknown", None, "indian_policy",
     "government stake in IDBI Bank"),
    ("शिल्प समागम "
     "मेला 2026-मैसूर, "
     "कर्नाटक",
     "other", "unknown", None, "indian_policy",
     "a craft fair: correctly NOT a market event"),
)

#: Group -> the plan's required count, for the corpus sufficiency check.
GROUPS = ("indian_policy", "foreign_trade_regulation", "company_operations",
          "macro_monetary", "logistics_hazards", "adversarial")

#: The plan names the sixth group "hard negatives/retractions"; these are the
#: adversarial cases, so they are counted under that name.
GROUP_TO_REQUIREMENT = {"adversarial": "hard_negatives"}

LABELLER_COUNT = 1
LABELLER_NOTE = ("single labeller, and not a human one. The plan requires two "
                 "independent reviewers with adjudication, so this corpus is "
                 "PROVISIONAL and no inter-annotator reliability is claimed")
