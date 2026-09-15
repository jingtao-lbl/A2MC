"""Named hold-out strategies, and the property that makes each one worth having.

A splitter is easy to write and easy to write WRONG in a way no test catches, because a broken
split still returns two disjoint index sets and still produces a plausible score. So these tests
assert the DISTRIBUTIONAL property each split claims, not just its shape: that an axis split really
does put the tail of one parameter entirely outside training, that a shell split really does move
the mean radius, and above all that the high-dimensional degeneracy the module warns about is real.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.surrogate.splits import (SPLITTERS, Split, axis_split, block_split,   # noqa: E402
                                     levels_split, random_split, shell_split)


def _cube(n=800, d=54, seed=0):
    return np.random.default_rng(seed).uniform(0.0, 1.0, size=(n, d))


# --------------------------------------------------------------------------------------------
# every split, the shared contract
# --------------------------------------------------------------------------------------------

def test_every_splitter_partitions_without_overlap_and_says_what_it_is_optimistic_about():
    X = _cube()
    splits = [random_split(len(X)), block_split(len(X)), axis_split(X, 0),
              shell_split(X), levels_split(np.repeat([1, 2, 3, 4, 5], len(X) // 5), [2])]
    for s in splits:
        assert len(np.intersect1d(s.train, s.test)) == 0
        assert s.n_train + s.n_test == len(X), f"{s.kind} loses rows"
        assert s.optimistic_about.strip(), f"{s.kind} claims to be optimistic about nothing"
        assert s.description.strip()


def test_overlapping_indices_are_REFUSED_at_construction():
    """The one error that silently inflates every score downstream."""
    with pytest.raises(ValueError, match="overlap"):
        Split(train=np.array([0, 1, 2]), test=np.array([2, 3]), kind="bad",
              description="d", optimistic_about="o")


def test_an_empty_side_is_refused():
    with pytest.raises(ValueError, match="empty test set"):
        Split(train=np.array([0, 1]), test=np.array([], dtype=int), kind="bad",
              description="d", optimistic_about="o")
    with pytest.raises(ValueError, match="empty training set"):
        Split(train=np.array([], dtype=int), test=np.array([0]), kind="bad",
              description="d", optimistic_about="o")


def test_a_fraction_outside_the_open_unit_interval_is_refused():
    for f in (0.0, 1.0, -0.1, 1.5):
        with pytest.raises(ValueError, match="test_fraction"):
            random_split(100, test_fraction=f)


# --------------------------------------------------------------------------------------------
# each split's own claim
# --------------------------------------------------------------------------------------------

def test_random_is_reproducible_and_seed_dependent():
    a, b, c = random_split(500, seed=1), random_split(500, seed=1), random_split(500, seed=2)
    assert np.array_equal(a.test, b.test)
    assert not np.array_equal(a.test, c.test)


def test_block_takes_a_CONTIGUOUS_run_from_the_end():
    s = block_split(1000, test_fraction=0.2)
    assert np.array_equal(s.test, np.arange(800, 1000))
    assert block_split(1000, position="head").test[0] == 0


def test_axis_split_puts_the_whole_TAIL_of_that_parameter_outside_training():
    """The claim that makes it an extrapolation test: no training point reaches the test range."""
    X = _cube()
    s = axis_split(X, axis=3, test_fraction=0.2, side="upper", axis_name="VRNXI")
    assert X[s.test, 3].min() >= X[s.train, 3].max(), (
        "training data reaches into the withheld range; this is not extrapolation")
    assert "VRNXI" in s.description


def test_axis_split_lower_side_is_the_mirror_image():
    X = _cube()
    s = axis_split(X, axis=7, test_fraction=0.15, side="lower")
    assert X[s.test, 7].max() <= X[s.train, 7].min()


def test_shell_split_actually_moves_the_radius():
    # Explicit bounds, which is how a caller with a SurrogateSpec uses it. With lower/upper left to
    # None the splitter normalises by the DATA range, so the radius is computed on rescaled
    # coordinates and comparing against a raw-coordinate radius is off by the rescaling.
    X = _cube(d=8)
    s = shell_split(X, test_fraction=0.2, lower=[0.0] * 8, upper=[1.0] * 8)
    r = np.abs(X - 0.5).mean(axis=1)
    assert r[s.test].min() >= r[s.train].max()


def test_shell_split_normalises_by_the_DECLARED_bounds_when_given_them():
    """Bounds are part of a design's identity, so a splitter that ignores them and uses the data
    range gives a different partition on the same points."""
    X = _cube(n=400, d=6) * 0.5 + 0.25          # occupies only the middle half of [0, 1]
    by_data = shell_split(X, test_fraction=0.2)
    by_bounds = shell_split(X, test_fraction=0.2, lower=[0.0] * 6, upper=[1.0] * 6)
    assert not np.array_equal(by_data.test, by_bounds.test)


def test_THE_HIGH_DIMENSIONAL_DEGENERACY_THE_MODULE_WARNS_ABOUT_IS_REAL():
    """The reason `shell_split` does not use the Chebyshev radius.

    If it did, this assertion would hold for the split it produces, and the split would be random
    while reading as an extrapolation test. The test exists so the choice cannot be quietly
    reverted by someone who finds `max` more natural than `mean`.
    """
    X = _cube(n=2000, d=54)
    cheb = np.abs(X - 0.5).max(axis=1)
    assert cheb.min() > 0.44, (
        "the Chebyshev radius did NOT concentrate, so the module's stated reason for using the "
        "mean deviation no longer holds and the docstring must be corrected")
    assert cheb.std() < 0.02
    # the mean deviation, by contrast, still has a usable ordering
    mad = np.abs(X - 0.5).mean(axis=1)
    assert mad.std() > 0.01


def test_levels_split_withholds_ENTIRE_levels():
    years = np.repeat(np.arange(2006, 2017), 100)
    s = levels_split(years, [2009, 2014])
    assert set(years[s.test].tolist()) == {2009, 2014}
    assert not ({2009, 2014} & set(years[s.train].tolist())), (
        "a withheld year leaked into training")


def test_levels_split_refuses_a_level_that_is_not_present():
    """Silently withholding nothing would report a clean extrapolation score on an interpolation."""
    years = np.repeat(np.arange(2006, 2017), 10)
    with pytest.raises(ValueError, match="do not appear"):
        levels_split(years, [1999])
    with pytest.raises(ValueError, match="at least one level"):
        levels_split(years, [])


def test_the_registry_lists_every_splitter():
    assert set(SPLITTERS) == {"random", "block", "axis", "shell", "levels"}
