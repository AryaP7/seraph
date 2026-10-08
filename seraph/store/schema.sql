-- C1 — Store & Schema (FR8, FR38)
-- DDL for E1–E14 (SPEC §6) + ingestion watermarks + universe snapshots.
-- Hypertables partitioned on the timestamp axis per FR8 / NFR34.
-- Idempotent: safe to apply repeatedly (initdb mount, tests, migrations).

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- ---------------------------------------------------------------- E1
CREATE TABLE IF NOT EXISTS intraday_bars (
    symbol          text             NOT NULL,
    ts              timestamptz      NOT NULL,
    open            double precision NOT NULL,
    high            double precision NOT NULL,
    low             double precision NOT NULL,
    close           double precision NOT NULL,
    volume          bigint           NOT NULL,
    signed_volume   bigint           NOT NULL DEFAULT 0,      -- FR5, written by C4
    log_return      double precision NOT NULL DEFAULT 0,
    is_jump         boolean          NOT NULL DEFAULT false,  -- FR50, written by C4
    jump_sign       smallint         NOT NULL DEFAULT 0 CHECK (jump_sign IN (-1, 0, 1)),
    PRIMARY KEY (symbol, ts)
);
SELECT create_hypertable('intraday_bars', 'ts', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E2
CREATE TABLE IF NOT EXISTS microstructure_state (
    symbol               text             NOT NULL,
    ts                   timestamptz      NOT NULL,
    spread_ar            double precision,                     -- NULL → warning, not error
    spread_cs            double precision,
    amihud_illiq         double precision,
    signed_vol_imbalance double precision NOT NULL,
    spread_quintile      smallint         NOT NULL CHECK (spread_quintile BETWEEN 1 AND 5),
    imbalance_quintile   smallint         NOT NULL CHECK (imbalance_quintile BETWEEN 1 AND 5),
    s_t                  smallint         NOT NULL CHECK (s_t BETWEEN 1 AND 25),
    PRIMARY KEY (symbol, ts)
);
SELECT create_hypertable('microstructure_state', 'ts', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E3
CREATE TABLE IF NOT EXISTS daily_prices (
    symbol                text             NOT NULL,
    date                  date             NOT NULL,
    open                  double precision NOT NULL,
    high                  double precision NOT NULL,
    low                   double precision NOT NULL,
    close                 double precision NOT NULL,
    volume                bigint           NOT NULL,
    tottrdval             numeric          NOT NULL,           -- split-invariant (SPEC E3 note)
    adj_close             double precision NOT NULL,
    log_return_std        double precision,                    -- written by C4
    yz_volatility         double precision,                    -- written by C4
    universe_member_flag  boolean          NOT NULL DEFAULT false,  -- written by C3, never C2
    listing_days_to_date  integer          NOT NULL DEFAULT 0,
    PRIMARY KEY (symbol, date)
);
SELECT create_hypertable('daily_prices', 'date', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E4
CREATE TABLE IF NOT EXISTS macro_covariates (
    date                    date             NOT NULL,
    rbi_repo_rate           double precision,
    bank_credit_growth_yoy  double precision,
    india_vix               double precision,                  -- NULL before Nov 2007
    vix_available           boolean          NOT NULL DEFAULT false,
    inr_twi                 double precision,
    brent_price             double precision,
    g_t                     double precision,                  -- FR22, written by C4
    g_t_sector_weighted     double precision,
    PRIMARY KEY (date)
);
SELECT create_hypertable('macro_covariates', 'date', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E5
CREATE TABLE IF NOT EXISTS tariff_events (
    event_id         text             NOT NULL,
    tau_k            date             NOT NULL,
    delta_r_k        double precision NOT NULL,
    severity_score   double precision NOT NULL,
    sectors_affected text[]           NOT NULL DEFAULT '{}',
    source_ref       text             NOT NULL,
    PRIMARY KEY (event_id)
);

-- ---------------------------------------------------------------- E6
CREATE TABLE IF NOT EXISTS hawkes_output (
    ts                 timestamptz      NOT NULL,
    scope              text             NOT NULL CHECK (scope IN ('market', 'sector', 'instrument')),
    scope_id           text             NOT NULL DEFAULT '',
    branching_ratio_n  double precision NOT NULL CHECK (branching_ratio_n < 1),  -- FR11
    mts                double precision NOT NULL CHECK (mts >= 0),               -- FR13
    jump_count_neg     integer          NOT NULL,
    jump_count_pos     integer          NOT NULL,
    asymmetry_ratio    double precision NOT NULL,
    sector_microflag   text             NOT NULL DEFAULT 'none' CHECK (sector_microflag IN ('none', 'amber')),
    branching_matrix   jsonb,                                                    -- Φ(S_t), FR15
    alpha_beta         jsonb,                                                    -- per (i,j,k,S)
    PRIMARY KEY (scope, scope_id, ts)
);
SELECT create_hypertable('hawkes_output', 'ts', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E7
CREATE TABLE IF NOT EXISTS rmt_output (
    date                     date               NOT NULL,
    eigenvalues              double precision[] NOT NULL,
    v1                       double precision[] NOT NULL,
    f_t                      double precision   NOT NULL,
    v_eig_t                  double precision   NOT NULL,
    omega_t                  double precision   NOT NULL,
    sca_t                    double precision   NOT NULL,
    mp_pvalue                double precision   NOT NULL,       -- FR19
    lambda_minus             double precision   NOT NULL,
    lambda_plus              double precision   NOT NULL,
    common_support_fraction  double precision   NOT NULL DEFAULT 1.0,  -- D3
    rebalance_adjacent       boolean            NOT NULL DEFAULT false, -- D3
    PRIMARY KEY (date)
);
SELECT create_hypertable('rmt_output', 'date', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E8
CREATE TABLE IF NOT EXISTS hamilton_output (
    date                    date             NOT NULL,
    rv_t_yz                 double precision NOT NULL,
    rv_t_5min               double precision,                  -- NULL before intraday coverage
    ar_t                    double precision NOT NULL,
    bas_t                   double precision NOT NULL,
    xi_1                    double precision NOT NULL,
    xi_2                    double precision NOT NULL,
    xi_3                    double precision NOT NULL,
    lsd_t                   double precision NOT NULL CHECK (lsd_t >= 0 AND lsd_t <= 3),
    p_hat_22                double precision NOT NULL,
    p_hat_33                double precision NOT NULL,
    tau_half_stressed       double precision NOT NULL,
    tau_half_crisis         double precision NOT NULL,
    estimation_uncertainty  double precision NOT NULL,          -- FR23
    gamma_ij                jsonb,                              -- TVTP coefficients
    PRIMARY KEY (date),
    CHECK (abs(xi_1 + xi_2 + xi_3 - 1.0) < 1e-6)
);
SELECT create_hypertable('hamilton_output', 'date', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E9
CREATE TABLE IF NOT EXISTS reconciled_state (
    ts               timestamptz        NOT NULL,
    mode             text               NOT NULL CHECK (mode IN ('kalman', 'forward_fill')),  -- FR27
    x_hat            double precision[] NOT NULL,               -- length 3, PILLAR_ORDER
    p_matrix         double precision[] NOT NULL,               -- 9 elements, row-major
    tau_last_update  timestamptz[]      NOT NULL,               -- length 3, NULL elements allowed
    mask             boolean[]          NOT NULL,               -- D2
    noise_saturated  boolean[]          NOT NULL,               -- D4
    PRIMARY KEY (mode, ts)
);
SELECT create_hypertable('reconciled_state', 'ts', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E10
CREATE TABLE IF NOT EXISTS csrs (
    ts                   timestamptz        NOT NULL,
    reconciliation_mode  text               NOT NULL CHECK (reconciliation_mode IN ('kalman', 'forward_fill')),
    xi_mode              text               NOT NULL DEFAULT 'hamilton' CHECK (xi_mode IN ('hamilton', 'uniform')),
    weights_artefact_id  text               NOT NULL,           -- audit trail (D1)
    csrs                 double precision   NOT NULL CHECK (csrs >= 0 AND csrs <= 1),
    var_csrs             double precision   NOT NULL CHECK (var_csrs >= 0),
    ci_lower             double precision   NOT NULL,
    ci_upper             double precision   NOT NULL,
    shapley              double precision[] NOT NULL,           -- length 3, PILLAR_ORDER
    alert_level          text               NOT NULL CHECK (alert_level IN ('green', 'amber', 'red')),
    mask                 boolean[]          NOT NULL,           -- D2 provenance
    effective_weights    jsonb              NOT NULL,           -- D2 post-renormalisation
    PRIMARY KEY (reconciliation_mode, xi_mode, weights_artefact_id, ts)
);
SELECT create_hypertable('csrs', 'ts', if_not_exists => TRUE);

-- ---------------------------------------------------------------- E11
CREATE TABLE IF NOT EXISTS user_portfolio (
    user_id       text             NOT NULL,
    symbol        text             NOT NULL,
    quantity      double precision NOT NULL,
    value         double precision NOT NULL,
    sector        text             NOT NULL,
    exposure_pct  double precision NOT NULL,
    PRIMARY KEY (user_id, symbol)
);

-- ---------------------------------------------------------------- E12
CREATE TABLE IF NOT EXISTS regulatory_action_log (
    alert_id                       text        NOT NULL,
    ts                             timestamptz NOT NULL,
    action_taken                   text        NOT NULL CHECK (action_taken IN ('none', 'soft_warning', 'circuit_breaker')),
    pillar_decomposition_snapshot  double precision[] NOT NULL,  -- length 3, PILLAR_ORDER
    PRIMARY KEY (alert_id)
);

-- ---------------------------------------------------------------- E13
CREATE TABLE IF NOT EXISTS validation_results (
    pillar_subset          text             NOT NULL,           -- e.g. 'hawkes+rmt+hamilton'
    reconciliation_mode    text             NOT NULL CHECK (reconciliation_mode IN ('kalman', 'forward_fill')),
    xi_mode                text             NOT NULL DEFAULT 'hamilton' CHECK (xi_mode IN ('hamilton', 'uniform')),
    epoch                  text             NOT NULL,
    table_id               text             NOT NULL CHECK (table_id IN ('A', 'B')),
    auc                    double precision NOT NULL,
    mean_lead_time_days    double precision NOT NULL,
    precision_at_recall    double precision NOT NULL,
    weights_artefact_id    text             NOT NULL,
    leakage_check          text             NOT NULL CHECK (leakage_check IN ('clean', 'TRAIN_TEST_OVERLAP')),
    pre_registration_hash  text             NOT NULL,           -- D5(d)
    PRIMARY KEY (pillar_subset, reconciliation_mode, xi_mode, epoch)
);

-- ---------------------------------------------------------------- E14
CREATE TABLE IF NOT EXISTS flow_aggregates (
    date                 date             NOT NULL,
    fii_net              numeric          NOT NULL,
    dii_net              numeric          NOT NULL,
    total_turnover       numeric          NOT NULL,
    residual_flow_share  double precision NOT NULL,
    PRIMARY KEY (date)
);
SELECT create_hypertable('flow_aggregates', 'date', if_not_exists => TRUE);

-- ------------------------------------------------------- universe (C3, S3)
CREATE TABLE IF NOT EXISTS universe_snapshots (
    rebalance_date  date             NOT NULL,
    members         text[]           NOT NULL,                  -- invariant: 500 names
    eligible_count  integer          NOT NULL,
    entrants        text[]           NOT NULL DEFAULT '{}',
    leavers         text[]           NOT NULL DEFAULT '{}',
    churn_fraction  double precision NOT NULL DEFAULT 0,
    rule            jsonb            NOT NULL,                  -- FR52 + D3, auditable
    PRIMARY KEY (rebalance_date)
);

-- ------------------------------------------------------- watermarks (S1)
CREATE TABLE IF NOT EXISTS ingestion_watermarks (
    source      text        NOT NULL,
    entity      text        NOT NULL,
    watermark   timestamptz NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (source, entity)
);
