# AMENDMENT-02 — Burn-in history and a floating universe size

**Status:** Approved 2026-08-23. Supersedes the fixed `N = 500` / `Q = 2` reading of FR16 and the
SPEC §4 coverage matrix entry for the 2008 epoch. Requirement *text* is unchanged; what changes is
the operating configuration and the claims the report may make about it.

**Applies to:** SPEC FR16, FR52, NFR6, NFR8, SPEC §4 (coverage matrix), ARCHITECTURE S3, and report
§2.2, §5.2, §7.1, §7.5, Figure 2.1.

---

## 1. What was found

The measurements below come from the loaded corpus (EOD2 daily, 3,524 NSE equities), not from an
estimate. They are reproducible with `seraph/universe/constructor.py` and the queries in §6.

**(a) FR52 cannot fill 500 names in the early corpus.** Symbols clearing the ">= 1000 trading days
of listing history" filter, as at each rebalance date:

| Rebalance | Eligible (>= 1000 days) | Target | Shortfall |
|---|---|---|---|
| 2008-01-01 | **361** | 500 | 139 |
| 2009-01-01 | **412** | 500 | 88 |
| 2010-07-01 | 539 | 500 | — |
| 2013-01-01 | 824 | 500 | — |
| 2018-07-01 | 1,123 | 500 | — |
| 2026-01-01 | 1,836 | 500 | — |

**(b) A 2005-start corpus cannot produce a `C_t` for the 2008 epoch at all.** The 1,000th NSE
trading day after 2005-01-03 is **2009-01-06**. With FR16's `T = 1000`, the first computable
correlation matrix therefore postdates the entire GFC epoch. This was already anticipated in
DATA-ACQUISITION §2 ("your first spectral output is ~2009 regardless"), but its consequence for the
coverage matrix was never carried through.

**(c) Burn-in history exists, but only for a minority of names.** 415 of 3,524 symbols have data
before 2005.

Together these mean SPEC §4's coverage matrix — which marks the 2008 GFC epoch **RMT ✔** — was not
achievable as written.

## 2. What was decided

**Two changes, both adopted.**

**Change 1 — pre-2005 data is loaded as rolling-window burn-in, and is not part of the validation
corpus.** The FR16 window may reach back before 2005-01-03; the labelled epochs, the FR30
calibration sample and every reported metric remain confined to 2005–2026. This is not a corpus
extension and does not reopen SPEC §7 out-of-scope item 10 ("NSE history back to 1994"): no result
is computed *on* pre-2005 data, it only conditions estimates *at* 2005+ dates. The distinction must
be stated explicitly wherever the corpus is described.

**Change 2 — the universe size floats, and `Q` is recomputed per rebalance.**

```
N_t  = min(500, eligible_t)
Q_t  = T / N_t
λ±(Q_t) = (1 ± 1/√Q_t)²
```

`N_t = 500`, hence `Q_t = 2`, holds from roughly mid-2010 onward — the large majority of the corpus
and every epoch from 2013 on. Earlier dates run at `Q_t > 2` (Jan-2008: `N = 361`, `Q ≈ 2.77`) and
are labelled as such.

### Why this is the more defensible option

The alternative — holding `N = 500` and simply having no RMT pillar before mid-2010 — was
considered and rejected on four grounds.

1. **Nothing in the Marchenko–Pastur law privileges `Q = 2`.** The MP density and its support are
   *functions of* `Q`; evaluating `λ±` at the `Q_t` that actually obtains is the correct
   application of the theorem, whereas quoting `Q = 2` on a date where `T/N = 2.77` would simply be
   a false statement about the data. The reviewed literature uses whatever `Q` its panel yields
   (Laloux et al. and Plerou et al. both operate far from 2); there is no convention to violate.
2. **The comparability objection is already answered by FR19.** The raw exceedance fraction `F_t`
   does have a `Q`-dependent null distribution, so `F_t` at `Q = 2.77` is not on the same scale as
   `F_t` at `Q = 2`. But FR19 already requires a 1,000-replication parametric bootstrap at every
   daily update, and that bootstrap is run under the configuration in force on the day. **The
   bootstrap p-value is the cross-date-comparable statistic; `F_t` is not, and the report should say
   so.** FR28's rolling five-year empirical-CDF standardisation absorbs the residual level effect
   before fusion.
3. **It preserves the single most important epoch in the sample.** The 2008 GFC is the canonical
   systemic event; a framework that cannot speak to it is substantially weaker than one that speaks
   to it at `N = 361` with the reduced precision disclosed.
4. **It is honest in the direction that costs us something.** Reporting "N floats from 361 to 500;
   Q from 2.77 to 2" invites a question that "Q = 2" would have hidden. Methodology sections are
   strengthened, not weakened, by disclosing a limitation the reader could not otherwise have
   detected.

**The cost, stated plainly:** the 2008 and 2009 spectral estimates rest on a narrower
cross-section, so their eigenvalue estimates are noisier and their `F_t` values are not directly
comparable to later dates. Every such date carries `UNIVERSE_UNDERFILLED`, and the report must not
place early- and late-corpus `F_t` on one axis without annotation.

### What was *not* changed

- **FR52's ordering.** Filter, then rank, then take. Untouched.
- **`T = 1000`.** Shortening `T` for early epochs was rejected: it would move `Q` *and* change the
  estimator's memory, confounding two things at once.
- **The 500 target.** `N_t` never exceeds 500, so the cap remains exactly as specified; only the
  floor gives way.
- **D3's buffer**, which is now scaled to the realised size — incumbent retained at rank
  ≤ 1.10·N_t, entrant admitted at ≤ 0.90·N_t. At `N_t = 500` this is exactly D3's 550/450, so the
  decision is unchanged where it was specified and merely well-defined where it was not.

## 3. Consequential edits

| Location | Edit |
|---|---|
| **SPEC §4 coverage matrix** | 2008 GFC row: RMT ✔ → **✔\*** with the footnote "available only under AMENDMENT-02 burn-in, at `N = 361`, `Q ≈ 2.77`; not comparable to full-size dates without annotation." |
| **SPEC FR16** | Add a clarification note (not a text change): `N` is `min(500, eligible_t)` and `Q_t = T/N_t` is recomputed per rebalance; `λ±` is evaluated at `Q_t`. |
| **SPEC NFR6** | "500 for RMT (daily)" → "up to 500 for RMT (daily); `N_t = min(500, eligible_t)`, reaching 500 from ~mid-2010." |
| **SPEC NFR8** | "≈2.6M daily rows" → **≈7.4M daily rows** measured (2005–2026, 3,524 symbols); ≈8.0M including pre-2005 burn-in (637,900 burn-in rows). The 2.6M figure was a pre-acquisition estimate. |
| **Report §2.2 / Figure 2.1** | Caption becomes "Theoretical Marchenko–Pastur density **at `Q = 2`, the configuration in force from mid-2010 onward**"; add one sentence that `λ±` is recomputed per date from `Q_t`. |
| **Report §5.2** | State `N_t`, `Q_t` and the per-date `λ±` explicitly where the pillar is specified. |
| **Report §7.1** | Replace with §4 below. |
| **Report §7.5 / Table B** | Note that the 2008 fold's RMT component runs at reduced cross-section, and report `N_t` alongside every early-epoch row. |
| **ARCHITECTURE S3** | `members.length === 500` is now `members.length === min(500, eligibleCount)`; the `UNIVERSE_UNDERFILLED` warning already specified is the mechanism, and it fires with the exact shortfall. |

## 4. Replacement text for report §7.1

> **Universe construction.** The analytical universe is a Nifty-500-analogous set of the most liquid
> NSE equities, reconstructed point-in-time rather than taken from published index membership. At
> each semi-annual rebalance date (1 January and 1 July, effective immediately, no lag), all NSE
> equities are first **filtered** to those with at least 1,000 trading days of listing history as at
> that date, then **ranked** by six-month median daily traded value (`TOTTRDVAL`), and the top 500
> **taken**. The filter strictly precedes the ranking; reversing the two admits recently-listed,
> heavily-traded names and silently yields fewer than 500 constituents. To reduce turnover at the
> selection boundary, an incumbent is retained while its rank remains within 110% of the universe
> size and a non-incumbent is admitted only within 90% of it.
>
> This reconstruction is adopted in preference to published Nifty 500 membership for three reasons.
> The official inclusion/exclusion file ceased updating in approximately July 2020, so a
> point-in-time membership series cannot be assembled from free sources for the full corpus.
> Back-applying present-day membership to 2005 would introduce survivorship bias in its purest
> form — selecting a crisis-detection sample on the basis of having survived every crisis in it.
> The liquidity-rank rule is instead survivorship-free by construction, since a company enters the
> universe for exactly the period in which it was liquid and leaves when it was not, and it is
> fully reproducible from a stated rule. Because traded value is split-invariant, the known
> limitation that pre-2005 prices may not be fully adjusted for corporate actions does not affect
> universe selection at all; it bears only on the return series. As representativeness evidence,
> the equal-weighted return of the reconstructed universe is reported against the official Nifty
> 500 index level, which is retained as a benchmark series.
>
> **Universe size and the aspect ratio `Q`.** The rule cannot always supply 500 eligible names. In
> the early corpus the listing-history filter is binding: 361 symbols qualify at January 2008 and
> 412 at January 2009, with 500 first reached in mid-2010. The universe size is therefore
> `N_t = min(500, eligible_t)`, and the Marchenko–Pastur aspect ratio `Q_t = T/N_t` is recomputed at
> each rebalance, with the noise-band edges `λ_± = (1 ± 1/√Q_t)²` evaluated at the value in force on
> the day. From mid-2010 onward `N_t = 500` and `Q_t = 2`; before then `Q_t` is larger, reaching
> approximately 2.77 in January 2008. Fixing `Q = 2` throughout was rejected: the
> Marchenko–Pastur law is a function of the aspect ratio rather than a statement about any
> particular value of it, so evaluating the bounds at the realised `Q_t` is the correct application
> of the result, whereas a fixed `Q = 2` would misdescribe the data on precisely those dates where
> the cross-section is thinnest.
>
> Two consequences are disclosed. First, spectral estimates from the early corpus rest on a
> narrower cross-section and are correspondingly noisier. Second, because the null distribution of
> the exceedance fraction depends on `Q`, raw `F_t` values are not directly comparable across dates
> with different `N_t`; the parametric bootstrap p-value, which is computed under the configuration
> in force on each day, is the comparable statistic and is the one used for cross-date inference.
> Every date whose universe falls short of 500 is flagged in the system output and is annotated
> wherever it is plotted.
>
> **Estimation burn-in.** The rolling correlation window requires 1,000 trading days of returns, and
> the 1,000th trading day after the corpus start of 3 January 2005 falls on 6 January 2009 — after
> the global financial crisis. Daily history prior to 2005 is therefore loaded and used **solely to
> populate the rolling estimation window**, so that a correlation matrix is defined at dates from
> 2005 onward. It is not part of the validation corpus: the labelled structural-break epochs, the
> weight calibration sample and every reported performance figure remain confined to 2005–2026. No
> result is computed on pre-2005 observations; they only condition estimates at later dates.

## 4a. Verified outcome (built, not projected)

`scripts/build_universe.py` was run across the full corpus and the 44 snapshots persisted to
`universe_snapshots`. Measured result:

| Rebalance | `N_t` | Eligible | `Q_t` | Churn |
|---|---|---|---|---|
| 2005-01-01 | 292 | 292 | 3.42 | — (first build) |
| 2008-01-01 | 361 | 361 | 2.77 | 0.053 |
| 2010-01-01 | 485 | 485 | 2.06 | 0.095 |
| **2010-07-01** | **500** | 539 | **2.00** | 0.082 |
| 2013-01-01 | 500 | 824 | 2.00 | 0.048 |
| 2020-01-01 | 500 | 1,210 | 2.00 | 0.060 |
| 2026-01-01 | 500 | 1,836 | 2.00 | 0.104 |

**11 of 44 rebalance dates are underfilled**, all of them before 2010-07-01, which is the first date
reaching a full 500. `Q_t` therefore runs from 3.42 at the corpus start down to exactly 2.00 from
mid-2010 onward — confirming the "`Q = 2` for the large majority of the corpus" claim in §2 as a
measured fact rather than a projection. Semi-annual churn settles at roughly 5-10% under the scaled
D3 buffer.

## 5. Traceability

- The `UNIVERSE_UNDERFILLED` warning carries `members`, `target`, `shortfall`, `eligible` and
  `rebalanceDate`, so every affected date is machine-identifiable in the archive (FR38).
- CT-2 asserts the floating-N behaviour directly: a 480-eligible panel yields 480 members plus the
  warning, never a silent short universe.
- C6 must read `N_t` from the `UniverseSnapshot` rather than assuming 500, and must recompute
  `λ±` per date. This is a build requirement on the RMT engine arising from this amendment.

## 6. Reproducing the measurements

```sql
-- Eligible-symbol count at a rebalance date (the §1(a) table)
WITH s AS (
  SELECT symbol, max(listing_days_to_date) AS listing_days
  FROM daily_prices
  WHERE date <= DATE '2008-01-01'
    AND date >  DATE '2008-01-01' - INTERVAL '6 months'
  GROUP BY symbol
)
SELECT count(*) FILTER (WHERE listing_days >= 1000) AS eligible FROM s;

-- The 1000th trading day after the corpus start (the §1(b) claim)
WITH n AS (
  SELECT date, row_number() OVER (ORDER BY date) AS i
  FROM (SELECT DISTINCT date FROM daily_prices WHERE date >= DATE '2005-01-01') d
)
SELECT date FROM n WHERE i = 1000;
```
