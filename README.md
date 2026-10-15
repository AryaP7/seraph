# SERAPH — Astra version codebase

The current development and research baseline, retaining **Hawkes, RMT and
Hamilton**. Includes corrected mathematical components, causal future-loss
forecasting, volatility benchmarks, reproducible historical evaluation and
a Streamlit research dashboard.

**Start with [README-RESEARCH.md](README-RESEARCH.md)** for installation,
reproduction and the dashboard. [VALIDATION.md](VALIDATION.md) records testing
and empirical limits. This is a research baseline, not a validated crisis
prediction service. Historical negative results remain preserved.

## Quick start

Python 3.12, from the repository root:

```sh
python -m venv .venv
# Activate the environment for your platform, then:
python -m pip install -r requirements-research.lock.txt
python scripts/check_invariants.py
python scripts/verify_research_artifacts.py
python -m streamlit run seraph/prediction/app.py --server.address 127.0.0.1
```

Windows users can instead run `./launch_research.ps1` after setup. Saved
research data and results are included, so viewing and verifying them do not
require the original database or this author's filesystem.

The optional original-file preservation check accepts
`python scripts/verify_research_artifacts.py --original-root PATH`.

## History and integration

- Previous checkpoint: `pre-astra-codebase` (the saved Opus/evidence version).
- Astra development branch: `astra-version-codebase`; integrated into `main`
  through a merge commit, preserving prior history.
- The default experimental database is isolated on localhost port 5434.
  Snapshot extraction from another database is an explicit read-only operation.
- Local environments, credentials and nested agent worktrees are excluded.
- Historical byte hashes are preserved across Git checkouts; do not normalize
  evidence files and then present their old hashes as valid.
