# Verification and acceptance — 2026-10-14

## Astra GitHub integration — 2026-10-15

The Astra branch starts from the saved `9b8bb97` evidence/Opus checkpoint.
Original history is retained. A fresh isolated environment installs from the
recorded dependency lock. The public ISIN classification dependency is included
explicitly, while credentials, environments and nested worktrees are excluded.

Artifact verification is now portable: Windows manifest separators are handled
on other platforms, and checking the author's original checkout is optional
through `--original-root`. Git attributes preserve evidence bytes so recorded
SHA-256 hashes survive checkout. These integration changes do not alter fitted
models or the saved prediction results. GitHub Actions verifies artifacts,
invariants and the test suite in five non-overlapping partitions; DB-dependent
checks remain explicitly skipped without their integration fixtures.

## Software verification

Final collection contains **306 tests**. Across non-overlapping completed
partitions and targeted reruns after fixes, **297 passed, 8 skipped, 1 expected
failure**. There are no unresolved unexpected failures. This is an accumulated
result, not a claim that one uninterrupted full-suite command produced it.

The broad initial partition plus original Hamilton modules covered 272 tests.
During parallel development 28 more tests were added: evaluation (19), hazard
watch (3), and viewer (6). Two evaluation hardening tests followed. The jump
calibration repair expanded that module from three tests to seven and resolved
its previous expected failure, bringing the total to 306.

- All eight skipped tests require database integration: two ingestion tests,
  four intraday jump-density tests and two Hawkes-writer tests. Test subprocesses
  used a disabled database DSN, so they could not mutate the original database.
- The remaining strict expected failure records the inherited FR35 Table B
  fold-count specification conflict. It is not an achieved acceptance criterion.
- All original slow Hamilton tests completed: groups of 7, 5 and 6 tests, plus
  the policy integration test. Their runtimes were approximately 276, 243, 223
  and 201 seconds respectively, each within its 300-second subprocess bound.
- All five mechanical invariant checks passed.
- Streamlit AppTest verifies unavailable data, exact historical feature rows,
  abstention, target separation and external-watch attribution. Actual saved
  results render without exceptions at 2008-09-12, 2020-01-31 and 2026-08-21.
- The launcher health check returned `ok` and confirmed localhost-only binding.
  The temporary smoke-test server was stopped.

The initial missing-copy failure in equity/ETF classification was resolved by
copying the original public ISIN reference CSV unchanged. Its hash is recorded
in `docs/PREDICTION-PILLARS.md`. No historical universe was silently rewritten.

## Replay and data verification

The snapshot contains **5,361 observed sessions**, from 2005-01-03 through
2026-08-21. It was extracted with a read-only repeatable-read transaction.
The replay itself has no database or network access.

The first `v1` artifacts remain preserved. `v1_verified` uses the same fixed
parameters after input-contract hardening; all daily predictions and pillar
features compare **exactly equal**, including missingness. This is replication
of one retrospective experiment, not a second independent validation sample.

`scripts/verify_research_artifacts.py` checks:

- All snapshot data hashes, replay model-code hashes and original output hashes.
- Every one of 876 supervised refits uses labels matured at least 15 sessions
  before the decision; 977 alert-policy fits obey the same outcome-availability
  constraint and their stated historical alarm budgets.
- Forecast and feature identity between the two saved runs.
- Nine sourced external declarations, strictly later session activation and
  exactly 20 observed watch sessions each.
- The external COVID watch date of 2020-01-31, 14 sessions before the inherited
  onset date.
- **All 307 recorded original files remain hash-identical**, with none missing.
  This refers to the manifest's scope, not every unlisted original asset.

Run this read-only check (apart from its own result file):

```powershell
.\.venv\Scripts\python.exe scripts/verify_research_artifacts.py
```

The result is saved in `research_results/v1_verified/integrity_check.json`.

## Mathematical repairs versus historical artifacts

The copied fusion variance, missing-observation Kalman behavior, time clock
and intraday jump detector have explicit amendments. Their tests establish
specific mathematical behavior; they do not establish calibrated economic risk.

Existing intraday jump and Hawkes database snapshots were **not regenerated**.
Prior density estimates and fitted Hawkes parameters must not be described as
results of the corrected jump detector. The new daily-tail pipeline does not
read those stored intraday results, so its saved replay is unaffected. See
`docs/AMENDMENT-RESEARCH-JUMP-CALIBRATION.md`.

## Predictive acceptance remains unmet

The combined market model does not warn before COVID or the other assessable
project event labels. Its loss-probability improvement over the volatility
logistic baseline is not clearly separated from zero by the descriptive paired
bootstrap. Its onset warning policy exceeds its historical calibration budget
out of sample. Early GFC coverage is unassessable and tariff-2026 is unresolved.

The public-health overlay supplies a narrower counterfactual watch before
COVID, plus eight unmatched watches under these labels. The combined watch's
false-alarm rate is worse than the external channel alone. Neither hindsight
design nor approximate announcement availability supports claiming proven
pre-COVID predictive performance.

Production integration, broker execution, immutable vintage-data validation,
general credit/policy-event ingestion and prospective acceptance are not
completed by this research delivery. The saved reports expose these gaps.
