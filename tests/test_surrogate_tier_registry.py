"""A spec may only declare a tier that has a class behind it.

`VALID_TIERS` declared four tiers while `tiers.py` implemented two, so
`SurrogateSpec(tier="S3")` constructed cleanly and failed only much later, at
`load()`, with `NotImplementedError`. Validation that cannot reject the thing it
is named for is not validation ([[feedback_a_check_that_cannot_fail]]).

The fix keeps BOTH tuples, because they answer different questions:
`VALID_TIERS` is the roadmap (what the design admits), `IMPLEMENTED_TIERS` is the
registry (what exists). Construction validates against the registry.

Every test below is written to FAIL if the guard is removed or if the two tuples
drift out of agreement with the classes actually exported.
"""
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.surrogate.spec import (  # noqa: E402
    IMPLEMENTED_TIERS,
    VALID_TIERS,
    SurrogateSpec,
)


def _spec(**kw):
    base = dict(
        name="t", use_mode="offline_search", tier="S1",
        input_names=("a",), input_lower=(0.0,), input_upper=(1.0,),
    )
    base.update(kw)
    return SurrogateSpec(**base)


@pytest.mark.parametrize("tier", [t for t in VALID_TIERS if t not in IMPLEMENTED_TIERS])
def test_an_unimplemented_roadmap_tier_is_REJECTED_at_construction(tier):
    """THE property. Before the fix every one of these constructed silently."""
    with pytest.raises(ValueError) as e:
        _spec(tier=tier)
    assert "no implementation" in str(e.value)


@pytest.mark.parametrize("tier", IMPLEMENTED_TIERS)
def test_every_implemented_tier_still_constructs(tier):
    """The guard must not have been bought by rejecting something real."""
    assert _spec(tier=tier).tier == tier


def test_a_tier_outside_the_roadmap_is_still_rejected_by_the_ORIGINAL_check():
    """The roadmap check is not made dead by the registry check standing in front."""
    with pytest.raises(ValueError) as e:
        _spec(tier="S9")
    assert "not in" in str(e.value)


def test_the_registry_is_a_SUBSET_of_the_roadmap():
    """An implemented tier absent from the roadmap would be unreachable: the
    roadmap check runs first and would reject it before the registry saw it."""
    assert set(IMPLEMENTED_TIERS) <= set(VALID_TIERS)


def test_the_registry_matches_the_classes_tiers_py_ACTUALLY_exports():
    """The drift this whole pair exists to prevent, asserted against the code
    rather than against another list. A new tier class added without updating
    IMPLEMENTED_TIERS (or the reverse) fails here."""
    import models.surrogate.tiers as tiers
    exported = {n[:-len("Surrogate")] for n in dir(tiers)
                if n.endswith("Surrogate") and n != "SurrogateModel"
                and n[:-len("Surrogate")] in VALID_TIERS}
    assert exported == set(IMPLEMENTED_TIERS), (
        f"tiers.py exports {sorted(exported)} but IMPLEMENTED_TIERS is "
        f"{sorted(IMPLEMENTED_TIERS)}")


def test_the_rejection_message_NAMES_the_gate_not_just_the_fact():
    """A reader hitting this must learn what would unblock it -- a written S1
    acceptance failure -- or they will simply add the tier to the tuple."""
    with pytest.raises(ValueError) as e:
        _spec(tier="S2")
    msg = str(e.value)
    assert "FAILED a written acceptance test" in msg
    assert "IMPLEMENTED_TIERS" in msg
