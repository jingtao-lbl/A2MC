"""Shared torch machinery for the structured-output emulators.

`multioutput`, `fields`, `spatiotemporal`, `graphs` and `operators` all train a torch network on
standardised data, select a checkpoint on validation loss and rebuild the network on load. The
pieces they share live here so each of those modules states only what makes its architecture
different.

torch is imported INSIDE functions, never at module import, so `models.surrogate` keeps importing
with no torch installed. Classes that subclass `nn.Module` are therefore created by factory
functions and cached, the same seam `sequence.py` uses inside `_build`.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import math
import warnings
from types import SimpleNamespace
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np


# =============================================================================
# Devices
# =============================================================================

def resolve_device(device: Optional[str]) -> str:
    """`None` means cuda when present, else cpu."""
    if device:
        return str(device)
    import torch
    return "cuda" if torch.cuda.is_available() else "cpu"


def reload_device(requested: Optional[str], fit_device: Optional[str]) -> str:
    """The device a saved network is rebuilt on.

    Defaults to the device it was FITTED on, because cuDNN's kernels and the CPU's do not agree bit
    for bit: a reload that silently changes device predicts slightly differently from the artifact
    that was scored. When that device is not available, fall back to cpu and say so.
    """
    import torch
    if requested:
        return str(requested)
    want = fit_device or "cpu"
    if want.startswith("cuda") and not torch.cuda.is_available():
        warnings.warn(
            f"this network was fitted on {want!r}, which is not available here; reloading on cpu. "
            "Predictions can differ slightly from the fitted artifact's.", RuntimeWarning)
        return "cpu"
    return want


# =============================================================================
# Validation split and the training loop
# =============================================================================

def validation_split(n: int, val_fraction: float, random_state: int) -> Tuple[np.ndarray, np.ndarray]:
    """(train_idx, val_idx) over n cases. Refuses a split that leaves either side empty."""
    if not 0.0 < val_fraction < 1.0:
        raise ValueError(f"val_fraction must be in (0, 1), got {val_fraction}")
    if n < 2:
        raise ValueError(f"need at least 2 viable cases to hold one out for validation, got {n}")
    idx = np.random.default_rng(random_state).permutation(n)
    n_val = min(n - 1, max(1, int(round(val_fraction * n))))
    return idx[n_val:], idx[:n_val]


def minibatches(idx: np.ndarray, batch_size: int, rng: Optional[np.random.Generator] = None) -> List[np.ndarray]:
    idx = np.array(idx, copy=True)
    if rng is not None:
        rng.shuffle(idx)
    return [idx[a:a + batch_size] for a in range(0, len(idx), batch_size)]


def fit_torch(net: Any, *, train_batches: Callable[[int], Iterable[Any]],
              val_batches: Callable[[], Iterable[Any]],
              batch_loss: Callable[[Any], Any], epochs: int, lr: float,
              weight_decay: float = 0.0, patience: Optional[int] = None,
              clip_norm: Optional[float] = 5.0, verbose: bool = False,
              label: str = "emulator",
              step_hook: Optional[Callable[[Any], Iterable[Any]]] = None) -> Tuple[List[Dict[str, float]], Dict[str, Any]]:
    """Adam, best-validation checkpoint, optional patience. Returns (history, info).

    ``train_batches(epoch)`` and ``val_batches()`` yield batches; ``batch_loss(batch)`` returns a
    scalar tensor. The VALIDATION CRITERION IS THE TRAINING LOSS, so the checkpoint is chosen on the
    objective being minimised. A validation loss that leaves out terms the training loss carries
    selects a different checkpoint than the one the fit was driving towards.

    ``step_hook(batch)``, when given, replaces the single forward-backward per batch: it yields one
    loss tensor per optimiser step. A recurrent emulator uses it to step once per time window while
    carrying state between windows.

    Two ways a fit can look finished and not be, both reported rather than hidden:

      * validation loss is NaN -- refused, because a NaN never beats `best`, so the checkpoint
        would silently stay at "none" and the last epoch would be returned;
      * the epoch budget ran out while validation loss was still improving -- warned, with the
        best epoch, because a best epoch at the end of the budget means the fit was stopped by the
        budget and not by the data.
    """
    import torch

    opt = torch.optim.Adam(net.parameters(), lr=lr, weight_decay=weight_decay)
    best, best_state, best_epoch, since = math.inf, None, -1, 0
    history: List[Dict[str, float]] = []
    stopped_by_patience = False

    for ep in range(epochs):
        net.train()
        tot, nb = 0.0, 0
        for b in train_batches(ep):
            losses = step_hook(b) if step_hook is not None else (batch_loss(b),)
            for loss in losses:
                opt.zero_grad()
                loss.backward()
                if clip_norm:
                    torch.nn.utils.clip_grad_norm_(net.parameters(), clip_norm)
                opt.step()
                tot += float(loss.detach())
                nb += 1
        net.eval()
        with torch.no_grad():
            vals = [float(batch_loss(b)) for b in val_batches()]
        vl = float(np.mean(vals)) if vals else math.nan
        if not math.isfinite(vl):
            raise FloatingPointError(
                f"{label}: validation loss is {vl} at epoch {ep}. A non-finite validation loss "
                "never improves on the best checkpoint, so continuing would return the last epoch "
                "silently. Check the viable rows for NaN outputs and the inputs for NaN or inf.")
        history.append({"epoch": ep, "train": tot / max(nb, 1), "val": vl})
        if vl < best:
            best, best_epoch, since = vl, ep, 0
            best_state = {k: v.detach().clone() for k, v in net.state_dict().items()}
        else:
            since += 1
        if verbose and (ep % 10 == 0 or ep == epochs - 1):
            print(f"  [{label}] epoch {ep:4d}  train {tot / max(nb, 1):.5f}  val {vl:.5f}", flush=True)
        if patience and since >= patience:
            stopped_by_patience = True
            break

    if best_state is not None:
        net.load_state_dict(best_state)
    stopped = history[-1]["epoch"] if history else -1
    if not stopped_by_patience and best_epoch == stopped:
        warnings.warn(
            f"{label}: validation loss was still improving at the last epoch ({stopped} of "
            f"{epochs}); the epoch budget stopped this fit, not the data. Raise `epochs`.",
            RuntimeWarning)
    info = {"best_epoch": best_epoch, "stopped_epoch": stopped, "best_val": best,
            "stopped_by_patience": stopped_by_patience, "epochs_budget": epochs}
    return history, info


# =============================================================================
# Standardisation
# =============================================================================

def channel_stats(a: np.ndarray, channel_axis: int = 1) -> Tuple[np.ndarray, np.ndarray]:
    """Per-channel mean and sd over every OTHER axis, shaped to broadcast against `a`."""
    axes = tuple(i for i in range(a.ndim) if i != channel_axis)
    mu = np.nanmean(a, axis=axes, keepdims=True)
    sd = np.nanstd(a, axis=axes, keepdims=True)
    sd = np.where(sd < 1e-12, 1.0, sd)
    return mu.astype("f4"), sd.astype("f4")


def column_stats(a: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Per-column mean and sd of a 2-D array, shaped (1, P)."""
    mu = np.nanmean(a, axis=0, keepdims=True)
    sd = np.nanstd(a, axis=0, keepdims=True)
    sd = np.where(sd < 1e-12, 1.0, sd)
    return mu.astype("f4"), sd.astype("f4")


def refuse_nonfinite(name: str, a: np.ndarray, rows: Optional[np.ndarray] = None) -> None:
    """Refuse NaN or inf inside rows declared viable.

    A NaN target in a viable row makes every loss NaN, and every prediction NaN, while `fit` and
    `save` return normally. Refusing here names the rows instead.
    """
    bad = ~np.isfinite(a.reshape(len(a), -1)).all(axis=1)
    if bad.any():
        which = np.flatnonzero(bad)[:10] if rows is None else np.asarray(rows)[np.flatnonzero(bad)][:10]
        raise ValueError(
            f"{name}: {int(bad.sum())} row(s) declared viable contain NaN or inf (first: "
            f"{which.tolist()}). Mark them non-viable, or repair the extraction; a NaN target "
            "turns every loss and every prediction into NaN without raising.")


# =============================================================================
# Grids
# =============================================================================

def coord_grid(shape: Sequence[int]) -> np.ndarray:
    """(ndim, *shape) coordinates in [0, 1] along each axis.

    Normalised to the unit interval rather than to cell indices so a network conditioned on them
    sees the same coordinate for the same physical position at any resolution, which is what lets a
    Fourier neural operator be evaluated on a grid it was not trained on.
    """
    axes = [np.linspace(0.0, 1.0, int(n), dtype="f4") for n in shape]
    return np.stack(np.meshgrid(*axes, indexing="ij"), axis=0).astype("f4")


def check_grid_shape(grid_shape: Sequence[int], min_size: int = 4) -> Tuple[int, ...]:
    g = tuple(int(s) for s in grid_shape)
    if len(g) not in (1, 2):
        raise ValueError(f"grid_shape must have 1 or 2 spatial dimensions, got {g}")
    if any(s < min_size for s in g):
        raise ValueError(f"every grid dimension must be at least {min_size}, got {g}")
    return g


# =============================================================================
# torch building blocks
# =============================================================================

_BLOCKS: Optional[SimpleNamespace] = None


def blocks() -> SimpleNamespace:
    """Import torch and return the shared `nn.Module` classes (cached)."""
    global _BLOCKS
    if _BLOCKS is not None:
        return _BLOCKS

    import torch
    from torch import nn
    import torch.nn.functional as F

    def conv(ndim: int):
        return {1: nn.Conv1d, 2: nn.Conv2d, 3: nn.Conv3d}[ndim]

    class SpectralConv(nn.Module):
        """Fourier-space linear layer over 1, 2 or 3 trailing spatial axes (Li et al., 2021).

        Keeps the lowest `modes` frequencies per axis: the symmetric band 0..m-1 and -(m-1)..-1 on
        every axis but the last, and 0..m-1 on the last, which `rfftn` stores one-sided. The weight
        tensor is indexed by FREQUENCY, not by grid cell, so the same weights apply at any
        resolution; on a grid too small to hold `modes`, the band is clipped to what the grid can
        represent. Default fft normalisation makes the transform pair resolution-consistent:
        `rfftn` sums over cells and `irfftn` divides by their number.
        """

        def __init__(self, c_in: int, c_out: int, modes: int, ndim: int):
            super().__init__()
            self.c_in, self.c_out, self.modes, self.ndim = c_in, c_out, int(modes), ndim
            shape = (c_in, c_out) + (2 * self.modes - 1,) * (ndim - 1) + (self.modes,)
            scale = 1.0 / (c_in * c_out)
            self.w_re = nn.Parameter(scale * torch.randn(shape))
            self.w_im = nn.Parameter(scale * torch.randn(shape))

        def _kept(self, n: int, last: bool, device):
            m = self.modes
            if last:
                me = min(m, n // 2 + 1)
                i = torch.arange(me, device=device)
                return i, i
            me = min(m, (n + 1) // 2)
            pos = torch.arange(me, device=device)
            neg = torch.arange(1, me, device=device)
            data = torch.cat([pos, n - neg])
            weight = torch.cat([pos, (2 * m - 1) - neg])
            return data, weight

        def forward(self, x):
            S = tuple(x.shape[2:])
            d = len(S)
            dims = tuple(range(2, 2 + d))
            X = torch.fft.rfftn(x, dim=dims)
            kept = [self._kept(S[i], i == d - 1, x.device) for i in range(d)]
            grids = torch.meshgrid(*[k[0] for k in kept], indexing="ij")
            w = torch.complex(self.w_re, self.w_im)
            for i, (_, wi) in enumerate(kept):
                w = w.index_select(2 + i, wi)
            sel = (slice(None), slice(None)) + tuple(grids)
            Y = torch.einsum("bi...,io...->bo...", X[sel], w)
            out = torch.zeros((x.shape[0], self.c_out) + tuple(X.shape[2:]),
                              dtype=X.dtype, device=x.device)
            out[sel] = Y
            return torch.fft.irfftn(out, s=S, dim=dims).real

    class FNOLayer(nn.Module):
        """Spectral branch plus a pointwise branch, summed: the FNO layer's two paths."""

        def __init__(self, width: int, modes: int, ndim: int):
            super().__init__()
            self.spec = SpectralConv(width, width, modes, ndim)
            self.point = conv(ndim)(width, width, 1)

        def forward(self, x):
            return self.spec(x) + self.point(x)

    class MLP(nn.Module):
        def __init__(self, d_in: int, hidden: Sequence[int], d_out: int, act: str = "gelu"):
            super().__init__()
            A = {"gelu": nn.GELU, "tanh": nn.Tanh, "relu": nn.ReLU}[act]
            layers: List[Any] = []
            prev = d_in
            for h in hidden:
                layers += [nn.Linear(prev, int(h)), A()]
                prev = int(h)
            layers.append(nn.Linear(prev, d_out))
            self.net = nn.Sequential(*layers)

        def forward(self, x):
            return self.net(x)

    _BLOCKS = SimpleNamespace(torch=torch, nn=nn, F=F, conv=conv, SpectralConv=SpectralConv,
                              FNOLayer=FNOLayer, MLP=MLP)
    return _BLOCKS


def interp_mode(ndim: int) -> str:
    return {1: "linear", 2: "bilinear", 3: "trilinear"}[ndim]


# =============================================================================
# Reduction to the scalar interface
# =============================================================================

REDUCTIONS = ("mean", "sum", "max", "min")


def reduce_channels(a: np.ndarray, how: str) -> np.ndarray:
    """(N, C, ...) -> (N, C), over every axis after the channel axis, ignoring NaN."""
    if how not in REDUCTIONS:
        raise ValueError(f"reduce must be one of {REDUCTIONS}, got {how!r}")
    flat = a.reshape(a.shape[0], a.shape[1], -1)
    fn = {"mean": np.nanmean, "sum": np.nansum, "max": np.nanmax, "min": np.nanmin}[how]
    return fn(flat, axis=2)


def per_case_channel_r2(y_true: np.ndarray, y_pred: np.ndarray, min_r2: float,
                        names: Sequence[str]) -> Dict[str, Dict[str, Any]]:
    """Per-target acceptance blocks for a STRUCTURED output, normalised WITHIN each case.

    Every axis after the channel axis (space, time, nodes) is flattened, so each case is scored
    against its own mean over its own field. Pooling over cases would divide by the between-case
    spread, which a parameter sweep makes large, and would score a model that places only each
    case's level as nearly perfect. Built on `validate.summarise_per_case_r2`, so the blocks carry
    `r2_normalisation: within_case` and pass `require_r2_normalisation`.
    """
    from .validate import summarise_per_case_r2

    yt = np.asarray(y_true, dtype=float)
    yp = np.asarray(y_pred, dtype=float)
    if yt.shape != yp.shape:
        raise ValueError(f"shape mismatch {yt.shape} vs {yp.shape}")
    if yt.shape[1] != len(names):
        raise ValueError(f"{yt.shape[1]} channels but {len(names)} target names")
    out: Dict[str, Dict[str, Any]] = {}
    for j, n in enumerate(names):
        out[n] = summarise_per_case_r2(yt[:, j].reshape(len(yt), -1),
                                       yp[:, j].reshape(len(yp), -1), min_r2=min_r2)
    return out
