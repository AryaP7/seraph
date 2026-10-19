# Regression tests — O01, O02, V03, X05 (distribution and configuration)
"""Packaging and dependency defects from the 2026-10-18 completion audit.

O01's full acceptance needs a built wheel installed outside the checkout and
is exercised by `scripts/verify_packaging.py`. These tests cover the parts
that can be asserted without a 4-minute build, so a regression is caught in
the normal suite rather than only in the packaging job:

* the asset directories are importable packages (the root cause -- without
  an `__init__.py`, `packages.find` never sees them and `package-data` has
  nothing to attach to);
* every required asset is declared, and declared with a glob that reaches it
  (a `package-data` glob does not recurse into subdirectories);
* the lockfile pins every pyproject dependency, so `-e .` resolves nothing;
* `scripts/` absence is reported as a named missing capability rather than a
  bare ModuleNotFoundError;
* the Kite token location is configurable, so it can live outside the tree.
"""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pyproject() -> dict:
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))


# ------------------------------------------------------------------ O01


class TestO01AssetDirectoriesArePackages:
    """The root cause. `seraph/live/migrations/` and `seraph/news/curated/`
    had no `__init__.py`, so setuptools never found them at all."""

    @pytest.mark.parametrize("package", [
        "seraph.live.migrations",
        "seraph.news.curated",
        "seraph.store.migrations",
    ])
    def test_the_asset_directory_is_importable(self, package):
        __import__(package)

    def test_the_live_migration_sql_is_reachable_through_the_package(self):
        from seraph.live.migrations import migration_files
        names = [p.name for p in migration_files()]
        assert "001_runtime.sql" in names
        assert all(p.stat().st_size > 0 for p in migration_files())

    def test_the_curated_registry_files_are_all_present(self):
        from seraph.news.curated import REGISTRY_FILES, missing_registry_files
        assert len(REGISTRY_FILES) == 5
        assert missing_registry_files() == []

    def test_a_missing_registry_file_is_named_not_silently_skipped(self, monkeypatch):
        import seraph.news.curated as curated
        monkeypatch.setattr(curated, "CURATED_DIR", ROOT / "does-not-exist")
        assert sorted(curated.missing_registry_files()) == sorted(curated.REGISTRY_FILES)


class TestO01PackageDataDeclaresEveryRuntimeAsset:
    def test_every_required_asset_is_covered_by_a_declared_glob(self, pyproject):
        """A `package-data` glob does NOT recurse, which is why
        `"seraph.store" = ["*.sql"]` shipped schema.sql and silently dropped
        store/migrations/001_evaluation_identity.sql."""
        from fnmatch import fnmatch
        declared = pyproject["tool"]["setuptools"]["package-data"]
        globs: list[tuple[str, str]] = [
            (pkg.replace(".", "/"), pattern)
            for pkg, patterns in declared.items() for pattern in patterns]

        import scripts.verify_packaging as verifier
        uncovered = []
        for asset in verifier.REQUIRED:
            directory, _, name = asset.rpartition("/")
            if not any(directory == pkg_dir and fnmatch(name, pattern)
                       for pkg_dir, pattern in globs):
                uncovered.append(asset)
        assert uncovered == [], \
            f"declared package-data does not reach: {uncovered}"

    def test_the_verifier_checks_the_assets_the_audit_found_missing(self):
        """The old REQUIRED tuple covered a subset, so it passed a wheel
        missing seven files -- it reported success for a broken build."""
        import scripts.verify_packaging as verifier
        for asset in ("seraph/live/migrations/001_runtime.sql",
                      "seraph/store/migrations/001_evaluation_identity.sql",
                      "seraph/news/curated/entities.csv",
                      "seraph/news/curated/places.csv",
                      "seraph/news/curated/assets.csv",
                      "seraph/news/curated/exposure.csv",
                      "seraph/news/curated/source_places.csv"):
            assert asset in verifier.REQUIRED, f"{asset} is not verified"

    def test_every_required_asset_exists_in_the_source_tree(self):
        import scripts.verify_packaging as verifier
        missing = [a for a in verifier.REQUIRED if not (ROOT / a).is_file()]
        assert missing == []


# ------------------------------------------------------------- O02 / V03


class TestO02LockfilePinsEveryDependency:
    def _names(self, text: str) -> set[str]:
        out = set()
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            out.add(re.split(r"[<>=!~\[ ]", line)[0].lower().replace("_", "-"))
        return out

    def test_pypdf_is_pinned(self):
        """Declared in pyproject, absent from the lock, floating in CI."""
        lock = (ROOT / "requirements-research.lock.txt").read_text(encoding="utf-8")
        assert "pypdf==" in lock

    def test_no_pyproject_dependency_is_left_to_float(self, pyproject):
        lock = self._names((ROOT / "requirements-research.lock.txt").read_text(encoding="utf-8"))
        required = {re.split(r"[<>=!~\[ ]", d)[0].lower().replace("_", "-")
                    for d in pyproject["project"]["dependencies"]}
        assert required - lock == set()

    def test_the_invariant_check_enforces_this(self):
        import scripts.check_invariants as inv
        assert inv.check_lockfile_covers_pyproject() == []

    def test_the_invariant_check_would_catch_a_new_unpinned_dependency(self, monkeypatch, tmp_path):
        import scripts.check_invariants as inv
        fake = tmp_path
        (fake / "pyproject.toml").write_text(
            'dependencies = [\n  "numpy>=1.26",\n  "brand-new-thing>=1.0",\n]\n',
            encoding="utf-8")
        (fake / "requirements-research.lock.txt").write_text(
            "numpy==2.5.4\n-e .\n", encoding="utf-8")
        monkeypatch.setattr(inv, "REPO_ROOT", fake)
        problems = inv.check_lockfile_covers_pyproject()
        assert len(problems) == 1 and "brand-new-thing" in problems[0]

    def test_the_project_itself_is_installed_last(self):
        lines = [l.strip() for l in
                 (ROOT / "requirements-research.lock.txt").read_text(
                     encoding="utf-8").splitlines() if l.strip()]
        assert lines[-1] == "-e ."


class TestO02OptionalCapabilitiesAreDeclared:
    def test_the_live_broker_extra_exists(self, pyproject):
        extras = pyproject["project"]["optional-dependencies"]
        assert any("kiteconnect" in d for d in extras["live"])

    def test_the_auth_extra_exists(self, pyproject):
        extras = pyproject["project"]["optional-dependencies"]
        assert extras["auth"], "real identity verification needs a declared extra"

    def test_optional_extras_are_not_in_the_core_install(self, pyproject):
        core = " ".join(pyproject["project"]["dependencies"])
        assert "kiteconnect" not in core, \
            "the core install must not require a broker package"


class TestO02ScriptsAbsenceIsANamedCapability:
    def test_the_capability_is_available_from_this_checkout(self):
        from seraph.orchestration import research_scripts
        assert research_scripts.available() is True
        assert research_scripts.describe()["reason"] is None

    def test_loading_a_real_helper_works_from_a_checkout(self):
        from seraph.orchestration import research_scripts
        (universe_for,) = research_scripts.load("build_observations", "universe_for")
        assert callable(universe_for)

    def test_absence_raises_a_named_error_not_module_not_found(self, monkeypatch):
        from seraph.orchestration import research_scripts
        monkeypatch.setattr(research_scripts, "_CANDIDATE_ROOT",
                            ROOT / "does-not-exist")
        with pytest.raises(research_scripts.ResearchScriptsUnavailable) as caught:
            research_scripts.load("build_observations", "universe_for")
        message = str(caught.value)
        assert "does not ship the research" in message
        assert "archive adapter" in message, \
            "a missing capability must name the supported alternative"
        assert "Nothing is estimated" in message

    def test_absence_is_reportable_without_raising(self, monkeypatch):
        from seraph.orchestration import research_scripts
        monkeypatch.setattr(research_scripts, "_CANDIDATE_ROOT",
                            ROOT / "does-not-exist")
        report = research_scripts.describe()
        assert report["available"] is False and report["reason"]

    def test_a_drifted_script_names_the_missing_function(self):
        from seraph.orchestration import research_scripts
        with pytest.raises(research_scripts.ResearchScriptsUnavailable,
                           match="does not define"):
            research_scripts.load("build_observations", "no_such_function")

    def test_original_execution_no_longer_imports_scripts_directly(self):
        body = (ROOT / "seraph/orchestration/original_execution.py").read_text(
            encoding="utf-8")
        assert "from scripts." not in body
        assert "research_scripts.load" in body


# ------------------------------------------------------------------- X05


class TestX05TokenLocationIsConfigurable:
    def test_the_default_is_still_the_legacy_in_tree_path(self, monkeypatch):
        monkeypatch.delenv("SERAPH_KITE_TOKENS", raising=False)
        from seraph.ingestion import kite_client
        assert kite_client.token_cache_path().name == "kite_credentials.tokens.json"
        assert kite_client.token_cache_is_in_repo() is True

    def test_an_override_moves_the_token_out_of_the_tree(self, monkeypatch, tmp_path):
        target = tmp_path / "kite.tokens.json"
        monkeypatch.setenv("SERAPH_KITE_TOKENS", str(target))
        from seraph.ingestion import kite_client
        assert kite_client.token_cache_path() == target
        assert kite_client.token_cache_is_in_repo() is False

    def test_the_missing_token_message_names_the_override(self, monkeypatch, tmp_path):
        monkeypatch.setenv("SERAPH_KITE_TOKENS", str(tmp_path / "absent.json"))
        from seraph.ingestion import kite_client
        with pytest.raises(RuntimeError, match="SERAPH_KITE_TOKENS"):
            kite_client.cached_access_token()

    def test_no_token_value_appears_in_the_error(self, monkeypatch, tmp_path):
        """A diagnostic must never print the secret it could not find."""
        token = tmp_path / "t.json"
        token.write_text('{"access_token": "SECRETVALUE"}', encoding="utf-8")
        monkeypatch.setenv("SERAPH_KITE_TOKENS", str(tmp_path / "absent.json"))
        from seraph.ingestion import kite_client
        try:
            kite_client.cached_access_token()
        except RuntimeError as exc:
            assert "SECRETVALUE" not in str(exc)

    def test_the_invariant_check_reports_an_in_tree_token_as_info(self):
        """Informational, not a violation: remediation is an owner action on
        their own credential, and CI never sees the file."""
        import scripts.check_invariants as inv
        for note in inv.check_no_secrets_at_rest():
            assert note.startswith("[info]")
