"""Emulators for SPATIOTEMPORAL fields: a gridded output that evolves in time under drivers.

    theta (N, P) + drivers (D, F) [+ static input fields (N or 1, C_in, *S)]
        ->  output fields (N, C, D, *S)

Two architectures, both RECURRENT IN TIME, so both are causal by construction:

  convlstm   a convolutional LSTM (Shi et al., 2015): LSTM gates computed by convolutions, so the
             hidden state is itself a field and spatial context enters through the kernel.
  fno        a Fourier recurrent cell: GRU gates computed by a Fourier neural operator layer plus a
             pointwise path, so the state update sees the whole field through its low frequencies
             and the trained cell transfers across grid resolution the way an FNO does.

WHY RECURRENT, not a Fourier operator over the space-time block. An FNO applied jointly over time
mixes every step with every other, so a prediction at step t reads the drivers after t. That is the
leak `sequence.py`'s transformer mask exists to prevent: invisible to any whole-record accuracy
score, and fatal to an artifact consumed step by step.

STATE IS CARRIED ACROSS CHUNKS. Training runs truncated back-propagation through time over windows
of `chunk_steps`, but the recurrent state flows from one window into the next (detached, so the
gradient is truncated and the memory is not). Prediction runs the whole record in one pass from the
first step, because a state reset at a window edge, or a prediction started from a zero state
part-way through a record, discards what the record had built up to that point.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .base import BatchPrediction, HullGate, SurrogateModel
from .fields import _check_structured_spec
from .spec import SurrogateSpec
from ._nn import (REDUCTIONS, blocks, channel_stats, check_grid_shape, column_stats, coord_grid,
                  fit_torch, minibatches, reduce_channels, refuse_nonfinite, reload_device,
                  resolve_device, validation_split)

VALID_ST_ARCHS = ("convlstm", "fno")


def _detach_state(state):
    return [tuple(t.detach() for t in s) if isinstance(s, tuple) else s.detach() for s in state]


class SpatioTemporalEmulator(SurrogateModel):
    """theta + drivers(t) [+ static fields] -> fields over time. See the module docstring."""

    def __init__(self, spec: SurrogateSpec, grid_shape: Sequence[int], driver_names: Sequence[str],
                 arch: str = "convlstm", input_field_names: Sequence[str] = (), width: int = 16,
                 layers: int = 1, modes: int = 6, kernel: int = 3,
                 chunk_steps: Optional[int] = None, nonneg: Optional[Sequence[str]] = None,
                 reduce: str = "mean", epochs: int = 100, batch_size: int = 8, lr: float = 1e-3,
                 weight_decay: float = 1e-5, val_fraction: float = 0.15, patience: int = 20,
                 random_state: int = 0, device: Optional[str] = None) -> None:
        self.nonneg = list(nonneg or [])
        self._names = _check_structured_spec(spec, self.nonneg, "SpatioTemporalEmulator")
        super().__init__(spec)
        self.grid_shape = check_grid_shape(grid_shape)
        arch = str(arch).lower()
        if arch not in VALID_ST_ARCHS:
            raise ValueError(f"arch must be one of {VALID_ST_ARCHS}, got {arch!r}")
        self.driver_names = list(driver_names)
        if not self.driver_names:
            raise ValueError("a spatiotemporal emulator is driven by drivers(t); `driver_names` is "
                             "empty. For a static field use FieldEmulator.")
        if min(int(width), int(layers), int(modes)) < 1:
            raise ValueError("width, layers and modes must all be at least 1")
        if int(kernel) < 1 or int(kernel) % 2 == 0:
            raise ValueError(f"kernel must be a positive odd integer, got {kernel}")
        if chunk_steps is not None and int(chunk_steps) < 1:
            raise ValueError(f"chunk_steps must be at least 1, got {chunk_steps}")
        if reduce not in REDUCTIONS:
            raise ValueError(f"reduce must be one of {REDUCTIONS}, got {reduce!r}")
        self.arch = arch
        self.input_field_names = list(input_field_names)
        self.width, self.layers, self.modes, self.kernel = int(width), int(layers), int(modes), int(kernel)
        self.chunk_steps = None if chunk_steps is None else int(chunk_steps)
        self.reduce = reduce
        self.epochs, self.batch_size, self.lr = int(epochs), int(batch_size), float(lr)
        self.weight_decay, self.val_fraction = float(weight_decay), float(val_fraction)
        self.patience, self.random_state, self.device = int(patience), int(random_state), device
        self._net: Any = None
        self._gate = HullGate()
        self.history: List[Dict[str, float]] = []
        self.info: Dict[str, Any] = {}
        self.n_viable_train = 0
        self._imu = self._isd = None

    @property
    def ndim(self) -> int:
        return len(self.grid_shape)

    # ---- network ----

    def _build(self, n_theta: int):
        B = blocks()
        torch, nn = B.torch, B.nn
        ndim, C, width, kernel, modes = self.ndim, len(self._names), self.width, self.kernel, self.modes
        conv = B.conv(ndim)
        n_in = ndim + n_theta + len(self.driver_names) + len(self.input_field_names)

        if self.arch == "convlstm":
            class Cell(nn.Module):
                def __init__(self, c_in: int, h: int):
                    super().__init__()
                    self.h = h
                    self.gates = conv(c_in + h, 4 * h, kernel, padding=kernel // 2)

                def zero(self, n, S, dev):
                    z = torch.zeros((n, self.h) + tuple(S), device=dev)
                    return (z, z.clone())

                def forward(self, x, state):
                    h, c = state
                    i, f, o, g = torch.chunk(self.gates(torch.cat([x, h], 1)), 4, dim=1)
                    c = torch.sigmoid(f) * c + torch.sigmoid(i) * torch.tanh(g)
                    h = torch.sigmoid(o) * torch.tanh(c)
                    return h, (h, c)
        else:
            class Cell(nn.Module):
                def __init__(self, c_in: int, h: int):
                    super().__init__()
                    self.h = h
                    d = c_in + h
                    self.zr = conv(d, 2 * h, 1)
                    self.zr_spec = B.SpectralConv(d, 2 * h, modes, ndim)
                    self.cand = conv(d, h, 1)
                    self.cand_spec = B.SpectralConv(d, h, modes, ndim)

                def zero(self, n, S, dev):
                    return torch.zeros((n, self.h) + tuple(S), device=dev)

                def forward(self, x, h):
                    xh = torch.cat([x, h], 1)
                    z, r = torch.chunk(torch.sigmoid(self.zr(xh) + self.zr_spec(xh)), 2, dim=1)
                    xr = torch.cat([x, r * h], 1)
                    cand = torch.tanh(self.cand(xr) + self.cand_spec(xr))
                    h = (1.0 - z) * h + z * cand
                    return h, h

        layers = self.layers

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.cells = nn.ModuleList([Cell(n_in if l == 0 else width, width) for l in range(layers)])
                self.head = conv(width, C, 1)

            def init_state(self, n, S, dev):
                return [c.zero(n, S, dev) for c in self.cells]

            def step(self, x, state):
                new, h = [], x
                for cell, st in zip(self.cells, state):
                    h, st = cell(h, st)
                    new.append(st)
                return self.head(h), new

        return Net()

    # ---- inputs ----

    def _static_fields(self, input_fields, n, S):
        cin = len(self.input_field_names)
        if cin == 0:
            if input_fields is not None:
                raise ValueError("input_fields given, but this emulator declares no input_field_names")
            return None
        if input_fields is None:
            raise ValueError(f"this emulator is conditioned on input fields {self.input_field_names}")
        a = np.asarray(input_fields, dtype="f4")
        if a.ndim != 2 + len(S) or a.shape[1] != cin or tuple(a.shape[2:]) != tuple(S) \
                or a.shape[0] not in (1, n):
            raise ValueError(f"input_fields must be (N or 1, {cin}, *{tuple(S)}), got {a.shape}")
        if not np.isfinite(a).all():
            raise ValueError("input_fields contain NaN or inf")
        return a

    def _drivers(self, drivers) -> np.ndarray:
        M = np.asarray(drivers, dtype="f4")
        if M.ndim != 2 or M.shape[1] != len(self.driver_names):
            raise ValueError(f"drivers must be (D, {len(self.driver_names)}) for {self.driver_names}, "
                             f"got {M.shape}")
        if not np.isfinite(M).all():
            raise ValueError("drivers contain NaN or inf")
        return M

    def _roll(self, torch, Xn_b, It_b, Mn_t, S, s, e, state, dev):
        """Run steps s..e-1 from `state`. Returns (pred (B, C, e-s, *S), state)."""
        n = Xn_b.shape[0]
        ndim = len(S)
        coords = torch.as_tensor(coord_grid(S), device=dev).unsqueeze(0).expand(n, ndim, *S)
        theta = Xn_b.view(n, -1, *([1] * ndim)).expand(n, Xn_b.shape[1], *S)
        parts = [coords, theta] + ([It_b] if It_b is not None else [])
        static = torch.cat(parts, 1)
        outs = []
        for t in range(s, e):
            drv = Mn_t[t].view(1, -1, *([1] * ndim)).expand(n, Mn_t.shape[1], *S)
            y, state = self._net.step(torch.cat([static, drv], 1), state)
            outs.append(y)
        return torch.stack(outs, 2), state

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: Optional[np.ndarray] = None,
            viable: Optional[np.ndarray] = None, fields: Optional[np.ndarray] = None,
            drivers: Optional[np.ndarray] = None, input_fields: Optional[np.ndarray] = None,
            verbose: bool = False) -> "SpatioTemporalEmulator":
        import torch
        import torch.nn.functional as F

        if fields is None or drivers is None:
            raise ValueError("SpatioTemporalEmulator.fit needs `fields` (N, C, D, *grid_shape) and "
                             "`drivers` (D, F); Y is unused")
        X = self._check_X(X)
        M = self._drivers(drivers)
        Fa = np.asarray(fields, dtype="f4")
        want = (len(X), len(self._names), M.shape[0]) + self.grid_shape
        if Fa.shape != want:
            raise ValueError(f"fields must be {want}, got {Fa.shape}")
        Ia = self._static_fields(input_fields, len(X), self.grid_shape)
        if viable is None:
            viable = np.isfinite(Fa.reshape(len(Fa), -1)).all(axis=1)
        viable = np.asarray(viable, dtype=bool)
        refuse_nonfinite("SpatioTemporalEmulator fields", Fa[viable], rows=np.flatnonzero(viable))
        Xv, Fv = X[viable], Fa[viable]
        Iv = None if Ia is None else (Ia if Ia.shape[0] == 1 else Ia[viable])
        self.n_viable_train = len(Xv)
        if self.n_viable_train < 4:
            raise ValueError(f"only {self.n_viable_train} viable cases; need >= 4")
        self._gate.fit(Xv)

        self._xmu, self._xsd = column_stats(Xv)
        self._mmu, self._msd = column_stats(M)
        self._fmu, self._fsd = channel_stats(Fv)
        if Iv is not None:
            self._imu, self._isd = channel_stats(Iv)
        dev = resolve_device(self.device)
        torch.manual_seed(self.random_state)
        self._net = self._build(Xv.shape[1]).to(dev)
        net = self._net
        Xt = torch.as_tensor(((Xv - self._xmu) / self._xsd).astype("f4"), device=dev)
        Mt = torch.as_tensor((M - self._mmu) / self._msd, device=dev)
        Ft = torch.as_tensor((Fv - self._fmu) / self._fsd, device=dev)
        It = None if Iv is None else torch.as_tensor((Iv - self._imu) / self._isd, device=dev)
        D, S = M.shape[0], self.grid_shape
        c = self.chunk_steps or D
        windows = [(s, min(s + c, D)) for s in range(0, D, c)]
        tr, va = validation_split(len(Xv), self.val_fraction, self.random_state)
        rng = np.random.default_rng(self.random_state)

        def it_of(ii):
            it = torch.as_tensor(ii, device=dev)
            ib = None if It is None else (It.expand(len(it), *It.shape[1:]) if It.shape[0] == 1 else It[it])
            return it, ib

        def windows_loss(ii):
            it, ib = it_of(ii)
            state = net.init_state(len(it), S, dev)
            for (s, e) in windows:
                pred, state = self._roll(torch, Xt[it], ib, Mt, S, s, e, state, dev)
                yield F.mse_loss(pred, Ft[it][:, :, s:e])
                state = _detach_state(state)

        def full_loss(ii):
            it, ib = it_of(ii)
            pred, _ = self._roll(torch, Xt[it], ib, Mt, S, 0, D, net.init_state(len(it), S, dev), dev)
            return F.mse_loss(pred, Ft[it])

        self.history, self.info = fit_torch(
            net, train_batches=lambda ep: minibatches(tr, self.batch_size, rng),
            val_batches=lambda: minibatches(va, self.batch_size), batch_loss=full_loss,
            step_hook=windows_loss, epochs=self.epochs, lr=self.lr,
            weight_decay=self.weight_decay, patience=self.patience, verbose=verbose,
            label=f"SpatioTemporalEmulator[{self.arch}]")
        self._fit_device = dev
        net.eval()
        self.fitted = True
        return self

    # ---- predict ----

    def predict_fields(self, X: np.ndarray, drivers: np.ndarray,
                       input_fields: Optional[np.ndarray] = None,
                       grid_shape: Optional[Sequence[int]] = None) -> np.ndarray:
        """(N, C, D, *S), the whole record in one pass with the state carried throughout."""
        import torch
        self._check_fitted()
        X = self._check_X(X)
        M = self._drivers(drivers)
        if grid_shape is not None:
            S = check_grid_shape(grid_shape)
        elif input_fields is not None:
            S = tuple(np.asarray(input_fields).shape[2:])
        else:
            S = self.grid_shape
        Ia = self._static_fields(input_fields, len(X), S)
        dev = next(self._net.parameters()).device
        Xn = torch.as_tensor(((X - self._xmu) / self._xsd).astype("f4"), device=dev)
        Mn = torch.as_tensor((M - self._mmu) / self._msd, device=dev)
        It = None if Ia is None else torch.as_tensor((Ia - self._imu) / self._isd, device=dev)
        out = np.empty((len(X), len(self._names), M.shape[0]) + tuple(S), dtype="f4")
        with torch.no_grad():
            for a in range(0, len(X), 16):
                it = torch.arange(a, min(a + 16, len(X)), device=dev)
                ib = None if It is None else (It.expand(len(it), *It.shape[1:]) if It.shape[0] == 1 else It[it])
                pred, _ = self._roll(torch, Xn[it], ib, Mn, S, 0, M.shape[0],
                                     self._net.init_state(len(it), S, dev), dev)
                out[a:a + len(it)] = pred.cpu().numpy()
        out = out * self._fsd + self._fmu
        for n in self.nonneg:
            j = self._names.index(n)
            np.clip(out[:, j], 0.0, None, out=out[:, j])
        return out

    def predict_batch(self, X: np.ndarray, drivers: Optional[np.ndarray] = None,
                      input_fields: Optional[np.ndarray] = None) -> BatchPrediction:
        if drivers is None:
            raise ValueError("SpatioTemporalEmulator.predict_batch needs `drivers`")
        X = self._check_X(X)
        vals = reduce_channels(self.predict_fields(X, drivers, input_fields), self.reduce)
        dist = self._gate.distance(X)
        return BatchPrediction(spec=self.spec, values=vals, in_hull=dist <= self._gate.threshold,
                               hull_distance=dist)

    # ---- persistence ----

    def _cfg(self) -> Dict[str, Any]:
        return {"grid_shape": list(self.grid_shape), "driver_names": self.driver_names,
                "arch": self.arch, "input_field_names": self.input_field_names,
                "width": self.width, "layers": self.layers, "modes": self.modes,
                "kernel": self.kernel, "chunk_steps": self.chunk_steps, "nonneg": self.nonneg,
                "reduce": self.reduce, "epochs": self.epochs, "batch_size": self.batch_size,
                "lr": self.lr, "weight_decay": self.weight_decay,
                "val_fraction": self.val_fraction, "patience": self.patience,
                "random_state": self.random_state}

    def _save_artifacts(self, directory: Path) -> None:
        import torch
        torch.save({"state_dict": self._net.state_dict(), "cfg": self._cfg(),
                    "fit_device": getattr(self, "_fit_device", "cpu"),
                    "scalers": {"xmu": self._xmu, "xsd": self._xsd, "mmu": self._mmu,
                                "msd": self._msd, "fmu": self._fmu, "fsd": self._fsd,
                                "imu": self._imu, "isd": self._isd},
                    "gate": self._gate, "history": self.history, "info": self.info,
                    "n_viable_train": self.n_viable_train}, Path(directory) / "spatiotemporal.pt")
        (Path(directory) / "history.json").write_text(json.dumps(
            {"history": self.history, "info": self.info}, indent=2, default=float))


def load_spatiotemporal(directory: Path, spec: SurrogateSpec, device: Optional[str] = None,
                        strict: bool = True, check_env: bool = True) -> SpatioTemporalEmulator:
    import torch
    from .environment import enforce_environment
    if check_env:
        enforce_environment(directory, strict=strict)
    blob = torch.load(Path(directory) / "spatiotemporal.pt", weights_only=False, map_location="cpu")
    m = SpatioTemporalEmulator(spec, **blob["cfg"])
    s = blob["scalers"]
    m._xmu, m._xsd, m._mmu, m._msd = s["xmu"], s["xsd"], s["mmu"], s["msd"]
    m._fmu, m._fsd, m._imu, m._isd = s["fmu"], s["fsd"], s["imu"], s["isd"]
    m._gate, m.history, m.info = blob["gate"], blob["history"], blob["info"]
    m.n_viable_train = blob["n_viable_train"]
    dev = reload_device(device, blob.get("fit_device"))
    m._fit_device = blob.get("fit_device", "cpu")
    m._net = m._build(m._xmu.shape[1]).to(dev)
    m._net.load_state_dict({k: v.to(dev) for k, v in blob["state_dict"].items()})
    m._net.eval()
    m.fitted = True
    return m
