"""The shared training loop and the spectral layer every structured-output emulator builds on.

Two ways a fit can LOOK finished and not be are guarded here, because an emulator inherits both:

  * the epoch budget runs out while validation loss is still falling -- `fit_torch` must say so,
    because a best epoch at the end of the budget means the budget, not the data, ended the fit;
  * validation loss is NaN -- `fit_torch` must refuse, because a NaN never beats the best
    checkpoint and the last epoch would be returned silently.

The spectral layer is guarded for the property that makes an FNO an OPERATOR: on a band-limited
periodic input, the same weights give the same answer at shared points on a finer grid. A
convolution indexed by cells has no such property, and the negative control shows the test can tell
the two apart.
"""
from __future__ import annotations

import warnings

import numpy as np
import pytest

torch = pytest.importorskip("torch", reason="the structured emulators need torch")

from models.surrogate._nn import (blocks, fit_torch, per_case_channel_r2,  # noqa: E402
                                  validation_split)


def _quadratic_net():
    net = torch.nn.Linear(1, 1, bias=False)
    with torch.no_grad():
        net.weight.fill_(5.0)
    return net


def _fit(net, epochs, patience, target=0.0, lr=0.01):
    x = torch.ones(8, 1)
    y = torch.full((8, 1), target)
    loss = lambda _: torch.nn.functional.mse_loss(net(x), y)
    return fit_torch(net, train_batches=lambda ep: [0], val_batches=lambda: [0], batch_loss=loss,
                     epochs=epochs, lr=lr, patience=patience, label="probe")


def test_a_fit_STOPPED_BY_ITS_BUDGET_while_still_improving_is_WARNED():
    """Plain gradient descent on a quadratic improves every epoch, so the best epoch is the last."""
    with pytest.warns(RuntimeWarning, match="epoch budget stopped this fit"):
        _, info = _fit(_quadratic_net(), epochs=5, patience=10)
    assert info["best_epoch"] == 4 and not info["stopped_by_patience"]


def test_a_fit_stopped_by_PATIENCE_is_not_warned():
    """Once the loss has settled, patience ends the fit and there is nothing to warn about."""
    net = _quadratic_net()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _, info = _fit(net, epochs=4000, patience=5, lr=0.5)
    assert not [w for w in caught if "epoch budget" in str(w.message)]
    assert info["stopped_by_patience"]
    assert info["best_epoch"] < info["stopped_epoch"]


def test_a_NaN_validation_loss_is_REFUSED():
    net = _quadratic_net()
    with pytest.raises(FloatingPointError, match="validation loss is nan"):
        _fit(net, epochs=3, patience=None, target=float("nan"))


def test_the_best_checkpoint_is_RESTORED_not_the_last_epoch():
    """Training pulls the weight toward -5 while validation scores distance to +5, so validation is
    best after the FIRST epoch and worse every epoch after. What comes back must be that epoch's
    weight: 5.0 minus Adam's first step of exactly lr = 0.5, not the far-travelled last one.
    """
    net = _quadratic_net()
    x = torch.ones(4, 1)

    def batch_loss(_):
        aim = -5.0 if net.training else 5.0
        return torch.nn.functional.mse_loss(net(x), torch.full((4, 1), aim))

    _, info = fit_torch(net, train_batches=lambda ep: [0], val_batches=lambda: [0],
                        batch_loss=batch_loss, epochs=6, lr=0.5, patience=None, label="probe")
    assert info["best_epoch"] == 0
    assert float(net.weight.detach()) == pytest.approx(4.5, abs=1e-4)


def test_validation_split_refuses_a_split_that_leaves_a_side_empty():
    with pytest.raises(ValueError):
        validation_split(1, 0.2, 0)
    with pytest.raises(ValueError):
        validation_split(10, 0.0, 0)
    tr, va = validation_split(10, 0.99, 0)
    assert len(tr) >= 1 and len(va) >= 1 and not set(tr) & set(va)


def _periodic(S):
    axes = [torch.arange(n, dtype=torch.float32) / n for n in S]
    return torch.stack(torch.meshgrid(*axes, indexing="ij"))


@pytest.mark.parametrize("S", [(32,), (12, 20)])
def test_the_SPECTRAL_LAYER_gives_the_same_answer_on_a_finer_grid(S):
    """The operator property. The fine grid contains every coarse point, so they can be compared
    exactly, with no interpolation to blame.
    """
    torch.manual_seed(0)
    layer = blocks().SpectralConv(2, 3, modes=5, ndim=len(S))
    fine = tuple(2 * s for s in S)

    def band_limited(shape):
        g = _periodic(shape)
        v = torch.sin(2 * np.pi * g[0])
        if len(shape) == 2:
            v = v * torch.cos(2 * np.pi * g[1])
        return v[None, None].repeat(1, 2, *([1] * len(shape)))

    with torch.no_grad():
        a = layer(band_limited(S))
        b = layer(band_limited(fine))
    shared = b[(Ellipsis,) + tuple(slice(None, None, 2) for _ in S)]
    assert torch.allclose(a, shared, atol=1e-5)


def test_a_CELL_INDEXED_convolution_WOULD_fail_that_test():
    """Negative control: a kernel that spans five CELLS spans half the physical width on a grid
    twice as fine, so it computes a different function.
    """
    torch.manual_seed(0)
    conv = torch.nn.Conv1d(2, 3, 5, padding=2, padding_mode="circular")
    g1, g2 = _periodic((32,)), _periodic((64,))
    with torch.no_grad():
        a = conv(torch.sin(2 * np.pi * g1[0])[None, None].repeat(1, 2, 1))
        b = conv(torch.sin(2 * np.pi * g2[0])[None, None].repeat(1, 2, 1))
    assert not torch.allclose(a, b[..., ::2], atol=1e-3)


def test_per_case_channel_r2_normalises_WITHIN_each_case():
    """A prediction that places each case's LEVEL but not its shape scores near 1 pooled and ~0
    within case; the within-case score is the one a structured emulator must be judged by.
    """
    rng = np.random.default_rng(0)
    levels = rng.uniform(0, 100, size=(20, 1, 1))
    shape = rng.normal(size=(20, 1, 50))
    truth = levels + shape
    pred = levels + 0.0 * shape                    # right level, flat shape
    block = per_case_channel_r2(truth, pred, min_r2=0.9, names=["u"])["u"]
    assert block["r2_normalisation"] == "within_case"
    assert block["r2"] < 0.1
    pooled = 1 - ((truth - pred) ** 2).mean() / truth.var()
    assert pooled > 0.9
