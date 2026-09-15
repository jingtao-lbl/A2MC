"""S2Surrogate: theta -> trajectory, reduced to the scalar every other consumer expects.

The load-bearing assertion is the REDUCER CHECK. A trajectory tier whose reducer disagrees with the
Y matrix produces a surrogate that is internally consistent and answers a different question than
the calibration is scored on, and nothing downstream can see it.
"""
from __future__ import annotations

import numpy as np
import pytest

from models.surrogate.spec import IMPLEMENTED_TIERS, Provenance, SurrogateSpec, TargetSpec
from models.surrogate.tiers import REDUCERS, S2Surrogate, load


def _case(n=180, d=120, seed=0):
    """A synthetic ensemble whose trajectories are a smooth function of theta."""
    rng = np.random.default_rng(seed)
    X = rng.uniform(0.0, 1.0, size=(n, 3))
    t = np.linspace(0.0, 4 * np.pi, d)
    years = np.repeat([2001, 2002, 2003, 2004], d // 4)
    traj = np.empty((n, 2, d))
    for i in range(n):
        a, b, c = X[i]
        traj[i, 0] = 2.0 + 3.0 * a + (1.0 + 2.0 * b) * np.sin(t) + 0.05 * rng.normal(size=d)
        traj[i, 1] = 1.0 + 2.0 * c + (0.5 + b) * np.cos(t) + 0.05 * rng.normal(size=d)
    spec = SurrogateSpec(
        name="synthetic", tier="S2", use_mode="offline_search",
        input_names=["a", "b", "c"],
        input_lower=(0.0, 0.0, 0.0), input_upper=(1.0, 1.0, 1.0),
        targets=[TargetSpec("T1", observed=10.0), TargetSpec("T2", observed=5.0)],
        provenance=Provenance(model="test"))
    return X, traj, years, spec


def _fit(X, traj, years, spec, **kw):
    Y = REDUCERS["annual_mean_sum"](traj, years)
    m = S2Surrogate(spec, learner="rf", n_components=8, reduce="annual_mean_sum",
                    time_index=years, random_state=0, **kw)
    return m.fit(X, Y, trajectories=traj), Y


def test_s2_is_in_the_registry_so_a_spec_can_declare_it():
    assert "S2" in IMPLEMENTED_TIERS
    SurrogateSpec(name="x", tier="S2", input_names=["a"], use_mode="offline_search",
                  input_lower=(0.0,), input_upper=(1.0,),
                  targets=[TargetSpec("T1")], provenance=Provenance(model="t"))


def test_predicts_a_trajectory_and_reduces_it_to_the_scalar():
    X, traj, years, spec = _case()
    m, _ = _fit(X, traj, years, spec)
    P = m.predict_trajectories(X[:5])
    assert P.shape == (5, 2, traj.shape[2]), "a trajectory tier must return (N, T, D)"
    b = m.predict_batch(X[:5])
    assert b.values.shape == (5, 2), "predict_batch must stay the scalar drop-in for S1"
    # the scalar MUST be the reduction of the series the same call would return
    assert np.allclose(b.values, REDUCERS["annual_mean_sum"](P, years)), (
        "predict_batch disagrees with reducing predict_trajectories: the two would "
        "give a caller different answers to the same question")


def test_it_actually_learns_the_shape_not_just_the_level():
    """A trajectory tier that only got the level right would be an S1 with extra steps."""
    X, traj, years, spec = _case()
    m, _ = _fit(X[:150], traj[:150], years, spec)
    P = m.predict_trajectories(X[150:])
    A = traj[150:]
    # correlation of the ANOMALY about each series' own mean: pure shape, level removed
    def anom(a):
        return a - a.mean(axis=2, keepdims=True)
    r = np.corrcoef(anom(P).ravel(), anom(A).ravel())[0, 1]
    assert r > 0.9, f"shape correlation on held-out draws is only {r:.3f}"


def test_the_reducer_check_refuses_a_mismatched_Y():
    """THE guard. A Y matrix built with a different reduction must stop the fit."""
    X, traj, years, spec = _case()
    Y_wrong = REDUCERS["mean"](traj, years)          # a different, plausible reduction
    m = S2Surrogate(spec, learner="rf", n_components=4, reduce="annual_mean_sum",
                    time_index=years)
    with pytest.raises(ValueError, match="does not reproduce the Y matrix"):
        m.fit(X, Y_wrong, trajectories=traj)


def test_fit_without_trajectories_is_refused():
    X, traj, years, spec = _case()
    Y = REDUCERS["annual_mean_sum"](traj, years)
    m = S2Surrogate(spec, learner="rf", reduce="annual_mean_sum", time_index=years)
    with pytest.raises(ValueError, match="requires `trajectories`"):
        m.fit(X, Y)


def test_annual_reducer_without_a_time_index_is_refused_at_construction():
    _, _, _, spec = _case()
    with pytest.raises(ValueError, match="needs `time_index`"):
        S2Surrogate(spec, reduce="annual_mean_sum")


def test_round_trips_through_save_and_load(tmp_path):
    X, traj, years, spec = _case()
    m, _ = _fit(X, traj, years, spec)
    before = m.predict_trajectories(X[:4])
    m.save(tmp_path)
    again = load(tmp_path, expect=None)
    assert np.allclose(again.predict_trajectories(X[:4]), before), (
        "a reloaded S2 predicts different trajectories than the one that was saved")
    assert np.allclose(again.predict_batch(X[:4]).values, m.predict_batch(X[:4]).values)


def test_annual_mean_sum_is_the_year_end_of_a_cumulative_series():
    """Ties the reducer to the EcoSIM convention it was written for.

    A tape variable is within-year cumulative; de-cumulating gives a daily flux whose
    within-year sum is that year's end-of-year value. Mean over years is the scalar.
    """
    rng = np.random.default_rng(3)
    flux = rng.uniform(0.0, 2.0, size=(1, 1, 12))
    years = np.repeat([2001, 2002], 6)
    cum = np.concatenate([np.cumsum(flux[0, 0, :6]), np.cumsum(flux[0, 0, 6:])])
    year_end_mean = np.mean([cum[5], cum[11]])
    assert np.isclose(REDUCERS["annual_mean_sum"](flux, years)[0, 0], year_end_mean)
