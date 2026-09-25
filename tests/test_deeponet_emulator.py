"""DeepONetEmulator: theta [+ an input function at sensors] -> output values at ANY coordinates.

What is guarded, and why:
  * it predicts at coordinates it NEVER saw, which is what its trunk network exists for;
  * in operator mode it generalises to input FUNCTIONS it never saw, at unseen coordinates;
  * a prediction does not depend on which other points are queried with it -- the trunk is a
    function of one coordinate, so querying a point alone and inside a set must agree;
  * the artifact round-trips through the GENERIC loader, `tiers.load`.
"""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="DeepONetEmulator needs torch")

from models.surrogate._nn import per_case_channel_r2                   # noqa: E402
from models.surrogate.operators import DeepONetEmulator                # noqa: E402
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec  # noqa: E402
from models.surrogate.tiers import load                                # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore:.*epoch budget", "ignore:.*unstamped provenance")

XS = np.linspace(0, 1, 40, dtype="f4")


def _spec():
    return SurrogateSpec(name="don", use_mode="online_inference", tier="S2",
                         input_names=("a", "b"), input_lower=(0.0,) * 2, input_upper=(1.0,) * 2,
                         targets=(TargetSpec("u"),), provenance=Provenance(model="test"))


def _theta(n, seed):
    return np.random.default_rng(seed).uniform(0, 1, size=(n, 2))


def _u(X, x):
    return (X[:, [0]] * np.sin(2 * np.pi * x[None, :] * (1 + 0.5 * X[:, [1]])))[:, None].astype("f4")


def test_it_predicts_at_coordinates_it_NEVER_saw():
    X, Xt = _theta(120, 0), _theta(30, 1)
    m = DeepONetEmulator(_spec(), coord_dim=1, basis=32, epochs=500, patience=80).fit(
        X, coords=XS, values=_u(X, XS))
    xq = np.random.default_rng(2).uniform(0, 1, 97).astype("f4")
    score = per_case_channel_r2(_u(Xt, xq), m.predict_at(Xt, xq), 0.9, ["u"])["u"]
    assert score["r2"] > 0.9, score


def test_OPERATOR_MODE_generalises_to_input_functions_it_never_saw():
    rng = np.random.default_rng(0)
    sensors = np.linspace(0, 1, 16)

    def cases(n):
        c = rng.normal(size=(n, 3))
        a = (c[:, [0]] * np.sin(np.pi * sensors) + c[:, [1]] * np.cos(np.pi * sensors) + c[:, [2]])
        X = rng.uniform(0, 1, size=(n, 2))

        def u(x):
            g = c[:, [0]] * np.sin(np.pi * x) + c[:, [1]] * np.cos(np.pi * x) + c[:, [2]]
            return ((0.5 + X[:, [0]]) * g)[:, None].astype("f4")
        return X, a[:, None].astype("f4"), u

    X, A, u = cases(120)
    m = DeepONetEmulator(_spec(), coord_dim=1, input_function_names=["a"], n_sensors=16, basis=32,
                         epochs=500, patience=80).fit(X, coords=XS, values=u(XS), input_functions=A)
    Xt, At, ut = cases(30)
    xq = rng.uniform(0, 1, 60).astype("f4")
    score = per_case_channel_r2(ut(xq), m.predict_at(Xt, xq, input_functions=At), 0.9, ["u"])["u"]
    assert score["r2"] > 0.8, score


def test_a_point_queried_ALONE_matches_the_same_point_queried_in_a_set():
    X = _theta(20, 0)
    m = DeepONetEmulator(_spec(), coord_dim=1, basis=8, epochs=5, patience=10).fit(
        X, coords=XS, values=_u(X, XS))
    together = m.predict_at(X[:3], XS)
    alone = m.predict_at(X[:3], XS[[7]])
    assert np.allclose(together[:, :, 7:8], alone, atol=1e-6)


def test_it_round_trips_through_the_GENERIC_loader(tmp_path):
    X = _theta(20, 0)
    m = DeepONetEmulator(_spec(), coord_dim=1, basis=8, epochs=5, patience=10).fit(
        X, coords=XS, values=_u(X, XS))
    m.save(tmp_path / "art")
    back = load(tmp_path / "art", strict=False)
    assert isinstance(back, DeepONetEmulator)
    q = np.array([0.013, 0.5, 0.97], dtype="f4")
    assert np.array_equal(m.predict_at(X[:3], q), back.predict_at(X[:3], q))
    assert np.array_equal(m.predict_batch(X[:3]).values, back.predict_batch(X[:3]).values)


def test_refusals():
    with pytest.raises(ValueError, match="together"):
        DeepONetEmulator(_spec(), coord_dim=1, input_function_names=["a"])
    m = DeepONetEmulator(_spec(), coord_dim=2)
    X = _theta(10, 0)
    with pytest.raises(ValueError, match="coords must be"):
        m.fit(X, coords=XS, values=_u(X, XS))
    m1 = DeepONetEmulator(_spec(), coord_dim=1)
    with pytest.raises(ValueError, match="values must be"):
        m1.fit(X, coords=XS, values=_u(X, XS)[:, :, :-1])
    with pytest.raises(ValueError, match="declares none"):
        m1.fit(X, coords=XS, values=_u(X, XS), input_functions=np.zeros((10, 1, 4), "f4"))
