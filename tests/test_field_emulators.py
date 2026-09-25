"""FieldEmulator: theta [+ input fields] -> gridded output fields (cnn, unet, fno).

What is guarded, and why:
  * each architecture LEARNS a theta-dependent field, scored WITHIN each case over its own grid
    (a pooled score would reward placing each case's level and nothing else);
  * the FNO evaluates on a grid it was NOT trained on -- the operator property that justifies it;
  * in operator mode the emulator actually USES its input field: change the field, the output moves;
  * an admissibility clamp is refused on an S2 spec and honoured on an S3 one, which is how the tier
    ladder separates knowledge from data;
  * the artifact round-trips through the GENERIC loader, `tiers.load`.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="FieldEmulator needs torch")

from models.surrogate._nn import per_case_channel_r2                     # noqa: E402
from models.surrogate.fields import FieldEmulator                        # noqa: E402
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec  # noqa: E402
from models.surrogate.tiers import load                                  # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore:.*epoch budget", "ignore:.*unstamped provenance")


def _spec(names=("u",), tier="S2", p=2):
    return SurrogateSpec(name="field", use_mode="online_inference", tier=tier,
                         input_names=tuple(f"x{i}" for i in range(p)), input_lower=(0.0,) * p,
                         input_upper=(1.0,) * p, targets=tuple(TargetSpec(n) for n in names),
                         provenance=Provenance(model="test"))


def _profile(X, n):
    x = np.linspace(0.0, 1.0, n)
    u = X[:, [0]] * np.sin(2 * np.pi * x[None, :]) + X[:, [1]] * np.cos(2 * np.pi * x[None, :])
    return u[:, None, :].astype("f4")


def _theta(n, seed):
    return np.random.default_rng(seed).uniform(0.0, 1.0, size=(n, 2))


@pytest.mark.parametrize("arch", ["cnn", "unet", "fno"])
def test_each_architecture_LEARNS_a_theta_dependent_profile(arch):
    X, Xt = _theta(60, 0), _theta(30, 1)
    m = FieldEmulator(_spec(), grid_shape=(24,), arch=arch, width=16, depth=2, modes=6,
                      epochs=120, patience=30).fit(X, fields=_profile(X, 24))
    score = per_case_channel_r2(_profile(Xt, 24), m.predict_fields(Xt), 0.9, ["u"])["u"]
    assert score["r2"] > 0.8, (arch, score)


@pytest.mark.parametrize("arch", ["cnn", "unet", "fno"])
def test_each_architecture_runs_on_a_2D_grid(arch):
    X = _theta(12, 0)
    g = np.linspace(0, 1, 10)
    F = np.stack([np.outer(np.sin(np.pi * a * g), np.cos(np.pi * b * g)) for a, b in X])[:, None]
    m = FieldEmulator(_spec(), grid_shape=(10, 10), arch=arch, width=8, depth=2, modes=3,
                      epochs=3, patience=10).fit(X, fields=F.astype("f4"))
    P = m.predict_fields(X[:4])
    assert P.shape == (4, 1, 10, 10) and np.isfinite(P).all()


def test_the_FNO_evaluates_on_a_grid_it_was_NOT_trained_on():
    X, Xt = _theta(60, 5), _theta(30, 6)
    m = FieldEmulator(_spec(), grid_shape=(24,), arch="fno", width=24, depth=3, modes=6,
                      epochs=150, patience=40).fit(X, fields=_profile(X, 24))
    for n in (48, 96):
        score = per_case_channel_r2(_profile(Xt, n), m.predict_fields(Xt, grid_shape=(n,)),
                                    0.9, ["u"])["u"]
        assert score["r2"] > 0.9, (n, score)


def test_operator_mode_USES_the_input_field():
    """u = (0.5 + theta_0) * a(x) with a different random smooth a in every case."""
    rng = np.random.default_rng(0)
    x = np.linspace(0, 1, 24)

    def fields(n):
        c = rng.normal(size=(n, 2))
        a = (c[:, [0]] * np.sin(np.pi * x) + c[:, [1]] * np.cos(np.pi * x))[:, None].astype("f4")
        X = rng.uniform(0, 1, size=(n, 2))
        return X, a, ((0.5 + X[:, [0]])[:, :, None] * a).astype("f4")

    X, A, U = fields(80)
    m = FieldEmulator(_spec(), grid_shape=(24,), arch="fno", input_field_names=["a"], width=16,
                      depth=2, modes=6, epochs=150, patience=40).fit(X, fields=U, input_fields=A)
    Xt, At, Ut = fields(30)
    score = per_case_channel_r2(Ut, m.predict_fields(Xt, input_fields=At), 0.9, ["u"])["u"]
    assert score["r2"] > 0.8, score
    moved = np.abs(m.predict_fields(Xt[:5], input_fields=At[:5])
                   - m.predict_fields(Xt[:5], input_fields=-At[:5])).mean()
    assert moved > 0.1, "flipping the input field barely moved the output"


def test_a_clamp_is_REFUSED_on_S2_and_HONOURED_on_S3():
    with pytest.raises(ValueError, match="tier S3"):
        FieldEmulator(_spec(tier="S2"), grid_shape=(16,), nonneg=["u"])
    X = _theta(20, 0)
    F = _profile(X, 16) - 0.5                           # plenty of negative truth to clamp
    m = FieldEmulator(_spec(tier="S3"), grid_shape=(16,), arch="cnn", nonneg=["u"], width=8,
                      depth=2, epochs=5, patience=10).fit(X, fields=F)
    assert (m.predict_fields(X) >= 0).all()


def test_refusals():
    X = _theta(10, 0)
    with pytest.raises(ValueError, match="arch must be"):
        FieldEmulator(_spec(), grid_shape=(16,), arch="vit")
    with pytest.raises(ValueError, match="1 or 2 spatial"):
        FieldEmulator(_spec(), grid_shape=(8, 8, 8))
    with pytest.raises(ValueError, match="structured output"):
        FieldEmulator(_spec(tier="S1"), grid_shape=(16,))
    m = FieldEmulator(_spec(), grid_shape=(16,))
    with pytest.raises(ValueError, match="fields must be"):
        m.fit(X, fields=_profile(X, 12))
    with pytest.raises(ValueError, match="needs `fields`"):
        m.fit(X)
    with pytest.raises(ValueError, match="declares no input_field_names"):
        m.fit(X, fields=_profile(X, 16), input_fields=_profile(X, 16))
    bad = _profile(X, 16)
    bad[2, 0, 3] = np.nan
    with pytest.raises(ValueError, match="declared viable contain NaN"):
        m.fit(X, fields=bad, viable=np.ones(10, bool))


def test_it_round_trips_through_the_GENERIC_loader(tmp_path):
    X = _theta(20, 0)
    m = FieldEmulator(_spec(), grid_shape=(16,), arch="unet", width=8, depth=2, epochs=3,
                      patience=10).fit(X, fields=_profile(X, 16))
    m.save(tmp_path / "art")
    back = load(tmp_path / "art", strict=False)
    assert isinstance(back, FieldEmulator) and back.arch == "unet"
    assert np.array_equal(m.predict_fields(X[:4]), back.predict_fields(X[:4]))
    assert np.array_equal(m.predict_batch(X[:4]).values, back.predict_batch(X[:4]).values)
