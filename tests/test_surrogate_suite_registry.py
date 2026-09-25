"""The surrogate suite is a NAMED SET, and this is what keeps the name true.

Three dev logs reported three different totals for "the surrogate tests" because each derived the
set its own way, and both recipes were wrong in a way nobody could see:

  * `pytest -k surrogate` deselects `tests/test_kgml_emulator.py` wholesale -- neither the module
    name nor any test name contains the word -- so every count taken that way omitted the file
    holding the causal-mask and adjacency properties;
  * a `grep -l` over `tests/*.py` matches more files every time one is added, so two counts taken a
    week apart were never comparable.

`tests/SURROGATE_SUITE.txt` is the set. These tests make it self-maintaining: a new test file that
touches the surrogate surface fails here until it is listed, and a listed file that disappears
fails here too. Neither can drift quietly, which is the whole difference from a recipe.
"""
from __future__ import annotations

import re
from pathlib import Path

TESTS = Path(__file__).resolve().parent
REGISTRY = TESTS / "SURROGATE_SUITE.txt"

#: A test file belongs to the suite when it imports the surrogate package or one of the tools and
#: scripts built on it. Import, not mention: a test that merely names `package_surrogate` in a
#: docstring is not exercising it.
SURFACE = (r"models\.surrogate", r"tools\.package_surrogate", r"tools\.promote_surrogate",
           r"scripts\.fit_ensemble_surrogate", r"scripts\.check_surrogate_gate",
           r"scripts\.surrogate_sobol_indices")
IMPORTS = re.compile(r"(?:from|import)\s+(?:" + "|".join(SURFACE) + r")")


def _registry() -> list:
    return [ln.strip() for ln in REGISTRY.read_text().splitlines()
            if ln.strip() and not ln.startswith("#")]


def _touches_surrogate(path: Path) -> bool:
    return bool(IMPORTS.search(path.read_text()))


def test_every_listed_file_exists():
    """A registry pointing at a deleted file would quietly shrink the suite on the next run."""
    missing = [p for p in _registry() if not (TESTS.parent / p).is_file()]
    assert not missing, f"SURROGATE_SUITE.txt lists files that do not exist: {missing}"


def test_every_surrogate_test_file_is_LISTED():
    """The half that matters: a new test file cannot fall outside the suite unnoticed.

    This is what `-k surrogate` could never do. A file named for what it tests rather than for the
    module it imports -- `test_kgml_emulator.py`, `test_graph_emulators.py` -- is invisible to a
    name filter and visible here.
    """
    listed = {Path(p).name for p in _registry()}
    found = {p.name for p in sorted(TESTS.glob("test_*.py")) if _touches_surrogate(p)}
    unlisted = sorted(found - listed)
    assert not unlisted, (
        "these test files import the surrogate surface and are not in "
        f"tests/SURROGATE_SUITE.txt: {unlisted}. Add them, or the next 'the suite passes' is "
        "measured over a different set than the last one.")


def test_the_registry_does_not_list_files_that_do_not_touch_the_surface():
    """The other direction: a registry that accumulates unrelated files stops meaning anything."""
    stray = sorted(Path(p).name for p in _registry()
                   if (TESTS.parent / p).is_file() and not _touches_surrogate(TESTS.parent / p))
    assert not stray, f"listed but does not import the surrogate surface: {stray}"


def test_the_kgml_file_is_in_the_suite_and_a_NAME_FILTER_would_miss_it():
    """The concrete failure that motivated the registry, pinned so it cannot come back.

    If someone later renames the file or its tests to contain "surrogate", this test goes red and
    should simply be deleted -- the hazard it guards would be gone.
    """
    listed = {Path(p).name for p in _registry()}
    assert "test_kgml_emulator.py" in listed
    text = (TESTS / "test_kgml_emulator.py").read_text()
    names = re.findall(r"^def (test_\w+)", text, re.M)
    assert names, "no tests found in test_kgml_emulator.py"
    assert not any("surrogate" in n for n in names), (
        "a test in test_kgml_emulator.py is now named '...surrogate...', so `-k surrogate` would "
        "partially select this file; the registry is still the suite, but this note is stale")
