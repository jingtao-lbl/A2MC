"""Joint learners for a SHORT OUTPUT VECTOR, and `VectorSurrogate` (S1 with one regressor).

What is guarded, and why:
  * a joint learner predicts every target, and does it from X rather than from the target means;
  * the ICM Gaussian process LEARNS the between-target correlation it exists to exploit;
  * it FITS in 54 dimensions and its ARD length-scales separate active inputs from inert ones,
    which is the regime where a GP's kernel start decides whether the optimiser moves at all;
  * it tolerates a missing target, so a row that lost one output still informs the others;
  * split-conformal intervals cover near nominal, and a calibration set too small to support the
    level gives UNBOUNDED intervals and a warning rather than a silently narrow band;
  * the artifact round-trips through the GENERIC loader, `tiers.load`, not only a private one.
"""
from __future__ import annotations

import importlib.util
import warnings

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="the multi-output learners need torch")

from models.surrogate.learners import LEARNERS, make_learner                   # noqa: E402
from models.surrogate.multioutput import (MultiOutputGPLearner,                 # noqa: E402
                                          MultiOutputMLPLearner, VectorSurrogate)
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec         # noqa: E402
from models.surrogate.tiers import load                                         # noqa: E402


def _truth(X):
    s = np.sin(3 * X[:, 0])
    return np.column_stack([s + X[:, 1], s - X[:, 1], 2 * s])


def _data(n=200, p=4, seed=0):
    rng = np.random.default_rng(seed)
    X = rng.uniform(0, 1, size=(n, p))
    return X, _truth(X) + 0.02 * rng.normal(size=(n, 3))


def _r2(pred, truth):
    return 1 - ((pred - truth) ** 2).mean(axis=0) / truth.var(axis=0)


def _spec(p=4, tier="S1", **kw):
    return SurrogateSpec(name="vec", use_mode="offline_search", tier=tier,
                         input_names=tuple(f"x{i}" for i in range(p)), input_lower=(0.0,) * p,
                         input_upper=(1.0,) * p,
                         targets=tuple(TargetSpec(n, **kw) for n in ("p", "q", "r")),
                         provenance=Provenance(model="test"))


@pytest.mark.filterwarnings("ignore:.*epoch budget")
def test_the_joint_MLP_predicts_every_target_from_X():
    X, Y = _data()
    Xt, _ = _data(200, seed=1)
    m = MultiOutputMLPLearner(n_models=2, epochs=300, patience=40).fit(X, Y)
    r2 = _r2(m.predict(Xt), _truth(Xt))
    assert (r2 > 0.95).all(), r2
    assert (m.predict_std(Xt) > 0).all()


def test_the_ICM_GP_LEARNS_which_targets_move_together():
    """Target 0 and target 1 are the same signal with independent noise; target 2 is unrelated."""
    rng = np.random.default_rng(0)
    X = rng.uniform(0, 1, size=(120, 3))
    s = np.sin(4 * X[:, 0])
    Y = np.column_stack([s + 0.05 * rng.normal(size=120), s + 0.05 * rng.normal(size=120),
                         np.cos(5 * X[:, 2]) + 0.05 * rng.normal(size=120)])
    g = MultiOutputGPLearner(n_iter=250).fit(X, Y)
    c = g.coregionalization()
    assert c[0, 1] > 0.8, c
    assert abs(c[0, 2]) < 0.5 and abs(c[1, 2]) < 0.5, c


def test_the_ICM_GP_FITS_in_54_dimensions_and_its_lengthscales_find_the_active_inputs():
    rng = np.random.default_rng(0)
    f = lambda X: np.sin(3 * X[:, 0]) + X[:, 1] ** 2
    X = rng.uniform(0, 1, size=(150, 54))
    Y = np.column_stack([f(X), -f(X)])
    Xt = rng.uniform(0, 1, size=(200, 54))
    g = MultiOutputGPLearner(n_iter=150).fit(X, Y)
    assert _r2(g.predict(Xt)[:, :1], f(Xt)[:, None])[0] > 0.9
    ls = g.lengthscales()
    assert ls[:2].max() < np.median(ls[2:]), "an active input's length-scale is no shorter than an inert one's"


def test_the_ICM_GP_uses_a_row_that_is_MISSING_one_target():
    X, Y = _data(160)
    Y[::3, 1] = np.nan                                  # a third of the rows lost target q
    g = MultiOutputGPLearner(n_iter=200).fit(X, Y)
    Xt, _ = _data(150, seed=2)
    assert np.isfinite(g.predict(Xt)).all()
    assert _r2(g.predict(Xt), _truth(Xt))[1] > 0.9


def test_VectorSurrogate_intervals_cover_NEAR_NOMINAL():
    X, Y = _data(300)
    m = VectorSurrogate(_spec(), learner="gp_multi", alpha=0.1, n_iter=150).fit(X, Y)
    Xt, Yt = _data(400, seed=3)
    p = m.predict_batch(Xt)
    cover = ((Yt >= p.lower) & (Yt <= p.upper)).mean(axis=0)
    assert (cover > 0.82).all(), cover


def test_a_calibration_set_too_small_gives_UNBOUNDED_intervals_and_says_so():
    """n_cal = 3 at alpha 0.1 needs the 4th of 3 scores. Capping at the largest would cover 3/4."""
    X, Y = _data(12)
    with pytest.warns(RuntimeWarning, match="intervals are unbounded"):
        m = VectorSurrogate(_spec(), learner="gp_multi", alpha=0.1, calibration_fraction=0.3,
                            n_iter=50).fit(X, Y)
    p = m.predict_batch(X[:3])
    assert np.isinf(p.upper).all() and np.isinf(p.lower).all()


def test_dead_rows_train_the_viability_classifier():
    X, Y = _data(200)
    viable = X[:, 0] < 0.8
    Y[~viable] = np.nan
    m = VectorSurrogate(_spec(), learner="gp_multi", n_iter=80).fit(X, Y, viable)
    v = m.predict_batch(np.array([[0.1, 0.5, 0.5, 0.5], [0.95, 0.5, 0.5, 0.5]])).viability
    assert v[0] > 0.5 > v[1]


def test_it_round_trips_through_the_GENERIC_loader(tmp_path):
    X, Y = _data(120)
    m = VectorSurrogate(_spec(), learner="gp_multi", n_iter=60).fit(X, Y)
    m.save(tmp_path / "art")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")                 # the fixture's provenance is unstamped
        back = load(tmp_path / "art", strict=False)
    assert isinstance(back, VectorSurrogate)
    q = X[:5]
    a, b = m.predict_batch(q), back.predict_batch(q)
    assert np.array_equal(a.values, b.values) and np.array_equal(a.upper, b.upper)


def test_refusals():
    X, Y = _data(40)
    with pytest.raises(ValueError, match="requires tier 'S1'"):
        VectorSurrogate(_spec(tier="S2"))
    with pytest.raises(ValueError, match="transform"):
        VectorSurrogate(_spec(transform="log"))
    with pytest.raises(ValueError, match="unknown multi-output learner"):
        VectorSurrogate(_spec(), learner="nope").fit(X, Y)
    with pytest.raises(ValueError, match="Y must be"):
        VectorSurrogate(_spec(), learner="gp_multi").fit(X, Y[:, :2])


@pytest.mark.skipif(importlib.util.find_spec("xgboost") is None, reason="xgboost not installed")
def test_the_xgb_learner_fits_when_xgboost_is_installed():
    X, Y = _data(200)
    m = make_learner("xgb", n_estimators=200).fit(X, Y[:, 0])
    Xt, _ = _data(100, seed=4)
    assert _r2(m.predict(Xt)[:, None], _truth(Xt)[:, :1])[0] > 0.8


@pytest.mark.skipif(importlib.util.find_spec("xgboost") is not None, reason="xgboost is installed")
def test_the_xgb_learner_is_registered_and_fails_LOUDLY_without_xgboost():
    assert "xgb" in LEARNERS
    X, Y = _data(20)
    with pytest.raises(ImportError, match="pip install xgboost"):
        make_learner("xgb").fit(X, Y[:, 0])
