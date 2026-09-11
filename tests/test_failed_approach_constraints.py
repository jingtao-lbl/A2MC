"""`check_do_not_repeat` must actually fire on a recorded viability bound.

REGRESSION FOR A GUARD THAT COULD NOT FAIL. Before 2026-09-05 the do-not-repeat check matched
only on prose: the parameter name had to appear in the approach text, the proposed change had to
exceed 5x, AND the literal string "10" had to appear in the text. That triple was written for one
historical entry of the form "10x increase in X" and cannot express a BOUND, so an entry saying
"values below 2.52 kill the stand" was stored and then never matched -- not even by a proposal to
halve the parameter. Measured on the EcoSIM_Lusignan viability bounds: 1 entry written, 0 warnings
across four proposals, one of them a 10x increase.

That is the shape of defect where a populated do-not-repeat list looks like protection and is not,
so the fix ships with the test that would have caught it.
"""
import json
from pathlib import Path

import pytest

from memory import MemoryManager


@pytest.fixture()
def store(tmp_path: Path) -> MemoryManager:
    for name, seed in (("discoveries.json", {"discoveries": []}),
                       ("experiments.json", {"experiments": []}),
                       ("parameters.json", {"parameters": {}}),
                       ("failed_approaches.json", {"failed_approaches": []})):
        (tmp_path / name).write_text(json.dumps(seed))
    m = MemoryManager(str(tmp_path))
    m.add_failed_approach(
        approach="Setting CNWL below 2.52 (protein C to leaf N ratio)",
        experiment_id="R1b_ensemble_mortality_20260905o",
        why_failed="stand collapses; 18.7% of bottom-decile cases died against a 4.4% base rate",
        severity="catastrophic", alternatives=["keep CNWL >= 2.52"],
        constraint={"parameter": "CNWL", "direction": "min", "bound": 2.52})
    m.add_failed_approach(
        approach="Setting XKCO2 above 21.4 (Rubisco Km)",
        experiment_id="R1b_ensemble_mortality_20260905o",
        why_failed="stand collapses; risk rises monotonically to 8.4% in the top deciles",
        severity="catastrophic", alternatives=["keep XKCO2 <= 21.4"],
        constraint={"parameter": "XKCO2", "direction": "max", "bound": 21.4})
    m.add_failed_approach(          # legacy prose entry, no constraint
        approach="10x increase in vmax_p", experiment_id="legacy",
        why_failed="overshoots", severity="degradation", alternatives=[])
    return MemoryManager(str(tmp_path))


def warned(m, parameter, old, new) -> bool:
    return bool(m.check_do_not_repeat(
        [{"parameter": parameter, "old_value": old, "new_value": new}]))


@pytest.mark.parametrize("parameter,old,new,expected,why", [
    ("CNWL",    2.8,  2.00, True,  "below a recorded min bound"),
    ("CNWL_1",  2.8,  2.00, True,  "Morris shorthand names the same knob"),
    ("cnwl",    2.8,  1.50, True,  "comparison is case-insensitive"),
    ("CNWL",    2.8,  3.50, False, "above the bound is allowed"),
    ("CNWL",    2.8,  2.52, False, "exactly at the bound is allowed"),
    ("XKCO2_1", 12.5, 30.0, True,  "above a recorded max bound"),
    ("XKCO2",   12.5, 15.0, False, "below a max bound is allowed"),
    ("RMOM",    0.01, 0.05, False, "a parameter with no recorded bound is allowed"),
])
def test_structured_bound_matching(store, parameter, old, new, expected, why):
    assert warned(store, parameter, old, new) is expected, why


@pytest.mark.parametrize("parameter,old,new", [
    ("vmax_p",      1.0, 10.0),    # the exact shape the deleted heuristic was written for
    ("vmax_p",      1.0,  2.0),    # and a smaller move on the same entry
    ("leaf_slatop", 0.01, 0.06),   # the FALSE ALARM: a name that merely ENDS in _10
])
def test_prose_only_entry_never_warns(store, parameter, old, new):
    """A failed approach with no `constraint` matches NOTHING, whatever its prose says.

    The prose branch was deleted 2026-09-08 (PI). It fired when the parameter name was a
    SUBSTRING of the entry text, the proposal exceeded 5x, and the characters "10" appeared
    in that text -- two literals reverse-engineered from one case's phrasing, which put that
    case's vocabulary and its PFT NUMBERING inside shared framework code.

    Measured over all 88 stored entries before deleting it: 9 could fire it, all in the one
    case it was written for, and in 7 of those 9 the "10" meant something else -- `PFT#10`
    four times, the parameter name `leaf_slatop_10`, `10 degC`, and the "10" inside `> 100`.
    The third case below is that false alarm, and it is the reason this is an assertion
    rather than a deletion: a name ending in _10 must not resurrect the behaviour.

    Two genuine 10x entries lost coincidental coverage and are owed a `constraint` through
    the curated-write gate; a bound is how such a refutation is expressed now.
    """
    assert warned(store, parameter, old, new) is False


def test_unevaluatable_bound_warns_rather_than_going_silent(store):
    """A non-numeric proposal on a CONSTRAINED parameter must say so, not return nothing.

    Silence is byte-identical to "no problem found", which is the failure mode of the branch
    just deleted. The guard reports that it could not evaluate the bound instead.
    """
    out = store.check_do_not_repeat(
        [{"parameter": "CNWL", "old_value": 2.8, "new_value": "2.0"}])
    assert len(out) == 1
    assert out[0].get("unevaluated") is True
    assert "not numeric" in out[0]["warning"]

    # and it stays quiet for a parameter nothing constrains
    assert store.check_do_not_repeat(
        [{"parameter": "RMOM", "old_value": 0.01, "new_value": "x"}]) == []


def test_constraint_is_validated(store):
    for bad in ({"parameter": "X", "direction": "min"},            # no bound
                {"parameter": "X", "bound": 1.0},                  # no direction
                {"parameter": "X", "direction": "sideways", "bound": 1.0}):
        with pytest.raises(ValueError):
            store.add_failed_approach("a", "e", "w", "catastrophic", [], constraint=bad)
