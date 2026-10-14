#!/usr/bin/env python3
# C10 — event-count limitation audit (FR32, FR33, FR35, D5). READ-ONLY research.
"""Why is SERAPH's validation limited to six events, and is that limit binding?

**Pre-registered in docs/evidence/20261013T124358Z-32-event-count-preregistration.log
BEFORE any query below was executed.** The hypothesis, the decision rule, the
admissibility rule for candidate dates and the power protocol are all fixed
there; this script only executes them.

### What this script does NOT do

It writes nothing to the database (every statement is a SELECT), it does not
amend FR32, and it does not choose candidate onset dates by looking at any
SERAPH output. The candidate table below is a literal constant, fixed before
coverage was measured, each row carrying the *exogenous* public record that
fixes its date. Coverage measurement can only REMOVE a candidate (criterion B2)
— never add one. That asymmetry is the whole defence against outcome selection.

### The three arms

1. **Specification trace** — enumerate every site where the number six is
   load-bearing, and classify what each one controls. Answers: if FR32 said a
   different number, what would mechanically have to change?

2. **Data-vs-definition audit** — the corpus in `daily_prices` runs from 1995
   but every pillar output starts 2005. Establish which of the two boundaries
   (the FR52 1000-listing-day filter, the EOD2 pre-2005 adjustment caveat, the
   `macro_covariates` span that feeds Hamilton's `exog_tvtp`) actually binds,
   and whether it is irreducible or merely unacquired.

3. **Candidate coverage** — for each pre-registered candidate episode, the
   mechanical 60-trading-day separation test (`CRISIS_WINDOW_DAYS` 30 +
   `LEAD_WINDOW_DAYS` upper 15, rounded up, so no two accepted onsets can share
   a crisis or lead window) and the >=95% RMT+Hamilton coverage test over
   `[onset-15, onset+30]`.

`--power` runs the fourth arm: the N in {6,10,15,20} extension of
`scripts/early_warning_power.py`, reusing that script's own `t3_auc`,
`relocation_null`, `aaft_null` and `ar1_stationary` by import rather than
reimplementation, so the null cannot drift from the published one. Its delta=0
row is the negative control: if it is not near the nominal 0.05 the whole row is
void and is printed as VOID, not as a power number.

Run: python scripts/audit_event_coverage.py [--power] [--draws 40] [--perms 200]
"""
from __future__ import annotations

import argparse
import asyncio
import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

import asyncpg  # noqa: E402
import numpy as np  # noqa: E402

from seraph.store.bootstrap import resolve_dsn  # noqa: E402
from seraph.validation.epochs import (  # noqa: E402
    CRISIS_WINDOW_DAYS,
    EPOCH_BREAKS,
    LEAD_WINDOW_DAYS,
)

LEAD_H = LEAD_WINDOW_DAYS[1]                 # 15 — FR32 early-warning upper
MIN_SEPARATION = CRISIS_WINDOW_DAYS + LEAD_H  # 45 -> rounded to 60, see below
SEPARATION_DAYS = 60                          # pre-registered, trading days
COVERAGE_FLOOR = 0.95                         # pre-registered (criterion B2)

# ---------------------------------------------------------------- candidates --
# (id, exogenous anchor date, india onset date, tier, exogenous source record)
#
# TIER 1 = dated non-market action + broad macro-financial transmission channel.
# TIER 2 = dated action, but narrower channel or a weaker/compound anchor.
# TIER X = REJECTED BEFORE MEASUREMENT for crisis-splitting; kept visible so the
#          rejection is auditable rather than silent.
#
# Every `anchor` is a calendar-dated action taken OUTSIDE the Indian equity
# market: a policy decision, a statutory filing, a rating action, a referendum
# or election result declaration. None is a date on which Indian equities fell.
# Where the anchor is a non-NSE-trading day or a post-close announcement, the
# onset moves to the next NSE session and `shift` records it.
CANDIDATES: tuple[dict, ...] = (
    dict(id="fomc_may_2006", anchor="2006-05-10", onset="2006-05-11", tier=2,
         source="FOMC raised the funds target to 5.00% and signalled further "
                "firming (statement 2006-05-10); start of the global "
                "commodity/EM-carry unwind. WEAK ANCHOR: the May-2006 EM "
                "selloff has no single crisp exogenous trigger, so this date is "
                "the closest dated policy action, not an undisputed onset."),
    dict(id="greece_bailout_2010", anchor="2010-04-23", onset="2010-04-23", tier=1,
         source="Greece formally requested the EU/IMF support package "
                "(Papandreou announcement, 2010-04-23) — a dated sovereign "
                "administrative act opening the euro-area crisis."),
    dict(id="us_downgrade_2011", anchor="2011-08-05", onset="2011-08-08", tier=1,
         source="Standard & Poor's downgraded the US sovereign rating AAA->AA+ "
                "after the US close on Friday 2011-08-05; first NSE session "
                "Monday 2011-08-08. A dated rating action, not a price event."),
    dict(id="brexit_vote_2016", anchor="2016-06-24", onset="2016-06-24", tier=1,
         source="UK EU-membership referendum result declared 2016-06-24 "
                "(Electoral Commission). Date fixed by a statutory count."),
    dict(id="pboc_cny_2015", anchor="2015-08-11", onset="2015-08-11", tier=1,
         source="People's Bank of China changed the CNY central-parity "
                "mechanism and devalued, announced 2015-08-11. A dated "
                "foreign-central-bank action."),
    dict(id="demonetisation_2016", anchor="2016-11-08", onset="2016-11-09", tier=1,
         source="Government of India withdrew Rs500/Rs1000 notes, announced "
                "20:15 IST 2016-11-08; first affected NSE session 2016-11-09. "
                "CONFOUND: the US presidential result landed in the same "
                "session, so this onset carries two causes and cannot be "
                "attributed to either alone."),
    dict(id="ltcg_budget_2018", anchor="2018-02-01", onset="2018-02-01", tier=2,
         source="Union Budget 2018-19 (2018-02-01) reintroduced long-term "
                "capital-gains tax on listed equity. A dated fiscal action with "
                "a direct equity channel; coincident with the global Feb-2018 "
                "volatility spike, hence tier 2."),
    dict(id="adani_hindenburg_2023", anchor="2023-01-24", onset="2023-01-25", tier=2,
         source="Hindenburg Research report published 2023-01-24 (US hours); "
                "first full NSE session 2023-01-25. Dated publication, but a "
                "single-issuer event — 'systemic' is contestable."),
    dict(id="svb_cs_2023", anchor="2023-03-10", onset="2023-03-13", tier=1,
         source="Silicon Valley Bank placed in FDIC receivership 2023-03-10 "
                "(statutory action); Credit Suisse emergency measures followed. "
                "First NSE session after the weekend 2023-03-13."),
    dict(id="loksabha_result_2024", anchor="2024-06-04", onset="2024-06-04", tier=1,
         source="Election Commission of India declared the 18th Lok Sabha "
                "result on 2024-06-04. Date fixed by statute, independent of "
                "any market outcome."),
    dict(id="boj_carry_2024", anchor="2024-07-31", onset="2024-07-31", tier=2,
         source="Bank of Japan raised the policy rate to ~0.25% and announced "
                "JGB taper (2024-07-31), the trigger of the yen carry unwind "
                "that peaked 2024-08-05. Anchored on the policy date, not the "
                "rout date, to keep the dating exogenous."),
    # ---- rejected before measurement: splitting one crisis into several ----
    dict(id="bnp_credit_crunch_2007", anchor="2007-08-09", onset="2007-08-09", tier="X",
         source="BNP Paribas froze three ABS funds 2007-08-09. REJECTED: the "
                "same crisis as FR32's gfc_2008 at an earlier phase. Admitting "
                "it would be splitting one episode into two."),
    dict(id="india_crash_jan_2008", anchor="2008-01-21", onset="2008-01-21", tier="X",
         source="REJECTED: EPOCH_BREAKS already names 2008-01-21 as the "
                "ALTERNATIVE label for gfc_2008. Using both is re-slicing one "
                "epoch, explicitly disallowed."),
    dict(id="rupee_crisis_2013", anchor="2013-08-28", onset="2013-08-28", tier="X",
         source="REJECTED: the rupee's low is inside FR32's taper_2013 "
                "sequence, and is a price extremum, i.e. an endogenous date."),
    dict(id="covid_bottom_2020", anchor="2020-03-23", onset="2020-03-23", tier="X",
         source="REJECTED: EPOCH_BREAKS names 2020-03-23 as the ALTERNATIVE "
                "label for covid_2020, and it is a market bottom — endogenous."),
    dict(id="reciprocal_tariff_2025", anchor="2025-04-02", onset="2025-04-03", tier="X",
         source="REJECTED: FR32 epoch 6 is the '2025-26 tariff sequence', and "
                "EPOCH_BREAKS/tariff_2026 names the 50% peak and the solar-CVD "
                "drop as the competing labels for that same sequence. Any 2025 "
                "tariff date is a re-slice of epoch 6, and SPEC OQ3 is the open "
                "question about which date wins — not a licence to use several."),
)


# ------------------------------------------------------------------ helpers ---

def idx_on_or_after(dates: list[str], d: str) -> int | None:
    for i, x in enumerate(dates):
        if x >= d:
            return i
    return None


def hdr(s: str) -> None:
    print(f"\n{'=' * 78}\n{s}\n{'=' * 78}", flush=True)


# ------------------------------------------------------- arm 1: spec trace ---

def spec_trace() -> None:
    hdr("ARM 1 — SPECIFICATION TRACE: where the number six is load-bearing")
    sites = [
        ("docs/SPEC.md:240  FR32 [v2]",
         "names SIX epochs by name + the 30-day crisis window and 5-15d lead",
         "NORMATIVE SOURCE. Everything below derives from this line."),
        ("docs/SPEC.md:102  O5 [v2]",
         "'Six epochs, corpus 2005-2026'",
         "ties the event count to the CORPUS BOUND — the two are stated together"),
        ("docs/SPEC.md:243  FR35 [v2]",
         "Table A = 7 subsets x 2 modes on 4 Hawkes epochs; Table B = 3 x 2 on 2 pre-2015",
         "the 4/2 split of the six; changes the CONFIG COUNT (14)"),
        ("docs/ARCHITECTURE.md:756 D5(a,b)",
         "LOEO; Table A 4 folds, Table B 6 folds; tables not comparable",
         "FOLD COUNTS are literally the event counts"),
        ("docs/ARCHITECTURE.md:645 R4",
         "'Six positive events, 14 configurations, one calibration step'",
         "the risk register's justification for pre-registration existing at all"),
        ("seraph/shared_types/fusion.py:27 EpochId",
         "Literal of exactly 6 string ids",
         "TYPE-LEVEL CLOSED SET. A 7th epoch is a type error until edited; "
         "shared_types is approval-gated, so this is the hardest gate."),
        ("seraph/validation/epochs.py:23 EPOCH_BREAKS",
         "6 (date, provenance) pairs; HAWKES_COVERED 4 / PRE_HAWKES 2",
         "the only place dates live; OQ13 + OQ3 both flagged OPEN here"),
        ("seraph/validation/preregistration.py:24 EPOCHS",
         "6-tuple duplicated from epochs.py; folds=len(EPOCHS)",
         "feeds configuration_list() -> content_hash() -> the PRE-REG HASH"),
    ]
    w = max(len(s[0]) for s in sites)
    for site, what, controls in sites:
        print(f"  {site:<{w}}  {what}")
        print(f"  {'':<{w}}  -> {controls}")
    print("\n  MECHANICAL CONSEQUENCE of changing the count, in dependency order:")
    print("   1. EpochId Literal (approval-gated shared_types) must gain members")
    print("   2. EPOCH_BREAKS gains (date, provenance) rows -> OQ13 must close")
    print("   3. preregistration.EPOCHS changes -> configuration_list() changes")
    print("      -> content_hash() changes -> EVERY existing EvaluationRow's")
    print("         preRegistrationHash stops matching -> by D5(d) every existing")
    print("         result becomes NON-REPORTABLE until re-run.")
    print("   4. D5(b) fold counts change (Table B 6 -> N; Table A only if the")
    print("      new epoch has Hawkes coverage, i.e. onset >= 2017-02-09)")
    print("   5. FR35's '7 subsets x 2' / '3 subsets x 2' are unaffected — the")
    print("      CONFIG count is independent of the EVENT count.")
    print("\n  So the '6' controls: fold counts (D5b), a closed type (EpochId),")
    print("  the pre-registration hash (D5d), and the Table A/B partition.")
    print("  It does NOT control the 14 configurations.")


# -------------------------------------------- arm 2: data-vs-definition ------

async def data_vs_definition(c: asyncpg.Connection) -> dict:
    hdr("ARM 2 — DATA OR DEFINITION? where the 2005 pillar boundary comes from")

    print("\n-- 2a. raw corpus reach in daily_prices (the data we actually hold) --")
    rows = await c.fetch("""
        SELECT extract(year FROM date)::int yr, count(*) n,
               count(DISTINCT symbol) syms,
               count(*) FILTER (WHERE universe_member_flag) memb
        FROM daily_prices WHERE date < '2011-01-01'
        GROUP BY 1 ORDER BY 1""")
    print(f"  {'year':>6} {'rows':>10} {'symbols':>9} {'universe_member rows':>21}")
    for r in rows:
        print(f"  {r['yr']:>6} {r['n']:>10,} {r['syms']:>9,} {r['memb']:>21,}")
    pre2005 = sum(r["n"] for r in rows if r["yr"] < 2005)
    pre2005_memb = sum(r["memb"] for r in rows if r["yr"] < 2005)
    print(f"\n  pre-2005 rows held: {pre2005:,}   of which flagged universe "
          f"members: {pre2005_memb:,}")

    print("\n-- 2b. FR52 eligibility: how many symbols clear the 1000-day filter --")
    print("  (listing_days_to_date counts from the symbol's true first row, 1995+,")
    print("   per eod2_client.py — so this is real listing age, not age-in-corpus)")
    elig = await c.fetch("""
        SELECT d AS probe,
               (SELECT count(DISTINCT symbol) FROM daily_prices p
                 WHERE p.date = (SELECT max(date) FROM daily_prices WHERE date <= d)
                   AND p.listing_days_to_date >= 1000) eligible
        FROM (VALUES ('1998-01-01'::date),('2000-01-01'),('2002-01-01'),
                     ('2004-01-01'),('2005-01-03'),('2006-01-02'),('2008-01-01'),
                     ('2009-01-01'),('2010-07-01'),('2011-01-03')) v(d)
        ORDER BY d""")
    print(f"  {'probe date':>12} {'symbols with >=1000 listing days':>34}")
    for r in elig:
        print(f"  {str(r['probe']):>12} {r['eligible']:>34,}")

    print("\n-- 2c. universe_snapshots: the realised point-in-time universe --")
    snaps = await c.fetch("""
        SELECT rebalance_date, eligible_count,
               coalesce(array_length(members,1),0) n_members, churn_fraction
        FROM universe_snapshots ORDER BY rebalance_date LIMIT 14""")
    tot = await c.fetchrow("SELECT count(*) n, min(rebalance_date) lo, "
                           "max(rebalance_date) hi FROM universe_snapshots")
    print(f"  {tot['n']} snapshots, {tot['lo']} .. {tot['hi']}; first 14:")
    print(f"  {'rebalance':>12} {'eligible':>9} {'N_members':>10} {'churn':>8}")
    for r in snaps:
        ch = "-" if r["churn_fraction"] is None else f"{float(r['churn_fraction']):.4f}"
        print(f"  {str(r['rebalance_date']):>12} {r['eligible_count']:>9,} "
              f"{r['n_members']:>10,} {ch:>8}")

    print("\n-- 2d. macro_covariates: Hamilton's exog_tvtp input span --")
    mc = await c.fetchrow("""
        SELECT count(*) n, min(date) lo, max(date) hi,
               count(*) FILTER (WHERE g_t IS NOT NULL) g_ok,
               min(date) FILTER (WHERE g_t IS NOT NULL) g_lo,
               count(*) FILTER (WHERE vix_available) vix_ok,
               min(date) FILTER (WHERE vix_available) vix_lo,
               count(*) FILTER (WHERE rbi_repo_rate IS NOT NULL) repo_ok,
               min(date) FILTER (WHERE rbi_repo_rate IS NOT NULL) repo_lo
        FROM macro_covariates""")
    print(f"  rows {mc['n']:,}  span {mc['lo']} .. {mc['hi']}")
    print(f"  g_t non-null      {mc['g_ok']:,} from {mc['g_lo']}")
    print(f"  vix_available     {mc['vix_ok']:,} from {mc['vix_lo']}")
    print(f"  rbi_repo non-null {mc['repo_ok']:,} from {mc['repo_lo']}")

    print("\n-- 2e. pillar output spans and the trading-day grid --")
    spans = {}
    for t in ("rmt_output", "hamilton_output", "hawkes_output", "csrs"):
        col = "date" if t != "hawkes_output" else "date"
        try:
            r = await c.fetchrow(
                f"SELECT count(*) n, min({col}) lo, max({col}) hi FROM {t}")
        except asyncpg.PostgresError:
            r = await c.fetchrow(
                f"SELECT count(*) n, min(ts)::date lo, max(ts)::date hi FROM {t}")
        spans[t] = r
        print(f"  {t:<16} {r['n']:>8,} rows  {r['lo']} .. {r['hi']}")
    grid = await c.fetch("""
        SELECT DISTINCT date FROM daily_prices
        WHERE date >= '2005-01-03' AND universe_member_flag ORDER BY date""")
    dates = [str(r["date"]) for r in grid]
    print(f"\n  trading-day grid (universe members, 2005+): {len(dates):,} sessions "
          f"{dates[0]} .. {dates[-1]}")
    full = await c.fetch("SELECT DISTINCT date FROM daily_prices ORDER BY date")
    print(f"  trading-day grid (all rows, 1995+):          {len(full):,} sessions "
          f"{full[0]['date']} .. {full[-1]['date']}")

    print("\n  VERDICT INPUTS for the 2005 boundary — three candidate causes:")
    print("   (i)  FR52 1000-listing-day filter: see 2b. If eligibility is")
    print("        non-trivial well before 2005, the filter is NOT what binds.")
    print("   (ii) EOD2 pre-2005 adjustment caveat: eod2_client.py:8 states")
    print("        'pre-2005 rows may not be fully adjusted - the corpus starts")
    print("        2005', and CORPUS_START = '2005-01-01' is a literal constant.")
    print("        This is a DATA-QUALITY decision recorded in code.")
    print("   (iii) macro_covariates span: see 2d. Hamilton's TVTP exog cannot")
    print("        start before g_t does.")
    return {"dates": dates, "spans": spans}


# ---------------------------------------- arm 3: candidate episode coverage ---

async def candidate_coverage(c: asyncpg.Connection, dates: list[str]) -> list[dict]:
    hdr("ARM 3 — CANDIDATE EPISODES: separation test, then coverage test")
    n = len(dates)
    date_pos = {d: i for i, d in enumerate(dates)}

    fr32 = {}
    for ep, (bd, _) in EPOCH_BREAKS.items():
        i = idx_on_or_after(dates, bd)
        fr32[ep] = i
    print("\n-- FR32 reference onsets on the 2005+ grid --")
    for ep, i in fr32.items():
        print(f"  {ep:<16} {EPOCH_BREAKS[ep][0]}  grid idx "
              f"{i if i is not None else 'OFF-GRID'}"
              f"{'' if i is None else '  (session ' + dates[i] + ')'}")
    fr32_idx = sorted(v for v in fr32.values() if v is not None)

    print(f"\n-- separation test: >= {SEPARATION_DAYS} trading days from every "
          f"FR32 onset and every accepted candidate --")
    print("   (pre-registered; greedy in chronological order, so the rule is")
    print("    mechanical and the tie-break is date priority, not judgement)")
    accepted: list[dict] = []
    accepted_idx: list[int] = list(fr32_idx)
    results: list[dict] = []
    for cand in sorted(CANDIDATES, key=lambda x: x["onset"]):
        row = dict(cand)
        if cand["tier"] == "X":
            row.update(status="REJECTED_SPLIT", gap=None, idx=None)
            results.append(row)
            continue
        i = idx_on_or_after(dates, cand["onset"])
        if i is None:
            row.update(status="OFF_GRID", gap=None, idx=None)
            results.append(row)
            continue
        row["idx"] = i
        row["onset_session"] = dates[i]
        row["shift"] = dates[i] != cand["onset"]
        gap = min(abs(i - j) for j in accepted_idx) if accepted_idx else 10**9
        row["gap"] = gap
        if gap < SEPARATION_DAYS:
            nearest = min(accepted_idx, key=lambda j: abs(i - j))
            row.update(status="REJECTED_SPACING",
                       collides_with=dates[nearest])
        else:
            row["status"] = "ACCEPTED_SPACING"
            accepted_idx.append(i)
            accepted.append(row)
        results.append(row)

    print(f"  {'candidate':>24} {'onset':>11} {'session':>11} {'tier':>5} "
          f"{'gap(d)':>7} {'status':>18}")
    print("  " + "-" * 82)
    for r in sorted(results, key=lambda x: x["onset"]):
        g = "-" if r.get("gap") is None else f"{r['gap']}"
        print(f"  {r['id']:>24} {r['onset']:>11} "
              f"{r.get('onset_session', '-'):>11} {str(r['tier']):>5} {g:>7} "
              f"{r['status']:>18}"
              + (f"  <- {r['collides_with']}" if r.get("collides_with") else ""))

    print(f"\n-- coverage test: >= {COVERAGE_FLOOR:.0%} of sessions in "
          f"[onset-{LEAD_H}, onset+{CRISIS_WINDOW_DAYS}] have RMT *and* Hamilton --")
    print(f"  {'candidate':>24} {'window':>23} {'sess':>5} {'rmt':>5} {'ham':>5} "
          f"{'both%':>7} {'B2':>6}")
    print("  " + "-" * 82)
    for r in accepted + [x for x in results if x["status"] == "REJECTED_SPACING"]:
        i = r["idx"]
        lo, hi = max(0, i - LEAD_H), min(n - 1, i + CRISIS_WINDOW_DAYS)
        win = dates[lo:hi + 1]
        cov = await c.fetchrow("""
            SELECT (SELECT count(*) FROM rmt_output
                     WHERE date = ANY($1::date[]) AND f_t IS NOT NULL) rmt,
                   (SELECT count(*) FROM hamilton_output
                     WHERE date = ANY($1::date[]) AND xi_1 IS NOT NULL) ham,
                   (SELECT count(*) FROM rmt_output r JOIN hamilton_output h
                       USING (date)
                     WHERE r.date = ANY($1::date[]) AND r.f_t IS NOT NULL
                       AND h.xi_1 IS NOT NULL) both
            """, [__import__("datetime").date.fromisoformat(d) for d in win])
        frac = cov["both"] / len(win) if win else 0.0
        r["coverage"] = frac
        r["b2"] = frac >= COVERAGE_FLOOR
        print(f"  {r['id']:>24} {win[0]}..{win[-1]} {len(win):>5} "
              f"{cov['rmt']:>5} {cov['ham']:>5} {frac:>6.1%} "
              f"{'PASS' if r['b2'] else 'FAIL':>6}"
              + ("" if r["status"] == "ACCEPTED_SPACING" else "   (spacing-rejected)"))

    final = [r for r in accepted if r["b2"]]
    print(f"\n  candidates passing BOTH separation and coverage: {len(final)}")
    for r in final:
        print(f"    {r['id']:<24} {r['onset_session']}  tier {r['tier']}")

    print("\n-- combined design: FR32 six + accepted candidates --")
    for tier_cut, name in ((1, "FR32 + tier-1 only"), (2, "FR32 + tier-1 + tier-2")):
        keep = [r for r in final if r["tier"] <= tier_cut]
        all_idx = sorted(fr32_idx + [r["idx"] for r in keep])
        gaps = np.diff(all_idx)
        span_days = all_idx[-1] - all_idx[0]
        pos_days = len(all_idx) * LEAD_H
        print(f"  {name:<26} N = {len(all_idx):>2}  "
              f"min gap {gaps.min():>4}d  median gap {int(np.median(gaps)):>4}d  "
              f"T3 positives {pos_days:>3}d / {n:,} sessions "
              f"({pos_days / n:.1%})")
        print(f"  {'':<26} onset sessions: "
              f"{', '.join(dates[i] for i in all_idx)}")
    print(f"\n  Ceiling check: with the {SEPARATION_DAYS}-session separation rule "
          f"and {n:,} sessions on the")
    print(f"  grid, the ARITHMETIC maximum number of non-overlapping onsets is "
          f"{n // SEPARATION_DAYS}.")
    print("  So separation is nowhere near binding — the binding constraint is")
    print("  how many episodes the exogenous public record actually supports.")
    return results


# ------------------------------- arm 3b: nominal N vs EFFECTIVE N ------------

async def dependence_arm(c: asyncpg.Connection, dates: list[str]) -> None:
    """How many of the extra onsets are actually independent observations?

    The power curve in arm 4 injects a clean, independent, identical step at
    every onset, which is the best case and an upper bound. This arm measures
    the thing that actually binds: how fast the observation series decorrelates.
    If the integral timescale is long relative to the onset spacing, then
    nominal N overstates the information content and the honest event count is
    smaller — a property of the data that no event definition can change.
    """
    hdr("ARM 3b — NOMINAL N vs EFFECTIVE N: the measured dependence deflation")
    rows = await c.fetch("SELECT date, rv_t_yz, ar_t, bas_t FROM hamilton_output "
                         "WHERE rv_t_yz IS NOT NULL ORDER BY date")
    m = len(rows)
    print(f"\n  autocorrelation of the Hamilton observables over {m:,} sessions")
    print(f"  {'series':>9} {'phi1':>7} {'1/(1-phi)':>10} {'lag@1/e':>8} "
          f"{'zerocross':>10} {'tau_int':>8} {'indep blocks':>13}")
    scales: dict[str, tuple[int, float]] = {}
    for col in ("rv_t_yz", "ar_t", "bas_t"):
        x = np.array([float(r[col]) for r in rows])
        x = x - x.mean()
        ac = np.correlate(x, x, "full")[m - 1:] / (np.arange(m, 0, -1) * x.var())
        phi1 = float(ac[1])
        e_lag = int(np.argmax(ac < 1 / np.e)) if np.any(ac < 1 / np.e) else m
        zc = int(np.argmax(ac <= 0)) if np.any(ac <= 0) else m
        tau = 1.0 + 2.0 * float(ac[1:zc].sum())
        scales[col] = (e_lag, tau)
        print(f"  {col:>9} {phi1:>7.4f} {1 / (1 - phi1):>10.1f} {e_lag:>8} "
              f"{zc:>10} {tau:>8.1f} {m / max(tau, 1):>13.1f}")
    print("\n  'indep blocks' = grid length / integral timescale: the number of")
    print("  effectively independent realisations the whole grid can hold. It is")
    print("  a property of the DATA, not of FR32.")

    e_lag, tau = scales["rv_t_yz"]
    tau_i = int(round(tau))
    fr32 = sorted(i for i in (idx_on_or_after(dates, bd)
                              for bd, _ in EPOCH_BREAKS.values()) if i is not None)
    t1 = [idx_on_or_after(dates, d) for d in
          ("2010-04-23", "2011-08-08", "2015-08-11", "2016-06-24",
           "2016-11-09", "2024-06-04")]
    t2 = [idx_on_or_after(dates, d) for d in
          ("2006-05-11", "2018-02-01", "2023-01-25")]

    def greedy(idx: list[int], L: int) -> int:
        keep = [idx[0]]
        for i in idx[1:]:
            if i - keep[-1] >= L:
                keep.append(i)
        return len(keep)

    print(f"\n  deflating each design by the rv_t_yz scales "
          f"(1/e = {e_lag}, integral = {tau_i} sessions)")
    print(f"  {'design':>26} {'N':>3} {'gaps<1/e':>9} {'gaps<tau':>9} "
          f"{'N_eff@1/e':>10} {'N_eff@tau':>10}")
    for name, ds in (("FR32 six", fr32), ("FR32 + tier-1", fr32 + t1),
                     ("FR32 + tier-1 + tier-2", fr32 + t1 + t2)):
        idx = sorted(ds)
        gaps = np.diff(idx)
        print(f"  {name:>26} {len(idx):>3} {int((gaps < e_lag).sum()):>9} "
              f"{int((gaps < tau_i).sum()):>9} {greedy(idx, e_lag):>10} "
              f"{greedy(idx, tau_i):>10}")
    full = sorted(fr32 + t1 + t2)
    print(f"\n  N=15 adjacent gaps (sessions): "
          f"{', '.join(str(int(g)) for g in np.diff(full))}")
    print(f"  N=6  adjacent gaps (sessions): "
          f"{', '.join(str(int(g)) for g in np.diff(fr32))}")
    print("\n  Read: if N_eff@tau barely moves as N rises, the extra onsets are")
    print("  re-observations of the same few independent states, and the power")
    print("  gain in arm 4 — which assumes independent signal per onset — is an")
    print("  UPPER BOUND that the real series cannot deliver.")


# ------------------------------------------------ arm 4: power at larger N ---

def power_arm(dates: list[str], rv: np.ndarray, draws: int, perms: int) -> None:
    hdr("ARM 4 — STATISTICAL POWER at N = 6, 10, 15, 20 onsets")
    spec = importlib.util.spec_from_file_location(
        "ewp", _ROOT / "scripts" / "early_warning_power.py")
    ewp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ewp)
    print("  machinery imported from scripts/early_warning_power.py:")
    print("    t3_auc, relocation_null (circular shift), aaft_null (surrogate),")
    print("    ar1_stationary — NOT reimplemented, so the null cannot drift.")

    n = len(dates)
    phi = float(np.corrcoef(rv[:-1], rv[1:])[0, 1])
    real_idx = sorted(i for i in
                      (idx_on_or_after(dates, bd) for bd, _ in EPOCH_BREAKS.values())
                      if i is not None)
    min_gap = int(np.diff(real_idx).min()) if len(real_idx) > 1 else SEPARATION_DAYS
    print(f"\n  grid {n:,} sessions {dates[0]}..{dates[-1]}")
    print(f"  AR(1) background phi = {phi:.4f} (real rv_t_yz lag-1 autocorr)")
    print(f"  real onsets: {len(real_idx)}, min spacing {min_gap} trading days")
    print(f"  synthetic onset sets keep that minimum spacing; {draws} draws, "
          f"{perms} perms/draw, alpha = 0.05")

    deltas = (0.0, 0.5, 1.0, 1.5, 2.0)
    rng0 = np.random.default_rng(20261013)

    def place(k: int, rg) -> list[int]:
        """k onsets on the grid, min spacing preserved, rejection-sampled."""
        for _ in range(4000):
            pick = sorted(rg.choice(np.arange(LEAD_H + 5, n - CRISIS_WINDOW_DAYS - 5),
                                    size=k, replace=False))
            if len(pick) == 1 or np.diff(pick).min() >= min_gap:
                return [int(x) for x in pick]
        return [int(x) for x in np.linspace(LEAD_H + 5, n - CRISIS_WINDOW_DAYS - 5,
                                            k).astype(int)]

    # Every arm randomises placement, INCLUDING N=6, so the only thing varying
    # across rows is the event count. The real FR32 dates are run as a separate
    # anchor row ("6*") to tie back to the published AAFT result; mixing a fixed
    # configuration into the N=6 row and random ones elsewhere would confound
    # event count with onset phase on a phi=0.997 series.
    print(f"\n  {'N':>4} {'delta':>6} {'meanAUC':>8} {'sdAUC':>7} {'power@.05':>10} "
          f"{'note':>22}")
    print("  " + "-" * 64)
    table: dict[str, dict] = {}
    for label, N, onsets_fixed in (("6*", 6, real_idx), ("6", 6, None),
                                   ("10", 10, None), ("15", 15, None),
                                   ("20", 20, None)):
        table[label] = {}
        ctrl = None
        for delta in deltas:
            aucs, rej = [], 0
            for d in range(draws):
                rg = np.random.default_rng(
                    770000 + 7000 * N + 100 * int(delta * 10) + d
                    + (500000 if onsets_fixed else 0))
                oi = onsets_fixed if onsets_fixed else place(N, rg)
                x = ewp.ar1_stationary(n, phi, rg)
                x = (x - x.mean()) / x.std()
                for i in oi:
                    x[max(0, i - LEAD_H):i] += delta
                a = ewp.t3_auc(x, oi, n)
                null = ewp.aaft_null(x, n, oi, perms, rg)
                p = (1 + int(np.sum(null >= a))) / (1 + null.size)
                aucs.append(a)
                rej += int(p <= 0.05)
            pw = rej / draws
            table[label][delta] = (float(np.nanmean(aucs)), pw)
            if delta == 0.0:
                ctrl = pw
            note = ""
            if delta == 0.0:
                note = "NEG CONTROL"
                if not (0.0 <= pw <= 0.12):
                    note = "NEG CONTROL **VOID**"
            print(f"  {label:>4} {delta:>6.1f} {np.nanmean(aucs):>8.4f} "
                  f"{np.nanstd(aucs):>7.4f} {pw:>9.0%} {note:>22}", flush=True)
        mde = next((d for d in deltas if d > 0 and table[label][d][1] >= 0.80), None)
        valid = ctrl is not None and 0.0 <= ctrl <= 0.12
        print(f"       -> N={label}: type-I at nominal 5% = {ctrl:.0%}; "
              f"MDE@80% = {('>%.1f sd' % deltas[-1]) if mde is None else '%.1f sd' % mde}"
              f"{'' if valid else '   [ROW VOID: control off calibration]'}")
        print(f"          (6* = the REAL FR32 onset dates, fixed — the anchor "
              f"row)" if label == "6*" else "  " + "-" * 64)

    print("\n  READ THIS BEFORE QUOTING THE ROWS ABOVE:")
    print("   * N here is the number of ONSETS, i.e. independent events. The")
    print("     positive-day count 15N is NOT the sample size — days inside one")
    print("     lead window are near-perfectly correlated (phi ~ 0.997).")
    print("   * Power rises with N only if the added onsets are independent. Two")
    print("     onsets 30 days apart add ~1 event's worth of information, not 2.")
    print("   * The AAFT null is used for the curve because the circular-shift")
    print("     null is miscalibrated on a near-unit-root series — that is the")
    print("     measured finding in docs/evidence/EARLY-WARNING-POWER.md, not an")
    print("     assumption made here.")


# ------------- arm 5: could more onsets change an observed 0/6? --------------

def warned_rate_arm(no_skill: float = 0.14, no_skill_sd: float = 0.13,
                    alpha: float = 0.05) -> None:
    """Sample size vs effect size, on the metric the causal replay reports.

    The unified causal replay measures a **warned rate**: the fraction of
    onsets preceded by a warning. Observed is 0.00 across 6 epochs x 5 lead
    horizons, against a no-skill relocation expectation of 0.14 +/- 0.13.

    Arm 4 asks "what effect would T3 detect at N onsets". That is the wrong
    question for a 0/N observation, because AUC power says nothing about a
    count of zero. This arm asks the two questions that are actually decidable
    from 0 warnings out of N:

      (a) How tight is the NEGATIVE claim? Exact Clopper-Pearson one-sided
          upper bound on the per-event warning probability p given k=0.
      (b) How large would a POSITIVE result have to be? The smallest warned
          count k that rejects `p <= no_skill` by an exact one-sided binomial
          test, and the warned RATE that implies.

    The gap between (b) and the observed 0.00 is the effect-size deficit. If
    that gap is large compared with what more onsets do to (b), then the
    binding constraint is effect size, not sample size -- and that is a
    statement about the system, not about FR32.
    """
    from scipy.stats import binom

    hdr("ARM 5 — CAN MORE ONSETS CHANGE AN OBSERVED 0/N? (warned-rate metric)")
    print(f"\n  observed warned rate: 0.00 over 6 onsets (unified causal replay)")
    print(f"  no-skill relocation expectation: {no_skill:.2f} +/- {no_skill_sd:.2f}")
    print(f"  alpha = {alpha}, one-sided, exact binomial\n")

    print("  (a) SHARPNESS OF THE NEGATIVE CLAIM, given k = 0 warnings:")
    print(f"  {'N':>4} {'95% upper bound on p':>22} {'< no-skill 0.14?':>18}")
    print("  " + "-" * 48)
    for N in (6, 10, 12, 15, 20, 25, 30):
        p_hi = 1.0 - alpha ** (1.0 / N)       # Clopper-Pearson, k=0
        print(f"  {N:>4} {p_hi:>22.4f} {('YES' if p_hi < no_skill else 'no'):>18}")
    print("\n  Read: 0 warnings out of 6 is consistent with a true per-event")
    print("  warning probability as high as 0.39 — i.e. it does not even")
    print("  establish sub-chance performance. The upper bound first falls")
    print("  below the 0.14 no-skill rate at N = 20, which is the point a")
    print("  continued zero-warning record becomes evidence of WORSE than")
    print("  chance rather than mere absence of evidence.")

    print("\n  (b) SIZE A POSITIVE RESULT WOULD NEED, to reject p <= 0.14:")
    print(f"  {'N':>4} {'min warned k':>13} {'= warned rate':>14} "
          f"{'deficit vs observed 0.00':>26}")
    print("  " + "-" * 60)
    for N in (6, 10, 12, 15, 20, 25, 30):
        kmin = next((k for k in range(N + 1)
                     if binom.sf(k - 1, N, no_skill) <= alpha), None)
        if kmin is None:
            print(f"  {N:>4} {'unreachable':>13}")
            continue
        rate = kmin / N
        print(f"  {N:>4} {kmin:>13} {rate:>14.3f} {rate:>26.3f}")
    print("\n  Read: the minimum detectable warned RATE falls only from ~0.50")
    print("  at N=6 to ~0.30 at N=20. The system sits at 0.00. The deficit is")
    print("  0.30-0.50 in warned rate; more onsets close none of it.")

    # ---- (b2) false-alarm-matched null, read from the replay artefacts ----
    rep = _ROOT / "docs" / "evidence" / "replay"
    files = [("lam1", rep / "replay_results.json"),
             ("sca", rep / "replay_results_sca.json")]
    if all(p.exists() for _, p in files):
        import json
        print("\n  (b2) FALSE-ALARM-MATCHED NULL — the comparison that decides")
        print("       whether a NON-ZERO warned count is skill or just a looser")
        print("       trigger. A signal that alerts more often warns more often")
        print("       by chance. Matching on the signal's OWN alert frequency:")
        print("         p0 = 1 - exp(-(FA/yr) * 15/252)")
        print("       i.e. the chance of >=1 alert episode landing in the 15-day")
        print("       pre-onset window if alert timing were unrelated to onsets.")
        print(f"\n  {'signal':<26} {'P2':>5} {'FA/yr':>7} {'p0':>6} "
              f"{'warned':>8} {'rate':>6} {'P(X>=k|p0)':>11} {'verdict':>12}")
        print("  " + "-" * 92)
        for variant, path in files:
            blob = json.loads(path.read_text(encoding="utf-8"))
            for sig, entry in blob["signals"].items():
                fa = entry["rule_B"]["false_alarms"]
                far = float(fa["false_alarms_per_year"])
                eps = entry["rule_B"]["epochs"]
                k = sum(1 for _e, h in eps.items() if h["15"]["verdict"] == "PASS")
                nt = sum(1 for _e, h in eps.items()
                         if h["15"]["verdict"] != "UNTESTABLE")
                if nt == 0:
                    continue
                p0 = 1.0 - np.exp(-far * 15.0 / 252.0)
                pv = float(binom.sf(k - 1, nt, p0)) if k > 0 else 1.0
                verdict = ("not sig" if pv > alpha else "SIGNIFICANT")
                if k / nt < p0:
                    verdict = "BELOW null"
                print(f"  {sig:<26} {variant:>5} {far:>7.2f} {p0:>6.3f} "
                      f"{str(k) + '/' + str(nt):>8} {k / nt:>6.3f} {pv:>11.4f} "
                      f"{verdict:>12}")
        print("\n  This Poisson matching slightly OVERSTATES p0 because alert")
        print("  episodes cluster; where a measured relocation null exists it is")
        print("  the better number (warning_null_h15.json gives 0.1298 for")
        print("  CSRS[rmt] vs 0.153 here). It is used for the SCA variant only")
        print("  because that variant's relocation null does not exist yet.")

    print("\n  (c) VERDICT ON SAMPLE SIZE vs EFFECT SIZE")
    print("  A detector that warns on 0 of 6 onsets warns on ~0 of 15 and ~0 of")
    print("  20 unless its per-event warn probability is actually non-zero.")
    print("  Sample size governs how PRECISELY a null result is stated; only")
    print("  effect size governs whether the result is null. At a warned rate")
    print("  of 0.00 against a 0.14 no-skill rate, the binding constraint is")
    print("  EFFECT SIZE, unambiguously. More onsets would sharpen the negative")
    print("  finding — they could not plausibly convert 0/6 into a detection.")


# ------- arm 6: event-clustered BLOCK bootstrap on pillar + CSRS series ------

#: Block lengths swept, in trading days. L=1 is the naive i.i.d. bootstrap —
#: the implicit assumption behind any interval that treats the 5,363 daily rows
#: as independent. 423 and 770 are arm 3b's MEASURED rv_t_yz scales.
BLOCK_LENGTHS = (1, 21, 63, 252, 423, 770)


def _labels(dates: list[str], lead: int = LEAD_H):
    """FR32 targets on the replay grid. Identical semantics to the T1/T3 used
    in study_stress_candidates.targets(): T1 is the 30 sessions from each onset
    inclusive; T3 is the `lead` sessions strictly before each onset, with every
    in-crisis day REMOVED from the sample so nothing 'predicts' a crisis from
    inside one."""
    n = len(dates)
    t1 = np.zeros(n, int)
    t3 = np.zeros(n, int)
    in_crisis = np.zeros(n, bool)
    onsets = []
    for bd, _ in EPOCH_BREAKS.values():
        i = idx_on_or_after(dates, bd)
        if i is None:
            continue
        onsets.append(i)
        t1[i:i + CRISIS_WINDOW_DAYS] = 1
        in_crisis[i:i + CRISIS_WINDOW_DAYS] = True
    for i in onsets:
        t3[max(0, i - lead):i] = 1
    return t1, t3, ~in_crisis, onsets


def _circular_block_auc(score, y, L, draws, rng, auc_fn):
    """Circular moving-block bootstrap of the AUC.

    Resamples CONTIGUOUS blocks of length L of the (score, label) pairs
    jointly, so the within-block serial dependence of the signal is preserved
    inside each block and destroyed only between blocks. L=1 reduces to the
    i.i.d. pair bootstrap. Blocks wrap, which keeps every start position
    equally likely and avoids the end-of-sample under-weighting of the
    non-circular version.

    Returns (auc draws, n_degenerate). A resample is degenerate when it does
    not contain enough of both classes to define an AUC at all — at long L that
    happens often, because a resample of ~7 blocks can easily contain no onset.
    **That failure rate is a result, not a nuisance.**
    """
    n = score.size
    nb = int(np.ceil(n / L))
    out, degen = [], 0
    for _ in range(draws):
        starts = rng.integers(0, n, size=nb)
        idx = (starts[:, None] + np.arange(L)[None, :]).ravel()[:n] % n
        s, yy = score[idx], y[idx]
        keep = np.isfinite(s)
        s, yy = s[keep], yy[keep]
        if yy.sum() < 5 or (1 - yy).sum() < 5:
            degen += 1
            continue
        out.append(float(auc_fn(s, yy)))
    return np.array(out), degen


def _onset_cluster_lead(dates, score, onsets, lead, draws, rng):
    """Onset-clustered bootstrap of the mean lead time.

    A block bootstrap CANNOT define a lead time: lead time is measured from an
    onset backwards along an intact time axis, and resampling blocks destroys
    that axis. So lead time is bootstrapped by resampling the SIX ONSETS with
    replacement, which is structurally the same correction Workstream C applied
    to its acceleration signals. Stated rather than blurred — the two arms of
    this script use different resampling units because the two statistics
    demand different ones.

    Lead time per onset = sessions between the first Rule-B-style exceedance
    inside [onset-lead, onset-1] and the onset. A causal trailing 5y 95th
    percentile is used, matching the replay's Rule B.
    """
    n = len(dates)
    thr = np.full(n, np.nan)
    win = 5 * 252
    for i in range(n):
        lo = max(0, i - win)
        seg = score[lo:i]
        seg = seg[np.isfinite(seg)]
        if seg.size >= 250:
            thr[i] = np.quantile(seg, 0.95)
    per_onset = {}
    for i in onsets:
        lead_days = None
        for j in range(max(0, i - lead), i):
            if np.isfinite(score[j]) and np.isfinite(thr[j]) and score[j] > thr[j]:
                lead_days = i - j
                break
        per_onset[i] = lead_days
    warned = [v for v in per_onset.values() if v is not None]
    n_test = sum(1 for i in onsets
                 if np.isfinite(thr[max(0, i - lead):i]).any())
    if not warned:
        return per_onset, n_test, np.array([]), np.array([])
    keys = list(per_onset)
    rates, leads = [], []
    for _ in range(draws):
        pick = rng.choice(len(keys), size=len(keys), replace=True)
        vals = [per_onset[keys[k]] for k in pick]
        hit = [v for v in vals if v is not None]
        rates.append(len(hit) / len(vals))
        if hit:
            leads.append(float(np.mean(hit)))
    return per_onset, n_test, np.array(rates), np.array(leads)


async def bootstrap_arm(pillar2_variants: tuple[str, ...], draws: int) -> None:
    hdr("ARM 6 — EVENT-CLUSTERED BLOCK BOOTSTRAP on the pillar and CSRS series")
    from seraph.validation.harness import auc as auc_fn

    spec = importlib.util.spec_from_file_location(
        "rcw", _ROOT / "scripts" / "replay_crisis_warnings.py")
    rcw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(rcw)
    print("  build_signals() imported from scripts/replay_crisis_warnings.py —")
    print("  the replayed series are NOT rebuilt here, so the bootstrap cannot")
    print("  be computed on a different construction path than the replay.")
    print(f"\n  block lengths swept: {BLOCK_LENGTHS} trading days")
    print("  L=1 is the naive i.i.d. bootstrap — the implicit basis of any")
    print("  interval that treats 5,363 daily rows as independent observations.")
    print("  L=423 and L=770 are arm 3b's MEASURED rv_t_yz decorrelation scales.")
    print(f"  {draws} resamples per (signal, target, L).")

    for variant in pillar2_variants:
        qname = ("SCA_t  [SPEC FR18 conformant]" if variant == "sca"
                 else "lambda_1/N  [as shipped in adapters.rmt_emission]")
        hdr(f"ARM 6 — Pillar 2 quantity = {qname}")
        signals = await rcw.build_signals(variant)
        grid = signals["CSRS[rmt]"][0]
        t1, t3, keep3, onsets = _labels(grid)
        print(f"\n  grid {len(grid):,} sessions {grid[0]} .. {grid[-1]}; "
              f"{len(onsets)} onsets")
        print(f"  T1 positives {int(t1.sum())}d   T3 positives {int(t3.sum())}d "
              f"(in-crisis days dropped: {int((~keep3).sum())})")

        for tname, y, mask in (("T1 crisis detection", t1, np.ones(len(grid), bool)),
                               ("T3 advance warning", t3, keep3)):
            print(f"\n  --- {tname} ---")
            print(f"  {'signal':<24} {'AUC':>7} " +
                  " ".join(f"{'L=' + str(L):>17}" for L in BLOCK_LENGTHS))
            print("  " + "-" * (32 + 18 * len(BLOCK_LENGTHS)))
            widths: dict[str, dict[int, float]] = {}
            for sig, (d, v, _meta) in signals.items():
                s = np.asarray(v, float)
                if len(d) != len(grid):
                    pos = {x: i for i, x in enumerate(d)}
                    s = np.array([v[pos[x]] if x in pos else np.nan
                                  for x in grid], float)
                ss, yy = s[mask], y[mask]
                fin = np.isfinite(ss)
                if yy[fin].sum() < 5 or (1 - yy[fin]).sum() < 5:
                    print(f"  {sig:<24} {'n/a':>7}   "
                          f"UNTESTABLE — {int(yy[fin].sum())} positive "
                          f"finite points")
                    continue
                point = float(auc_fn(ss[fin], yy[fin]))
                row, widths[sig] = f"  {sig:<24} {point:>7.4f} ", {}
                rng = np.random.default_rng(31337)
                for L in BLOCK_LENGTHS:
                    bs, degen = _circular_block_auc(ss, yy, L, draws, rng, auc_fn)
                    if bs.size < 50:
                        row += f"{'VOID(' + str(degen) + 'deg)':>18}"
                        widths[sig][L] = float("nan")
                        continue
                    lo, hi = np.percentile(bs, [2.5, 97.5])
                    widths[sig][L] = float(hi - lo)
                    flag = "*" if degen > draws * 0.05 else " "
                    row += f"[{lo:.3f},{hi:.3f}]{flag:>1}  "
                print(row, flush=True)
            print("\n  CI WIDTH by block length, and the overstatement factor:")
            print(f"  {'signal':<24} " +
                  " ".join(f"{'L=' + str(L):>9}" for L in BLOCK_LENGTHS) +
                  f"{'w770/w1':>10}")
            for sig, w in widths.items():
                r = f"  {sig:<24} "
                for L in BLOCK_LENGTHS:
                    r += f"{w.get(L, float('nan')):>9.4f}"
                f1, f770 = w.get(1, float("nan")), w.get(770, float("nan"))
                r += f"{(f770 / f1 if f1 else float('nan')):>10.2f}x"
                print(r)
            print("  '*' = >5% of resamples were degenerate (could not define an")
            print("  AUC). 'w770/w1' is how much the naive i.i.d. interval")
            print("  UNDERSTATES the width once the measured dependence is used.")

        # ---- lead time, onset-clustered (block bootstrap cannot do this) ----
        print(f"\n  --- mean lead time, ONSET-CLUSTERED bootstrap "
              f"(h={LEAD_H}d, Rule-B style) ---")
        print("  Block bootstrap is structurally incapable of this statistic;")
        print("  see _onset_cluster_lead.__doc__. Same resampling unit as")
        print("  Workstream C used on its acceleration signals.")
        print(f"  {'signal':<24} {'warned/testable':>16} {'rate 95% CI':>20} "
              f"{'mean lead':>10} {'lead 95% CI':>20}")
        for sig, (d, v, _m) in signals.items():
            s = np.asarray(v, float)
            if len(d) != len(grid):
                pos = {x: i for i, x in enumerate(d)}
                s = np.array([v[pos[x]] if x in pos else np.nan
                              for x in grid], float)
            rng = np.random.default_rng(90210)
            per, n_test, rates, leads = _onset_cluster_lead(
                grid, s, onsets, LEAD_H, draws, rng)
            nw = sum(1 for x in per.values() if x is not None)
            rci = (f"[{np.percentile(rates, 2.5):.3f},"
                   f"{np.percentile(rates, 97.5):.3f}]" if rates.size else "n/a")
            ml = (f"{np.mean([x for x in per.values() if x is not None]):.1f}d"
                  if nw else "none")
            lci = (f"[{np.percentile(leads, 2.5):.1f},"
                   f"{np.percentile(leads, 97.5):.1f}]" if leads.size else "n/a")
            print(f"  {sig:<24} {f'{nw}/{n_test}':>16} {rci:>20} {ml:>10} "
                  f"{lci:>20}")
        print("\n  A warned count of 0 gives a degenerate interval [0,0]: the")
        print("  onset-clustered bootstrap of an all-zero vector is all zero.")
        print("  That is exactly why arm 5 uses an exact binomial bound instead")
        print("  of a bootstrap for the 0/N case.")


# ---- arm 6b: which intervals actually exclude AUC = 0.5, at which L? -------

def exclusion_table(log_path: Path) -> None:
    """Exact 0.5-exclusion accounting, parsed from an arm-6 log.

    "Essentially every interval spans 0.5" is an impressionistic claim and a
    reader cannot check it. This makes it exact: for each signal, target and
    block length, does the 95% interval exclude AUC = 0.5 or not? Parsed from
    the arm-6 log rather than recomputed, so the numbers are definitionally the
    ones that were published.
    """
    import re
    hdr(f"ARM 6b — EXACT 0.5-EXCLUSION ACCOUNTING (parsed from {log_path.name})")
    text = log_path.read_text(encoding="utf-8", errors="replace")
    variant, target = None, None
    rows: list[tuple[str, str, str, float, list[tuple[int, float, float]]]] = []
    for line in text.splitlines():
        if "Pillar 2 quantity =" in line:
            variant = "sca" if "SCA_t" in line else "lam1"
        elif "--- T1 crisis detection" in line:
            target = "T1"
        elif "--- T3 advance warning" in line:
            target = "T3"
        elif "mean lead time" in line:
            target = None
        m = re.match(r"\s{2}((?:CSRS|BASE)\[[^\]]+\])\s+([0-9.]+)\s+(.*)$", line)
        if m and target and variant:
            ivs = re.findall(r"\[([0-9.]+),([0-9.]+)\]", m.group(3))
            if len(ivs) == len(BLOCK_LENGTHS):
                rows.append((variant, target, m.group(1), float(m.group(2)),
                             [(L, float(a), float(b))
                              for L, (a, b) in zip(BLOCK_LENGTHS, ivs)]))
    if not rows:
        print("  no arm-6 interval rows found — wrong log?")
        return

    for variant in ("lam1", "sca"):
        for target in ("T1", "T3"):
            sel = [r for r in rows if r[0] == variant and r[1] == target]
            if not sel:
                continue
            qn = "SCA_t (FR18)" if variant == "sca" else "lambda_1/N (shipped)"
            print(f"\n  === {target}, Pillar 2 = {qn} ===")
            print(f"  {'signal':<26} {'AUC':>7} " +
                  " ".join(f"{'L=' + str(L):>7}" for L in BLOCK_LENGTHS))
            print("  " + "-" * (35 + 8 * len(BLOCK_LENGTHS)))
            for _v, _t, sig, point, ivs in sel:
                r = f"  {sig:<26} {point:>7.4f} "
                for _L, lo, hi in ivs:
                    r += f"{('EXCL' if (lo > 0.5 or hi < 0.5) else ' -- '):>7}"
                print(r)
            for scope, pred in (("pillar/CSRS", lambda s: s.startswith("CSRS[")),
                                ("baselines", lambda s: s.startswith("BASE["))):
                tot = sum(1 for r in sel if pred(r[2]))
                for L_i, L in enumerate(BLOCK_LENGTHS):
                    nexc = sum(1 for r in sel if pred(r[2])
                               and (r[4][L_i][1] > 0.5 or r[4][L_i][2] < 0.5))
                    if L in (1, 770):
                        print(f"    {scope:<12} excluding 0.5 at L={L:<4}: "
                              f"{nexc}/{tot}")
    print("\n  'EXCL' = the 95% interval excludes AUC = 0.5, i.e. the result has")
    print("  resolving power. ' -- ' = the interval spans 0.5, i.e. the result")
    print("  is indistinguishable from chance AT THAT dependence assumption.")
    print("  L=1 is the naive i.i.d. assumption; L=770 is measured (arm 3b).")


# ------------------------------------------------------------------- main -----

async def run(args) -> int:
    c = await asyncpg.connect(resolve_dsn(), timeout=600)
    try:
        if args.bootstrap_only:
            await bootstrap_arm(tuple(args.pillar2), args.boot_draws)
            return 0
        if args.warned_rate_only:
            warned_rate_arm()
            return 0
        if args.dependence_only:
            grid = await c.fetch(
                "SELECT DISTINCT date FROM daily_prices WHERE date >= '2005-01-03' "
                "AND universe_member_flag ORDER BY date")
            await dependence_arm(c, [str(r["date"]) for r in grid])
            return 0
        spec_trace()
        ctx = await data_vs_definition(c)
        await candidate_coverage(c, ctx["dates"])
        await dependence_arm(c, ctx["dates"])
        if args.power:
            rows = await c.fetch(
                "SELECT date, rv_t_yz FROM hamilton_output "
                "WHERE rv_t_yz IS NOT NULL ORDER BY date")
            dates = [str(r["date"]) for r in rows]
            rv = np.array([float(r["rv_t_yz"]) for r in rows])
            power_arm(dates, rv, args.draws, args.perms)
    finally:
        await c.close()
    hdr("DONE — read-only. No row was written by this script.")
    return 0


def _maybe_exclusion_only(argv) -> int | None:
    """Arm 6b needs no database, so it short-circuits before connecting."""
    if argv.exclusion_table:
        exclusion_table(Path(argv.exclusion_table))
        return 0
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--power", action="store_true")
    ap.add_argument("--dependence-only", action="store_true",
                    help="run only arm 3b (the N_eff deflation)")
    ap.add_argument("--warned-rate-only", action="store_true",
                    help="run only arm 5 (0/N detectability; needs no DB)")
    ap.add_argument("--bootstrap-only", action="store_true",
                    help="run only arm 6 (block bootstrap on replay signals)")
    ap.add_argument("--pillar2", nargs="+", default=["lam1", "sca"],
                    choices=("lam1", "sca"),
                    help="Pillar 2 quantity/quantities for arm 6")
    ap.add_argument("--boot-draws", type=int, default=2000)
    ap.add_argument("--exclusion-table", metavar="ARM6_LOG",
                    help="run only arm 6b: exact 0.5-exclusion accounting "
                         "parsed from an arm-6 log. Needs no DB")
    ap.add_argument("--draws", type=int, default=40)
    ap.add_argument("--perms", type=int, default=200)
    argv = ap.parse_args()
    early = _maybe_exclusion_only(argv)
    if early is not None:
        return early
    return asyncio.run(run(argv))


if __name__ == "__main__":
    raise SystemExit(main())
