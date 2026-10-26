# Bounded F07 network diagnostic proposal

Status: proposed, not adopted. No real fit has been run under these settings.

This specifies the existing negative-binomial geometric-excitation implementation,
not a replacement pillar or production model. Fit interval: 2019-10-01 through
2020-04-30. Node order is the sorted five sectors from the existing provisional
tariff basket; actual contributors and omissions must be exported. Use actual
native five-minute negative-jump counts from the existing C4 detector. No
resampling from daily prices, no missing-bar filling, no fabricated edges.

Fixed proposed parameters: decay 0.5 per five-minute step (five-minute lag-state
half-life); negative-binomial dispersion 10; L2 coefficient 0.01; at least 750
native bins and ten events per node; source-column sums bounded by 0.95;
training-window time-of-day baseline; session-open lag reset; display threshold
0.001, with the full matrix retained. These are illustrative diagnostic choices,
not calibrated or established optimal financial parameters. They are not to be
tuned to produce a connected or visually attractive graph.

Matrix convention: B[target, source]. Simultaneous bar events have no invented
ordering. Weights are conditional excitation estimates, not causal transmission,
loss probabilities, or validated early warnings. Missing support or an optimizer
failure remains an unavailable result. Fit and artifact availability timestamps
are actual current times. The historical score and geographic news globe remain
unchanged; only the explicit retrospective network archive may display this fit.

Adoption requires the owner's explicit choice. Preserve the proposal, record the
choice, and create a separate specification with model_status=user_declared
before fitting once. Retain zero edges, negative findings and all warnings.
