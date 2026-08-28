"""Tests for ``scripts/given_data_sensitivity.py`` — sensitivity on a space-filling ensemble.

The load-bearing property is that this recovers the RIGHT parameters from an arbitrary `(X, Y)`
cloud, and — equally — that it says "noise" when a parameter is noise. The first version of the
inert-tail test could not do the second, calling 15 of 16 inputs significant on a problem where 3
mattered, so several tests below exist specifically to pin that down.
"""
import sys
from pathlib import Path

import numpy as np
import pytest

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

pytest.importorskip("SALib")

from scripts.given_data_sensitivity import (build_xy, consensus_ranks,  # noqa: E402
                                            distinguishable, noise_floor,
                                            run_estimators)

D = 8


def _problem():
    return {"num_vars": D, "names": [f"x{i}" for i in range(D)], "bounds": [[0.0, 1.0]] * D}


def _design(n=512, seed=0):   # power of 2: Sobol balance properties require it
    from scipy.stats import qmc
    return qmc.Sobol(d=D, scramble=True, seed=seed).random(n)


def test_recovers_the_influential_inputs_from_an_arbitrary_cloud():
    """The whole point: no Saltelli design, no trajectories, no surrogate.

    Response uses x0 strongly, x3 weakly, and ignores the other six.
    """
    X = _design()
    Y = 1.0 * X[:, 0] + 0.35 * X[:, 3]
    res = run_estimators(_problem(), X, Y, resamples=10)
    cr = consensus_ranks(res, D)
    top2 = set(np.argsort(cr)[:2])
    assert top2 == {0, 3}, f"expected x0 and x3 on top, got ranks {cr}"
    assert cr[0] < cr[3], "x0 has the larger coefficient and should outrank x3"


def test_an_interaction_only_input_is_still_found():
    """x2 has no main effect and acts only through x0 — the case a plain correlation misses."""
    X = _design()
    Y = 0.8 * X[:, 0] + 1.2 * X[:, 0] * X[:, 2]
    res = run_estimators(_problem(), X, Y, resamples=10)
    cr = consensus_ranks(res, D)
    assert set(np.argsort(cr)[:2]) == {0, 2}


def test_the_noise_floor_rejects_a_pure_noise_response():
    """When NOTHING matters, nothing may clear the floor.

    This is the direction the first implementation could not express, and the reason the check was
    rewritten from delta's bootstrap CI to a permutation null.
    """
    X = _design()
    Y = np.random.default_rng(1).standard_normal(len(X))
    res = run_estimators(_problem(), X, Y, resamples=10)
    floor = noise_floor(_problem(), X, Y, n_perm=5, seed=7)
    dis = distinguishable(res, D, floor)
    assert dis.sum() <= 1, f"pure noise should clear nothing; {int(dis.sum())} cleared"


def test_the_noise_floor_still_admits_a_real_signal():
    """The complement — a floor that rejects everything would be equally useless."""
    X = _design()
    Y = 1.0 * X[:, 0]
    res = run_estimators(_problem(), X, Y, resamples=10)
    floor = noise_floor(_problem(), X, Y, n_perm=5, seed=7)
    dis = distinguishable(res, D, floor)
    assert dis[0], "the sole driving input must clear the floor"
    assert dis.sum() <= 3, "the inert inputs should mostly be excluded"


def test_consensus_is_computed_on_ranks_not_values():
    """The three metrics are not on a common scale; a mean of their VALUES is meaningless.

    Asserted structurally: consensus ranks must lie in [1, D] and average to (1+D)/2, which holds
    for a mean of rank vectors and not for a mean of mixed-scale values.
    """
    X = _design()
    Y = X[:, 0] + 0.3 * X[:, 1]
    res = run_estimators(_problem(), X, Y, resamples=10)
    cr = consensus_ranks(res, D)
    assert np.all(cr >= 1) and np.all(cr <= D)
    assert cr.mean() == pytest.approx((1 + D) / 2, abs=1e-9)


def test_one_failed_estimator_does_not_lose_the_others():
    res = {"delta": {"delta": np.array([0.4] + [0.0] * (D - 1))},
           "rbd_fast": {"_error": "boom"},
           "pawn": {"median": np.array([0.5] + [0.0] * (D - 1))}}
    cr = consensus_ranks(res, D)
    assert not np.isnan(cr).any()
    assert np.argmin(cr) == 0


def test_rows_are_filtered_per_target_not_globally():
    """A case with a valid Si and a NaN Mn must still inform Si.

    Filtering once globally would discard it from every target, which silently shrinks the sample
    for targets that had no problem.
    """
    X_all = np.arange(30, dtype=float).reshape(10, 3)
    rows = [
        {"case": "1", "status": "COMPLETED", "si": "1.0", "mn": "nan"},
        {"case": "2", "status": "COMPLETED", "si": "2.0", "mn": "5.0"},
        {"case": "3", "status": "FAILED", "si": "nan", "mn": "nan"},
    ]
    Xs, Ys, dropped = build_xy(rows, ["si", "mn"], X_all, "si")
    assert len(Xs) == 2 and dropped == 1
    Xm, Ym, dropped_m = build_xy(rows, ["si", "mn"], X_all, "mn")
    assert len(Xm) == 1 and dropped_m == 2


def test_a_case_outside_the_matrix_is_dropped_not_wrapped():
    """Case 0 and an over-range case must not silently index another row."""
    X_all = np.zeros((5, 3))
    rows = [{"case": "0", "status": "COMPLETED", "a": "1.0"},
            {"case": "6", "status": "COMPLETED", "a": "1.0"},
            {"case": "2", "status": "COMPLETED", "a": "1.0"}]
    Xs, Ys, dropped = build_xy(rows, ["a"], X_all, "a")
    assert len(Xs) == 1 and dropped == 2
