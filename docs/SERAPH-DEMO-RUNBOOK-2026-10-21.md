# SERAPH local demonstration and retained input gates

This continues the [engineering audit](SERAPH-OVERALL-ENGINEERING-COMPLETION-AUDIT-2026-10-20.md). It does not change the original feature scope, research exclusions or authentication posture.

## Start the canonical application

From the checkout in PowerShell:

```powershell
.\launch_prototype.ps1
```

Open `http://127.0.0.1:8512`. The launcher owns the news worker, the daily acquisition/prediction job, and one market runtime. Closing the launcher stops its owned processes. `-NoLiveRuntime` is the explicit broker opt-out. `python scripts/run_live.py --status` is a read-only inspection; it does not connect a feed. A bare Streamlit process is not the owned multi-process launcher.

The prediction panel shows the actual forecast ledger ID, decision date, issuance mode and retained validation limits. Local retail/institutional/regulator switching is a demonstration identity, not P01 authentication. A role switch clears a previously active role's holdings and displayed analysis context.

## Reproduce the analytical workflows

1. Select a historical run/date and inspect CONSOLE, BACKTEST, the official NIFTY 500 coverage, and TOOLS flow. Missing date-bounded flow remains unavailable. The globe and role news surfaces continue to use their separate news clock.
2. Under MY WORKSPACE / PORTFOLIOS create a book, upload CSV columns `symbol,quantity,value,sector`, inspect rejected rows, save an explicit effective timestamp, and select **Use this portfolio**. Current and historical holdings bases are distinct. Missing measured sector flags mean unassessed coverage, not zero risk. Saved books survive reload; reactivate a saved book explicitly after a new browser session.
3. For an institutional defensive comparison, set the news clock to **historical_decision**, open MY WORKSPACE / SCENARIOS / **Save a defensive action comparison**, select the stored NIFTY 500 history, name and justify the assumptions, save, then Run and Export. The default example holds one notional index unit plus INR 1,000 cash, sells 50% at the next observed close, and charges 10 bps. It is a hypothetical position on observed prices, not an executable index share. Rotation, linear hedge and index-put actions accept explicit supplied instrument histories; index levels cannot substitute for option prices.
4. For a policy path, select the fitted artifact `b9a7459b4bfdff21efe19a59643524c1f84744904a2175b3f7e97307ec9c580e.json`. It fits the named RBI repo-rate variable from [BIS daily observations](https://data.bis.org/topics/CBPOL/BIS%2CWS_CBPOL%2C1.0/D.IN), not a renamed volatility variable. Use explicit baseline and hypothetical JSON rows with `session` and `rbi_repo_rate` (percent per annum). A 2026 fit beside a 2020 market baseline requires the retrospective checkbox. Save, Run and Export retain the parameters, inputs, initial state, regime paths and score paths. Hamilton stays excluded from production scoring; an unchanged score can coexist with a changed projected regime path.
5. The policy fit uses 278 retained observation pairs through July 23, 2026. Five missing-policy dates are omitted, so fitted transitions advance between retained observation pairs. The source is a latest-vintage series received in October, not historical release-vintage evidence. A higher-likelihood unconverged start and the selected converged fit are reported explicitly. This path provides conditional sensitivity, not causal policy effectiveness or demonstrated prediction skill.
6. For regulator submissions, open INSTITUTION EXPOSURES, choose the demo/user-supplied source, paste or upload INR holdings, preview, and accept. Two demo books of INR 1,000 and INR 2,000 must aggregate to INR 3,000. Reopen and export at a cutoff after receipt. The regulator console shows the same submitted decomposition. Market-value shares are not systemic-loss contributions. Retail/institutional payloads omit these restricted records.
7. The historical numerical tariff example remains in the institutional news controls with its cited old/new rate, old-duty-inclusive cost basis, user assumptions and downloaded analysis identity. It is separately labelled historical and conditional.

## Current input and decision gates

- The earlier October22 pre-open websocket connection is historical evidence. The latest daily/native websocket probes returned403, and recent-history API access failed. Restore broker access through the existing local login workflow; do not place credentials in chat. No probe produced a current decision.
- RMT preparation is complete:252 admitted observations. A fresh canonical cold start confirms usable history and latest-input admission. Native Hawkes is now implemented as an explicit owned worker/configuration; see [native runtime instructions](NATIVE-HAWKES-RUNTIME-2026-10-22.md). Its correct95-symbol basket has only143 historical sessions through April2020, with23 covered members, against the declared500-session window. Its own standardizer is not warmed by RMT history. Keep the window, mask and freshness gates unchanged.
- The pinned NSE calendar verifies **October 19–23, 2026 only**, including the October 20 holiday. Beyond that interval publication is unverified. Supply a complete bounded calendar with pinned official notices; do not extend coverage by assumption.
- Actual native intraday bars now support the bounded historical sector case. Select **Retrospective analytical archive** for the 2020 market date and activate the saved portfolio. The verified example covers INR 1,000 steel out of INR 3,000 total; the remainder is unassessed. Switching to **Selected market decision** restores zero coverage because the artifact was first produced in October 2026. Partial basket contributors and source timestamps remain visible.
- F07 has actual native sector counts and an implemented estimator/renderer. The owner explicitly chose to keep its fit pending on October22; do not run it. See `evidence/engineering-closeout-2026-10-21/NETWORK-DIAGNOSTIC-DESIGN.md`. No synthetic matrix is presented as measured transmission.
- FR35's authorized bounded design is registered. The actual two-mode report is `prototype_runs/experiments/2026-10-21-registered-real.json`; the canonical evaluation panel displays it with provenance. All 152 cells are unavailable because of insufficient support, rather than invented performance metrics. This completes the bounded report integration, not scientific validation.

The current evidence directory is `docs/evidence/engineering-closeout-2026-10-21/`. Browser verifiers copy the real stores into isolated directories, retain downloads, and label demonstration holdings and hypothetical actions. A failed or interrupted verifier is not a passed end-to-end journey; read each `result.json` and the audit reconciliation.

The completed broad regression run records2,585 passed and22 environment/data-dependent skips (`evidence/engineering-closeout-2026-10-22/full-suite-recheck.xml`). Historical browser journeys are verified; unrestricted live demo readiness remains open.
