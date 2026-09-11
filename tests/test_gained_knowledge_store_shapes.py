"""The curated knowledge stores must have the SHAPE MemoryManager indexes them with.

NEGATIVE CONTROL: reverting any `parameters` key from `{}` to `[]` turns
`test_parameters_is_a_dict_wherever_it_exists` red, and reverting a template's file to a list
additionally turns `test_memory_manager_read_paths_work_on_every_template` red with the real
error rather than a shape assertion.

MEASURED 2026-09-08, and both directions failed. `use_cases/TEMPLATE` and all four per-model
`*_template` cases shipped `parameters.json` with `"parameters": []`, while
`memory/manager.py` indexes that key by parameter name (`:736-739`) and iterates it with
`.items()` (`:285`, `:366`). So a case scaffolded from any of them raised

    add_parameter_knowledge  -> TypeError: list indices must be integers or slices, not str
    get_parameter_cautions   -> AttributeError: 'list' object has no attribute 'items'

and `get_parameter_cautions` is called by every diagnosis. The templates are what SHIP, so this
was in front of every new case on both public lines.

EXISTENCE IS ASSERTED OF EVERY CASE, as of 2026-09-08. It was asserted only of the TEMPLATES for
one commit, because two live cases carried only a README and a test that is red for a reason
nobody intends to fix is a test nobody reads; they were reported instead. Both were backfilled on
request the same day, so the report has nothing left to report and the weaker form is gone. The
enforced version is what catches the next case created without its stores, which is how
`EcoSIM_Lusignan` ran thirteen experiment cycles with three of four missing.
"""
import json
from pathlib import Path

import pytest

from memory import MemoryManager

ROOT = Path(__file__).resolve().parents[1]
USE_CASES = ROOT / "use_cases"
STORES = ("discoveries.json", "experiments.json", "parameters.json", "failed_approaches.json")
#: key -> the type MemoryManager requires. `discoveries` is absent from this map deliberately:
#: `add_discovery` writes entries at TOP LEVEL keyed by name (manager.py:611) and `stats()` counts
#: top-level dict values (manager.py:116), so the `discoveries` array is legacy and optional.
REQUIRED_SHAPE = {"parameters": dict, "experiments": list, "failed_approaches": list}


def _cases():
    return sorted(p for p in USE_CASES.iterdir()
                  if p.is_dir() and (p / "memory" / "gained_knowledge").is_dir())


def _templates():
    return [p for p in _cases() if p.name == "TEMPLATE" or p.name.endswith("_template")]


@pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
def test_every_case_carries_all_four_stores(case):
    """A missing store is INVISIBLE at runtime, which is why this is asserted rather than noticed.

    `memory/store.py::load_json` returns a default for a missing path, so `stats()` reports zeros
    byte-identical to an empty-but-present store. `EcoSIM_Lusignan` ran thirteen experiment cycles
    with three of its four absent and nothing anywhere said so.
    """
    g = case / "memory" / "gained_knowledge"
    missing = [s for s in STORES if not (g / s).exists()]
    assert not missing, (
        f"{case.name} is missing {missing}. Copy the empty stores from the matching "
        f"use_cases/<Model>_template/memory/gained_knowledge/ and replace each _comment with "
        f"this case's own description.")


@pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
def test_parameters_is_a_dict_wherever_it_exists(case):
    """THE REGRESSION. A list here breaks the write path and every diagnosis's read path."""
    p = case / "memory" / "gained_knowledge" / "parameters.json"
    assert p.exists(), f"{case.name} has no parameters.json"
    got = json.loads(p.read_text()).get("parameters")
    assert isinstance(got, dict), (
        f"{case.name}: parameters is {type(got).__name__}, must be dict -- MemoryManager indexes "
        f"it by name (manager.py:736) and calls .items() on it (manager.py:285)")


@pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
def test_store_shapes_are_what_the_manager_requires(case):
    g = case / "memory" / "gained_knowledge"
    for fn, (key, typ) in ((f, (f[:-5], REQUIRED_SHAPE.get(f[:-5]))) for f in STORES):
        if typ is None or not (g / fn).exists():
            continue
        got = json.loads((g / fn).read_text()).get(key)
        assert isinstance(got, typ), (
            f"{case.name}/{fn}: `{key}` is {type(got).__name__}, must be {typ.__name__}")


@pytest.mark.parametrize("case", _cases(), ids=lambda p: p.name)
def test_memory_manager_read_and_write_paths_work(case, tmp_path):
    """Exercise the paths a diagnosis actually calls, on a COPY so no real store is mutated.

    Deliberately CONTENT-AGNOSTIC: it asserts the calls do not raise and that a write lands,
    never that a store is empty, so it holds for a populated case as well as a fresh one. The
    list form failed here with a TypeError on the write and an AttributeError on
    `get_parameter_cautions`, which is on the read path of every diagnosis.
    """
    src = case / "memory" / "gained_knowledge"
    dst = tmp_path / "gk"; dst.mkdir()
    for f in src.glob("*.json"):
        dst.joinpath(f.name).write_bytes(f.read_bytes())
    m = MemoryManager(str(dst))
    m.stats()
    assert isinstance(m.get_parameter_cautions(parameters=["ZZ_NOT_A_PARAM"]), dict)
    assert isinstance(m.get_all_discoveries(), dict)
    assert isinstance(m.get_failed_experiments(parameters=["ZZ_NOT_A_PARAM"]), list)
    m.add_parameter_knowledge("ZZ_NOT_A_PARAM", "caution", "probe")
    assert "ZZ_NOT_A_PARAM" in json.loads((dst / "parameters.json").read_text())["parameters"]


def test_no_case_is_left_reporting_instead_of_asserting():
    """The report this file used to carry must stay empty, or the enforced test above is wrong.

    Kept as a one-line cross-check rather than deleted: if a case is ever added with its stores
    missing, BOTH this and `test_every_case_carries_all_four_stores` fail, and their messages say
    different halves of why.
    """
    incomplete = {c.name: [s for s in STORES
                           if not (c / "memory" / "gained_knowledge" / s).exists()]
                  for c in _cases()}
    incomplete = {k: v for k, v in incomplete.items() if v}
    assert not incomplete, f"cases missing stores: {incomplete}"
