"""PORT01 / PORT02 — holdings import, identifier handling, and position history.

The two rules these tests exist to hold:

* an import tells you what it rejected and **why**, preserves the original
  bytes, and merges a duplicated instrument instead of dropping one of them;
* a past-date view uses the positions that actually existed then, or says it
  cannot — it never hands back today's holdings under yesterday's date.
"""
from __future__ import annotations

import pytest

from seraph.decision_support.portfolio import portfolio_overlay
from seraph.decision_support.workspace import (
    DEFAULT_ASSET_SCOPE,
    WorkspaceStore,
    parse_holdings,
)
from seraph.identity import AuthorizationError, IdentityRegistry, Scope

CSV = ("symbol,qty,price,sector\n"
       "RELIANCE,10,2800,energy\n"
       "TCS,5,3600,it\n")

JSON = ('[{"symbol": "RELIANCE", "quantity": 10, "value": 28000, "sector": "energy"},'
        ' {"ticker": "TCS", "units": 5, "market_value": 18000}]')


@pytest.fixture
def owner(tmp_path):
    registry = IdentityRegistry(tmp_path / "identity.sqlite")
    workspace = WorkspaceStore(tmp_path / "workspace.sqlite", registry)
    registry.add_organisation("org_home", "Household", "retail_household")
    user = registry.upsert_user(provider_subject="s1", issuer="https://idp.test")
    registry.add_membership(user.user_id, "org_home")
    registry.grant(user.user_id, "org_home", "retail", granted_by="admin")
    principal = registry.resolve(registry.open_session(user.user_id).session_id)
    return registry, workspace, principal


# ------------------------------------------------------------ parsing


def test_csv_and_json_reach_the_same_positions():
    from_csv = parse_holdings(CSV, source_name="a.csv")
    from_json = parse_holdings(JSON, source_name="a.json")
    assert {r.symbol: r.value for r in from_csv.accepted} == \
           {"RELIANCE": 28000.0, "TCS": 18000.0}
    assert {r.symbol: r.value for r in from_json.accepted} == \
           {"RELIANCE": 28000.0, "TCS": 18000.0}


def test_column_aliases_are_resolved():
    preview = parse_holdings("ticker,units,ltp\nINFY,3,1500\n", source_name="x.csv")
    assert preview.accepted[0].symbol == "INFY"
    assert preview.accepted[0].quantity == 3 and preview.accepted[0].value == 4500


def test_value_is_derived_from_quantity_and_price_when_absent():
    row = parse_holdings("symbol,qty,price\nITC,100,450\n",
                         source_name="x.csv").accepted[0]
    assert row.value == 45000


def test_an_isin_only_row_is_keyed_by_its_isin():
    row = parse_holdings("isin,quantity,value\nINE002A01018,1,2800\n",
                         source_name="x.csv").accepted[0]
    assert row.symbol == "INE002A01018" and row.isin == "INE002A01018"


def test_a_duplicated_instrument_is_merged_not_dropped():
    preview = parse_holdings(
        "symbol,qty,price\nRELIANCE,10,2800\nRELIANCE,5,2800\n", source_name="x.csv")
    assert len(preview.accepted) == 1
    assert preview.accepted[0].quantity == 15 and preview.accepted[0].value == 42000
    assert preview.duplicates_merged == ["RELIANCE"]


def test_every_rejection_states_a_reason_the_user_can_act_on():
    preview = parse_holdings(
        "symbol,qty,price\n"
        ",5,100\n"                 # no identifier
        "ABC,notanumber,100\n"     # unparseable
        "DEF,,\n"                  # neither quantity nor value
        "GHI,-5,100\n",            # short position
        source_name="x.csv")
    reasons = [r.reason for r in preview.rejected]
    assert len(reasons) == 4
    assert any("no symbol" in r for r in reasons)
    assert any("not a number" in r for r in reasons)
    assert any("neither a quantity nor a value" in r for r in reasons)
    assert any("long_only" in r for r in reasons)


def test_the_long_only_scope_is_enforced_not_merely_documented():
    preview = parse_holdings("symbol,quantity,value\nX,-1,100\nY,1,-100\n",
                             source_name="x.csv")
    assert preview.accepted == [] and len(preview.rejected) == 2
    assert preview.describe()["asset_scope"] == DEFAULT_ASSET_SCOPE


def test_a_foreign_currency_row_is_rejected_with_the_reason():
    preview = parse_holdings("symbol,value,currency\nAAPL,1000,USD\n",
                             source_name="x.csv", base_currency="INR")
    assert "FX convention" in preview.rejected[0].reason


def test_an_unvalued_holding_warns_rather_than_counting_as_zero_worth():
    preview = parse_holdings("symbol,quantity\nXYZ,10\n", source_name="x.csv")
    assert preview.accepted[0].value is None
    assert any("not as zero-worth" in w for w in preview.warnings)


def test_malformed_files_are_rejected_whole():
    assert "not valid JSON" in parse_holdings("{oops", source_name="x.json").rejected[0].reason
    assert parse_holdings("", source_name="x.csv").rejected[0].reason == "file has no header row"


# ---------------------------------------------------- import lifecycle


def test_preview_writes_nothing(owner):
    _, workspace, principal = owner
    book = workspace.create_portfolio(principal, name="Main")
    workspace.preview_import(principal, book["portfolio_id"], CSV, source_name="b.csv")
    assert workspace.snapshots(principal, book["portfolio_id"]) == []
    assert workspace.current_holdings(principal, book["portfolio_id"])["basis"] == \
        "unavailable"


def test_active_saved_book_resolves_both_consumers_and_role_scope(owner):
    from seraph.dashboard.workspace_service import active_portfolio
    registry, workspace, principal = owner
    book = workspace.create_portfolio(principal, name='Active')
    preview = workspace.preview_import(principal, book['portfolio_id'], CSV,
                                       source_name='book.csv')
    workspace.commit_import(principal, book['portfolio_id'], preview, CSV,
                            effective_at='2024-06-30T15:30:00+05:30')
    selection = dict(portfolio_id=book['portfolio_id'], role='retail',
                     basis='historical')
    bundle = dict(registry=registry, workspace=workspace)
    result = active_portfolio(selection, 'retail',
        at='2024-07-01T15:30:00+05:30', bundle=bundle, principal=principal)
    assert result['overlay']['totalValue'] == 46000
    assert {r['symbol'] for r in result['holdings']} == {'RELIANCE', 'TCS'}
    assert result['context']['basis'] == 'historical'
    assert active_portfolio(selection, 'retail', at='2020-01-01T15:30:00+05:30',
        bundle=bundle, principal=principal)['holdings'] == []
    with pytest.raises(ValueError, match='another role'):
        active_portfolio(selection, 'institutional',
                         at='2024-07-01T15:30:00+05:30',
                         bundle=bundle, principal=principal)


def test_commit_saves_a_snapshot_and_preserves_the_original_bytes(owner):
    _, workspace, principal = owner
    book = workspace.create_portfolio(principal, name="Main")
    preview = workspace.preview_import(principal, book["portfolio_id"], CSV,
                                       source_name="b.csv")
    saved = workspace.commit_import(principal, book["portfolio_id"], preview, CSV,
                                    effective_at="2024-06-30T15:30:00+05:30")
    assert saved["rows"] == 2 and saved["total_value"] == 46000
    assert workspace.original_import(principal, preview.import_id).decode() == CSV


def test_a_file_that_changed_between_preview_and_commit_is_refused(owner):
    _, workspace, principal = owner
    book = workspace.create_portfolio(principal, name="Main")
    preview = workspace.preview_import(principal, book["portfolio_id"], CSV,
                                       source_name="b.csv")
    with pytest.raises(ValueError, match="changed between preview and commit"):
        workspace.commit_import(principal, book["portfolio_id"], preview,
                                CSV + "INFY,1,1500,it\n",
                                effective_at="2024-06-30T15:30:00+05:30")


def test_an_import_with_nothing_accepted_is_refused(owner):
    _, workspace, principal = owner
    book = workspace.create_portfolio(principal, name="Main")
    bad = "symbol,quantity\n,-1\n"
    preview = workspace.preview_import(principal, book["portfolio_id"], bad,
                                       source_name="b.csv")
    with pytest.raises(ValueError, match="no accepted row"):
        workspace.commit_import(principal, book["portfolio_id"], preview, bad,
                                effective_at="2024-06-30T15:30:00+05:30")


def test_snapshots_are_append_only(owner):
    _, workspace, principal = owner
    book = workspace.create_portfolio(principal, name="Main")
    preview = workspace.preview_import(principal, book["portfolio_id"], CSV,
                                       source_name="b.csv")
    workspace.commit_import(principal, book["portfolio_id"], preview, CSV,
                            effective_at="2024-06-30T15:30:00+05:30")
    again = workspace.preview_import(principal, book["portfolio_id"], CSV,
                                     source_name="b.csv")
    with pytest.raises(ValueError, match="append-only"):
        workspace.commit_import(principal, book["portfolio_id"], again, CSV,
                                effective_at="2024-06-30T15:30:00+05:30")


# -------------------------------------------------- point-in-time view


@pytest.fixture
def with_history(owner):
    registry, workspace, principal = owner
    book = workspace.create_portfolio(principal, name="Main")
    for effective, body in [
        ("2024-03-31T15:30:00+05:30", "symbol,qty,price\nRELIANCE,10,2800\n"),
        ("2024-09-30T15:30:00+05:30", "symbol,qty,price\nRELIANCE,10,2800\nTCS,5,3600\n"),
    ]:
        preview = workspace.preview_import(principal, book["portfolio_id"], body,
                                           source_name="b.csv")
        workspace.commit_import(principal, book["portfolio_id"], preview, body,
                                effective_at=effective)
    return registry, workspace, principal, book["portfolio_id"]


def test_a_past_date_uses_the_positions_that_existed_then(with_history):
    _, workspace, principal, book = with_history
    june = workspace.holdings_as_of(principal, book, "2024-06-30T15:30:00+05:30")
    assert june["basis"] == "historical"
    assert june["effective_at"] == "2024-03-31T15:30:00+05:30"
    assert [h["symbol"] for h in june["holdings"]] == ["RELIANCE"]
    assert june["age_days"] == 91


def test_a_later_date_picks_up_the_later_snapshot(with_history):
    _, workspace, principal, book = with_history
    december = workspace.holdings_as_of(principal, book, "2024-12-31T15:30:00+05:30")
    assert [h["symbol"] for h in december["holdings"]] == ["RELIANCE", "TCS"]
    assert december["effective_at"] == "2024-09-30T15:30:00+05:30"


def test_before_any_snapshot_it_says_unavailable_instead_of_substituting(with_history):
    _, workspace, principal, book = with_history
    early = workspace.holdings_as_of(principal, book, "2020-01-01T15:30:00+05:30")
    assert early["basis"] == "unavailable" and early["holdings"] == []
    assert "NOT substituted" in early["note"]
    assert early["earliest_snapshot"] == "2024-03-31T15:30:00+05:30"


def test_the_current_view_is_labelled_current_not_historical(with_history):
    _, workspace, principal, book = with_history
    now = workspace.current_holdings(principal, book)
    assert now["basis"] == "current"
    assert now["effective_at"] == "2024-09-30T15:30:00+05:30"


def test_saved_holdings_feed_the_existing_coverage_arithmetic(with_history):
    """The new store does not replace C11's pure function; it supplies it."""
    _, workspace, principal, book = with_history
    holdings = workspace.current_holdings(principal, book)["holdings"]
    result = portfolio_overlay(
        [dict(symbol=h["symbol"], value=h["value"], quantity=h["quantity"] or 0,
              sector=h["sector"]) for h in holdings], {})
    assert result.status == "ok"
    # No measured sector flags exist, so everything is uncovered. That is the
    # correct answer, not a defect.
    assert result.value["uncoveredPct"] == 100 and result.value["exposedPct"] == 0


# ------------------------------------------------------- authorization


def test_another_organisation_cannot_import_into_or_read_a_book(with_history):
    registry, workspace, _, book = with_history
    registry.add_organisation("org_other", "Other", "institution")
    other = registry.upsert_user(provider_subject="s-x", issuer="https://idp.test")
    registry.add_membership(other.user_id, "org_other")
    registry.grant(other.user_id, "org_other", "institutional", granted_by="admin")
    intruder = registry.resolve(registry.open_session(other.user_id).session_id)
    for call in (lambda: workspace.portfolio(intruder, book),
                 lambda: workspace.snapshots(intruder, book),
                 lambda: workspace.current_holdings(intruder, book),
                 lambda: workspace.holdings_as_of(intruder, book,
                                                  "2024-12-31T15:30:00+05:30"),
                 lambda: workspace.preview_import(intruder, book, CSV,
                                                  source_name="x.csv")):
        with pytest.raises(AuthorizationError):
            call()
