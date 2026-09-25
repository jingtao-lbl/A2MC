"""SpatioTemporalEmulator: theta + drivers(t) -> fields over time (convlstm, fno).

Two properties decide whether this is an emulator at all, and both are asserted directly:

  * CAUSALITY. Two driver records identical up to step k must give identical predictions up to k.
    A space-time Fourier operator fails this -- the negative control shows it -- and the failure is
    invisible in any whole-record accuracy score, because seeing the future simply scores better.
  * STATE CARRIED ACROSS CHUNKS. Training windows are short, but a driver at step 0 must still be
    able to reach the last step, because a state reset at a window edge discards the record's
    memory there.
"""
from __future__ import annotations

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="SpatioTemporalEmulator needs torch")

from models.surrogate._nn import blocks, per_case_channel_r2                   # noqa: E402
from models.surrogate.spatiotemporal import SpatioTemporalEmulator             # noqa: E402
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec        # noqa: E402
from models.surrogate.tiers import load                                        # noqa: E402

pytestmark = pytest.mark.filterwarnings("ignore:.*epoch budget", "ignore:.*unstamped provenance")

L, D = 12, 16


def _spec(tier="S2"):
    return SurrogateSpec(name="st", use_mode="online_inference", tier=tier,
                         input_names=("a", "b"), input_lower=(0.0,) * 2, input_upper=(1.0,) * 2,
                         targets=(TargetSpec("u"),), provenance=Provenance(model="test"))


def _drivers(seed=0):
    rng = np.random.default_rng(seed)
    return np.column_stack([np.abs(np.sin(np.arange(D) / 3.0)) + 0.2 * rng.random(D),
                            rng.random(D)]).astype("f4")


def _simulate(X, drv):
    """A recurrent field: decay set by theta_1, a source whose position is set by theta_0."""
    x = np.linspace(0, 1, L)
    out = np.zeros((len(X), 1, len(drv), L), "f4")
    for i, (a, b) in enumerate(X):
        u = np.zeros(L)
        prof = np.exp(-((x - (0.2 + 0.6 * a)) ** 2) / 0.02)
        for t in range(len(drv)):
            u = (0.6 + 0.35 * b) * u + drv[t, 0] * prof + 0.1 * drv[t, 1]
            out[i, 0, t] = u
    return out


def _theta(n, seed):
    return np.random.default_rng(seed).uniform(0, 1, size=(n, 2))


def _fit(arch, epochs=40, **kw):
    X, drv = _theta(40, 1), _drivers()
    kw.setdefault("chunk_steps", 4)
    return SpatioTemporalEmulator(_spec(), grid_shape=(L,), driver_names=["d0", "d1"], arch=arch,
                                  width=12, modes=4, epochs=epochs, patience=15, batch_size=8,
                                  **kw).fit(X, fields=_simulate(X, drv), drivers=drv), drv


@pytest.mark.parametrize("arch", ["convlstm", "fno"])
def test_each_architecture_LEARNS_a_driven_field(arch):
    m, drv = _fit(arch, epochs=50)
    Xt = _theta(20, 2)
    score = per_case_channel_r2(_simulate(Xt, drv), m.predict_fields(Xt, drv), 0.9, ["u"])["u"]
    assert score["r2"] > 0.8, (arch, score)


@pytest.mark.parametrize("arch", ["convlstm", "fno"])
def test_it_is_CAUSAL_so_a_step_cannot_see_its_future(arch):
    m, drv = _fit(arch, epochs=2)
    k = 8
    later = drv.copy()
    later[k:] = later[k:] * 3.0 + 1.0
    X = _theta(3, 3)
    a, b = m.predict_fields(X, drv), m.predict_fields(X, later)
    assert np.array_equal(a[:, :, :k], b[:, :, :k]), "a step saw its own future"
    assert not np.allclose(a[:, :, k:], b[:, :, k:]), "the change had no effect at all; test is inert"


def test_a_SPACE_TIME_Fourier_operator_WOULD_fail_that_test():
    """Negative control: a Fourier layer over the (time, space) block mixes every step with every
    other, so a change confined to late steps moves the early ones.
    """
    torch.manual_seed(0)
    layer = blocks().SpectralConv(2, 2, modes=4, ndim=2)
    x = torch.randn(1, 2, D, L)
    y = x.clone()
    y[:, :, 8:] = y[:, :, 8:] * 3.0 + 1.0
    with torch.no_grad():
        assert not torch.allclose(layer(x)[:, :, :8], layer(y)[:, :, :8], atol=1e-5)


@pytest.mark.parametrize("arch", ["convlstm", "fno"])
def test_the_STATE_IS_CARRIED_across_training_chunk_boundaries(arch):
    """chunk_steps=4 over 16 steps: a driver change at step 0 must still reach step 15."""
    m, drv = _fit(arch, epochs=2, chunk_steps=4)
    early = drv.copy()
    early[0] = early[0] * 5.0 + 2.0
    X = _theta(3, 4)
    a, b = m.predict_fields(X, drv), m.predict_fields(X, early)
    assert np.abs(a[:, :, -1] - b[:, :, -1]).max() > 1e-6, "step 0 cannot reach the last step"


def test_it_round_trips_through_the_GENERIC_loader(tmp_path):
    m, drv = _fit("fno", epochs=2)
    m.save(tmp_path / "art")
    back = load(tmp_path / "art", strict=False)
    assert isinstance(back, SpatioTemporalEmulator) and back.arch == "fno"
    X = _theta(3, 5)
    assert np.array_equal(m.predict_fields(X, drv), back.predict_fields(X, drv))


def test_refusals():
    with pytest.raises(ValueError, match="driver_names"):
        SpatioTemporalEmulator(_spec(), grid_shape=(L,), driver_names=[])
    with pytest.raises(ValueError, match="positive odd"):
        SpatioTemporalEmulator(_spec(), grid_shape=(L,), driver_names=["d"], kernel=4)
    with pytest.raises(ValueError, match="arch must be"):
        SpatioTemporalEmulator(_spec(), grid_shape=(L,), driver_names=["d"], arch="transformer")
    m = SpatioTemporalEmulator(_spec(), grid_shape=(L,), driver_names=["d0", "d1"])
    X, drv = _theta(6, 0), _drivers()
    with pytest.raises(ValueError, match="fields must be"):
        m.fit(X, fields=_simulate(X, drv)[:, :, :-1], drivers=drv)
    with pytest.raises(ValueError, match="drivers must be"):
        m.fit(X, fields=_simulate(X, drv), drivers=drv[:, :1])
    fitted, drv = _fit("convlstm", epochs=1)
    with pytest.raises(ValueError, match="needs `drivers`"):
        fitted.predict_batch(_theta(2, 0))
