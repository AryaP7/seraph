# Regression tests — X01, X02, X02b (one bug class, three places)
"""The ASCII-only identity assumption, and the two places N02 did not reach.

`docs/SERAPH-COMPLETION-AUDIT-VERIFICATION-2026-10-18.md` Part 3. The news
grouping repair (`SYNDICATION_KEY_VERSION = "syn/2"`) fixed one of three
functions that deleted every non-ASCII character before comparing:

* `news/model.syndication_tokens` -- fixed before this work (N02).
* `news/registry._norm`           -- X02, fixed here. The worse of the two:
  it produced FALSE POSITIVES reported as `status='resolved'`.
* `dashboard/globe_payload._slug` -- X01, fixed here. Collapsed every
  non-Latin place name to one geometry id.

Both were latent only because all 264 curated rows were ASCII, so an
ASCII-only fixture could not catch an ASCII-only normaliser. X02b adds
Devanagari aliases to the shipped registry to keep the class visible.
"""
from __future__ import annotations

import pytest

from seraph.dashboard.globe_payload import _slug
from seraph.news.model import syndication_tokens, word_tokens
from seraph.news.registry import Asset, MasterData, Place, _norm, load_master_data

# Written as escapes so the file itself is ASCII-safe on a cp1252 console.
BHARAT = "भारत"                       # भारत
MUMBAI_HI = "मुंबई"              # मुंबई
UTTAR_PRADESH = "उत्तर प्रदेश"
TAMIL_NADU = "तमिलनाडु"
NTPC_PLANT_HI = "एनटीपीसी संयंत्र"


# ------------------------------------------------------------------- X02


class TestX02OneNonLatinNameDoesNotResolveEverything:
    """The reproduced false positive. `"" in needle` is always True, so an
    asset whose normalised name was empty matched every mention."""

    @pytest.fixture
    def registry(self):
        return MasterData(assets=[
            Asset(asset_id="as:hindi", name=NTPC_PLANT_HI,
                  kind="power_plant", place_id="pl:in-up")])

    @pytest.mark.parametrize("mention", [
        "Reliance refinery", "anything at all", "Tata Steel Jamshedpur",
        "a completely unrelated phrase",
    ])
    def test_an_unrelated_mention_does_not_resolve(self, registry, mention):
        assert registry.resolve_asset(mention).status == "unknown"

    def test_the_non_latin_asset_still_resolves_to_itself(self, registry):
        resolution = registry.resolve_asset(NTPC_PLANT_HI)
        assert resolution.status == "resolved"
        assert resolution.entity_id == "as:hindi"

    def test_a_blank_registry_name_is_skipped_not_matched(self):
        """`_norm` no longer empties a non-Latin name, but a punctuation-only
        row still normalises to nothing -- and a containment rule that can
        match on no evidence must refuse."""
        registry = MasterData(assets=[
            Asset(asset_id="as:blank", name="---", kind="port",
                  place_id="pl:x"),
            Asset(asset_id="as:real", name="Paradip Port", kind="port",
                  place_id="pl:y")])
        assert registry.resolve_asset("Some other place").status == "unknown"
        assert registry.resolve_asset("Paradip Port").entity_id == "as:real"

    def test_an_empty_mention_resolves_to_nothing(self):
        registry = MasterData(assets=[
            Asset(asset_id="as:real", name="Paradip Port", kind="port",
                  place_id="pl:y")])
        for mention in ("", "   ", "---"):
            assert registry.resolve_asset(mention).status == "unknown"

    def test_genuine_ambiguity_still_abstains(self):
        registry = MasterData(assets=[
            Asset(asset_id="as:a", name="Paradip Port", kind="port", place_id="p"),
            Asset(asset_id="as:b", name="Paradip Port", kind="port", place_id="q")])
        assert registry.resolve_asset("Paradip Port").status == "ambiguous"


class TestX02NormalisationIsScriptAgnostic:
    def test_a_devanagari_name_does_not_normalise_to_nothing(self):
        assert _norm(NTPC_PLANT_HI) != ""

    def test_two_different_devanagari_names_differ(self):
        assert _norm(UTTAR_PRADESH) != _norm(TAMIL_NADU)

    @pytest.mark.parametrize("name,expected", [
        ("NTPC Ltd", "ntpc"),
        ("NTPC", "ntpc"),
        ("Reliance Industries Limited", "reliance industries"),
        ("Tata Steel", "tata steel"),
    ])
    def test_existing_ascii_normalisation_is_unchanged(self, name, expected):
        assert _norm(name) == expected

    @pytest.mark.parametrize("short", ["L&T", "BP", "3M"])
    def test_a_short_name_survives(self, short):
        """`syndication_tokens` drops words under three characters, which is
        right for headlines and would erase these real issuers. `_norm` must
        use the unfiltered primitive."""
        assert _norm(short) != "", f"{short} normalised to nothing"

    def test_norm_does_not_use_the_headline_filter(self):
        assert syndication_tokens("L&T") == ()        # correct for a headline
        assert _norm("L&T") != ""                     # wrong for a name


class TestWordTokensIsTheSharedPrimitive:
    def test_it_keeps_every_word_unfiltered(self):
        assert word_tokens("The BP of Mumbai") == ("the", "bp", "of", "mumbai")

    def test_syndication_tokens_filters_on_top_of_it(self):
        assert syndication_tokens("The BP of Mumbai") == ("mumbai",)

    def test_it_tokenises_devanagari_including_combining_marks(self):
        tokens = word_tokens(UTTAR_PRADESH)
        assert len(tokens) == 2
        assert "".join(tokens) != ""

    def test_it_is_safe_on_empty_and_none(self):
        assert word_tokens("") == ()
        assert word_tokens(None) == ()


# ------------------------------------------------------------------- X01


class TestX01GlobeSlugsDoNotCollide:
    def test_two_devanagari_state_names_get_distinct_ids(self):
        assert _slug(UTTAR_PRADESH) != _slug(TAMIL_NADU)

    def test_neither_is_empty(self):
        assert _slug(UTTAR_PRADESH) and _slug(TAMIL_NADU)

    def test_an_empty_name_still_yields_an_id(self):
        assert _slug("") != ""

    @pytest.mark.parametrize("name,expected", [
        ("Uttar Pradesh", "uttar-pradesh"),
        ("Tamil Nadu", "tamil-nadu"),
        ("Maharashtra", "maharashtra"),
        ("in_mh_mumbai", "in-mh-mumbai"),
    ])
    def test_existing_ascii_slugs_are_byte_identical(self, name, expected):
        """No stored payload or saved evidence may be invalidated by this."""
        assert _slug(name) == expected

    def test_a_slug_is_stable_across_calls(self):
        assert _slug(UTTAR_PRADESH) == _slug(UTTAR_PRADESH)

    def test_a_mixed_script_name_keeps_its_readable_prefix(self):
        slug = _slug("Mumbai " + MUMBAI_HI)
        assert slug.startswith("mumbai-")
        assert slug != "mumbai"

    def test_the_geometry_id_for_two_states_differs_end_to_end(self):
        """What the renderer actually receives."""
        ids = {f"geo:in-state:{_slug(n)}" for n in (UTTAR_PRADESH, TAMIL_NADU)}
        assert len(ids) == 2, f"both states share one geometry id: {ids}"


# ------------------------------------------------------------------ X02b


class TestX02bTheShippedRegistryExercisesNonLatinNames:
    @pytest.fixture(scope="class")
    def master(self):
        return load_master_data()[0]

    def test_the_curated_registry_now_contains_a_non_latin_alias(self, master):
        non_ascii = [p.place_id for p in master.places.values()
                     if any(ord(c) > 127 for alias in p.aliases for c in alias)]
        assert non_ascii, \
            "no curated row has a non-Latin alias, so an ASCII-only " \
            "normaliser cannot be caught by the shipped fixtures"

    @pytest.mark.parametrize("mention,place_id", [
        (BHARAT, "in"),
        (MUMBAI_HI, "in_mh_mumbai"),
    ])
    def test_a_devanagari_mention_resolves_to_the_right_place(
            self, master, mention, place_id):
        resolution = master.resolve_place(mention)
        assert resolution.status == "resolved"
        assert resolution.entity_id == place_id

    @pytest.mark.parametrize("mention,place_id", [
        ("India", "in"),
        ("Mumbai", "in_mh_mumbai"),
    ])
    def test_the_english_names_still_resolve(self, master, mention, place_id):
        assert master.resolve_place(mention).entity_id == place_id

    @pytest.mark.parametrize("state,canonical", [
        ("Maharashtra", "in_mh"),
        ("Odisha", "in_od"),
    ])
    def test_a_previously_duplicated_state_now_resolves(self, master, state,
                                                        canonical):
        """X12, FIXED. These two tests used to assert the defect existed.

        Exactly two states carried two rows each -- the canonical `in_*` row
        and an `ntpc_state_*` row created for the NTPC facility mapping -- so
        the resolver correctly abstained and neither Maharashtra nor Odisha
        could be resolved from a mention at all. The resolver was right; the
        DATA was wrong.

        The merge was unambiguous once the citations were read. The `in_*`
        rows carry coordinates, a geonames citation and child places parented
        to them. The `ntpc_state_*` rows carried no coordinates and cited
        NTPC's coal-stations page -- which is an ASSET fact ("NTPC has a
        station here"), not a geographic one, and it already sits on each
        asset row. So the duplicates were dropped, the three asset rows were
        repointed to the canonical places, and no citation was lost: the
        NTPC URL stayed where it belongs and the place kept geonames.
        """
        resolution = master.resolve_place(state)
        assert resolution.status == "resolved"
        assert resolution.entity_id == canonical

    def test_no_place_name_is_duplicated_any_more(self, master):
        """The inverse of the old blast-radius pin: the scan must now find
        nothing. If a duplicate reappears, this fails rather than a resolver
        silently abstaining on a state nobody checks."""
        from collections import defaultdict
        by_name = defaultdict(list)
        for place in master.places.values():
            by_name[(place.name.strip().lower(), place.kind)].append(place.place_id)
        duplicates = {k: sorted(v) for k, v in by_name.items() if len(v) > 1}
        assert duplicates == {}, f"duplicated place rows are back: {duplicates}"

    def test_the_repointed_assets_sit_in_the_canonical_places(self, master):
        """The three NTPC stations that referenced the dropped rows. A merge
        that removed the places without repointing these would leave assets
        pointing at a place_id that no longer exists -- which only shows up
        at load time, or not at all."""
        expected = {"ntpc_darlipali": "in_od", "ntpc_mouda": "in_mh",
                    "ntpc_solapur": "in_mh"}
        for asset_id, place_id in expected.items():
            asset = master.assets[asset_id]
            assert getattr(asset, "place_id", None) == place_id, asset_id

    def test_every_asset_points_at_a_place_that_exists(self, master):
        """The general form, so the next curated edit cannot dangle."""
        dangling = [a for a in master.assets.values()
                    if getattr(a, "place_id", None)
                    and a.place_id not in master.places]
        assert dangling == [], f"assets point at missing places: {dangling}"

    def test_the_ntpc_citation_survived_on_the_assets(self, master):
        """No citation was dropped by the merge: the NTPC page still backs
        each station, which is the claim it actually supports."""
        for asset_id in ("ntpc_darlipali", "ntpc_mouda", "ntpc_solapur"):
            asset = master.assets[asset_id]
            source = getattr(asset, "source", None) or getattr(
                asset, "known_from", None)
            assert source is not None, asset_id
            assert "ntpc.co.in" in str(source), asset_id

    def test_the_unduplicated_ntpc_states_still_resolve(self, master):
        """Most `ntpc_state_*` rows have no canonical twin and work fine, so
        X12 is a duplication defect and not an argument against the
        namespace itself."""
        assert master.resolve_place("Uttar Pradesh").entity_id == \
            "ntpc_state_uttar_pradesh"
        assert master.resolve_place("Bihar").status == "resolved"

    def test_the_two_hindi_mentions_do_not_resolve_to_each_other(self, master):
        assert (master.resolve_place(BHARAT).entity_id
                != master.resolve_place(MUMBAI_HI).entity_id)

    def test_registry_counts(self, master):
        """Places dropped from 21 to 19 when X12's two duplicate rows were
        merged away. Nothing else moved: the assets were repointed, not
        removed, and no entity or edge was touched.

        If this fails after a curated edit, re-derive the numbers from the
        loader rather than adjusting them to whatever came out -- the whole
        point of asserting a count is that a silent row loss is caught.

        Entities went 22 -> 58 on 2026-10-24: 36 energy-industry issuers
        from NSE's own Nifty 500 constituent list (its `Industry` column is
        the cited sector, not a judgement). Re-derived from the loader, and
        the other three counts are asserted UNCHANGED on purpose -- adding
        entities must not touch a place, asset or edge.
        """
        assert len(master.entities) == 58
        assert len(master.places) == 19
        assert len(master.assets) == 28
        assert len(master.edges) == 64
