# Public-event hazard watch: separate counterfactual replay

This is an additional contextual watch, not a crisis probability. The rule was designed after the market-model failure; it was not preregistered before COVID.

Every sourced new WHO public-health emergency declaration starts a fixed 20-session watch on the next observed trading session. No event is selected based on the subsequent market return.

| Declaration | Published | First session | Matched project events |
|---|---|---|---|
| H1N1_2009 | 2009-04-25 | 2009-04-27 | None |
| POLIO_2014 | 2014-05-05 | 2014-05-06 | None |
| EBOLA_WEST_AFRICA_2014 | 2014-08-08 | 2014-08-11 | None |
| ZIKA_NEUROLOGICAL_CLUSTERS_2016 | 2016-02-01 | 2016-02-02 | None |
| EBOLA_DRC_KIVU_ITURI_2019 | 2019-07-17 | 2019-07-18 | None |
| NOVEL_CORONAVIRUS_2020 | 2020-01-30 | 2020-01-31 | covid_2020 |
| MPOX_MULTICOUNTRY_2022 | 2022-07-23 | 2022-07-25 | None |
| MPOX_UPSURGE_2024 | 2024-08-14 | 2024-08-16 | None |
| EBOLA_BUNDIBUGYO_DRC_UGANDA_2026 | 2026-05-17 | 2026-05-18 | None |

## Full warning cost

| Policy | Episodes | Unmatched episodes | Unmatched/year | Time under watch |
|---|---:|---:|---:|---:|
| External watch | 9 | 8 | 0.47 | 4.2% |
| Union with combined model alarm | 54 | 53 | 3.12 | 16.7% |

These unmatched counts use the project's provisional market-event labels.
The union with the market alarm has a higher false-alarm rate; the external
COVID trigger does not validate the combined policy.

## Pre-onset record of the external channel alone

| Project event | Result | First warning | Lead sessions |
|---|---|---|---|
| gfc_2008 | unassessable | - | - |
| taper_2013 | missed | - | - |
| ilfs_2018 | missed | - | - |
| covid_2020 | warned | 2020-01-31 | 14 |
| tightening_2022 | missed | - | - |
| tariff_2026 | missed | - | - |

## Limits

- Historical counterfactual scenario, not evidence that this policy existed or was chosen before COVID.
- The public announcement identifies a health emergency. It does not establish an impending financial crisis, causal market effect, or probability of loss.
- The 20-session watch duration was chosen after seeing market-only results; sensitivity and prospective validation remain required. All declarations stay in the audit.
- Next-session availability from a page date approximates dissemination; publication timestamps and immutable as-of archives are incomplete.
- Unmatched health watches are labelled false only relative to the six provisional project market-event labels; these are not a universal inventory of financial crises.
- The external watch is additional context. It does not repair or validate the market-only three-pillar onset model.
