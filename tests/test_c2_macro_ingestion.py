# C2 — macro / flow / tariff ingestion (FR3, FR4, FR51) — focused tests.
"""Covers parsing, normalisation, timestamp alignment, missing data and
idempotency for the three E4/E5/E14 clients.

Everything above `--- DB-backed ---` runs offline against fixture strings: no
network, no database. The DB-backed block mirrors CT-1's idempotency contract
for E4/E5/E14 and skips when TimescaleDB is unreachable.

The leakage tests are the ones that matter most. A macro panel that leaks is
still a panel that trains, converges and reports a flattering AUC — the failure
is silent, so it has to be pinned by assertion rather than inspection.
"""
from __future__ import annotations

import asyncio
import json
from datetime import date
from pathlib import Path

import pytest

from seraph.ingestion import flow_client, macro_client, tariff_events
from seraph.ingestion.macro_client import (
    MacroSeries,
    Observation,
    align_as_of,
    align_native,
    available_from,
    compose_rows,
    coverage_report,
    parse_eod2_index_csv,
    parse_fred_csv,
    parse_nse_index_close_all,
    period_end,
    yoy_pct_4q,
)

# --- fixtures (verbatim shapes, captured from the live sources 2026-10-12) ---

FRED_DAILY = """observation_date,DCOILBRENTEU
2020-01-01,.
2020-01-02,66.25
2020-01-03,68.60
"""

FRED_MONTHLY = """observation_date,NBINBIS
2026-05-01,80.39
2026-06-01,81.50
2026-07-01,81.08
"""

FRED_QUARTERLY_LEVELS = """observation_date,CRDQINAPABIS
2024-10-01,100.0
2025-01-01,110.0
2025-04-01,120.0
2025-07-01,130.0
2025-10-01,121.0
"""

EOD2_VIX = """Date,Open,High,Low,Close,Volume,P/E,Series,TOTAL_TRADES,QTY_PER_TRADE,DLV_QTY
2014-05-14,32.0475,32.995,28.61,32.42,,,,,,
2014-05-15,32.42,37.48,31.1375,36.77,,,,,,
2026-08-21,10.755,11.35,9.57,11.2,nan,nan,,,,
"""

NSE_IND_CLOSE_ALL = (
    "Index Name,Index Date,Open Index Value,High Index Value,Low Index Value,"
    "Closing Index Value,Points Change,Change(%),Volume,Turnover (Rs. Cr.),"
    "P/E,P/B,Div Yield\n"
    "Nifty 50,09-10-2026,22314.95,22580.75,22304.45,22363.35,-157.1,-0.7,"
    "1234567890,45000.25,19.12,2.75,1.53\n"
    "Nifty 500,09-10-2026,21689.1,21928.55,21625.8,21866.65,250.5,1.16,"
    "1897774365,69762.13,21.56,3.06,1.31\n"
    "India VIX,09-10-2026,15.275,15.275,13.6625,14.38,-0.9,-5.89,-,-,-,-,-\n"
)

NSE_FII_DII = json.dumps([
    {"buyValue": "15506.73", "category": "DII", "date": "12-Oct-2026",
     "netValue": "3045.02", "sellValue": "12461.71"},
    {"buyValue": "12583.21", "category": "FII/FPI", "date": "12-Oct-2026",
     "netValue": "-1708.48", "sellValue": "14291.69"},
])

_DAILY = macro_client.SERIES_BY_FIELD["brent_price"]
_MONTHLY = macro_client.SERIES_BY_FIELD["inr_twi"]
_QUARTERLY = macro_client.SERIES_BY_FIELD["bank_credit_growth_yoy"]
_VIX = macro_client.SERIES_BY_FIELD["india_vix"]


# --- parsing --------------------------------------------------------------


def test_fred_missing_sentinel_is_none_not_zero():
    obs = parse_fred_csv(FRED_DAILY, "DCOILBRENTEU", _DAILY)
    assert [o.value for o in obs] == [None, 66.25, 68.60]
    # The gap is retained as a row, not dropped: dropping it would let the
    # previous value forward-fill across a hole the source published.
    assert obs[0].period_start == date(2020, 1, 1)


def test_fred_rejects_wrong_series_rather_than_mislabelling_it():
    with pytest.raises(ValueError, match="expected 'NBINBIS'"):
        parse_fred_csv(FRED_DAILY, "NBINBIS", _MONTHLY)


def test_fred_rejects_unknown_header_shape():
    with pytest.raises(ValueError, match="unexpected FRED date column"):
        parse_fred_csv("when,what\n2020-01-01,1.0\n", "WHAT", _DAILY)


def test_fred_accepts_legacy_date_header():
    obs = parse_fred_csv("DATE,DCOILBRENTEU\n2020-01-02,66.25\n",
                         "DCOILBRENTEU", _DAILY)
    assert [o.value for o in obs] == [66.25]


def test_eod2_vix_parses_and_treats_nan_columns_as_irrelevant():
    obs = parse_eod2_index_csv(EOD2_VIX)
    assert len(obs) == 3
    assert obs[0].period_start == date(2014, 5, 14)
    assert obs[0].value == pytest.approx(32.42)
    # "nan" appears in Volume/P-E on later rows; only Close is read.
    assert obs[-1].value == pytest.approx(11.2)


def test_nse_index_close_all_vix_placeholder_columns():
    obs = parse_nse_index_close_all(NSE_IND_CLOSE_ALL)
    assert obs is not None
    assert obs.period_start == date(2026, 10, 9)
    assert obs.value == pytest.approx(14.38)


def test_nse_index_close_all_missing_index_is_none_not_error():
    # The real pre-2014-05-15 situation: the file exists and parses, but has no
    # India VIX row. That is absence of data, not a failure.
    without_vix = "\n".join(
        l for l in NSE_IND_CLOSE_ALL.splitlines() if not l.startswith("India VIX")
    ) + "\n"
    assert parse_nse_index_close_all(without_vix) is None


def test_nse_index_close_all_rejects_foreign_csv():
    with pytest.raises(ValueError, match="not an NSE ind_close_all CSV"):
        parse_nse_index_close_all(FRED_DAILY)


# --- period arithmetic ----------------------------------------------------


@pytest.mark.parametrize("label,period,expected", [
    (date(2026, 7, 15), "day", date(2026, 7, 15)),
    (date(2026, 7, 1), "month", date(2026, 7, 31)),
    (date(2026, 2, 1), "month", date(2026, 2, 28)),      # non-leap
    (date(2024, 2, 1), "month", date(2024, 2, 29)),      # leap
    (date(2026, 12, 1), "month", date(2026, 12, 31)),    # year rollover
    (date(2026, 1, 1), "quarter", date(2026, 3, 31)),
    (date(2026, 10, 1), "quarter", date(2026, 12, 31)),  # year rollover
])
def test_period_end_closes_the_period_not_the_label(label, period, expected):
    assert period_end(label, period) == expected


def test_monthly_observation_is_not_available_on_its_label_date():
    # The central look-ahead trap: FRED labels July's value 2026-07-01, but it
    # describes all of July and cannot be known on 1 July.
    obs = Observation(date(2026, 7, 1), period_end(date(2026, 7, 1), "month"), 81.08)
    assert available_from(obs, _MONTHLY) > date(2026, 7, 31)


# --- derived series -------------------------------------------------------


def test_yoy_uses_four_quarter_lag_and_inherits_the_later_period():
    levels = parse_fred_csv(FRED_QUARTERLY_LEVELS, "CRDQINAPABIS", _QUARTERLY)
    yoy = yoy_pct_4q(levels)
    assert len(yoy) == 1                                  # 5 levels → 1 YoY point
    assert yoy[0].value == pytest.approx(21.0)            # 121 vs 100
    assert yoy[0].period_start == date(2025, 10, 1)
    assert yoy[0].period_end == date(2025, 12, 31)        # the *later* quarter


def test_yoy_propagates_missingness_instead_of_inventing_a_number():
    levels = (
        Observation(date(2024, 10, 1), date(2024, 12, 31), None),
        Observation(date(2025, 1, 1), date(2025, 3, 31), 110.0),
        Observation(date(2025, 4, 1), date(2025, 6, 30), 120.0),
        Observation(date(2025, 7, 1), date(2025, 9, 30), 130.0),
        Observation(date(2025, 10, 1), date(2025, 12, 31), 121.0),
    )
    assert yoy_pct_4q(levels)[0].value is None


def test_yoy_guards_zero_base():
    levels = tuple(
        Observation(date(2024 + i // 4, (i % 4) * 3 + 1, 1),
                    date(2024 + i // 4, (i % 4) * 3 + 3, 28),
                    0.0 if i == 0 else 100.0)
        for i in range(5)
    )
    assert yoy_pct_4q(levels)[0].value is None


# --- alignment / leakage --------------------------------------------------


def _axis(*isos: str) -> tuple[date, ...]:
    return tuple(date.fromisoformat(s) for s in isos)


def test_as_of_alignment_never_uses_an_observation_published_later():
    """The load-bearing leakage test.

    With a 30-day lag, availability is: May → 2026-06-30, June → 2026-07-30,
    July → 2026-08-30. So on 2026-08-15 the panel must still show JUNE's value;
    showing July's would be foresight of a figure not yet published.
    """
    obs = {"inr_twi": parse_fred_csv(FRED_MONTHLY, "NBINBIS", _MONTHLY)}
    axis = _axis("2026-06-15", "2026-07-15", "2026-08-15", "2026-08-30", "2026-09-30")
    aligned = align_as_of(obs, axis)

    assert aligned[date(2026, 6, 15)]["inr_twi"] is None          # nothing out yet
    assert aligned[date(2026, 7, 15)]["inr_twi"] == pytest.approx(80.39)   # May's
    assert aligned[date(2026, 8, 15)]["inr_twi"] == pytest.approx(81.50)   # June's
    assert aligned[date(2026, 8, 30)]["inr_twi"] == pytest.approx(81.08)   # July's
    assert aligned[date(2026, 9, 30)]["inr_twi"] == pytest.approx(81.08)

    # Restated as the property rather than the values: July's 81.08 must appear
    # nowhere before its publication date.
    assert all(
        aligned[d]["inr_twi"] != pytest.approx(81.08)
        for d in axis if d < date(2026, 8, 30)
    )


def test_as_of_alignment_is_inclusive_exactly_at_available_from():
    obs = (Observation(date(2026, 7, 15), date(2026, 7, 15), 70.0),)
    avail = available_from(obs[0], _DAILY)                   # +7 days
    aligned = align_as_of({"brent_price": obs}, (avail, ))
    assert aligned[avail]["brent_price"] == pytest.approx(70.0)

    day_before = date.fromordinal(avail.toordinal() - 1)
    aligned2 = align_as_of({"brent_price": obs}, (day_before, ))
    assert aligned2[day_before]["brent_price"] is None


def test_published_gap_overwrites_rather_than_carrying_the_prior_value():
    # 2020-01-01 is a published "." gap, but it is *earlier* than the real
    # values, so order matters: a later gap must null the series, not inherit.
    obs = (
        Observation(date(2020, 1, 2), date(2020, 1, 2), 66.25),
        Observation(date(2020, 1, 3), date(2020, 1, 3), None),
    )
    axis = _axis("2020-01-09", "2020-01-10")
    aligned = align_as_of({"brent_price": obs}, axis)
    assert aligned[date(2020, 1, 9)]["brent_price"] == pytest.approx(66.25)
    assert aligned[date(2020, 1, 10)]["brent_price"] is None


def test_as_of_alignment_is_order_independent():
    """Observations arriving unsorted must align identically — the cursor walk
    sorts by availability, so a source that reverses its CSV cannot shuffle the
    panel."""
    obs = parse_fred_csv(FRED_MONTHLY, "NBINBIS", _MONTHLY)
    axis = _axis("2026-08-15", "2026-08-30", "2026-09-30")
    assert align_as_of({"inr_twi": obs}, axis) == \
        align_as_of({"inr_twi": tuple(reversed(obs))}, axis)


def test_native_alignment_does_not_forward_fill():
    obs = {"inr_twi": parse_fred_csv(FRED_MONTHLY, "NBINBIS", _MONTHLY)}
    native = align_native(obs)
    assert set(native) == {date(2026, 5, 1), date(2026, 6, 1), date(2026, 7, 1)}
    assert native[date(2026, 7, 1)]["inr_twi"] == pytest.approx(81.08)


# --- row composition ------------------------------------------------------


def test_vix_available_tracks_the_datum_not_the_calendar():
    aligned = {
        date(2008, 1, 2): {"india_vix": None, "brent_price": 96.0},
        date(2026, 8, 21): {"india_vix": 11.2, "brent_price": 70.0},
    }
    rows = compose_rows(aligned)
    assert rows[0].india_vix is None and rows[0].vix_available is False
    assert rows[1].india_vix == pytest.approx(11.2) and rows[1].vix_available is True


def test_pre_2014_vix_gap_is_left_null_not_proxied():
    """The gap documented in the module docstring must stay a gap. If this test
    ever fails because a value appeared, check what filled it before cheering."""
    obs = {"india_vix": parse_eod2_index_csv(EOD2_VIX)}
    axis = _axis("2008-01-02", "2013-05-22", "2014-05-15", "2014-05-16", "2026-08-25")
    rows = compose_rows(align_as_of(obs, axis))
    gfc, taper, first, second, recent = rows
    # Both pre-2014 epochs score the covariate as structurally unavailable.
    assert (gfc.india_vix, gfc.vix_available) == (None, False)
    assert (taper.india_vix, taper.vix_available) == (None, False)
    assert first.india_vix == pytest.approx(32.42)    # 2014-05-14 close, +1d lag
    assert second.india_vix == pytest.approx(36.77)   # 2014-05-15 close
    assert recent.india_vix == pytest.approx(11.2)


def test_compose_preserves_c4_derived_columns_on_rerun():
    """C1's E4 upsert writes every non-key column, so a macro re-run would null
    out FR22's g_t unless it is carried through. Guards a cross-component
    data-loss bug, not just a field default."""
    aligned = {date(2026, 8, 21): {"brent_price": 70.0}}
    rows = compose_rows(aligned, preserve={"2026-08-21": (1.25, 0.8)})
    assert rows[0].g_t == pytest.approx(1.25)
    assert rows[0].g_t_sector_weighted == pytest.approx(0.8)


def test_compose_leaves_g_t_null_when_c4_has_not_run():
    rows = compose_rows({date(2026, 8, 21): {"brent_price": 70.0}})
    assert rows[0].g_t is None and rows[0].g_t_sector_weighted is None


def test_compose_is_deterministic_and_date_sorted():
    aligned = {
        date(2026, 8, 21): {"brent_price": 70.0},
        date(2026, 8, 19): {"brent_price": 69.0},
        date(2026, 8, 20): {"brent_price": None},
    }
    first = compose_rows(aligned)
    second = compose_rows(aligned)
    assert [r.date for r in first] == ["2026-08-19", "2026-08-20", "2026-08-21"]
    # Byte-identical on re-composition: the same inputs must produce the same
    # batch, or idempotency at the DB layer is meaningless.
    assert [r.model_dump_json() for r in first] == [r.model_dump_json() for r in second]


def test_coverage_report_surfaces_an_empty_covariate():
    rows = compose_rows({date(2026, 8, 21): {"brent_price": 70.0}})
    report = coverage_report(rows)
    assert report["brent_price"]["nonNull"] == 1
    assert report["india_vix"]["nonNull"] == 0        # must not read as ingested
    assert report["inr_twi"]["fidelity"] == "substitute"
    assert report["brent_price"]["fidelity"] == "exact"


def test_total_deadline_aborts_a_trickling_source(tmp_path):
    """Pins the fix for a real hang.

    `requests`' `timeout` is per-socket-read, so a server that dribbles a few
    bytes at a time resets it forever — a nominal 30 s timeout hung for >15 min
    against a throttling FRED. The fetcher must bound the WHOLE body instead.
    This server sends a header, then one byte per 0.2 s, never finishing.
    """
    import socket
    import threading

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    stop = threading.Event()

    def serve() -> None:
        try:
            conn, _ = srv.accept()
            with conn:
                conn.recv(4096)
                conn.sendall(
                    b"HTTP/1.1 200 OK\r\nContent-Type: text/csv\r\n"
                    b"Content-Length: 100000\r\n\r\n"
                )
                while not stop.is_set():
                    try:
                        conn.sendall(b"x")
                    except OSError:
                        return
                    stop.wait(0.2)
        except OSError:
            return

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    try:
        f = macro_client._Fetcher(tmp_path, attempts=1, timeout=30,
                                  gap_s=0.0, deadline_s=1.0)
        import time as _time
        started = _time.monotonic()
        with pytest.raises(macro_client._Unavailable):
            f.get(f"http://127.0.0.1:{port}/slow.csv", "slow.csv")
        elapsed = _time.monotonic() - started
        # Must be bounded by the deadline, not by the 30 s socket timeout.
        assert elapsed < 15, f"deadline did not bound the read ({elapsed:.1f}s)"
        assert not (tmp_path / "slow.csv").exists(), "a partial body must not cache"
    finally:
        stop.set()
        srv.close()
        t.join(timeout=3)


def test_dead_host_breaker_short_circuits_siblings(tmp_path):
    """A sustained block must cost one series' retries, not every series'.

    FRED blocked this IP for 25+ minutes on 2026-10-12; without the breaker the
    four covariates each burned `attempts x deadline` to re-prove it, turning a
    daily job into a 20-minute no-op.
    """
    import time as _time

    # Port 1 on loopback refuses instantly, so this measures breaker logic
    # rather than network latency.
    f = macro_client._Fetcher(tmp_path, attempts=3, timeout=2,
                              gap_s=0.5, deadline_s=2.0)
    with pytest.raises(macro_client._Unavailable):
        f.get("http://127.0.0.1:1/a.csv", "a.csv")
    assert "127.0.0.1:1" in f._dead_hosts

    started = _time.monotonic()
    with pytest.raises(macro_client._Unavailable) as caught:
        f.get("http://127.0.0.1:1/b.csv", "b.csv")
    assert _time.monotonic() - started < 0.4, "sibling must fail without retrying"
    # The sibling's provenance must say it was never attempted, not repeat the
    # other URL's failure as if it were its own.
    assert "not attempted" in str(caught.value.cause)
    assert "b.csv" in str(caught.value.url)

    # A different host is unaffected by another host's breaker.
    assert "127.0.0.2:1" not in f._dead_hosts


def test_every_series_declares_full_provenance():
    for s in macro_client._SERIES:
        assert s.units and s.licence and s.note
        assert s.fidelity in {"exact", "substitute"}
        assert s.period in {"day", "month", "quarter"}
        assert s.publication_lag_days >= 0, f"{s.field}: a negative lag leaks"


# --- flow / E14 -----------------------------------------------------------


def test_fii_dii_keeps_the_published_net_exactly():
    p = flow_client.parse_fii_dii(json.loads(NSE_FII_DII))
    assert p.date == date(2026, 10, 12)
    # The PUBLISHED values, bit-for-bit — not buy − sell, which introduces
    # float noise that E14's numeric columns would then persist.
    assert p.fii_net == -1708.48
    assert p.dii_net == 3045.02
    assert p.net_reconciliation() == (), "published nets agree with buy-sell here"
    # Gross is two-sided participation, which is what FR45 needs; netting would
    # understate it.
    assert p.gross == pytest.approx(12583.21 + 14291.69 + 15506.73 + 12461.71)


def test_fii_dii_surfaces_a_net_that_disagrees_with_buy_minus_sell():
    payload = json.loads(NSE_FII_DII)
    payload[1]["netValue"] = "-1700.00"          # 8.48 cr off
    p = flow_client.parse_fii_dii(payload)
    assert p.fii_net == -1700.00, "published value is kept, not overridden"
    recon = p.net_reconciliation()
    assert len(recon) == 1 and recon[0][0] == "fii"

    row, warnings = flow_client.to_entity(p, turnover_crore=400000.0)
    assert row.fii_net == -1700.00
    assert any("source fields disagree" in w.message for w in warnings)


def test_fii_dii_tolerates_source_rounding_in_the_net():
    payload = json.loads(NSE_FII_DII)
    payload[1]["netValue"] = "-1708.47"          # 1 paisa — rounding
    assert flow_client.parse_fii_dii(payload).net_reconciliation() == ()


def test_fii_dii_requires_the_published_net_field():
    payload = json.loads(NSE_FII_DII)
    del payload[1]["netValue"]
    with pytest.raises(ValueError, match="not published"):
        flow_client.parse_fii_dii(payload)


def test_fii_dii_rejects_partial_publication():
    only_dii = json.loads(NSE_FII_DII)[:1]
    with pytest.raises(ValueError, match="incomplete"):
        flow_client.parse_fii_dii(only_dii)


def test_fii_dii_rejects_mixed_dates():
    mixed = json.loads(NSE_FII_DII)
    mixed[1]["date"] = "11-Oct-2026"
    with pytest.raises(ValueError, match="mixes dates"):
        flow_client.parse_fii_dii(mixed)


def test_fii_dii_rejects_unpublished_values_rather_than_zeroing_them():
    blank = json.loads(NSE_FII_DII)
    blank[0]["buyValue"] = "-"
    with pytest.raises(ValueError, match="not published"):
        flow_client.parse_fii_dii(blank)


def test_fii_dii_accepts_the_legacy_fii_category_label():
    legacy = json.loads(NSE_FII_DII)
    legacy[1]["category"] = "FII"
    assert flow_client.parse_fii_dii(legacy).date == date(2026, 10, 12)


def test_index_turnover_found_by_column_name():
    assert flow_client.parse_index_turnover(NSE_IND_CLOSE_ALL) == \
        pytest.approx(69762.13)
    assert flow_client.parse_index_turnover(NSE_IND_CLOSE_ALL, "Nifty 50") == \
        pytest.approx(45000.25)


def test_index_turnover_placeholder_is_none():
    # India VIX has "-" in its turnover column — a real NSE placeholder.
    assert flow_client.parse_index_turnover(NSE_IND_CLOSE_ALL, "India VIX") is None


def test_residual_share_is_reported_unclipped_with_a_warning():
    p = flow_client.parse_fii_dii(json.loads(NSE_FII_DII))
    # Denominator far too small → share goes negative. The scope mismatch must
    # surface, not be hidden behind a clamp.
    row, warnings = flow_client.to_entity(p, turnover_crore=1000.0)
    assert row.residual_flow_share < 0
    assert any("outside [0,1]" in w.message for w in warnings)
    assert all(w.code == "ESTIMATOR_FALLBACK" for w in warnings)


def test_residual_share_always_carries_the_scope_caveat():
    p = flow_client.parse_fii_dii(json.loads(NSE_FII_DII))
    row, warnings = flow_client.to_entity(p, turnover_crore=400000.0)
    assert 0.0 <= row.residual_flow_share <= 1.0
    assert warnings, "a plausible value still needs the proxy caveat"


def test_residual_share_rejects_zero_turnover():
    with pytest.raises(ValueError, match="non-positive turnover"):
        flow_client.residual_flow_share(100.0, 0.0)


def test_crore_conversion_constant_is_correct():
    # A wrong constant moves residual_flow_share by 10^7 and is invisible in
    # the output, so it is pinned.
    assert flow_client.RUPEES_PER_CRORE == 1e7


# --- tariff / E5 ----------------------------------------------------------

_VALID_HEADER = "# scale: 0-1 normalised\nevent_id,tau_k,delta_r_k,severity_score,sectors_affected,source_ref\n"


def _registry(tmp_path: Path, body: str, header: str = _VALID_HEADER) -> Path:
    p = tmp_path / "reg.csv"
    p.write_text(header + body, encoding="utf-8")
    return p


def test_shipped_registry_is_empty_and_says_why():
    events, issues, meta = tariff_events.load_registry()
    assert events == (), "the shipped registry must not contain invented dates"
    assert issues == ()
    assert meta.scale is None, "the severity scale is the curator's to declare"


def test_valid_row_loads():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t_2025_baseline,2025-07-15,25.0,0.5,steel|aluminium,"
                               "https://ustr.gov/notice\n")
        events, issues, meta = tariff_events.load_registry(p)
    assert issues == ()
    assert len(events) == 1
    e = events[0]
    assert e.tau_k == "2025-07-15"
    assert e.sectors_affected == ("steel", "aluminium")
    assert meta.scale == "0-1 normalised"


def test_uncited_row_is_rejected():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2025-07-15,25.0,0.5,steel,\n")
        events, issues, _ = tariff_events.load_registry(p)
    assert events == ()
    assert any(i.field == "source_ref" for i in issues)


def test_placeholder_citation_is_rejected():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2025-07-15,25.0,0.5,steel,TBD\n")
        _, issues, _ = tariff_events.load_registry(p)
    assert any(i.field == "source_ref" for i in issues)


def test_news_style_citation_without_scheme_is_rejected():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2025-07-15,25.0,0.5,steel,some newspaper\n")
        _, issues, _ = tariff_events.load_registry(p)
    assert any("not a citation" in i.detail for i in issues)


def test_undated_row_is_rejected_not_guessed():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,,25.0,0.5,steel,https://ustr.gov/x\n")
        events, issues, _ = tariff_events.load_registry(p)
    assert events == ()
    assert any(i.field == "tau_k" for i in issues)


def test_future_dated_event_is_rejected():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2027-01-01,25.0,0.5,steel,https://ustr.gov/x\n")
        _, issues, _ = tariff_events.load_registry(p, today=date(2026, 10, 12))
    assert any("future" in i.detail for i in issues)


def test_unknown_sector_is_rejected():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2025-07-15,25.0,0.5,semiconductors,"
                               "https://ustr.gov/x\n")
        _, issues, _ = tariff_events.load_registry(p)
    assert any(i.field == "sectors_affected" for i in issues)


def test_sector_spelling_variants_normalise():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2025-07-15,25.0,0.5,Auto Components|auto-components,"
                               "https://ustr.gov/x\n")
        events, issues, _ = tariff_events.load_registry(p)
    assert issues == ()
    assert events[0].sectors_affected == ("auto_components", "auto_components")


def test_economy_wide_event_may_have_no_sectors():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2025-07-15,25.0,0.5,,https://ustr.gov/x\n")
        events, issues, _ = tariff_events.load_registry(p)
    assert issues == ()
    assert events[0].sectors_affected == ()


def test_missing_severity_scale_declaration_blocks_the_row():
    import tempfile
    header = "event_id,tau_k,delta_r_k,severity_score,sectors_affected,source_ref\n"
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2025-07-15,25.0,0.5,steel,https://ustr.gov/x\n",
                      header=header)
        events, issues, _ = tariff_events.load_registry(p)
    assert events == ()
    assert any("scale" in i.detail for i in issues)


def test_duplicate_event_id_is_rejected():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d),
                      "t1,2025-07-15,25.0,0.5,steel,https://ustr.gov/a\n"
                      "t1,2025-08-01,25.0,0.5,steel,https://ustr.gov/b\n")
        events, issues, _ = tariff_events.load_registry(p)
    assert len(events) == 1
    assert any("duplicate" in i.detail for i in issues)


def test_negative_severity_is_rejected():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2025-07-15,25.0,-0.5,steel,https://ustr.gov/x\n")
        _, issues, _ = tariff_events.load_registry(p)
    assert any(i.field == "severity_score" for i in issues)


def test_tariff_cut_may_be_negative_delta():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d), "t1,2026-02-01,-32.0,0.6,,https://ustr.gov/x\n")
        events, issues, _ = tariff_events.load_registry(p, today=date(2026, 10, 12))
    assert issues == ()
    assert events[0].delta_r_k == pytest.approx(-32.0)


def test_missing_required_column_raises():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = (Path(d) / "r.csv")
        p.write_text("# scale: x\nevent_id,tau_k\nt1,2025-07-15\n", encoding="utf-8")
        with pytest.raises(ValueError, match="missing columns"):
            tariff_events.load_registry(p)


def test_events_are_returned_in_chronological_order():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d),
                      "t_b,2026-02-01,-32.0,0.6,,https://ustr.gov/b\n"
                      "t_a,2025-07-15,25.0,0.5,steel,https://ustr.gov/a\n")
        events, issues, _ = tariff_events.load_registry(p, today=date(2026, 10, 12))
    assert issues == ()
    assert [e.event_id for e in events] == ["t_a", "t_b"]


def test_empty_registry_ingest_reports_empty_not_success():
    out = asyncio.run(tariff_events.ingest(dry_run=True))
    assert out["status"] == "empty"
    assert out["written"] is False
    assert "registry_empty" in out["reason"]


def test_invalid_rows_block_the_write_by_default():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = _registry(Path(d),
                      "t_ok,2025-07-15,25.0,0.5,steel,https://ustr.gov/a\n"
                      "t_bad,2025-08-01,25.0,0.5,steel,\n")
        out = asyncio.run(tariff_events.ingest(registry=p, dry_run=True))
    assert out["status"] == "error"
    assert out["written"] is False
    assert "partial event table" in out["reason"]


# --- DB-backed ------------------------------------------------------------
# Mirrors CT-1's contract for E4/E5/E14: a re-run reports inserted == 0.

asyncpg = pytest.importorskip("asyncpg")

from seraph.shared_types import FlowAggregate, IngestBatch, MacroRow  # noqa: E402
from seraph.store import StoreWriter, apply_schema, resolve_dsn      # noqa: E402


def _db_unavailable() -> str | None:
    """The reason the database cannot be used, or None if it can.

    Returns the real error rather than one fixed message: an authentication
    failure, a wrong port, a missing database and a stopped container are four
    different problems, and reporting all of them as "not reachable" sent a
    reader back to `docker compose up -d` when the password was what was wrong.
    """
    async def probe() -> None:
        conn = await asyncpg.connect(resolve_dsn(), timeout=3)
        await conn.close()

    try:
        asyncio.run(probe())
        return None
    except Exception as exc:                       # noqa: BLE001 - reported
        return (f"database unusable: {type(exc).__name__}: {exc}. "
                f"DB tests need a disposable seraph_test_* database with "
                f"SERAPH_TEST_DB_DSN and SERAPH_TEST_TOKEN (see "
                f"tests/conftest.py); `docker compose up -d` alone is not "
                f"enough")


_SKIP_REASON = _db_unavailable()
db_only = pytest.mark.skipif(_SKIP_REASON is not None,
                             reason=_SKIP_REASON or "")

_E4_DATES = ("1901-01-02", "1901-01-03")
_E14_DATE = "1901-01-02"
_E5_IDS = ("c2test_a", "c2test_b")

#: `ingestion_watermarks` is keyed on (source, entity) ALONE, so a test writing
#: under a production source label shares that production row. Two ways that
#: bites, both observed while writing this file:
#:   - deleting the row in cleanup destroys real ingestion progress (it wiped
#:     the live nse-fii-dii/E14 watermark);
#:   - leaving it behind advertises progress that never happened (a
#:     tariff-manual/E5 watermark sat next to an empty tariff_events).
#: So each DB test writes under a source label no production path pairs with
#: that entity. The labels are deliberately "wrong" semantically — the writer
#: does not validate source against entity, and that is the point: these rows
#: are unmistakably test rows.
_TEST_SOURCES = {"E4": "rbi", "E5": "bhavcopy", "E14": "eod2"}


async def _clean(writer: StoreWriter) -> None:
    # Test-only reach-in, as CT-1 does. Dates are in 1901 so they cannot
    # collide with real corpus rows. asyncpg binds date columns from
    # datetime.date, not from ISO strings.
    async with writer._pool.acquire() as conn:
        await conn.execute("DELETE FROM macro_covariates WHERE date = ANY($1)",
                           [date.fromisoformat(d) for d in _E4_DATES])
        await conn.execute("DELETE FROM flow_aggregates WHERE date = $1",
                           date.fromisoformat(_E14_DATE))
        await conn.execute("DELETE FROM tariff_events WHERE event_id = ANY($1)",
                           list(_E5_IDS))
        # Only the reserved test (source, entity) pairs are ever removed.
        for entity, source in _TEST_SOURCES.items():
            await conn.execute(
                "DELETE FROM ingestion_watermarks WHERE source = $1 AND entity = $2",
                source, entity,
            )


@db_only
def test_e4_macro_write_is_idempotent():
    rows = compose_rows({
        date(1901, 1, 2): {"brent_price": 66.25, "india_vix": None},
        date(1901, 1, 3): {"brent_price": 68.60, "india_vix": 12.5},
    })
    batch = IngestBatch(
        run_id="c2test-e4", source=_TEST_SOURCES["E4"], entity="E4", rows=rows,
        watermark="1901-01-03T18:00:00+05:30",
        source_schema_version="macro-asof-v1",
    )

    async def run() -> None:
        await apply_schema()
        writer = await StoreWriter.connect()
        try:
            await _clean(writer)
            first = await writer.write_batch_bulk(batch)
            assert first.status == "ok", getattr(first, "error", None)
            assert first.value.inserted == 2
            second = await writer.write_batch_bulk(batch)
            assert second.status == "ok"
            assert second.value.inserted == 0, "macro re-run must not duplicate"
            assert second.value.updated == 2
            wm = await writer.get_watermark(_TEST_SOURCES["E4"], "E4")
            assert wm.status == "ok" and wm.value == "1901-01-03T18:00:00+05:30", (
                "watermark must advance exactly once for identical batches"
            )
        finally:
            await _clean(writer)
            await writer.close()

    asyncio.run(run())


@db_only
def test_e4_nulls_and_vix_flag_round_trip_through_the_store():
    """Missingness must survive persistence — a NULL that comes back as 0.0
    would be indistinguishable from a real observation."""
    rows = compose_rows({
        date(1901, 1, 2): {"brent_price": 66.25, "india_vix": None,
                           "rbi_repo_rate": None},
        date(1901, 1, 3): {"brent_price": None, "india_vix": 12.5},
    })
    batch = IngestBatch(
        run_id="c2test-e4-nulls", source=_TEST_SOURCES["E4"], entity="E4", rows=rows,
        watermark="1901-01-03T18:00:00+05:30",
        source_schema_version="macro-asof-v1",
    )

    async def run() -> None:
        from seraph.store import StoreReader

        await apply_schema()
        writer = await StoreWriter.connect()
        reader = await StoreReader.connect()
        try:
            await _clean(writer)
            assert (await writer.write_batch_bulk(batch)).status == "ok"
            res = await reader.macro_covariates(from_date="1901-01-01",
                                                to_date="1901-01-31")
            assert res.status == "ok"
            got = {r.date: r for r in res.value}
            assert got["1901-01-02"].india_vix is None
            assert got["1901-01-02"].vix_available is False
            assert got["1901-01-02"].rbi_repo_rate is None
            assert got["1901-01-02"].brent_price == pytest.approx(66.25)
            assert got["1901-01-03"].brent_price is None
            assert got["1901-01-03"].vix_available is True
        finally:
            await _clean(writer)
            await reader.close()
            await writer.close()

    asyncio.run(run())


@db_only
def test_e4_refresh_preserves_c4_fields_without_read_merge():
    """C1 ingestion updates cannot replace concurrently owned C4 columns."""
    async def run() -> None:
        from seraph.store import StoreReader

        await apply_schema()
        writer = await StoreWriter.connect()
        reader = await StoreReader.connect()
        try:
            await _clean(writer)
            # C4 has written g_t for this date.
            seeded = MacroRow(date="1901-01-02", brent_price=66.25, g_t=1.25,
                              g_t_sector_weighted=0.8)
            assert (await writer.write_batch(IngestBatch(
                run_id="c2test-seed", source=_TEST_SOURCES["E4"], entity="E4", rows=(seeded,),
                watermark="1901-01-02T18:00:00+05:30",
                source_schema_version="macro-asof-v1"))).status == "ok"

            naive = compose_rows({date(1901, 1, 2): {"brent_price": 70.0}})
            assert (await writer.write_batch(IngestBatch(
                run_id="c2test-naive", source=_TEST_SOURCES["E4"], entity="E4", rows=naive,
                watermark="1901-01-02T18:00:00+05:30",
                source_schema_version="macro-asof-v1"))).status == "ok"
            res = await reader.macro_covariates(from_date="1901-01-01",
                                                to_date="1901-01-31")
            assert res.status == "ok"
            assert res.value[0].g_t == pytest.approx(1.25)
            assert res.value[0].g_t_sector_weighted == pytest.approx(0.8)

            # The preserve path keeps it.
            preserved = compose_rows({date(1901, 1, 2): {"brent_price": 70.0}},
                                     preserve={"1901-01-02": (1.25, 0.8)})
            assert (await writer.write_batch(IngestBatch(
                run_id="c2test-preserve", source=_TEST_SOURCES["E4"], entity="E4",
                rows=preserved, watermark="1901-01-02T18:00:00+05:30",
                source_schema_version="macro-asof-v1"))).status == "ok"
            res2 = await reader.macro_covariates(from_date="1901-01-01",
                                                 to_date="1901-01-31")
            assert res2.status == "ok"
            assert res2.value[0].g_t == pytest.approx(1.25)
            assert res2.value[0].g_t_sector_weighted == pytest.approx(0.8)
        finally:
            await _clean(writer)
            await reader.close()
            await writer.close()

    asyncio.run(run())


@db_only
def test_e14_flow_write_is_idempotent():
    row = FlowAggregate(date=_E14_DATE, fii_net=-1708.48, dii_net=3045.02,
                        total_turnover=400000.0, residual_flow_share=0.8679)
    batch = IngestBatch(
        run_id="c2test-e14", source=_TEST_SOURCES["E14"], entity="E14", rows=(row,),
        watermark=f"{_E14_DATE}T20:00:00+05:30",
        source_schema_version="nse-fiidii-react-v1+turnover-nse-index",
    )

    async def run() -> None:
        await apply_schema()
        writer = await StoreWriter.connect()
        try:
            await _clean(writer)
            first = await writer.write_batch(batch)
            assert first.status == "ok", getattr(first, "error", None)
            assert first.value.inserted == 1
            second = await writer.write_batch(batch)
            assert second.status == "ok"
            assert second.value.inserted == 0, "daily flow re-run must be a no-op"
            assert second.value.updated == 1
        finally:
            await _clean(writer)
            await writer.close()

    asyncio.run(run())


@db_only
def test_e5_tariff_write_is_idempotent_and_sectors_round_trip():
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        reg = _registry(
            Path(d),
            f"{_E5_IDS[0]},2025-07-15,25.0,0.5,steel|aluminium,https://ustr.gov/a\n"
            f"{_E5_IDS[1]},2026-02-01,-32.0,0.6,,https://ustr.gov/b\n",
        )
        events, issues, _ = tariff_events.load_registry(reg, today=date(2026, 10, 12))
        assert issues == ()

    batch = IngestBatch(
        run_id="c2test-e5", source=_TEST_SOURCES["E5"], entity="E5", rows=events,
        watermark="2026-02-01T18:00:00+05:30",
        source_schema_version="tariff-curated-csv-v1",
    )

    async def run() -> None:
        await apply_schema()
        writer = await StoreWriter.connect()
        try:
            await _clean(writer)
            first = await writer.write_batch(batch)
            assert first.status == "ok", getattr(first, "error", None)
            assert first.value.inserted == 2
            second = await writer.write_batch(batch)
            assert second.status == "ok"
            assert second.value.inserted == 0, "tariff re-run must not duplicate"
            async with writer._pool.acquire() as conn:
                got = await conn.fetchrow(
                    "SELECT sectors_affected, delta_r_k FROM tariff_events "
                    "WHERE event_id = $1", _E5_IDS[0]
                )
            assert list(got["sectors_affected"]) == ["steel", "aluminium"]
            assert got["delta_r_k"] == pytest.approx(25.0)
        finally:
            await _clean(writer)
            await writer.close()

    asyncio.run(run())
