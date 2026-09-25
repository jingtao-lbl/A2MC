"""Emulators for GRIDDED spatial fields, and for operators from input fields to output fields.

    theta (N, P) [+ input fields (N or 1, C_in, *S)]  ->  output fields (N, C, *S)

`S` is one spatial axis (a depth profile, a transect) or two (a map, a cross-section). Each output
channel is one target in the spec, so a field of three variables is a spec with three targets.

Three architectures, one class:

  cnn    a convolutional DECODER: theta through an MLP to a coarse grid, then repeated
         upsample-and-convolve to the output grid, mixed at the end with the coordinates and any
         input fields. The natural choice when the output is a smooth function of theta alone.
  unet   an encoder-decoder with skip connections (Ronneberger et al., 2015) over the grid of
         [coordinates, theta tiled, input fields]. Local detail travels through the skips, so it
         suits outputs with sharp spatial structure tied to an input field (a front, a boundary).
  fno    a Fourier neural operator (Li et al., 2021): lift, Fourier layers, project. Its weights
         act on FREQUENCIES rather than on grid cells, so a trained network can be evaluated on a
         grid it was never trained on. The operator-learning choice for "input function to output
         field" when the input is itself a field on the same grid.

The tier is S2 (a data-driven structured output). An admissibility clamp (`nonneg`) is knowledge,
so it is accepted only on an S3 spec, which is how the tier ladder already separates the two.

Scoring. `predict_batch` reduces each channel to a scalar so the class still plugs into the scalar
battery, but a field emulator's claim is about the FIELD. Score it with
`_nn.per_case_channel_r2`, which normalises within each case over its own grid; an R2 pooled over
cases divides by the between-case spread and rates a model that places only each case's level as
nearly perfect.

torch is imported inside methods only. Networks are rebuilt from a saved configuration and a
`state_dict`, never unpickled as modules.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .base import BatchPrediction, HullGate, SurrogateModel
from .spec import SurrogateSpec
from ._nn import (REDUCTIONS, blocks, channel_stats, check_grid_shape, column_stats, coord_grid,
                  fit_torch, interp_mode, minibatches, reduce_channels, refuse_nonfinite,
                  reload_device, resolve_device, validation_split)

VALID_FIELD_ARCHS = ("cnn", "unet", "fno")


def _check_structured_spec(spec: SurrogateSpec, nonneg: Sequence[str], kind: str) -> List[str]:
    """Shared tier and clamp rules for the structured-output emulators."""
    if spec.tier not in ("S2", "S3"):
        raise ValueError(f"{kind} emulates a structured output, which is tier S2 (or S3 with "
                         f"knowledge); the spec says {spec.tier!r}")
    names = [t.name for t in spec.targets]
    if not names:
        raise ValueError(f"{kind}: the spec declares no targets, so there is no output channel")
    for n in nonneg:
        if n not in names:
            raise ValueError(f"nonneg names {n!r}, not a target ({names})")
    if nonneg and spec.tier != "S3":
        raise ValueError(f"{kind}: an admissibility clamp (`nonneg`) is knowledge, which is tier S3; "
                         "declare tier 'S3' or drop the clamp")
    return names


class FieldEmulator(SurrogateModel):
    """theta [+ input fields] -> gridded output fields. See the module docstring."""

    def __init__(self, spec: SurrogateSpec, grid_shape: Sequence[int], arch: str = "fno",
                 input_field_names: Sequence[str] = (), width: int = 32, depth: int = 4,
                 modes: int = 8, nonneg: Optional[Sequence[str]] = None, reduce: str = "mean",
                 epochs: int = 300, batch_size: int = 16, lr: float = 1e-3,
                 weight_decay: float = 1e-5, val_fraction: float = 0.15, patience: int = 40,
                 random_state: int = 0, device: Optional[str] = None) -> None:
        self.nonneg = list(nonneg or [])
        self._names = _check_structured_spec(spec, self.nonneg, "FieldEmulator")
        super().__init__(spec)
        self.grid_shape = check_grid_shape(grid_shape)
        arch = str(arch).lower()
        if arch not in VALID_FIELD_ARCHS:
            raise ValueError(f"arch must be one of {VALID_FIELD_ARCHS}, got {arch!r}")
        if min(int(width), int(depth), int(modes)) < 1:
            raise ValueError("width, depth and modes must all be at least 1")
        if reduce not in REDUCTIONS:
            raise ValueError(f"reduce must be one of {REDUCTIONS}, got {reduce!r}")
        self.arch = arch
        self.input_field_names = list(input_field_names)
        self.width, self.depth, self.modes = int(width), int(depth), int(modes)
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

    def _unet_levels(self) -> int:
        return max(1, min(self.depth, int(math.floor(math.log2(min(self.grid_shape) / 2)))))

    def _build(self, n_theta: int):
        B = blocks()
        torch, nn, F = B.torch, B.nn, B.F
        ndim, C = self.ndim, len(self._names)
        conv = B.conv(ndim)
        width, depth, modes = self.width, self.depth, self.modes
        n_cond = ndim + len(self.input_field_names)
        mode = interp_mode(ndim)

        def tile(theta, S):
            return theta.view(theta.shape[0], theta.shape[1], *([1] * len(S))).expand(-1, -1, *S)

        if self.arch == "fno":
            class Net(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.lift = conv(n_theta + n_cond, width, 1)
                    self.layers = nn.ModuleList([B.FNOLayer(width, modes, ndim) for _ in range(depth)])
                    self.proj1 = conv(width, 2 * width, 1)
                    self.proj2 = conv(2 * width, C, 1)

                def forward(self, theta, cond):
                    h = self.lift(torch.cat([tile(theta, cond.shape[2:]), cond], 1))
                    for i, layer in enumerate(self.layers):
                        h = layer(h)
                        if i < len(self.layers) - 1:
                            h = F.gelu(h)
                    return self.proj2(F.gelu(self.proj1(h)))
            return Net()

        if self.arch == "unet":
            levels = self._unet_levels()
            chans = [min(width * 2 ** l, 8 * width) for l in range(levels + 1)]
            pool_cls = {1: nn.MaxPool1d, 2: nn.MaxPool2d}[ndim]

            def dconv(ci, co):
                return nn.Sequential(conv(ci, co, 3, padding=1), nn.GroupNorm(1, co), nn.GELU(),
                                     conv(co, co, 3, padding=1), nn.GroupNorm(1, co), nn.GELU())

            class Net(nn.Module):
                def __init__(self):
                    super().__init__()
                    self.enc = nn.ModuleList([dconv(n_theta + n_cond, chans[0])]
                                             + [dconv(chans[l - 1], chans[l]) for l in range(1, levels + 1)])
                    self.pool = pool_cls(2)
                    self.up = nn.ModuleList([conv(chans[l], chans[l - 1], 1) for l in range(levels, 0, -1)])
                    self.dec = nn.ModuleList([dconv(2 * chans[l - 1], chans[l - 1])
                                              for l in range(levels, 0, -1)])
                    self.out = conv(chans[0], C, 1)

                def forward(self, theta, cond):
                    S = tuple(cond.shape[2:])
                    x = torch.cat([tile(theta, S), cond], 1)
                    extra = [(-s) % (2 ** levels) for s in S]
                    if any(extra):
                        pad: List[int] = []
                        for p in reversed(extra):
                            pad += [0, p]
                        x = F.pad(x, pad, mode="replicate")
                    skips, h = [], x
                    for l, e in enumerate(self.enc):
                        h = e(h if l == 0 else self.pool(h))
                        skips.append(h)
                    for i, (up, dec) in enumerate(zip(self.up, self.dec)):
                        skip = skips[levels - 1 - i]
                        h = F.interpolate(h, size=skip.shape[2:], mode=mode, align_corners=False)
                        h = dec(torch.cat([up(h), skip], 1))
                    h = self.out(h)
                    return h[(slice(None), slice(None)) + tuple(slice(0, s) for s in S)]
            return Net()

        s0 = tuple(max(2, math.ceil(s / 2 ** depth)) for s in self.grid_shape)

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.fc = B.MLP(n_theta, (4 * width,), width * int(np.prod(s0)))
                self.ups = nn.ModuleList([nn.Sequential(conv(width, width, 3, padding=1), nn.GELU())
                                          for _ in range(depth)])
                self.mix = nn.Sequential(conv(width + n_cond, width, 3, padding=1), nn.GELU(),
                                         conv(width, C, 1))

            def forward(self, theta, cond):
                S = tuple(cond.shape[2:])
                h = self.fc(theta).view(theta.shape[0], width, *s0)
                for up in self.ups:
                    h = up(F.interpolate(h, scale_factor=2, mode=mode, align_corners=False))
                h = F.interpolate(h, size=S, mode=mode, align_corners=False)
                return self.mix(torch.cat([h, cond], 1))
        return Net()

    # ---- inputs ----

    def _input_fields(self, input_fields: Optional[np.ndarray], n: int,
                      S: Tuple[int, ...]) -> Optional[np.ndarray]:
        cin = len(self.input_field_names)
        if cin == 0:
            if input_fields is not None:
                raise ValueError("input_fields given, but this emulator declares no input_field_names")
            return None
        if input_fields is None:
            raise ValueError(f"this emulator is conditioned on input fields {self.input_field_names}; "
                             "pass `input_fields`")
        a = np.asarray(input_fields, dtype="f4")
        if a.ndim != 2 + len(S) or a.shape[1] != cin or tuple(a.shape[2:]) != tuple(S) \
                or a.shape[0] not in (1, n):
            raise ValueError(f"input_fields must be (N or 1, {cin}, *{tuple(S)}), got {a.shape}")
        if not np.isfinite(a).all():
            raise ValueError("input_fields contain NaN or inf")
        return a

    def _cond(self, torch, S, idx_or_n, It, dev):
        n = idx_or_n if isinstance(idx_or_n, int) else len(idx_or_n)
        c = torch.as_tensor(coord_grid(S), device=dev).unsqueeze(0).expand(n, len(S), *S)
        if It is None:
            return c
        ib = It.expand(n, *It.shape[1:]) if It.shape[0] == 1 else It[idx_or_n]
        return torch.cat([c, ib], 1)

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: Optional[np.ndarray] = None,
            viable: Optional[np.ndarray] = None, fields: Optional[np.ndarray] = None,
            input_fields: Optional[np.ndarray] = None, verbose: bool = False) -> "FieldEmulator":
        import torch
        import torch.nn.functional as F

        if fields is None:
            raise ValueError("FieldEmulator.fit needs `fields` (N, C, *grid_shape); Y is unused")
        X = self._check_X(X)
        Fa = np.asarray(fields, dtype="f4")
        want = (len(X), len(self._names)) + self.grid_shape
        if Fa.shape != want:
            raise ValueError(f"fields must be {want}, got {Fa.shape}")
        Ia = self._input_fields(input_fields, len(X), self.grid_shape)
        if viable is None:
            viable = np.isfinite(Fa.reshape(len(Fa), -1)).all(axis=1)
        viable = np.asarray(viable, dtype=bool)
        refuse_nonfinite("FieldEmulator fields", Fa[viable], rows=np.flatnonzero(viable))
        Xv, Fv = X[viable], Fa[viable]
        Iv = None if Ia is None else (Ia if Ia.shape[0] == 1 else Ia[viable])
        self.n_viable_train = len(Xv)
        if self.n_viable_train < 4:
            raise ValueError(f"only {self.n_viable_train} viable cases; need >= 4")
        self._gate.fit(Xv)

        self._xmu, self._xsd = column_stats(Xv)
        self._fmu, self._fsd = channel_stats(Fv)
        if Iv is not None:
            self._imu, self._isd = channel_stats(Iv)
        dev = resolve_device(self.device)
        torch.manual_seed(self.random_state)
        net = self._build(Xv.shape[1]).to(dev)
        Xt = torch.as_tensor(((Xv - self._xmu) / self._xsd).astype("f4"), device=dev)
        Ft = torch.as_tensor((Fv - self._fmu) / self._fsd, device=dev)
        It = None if Iv is None else torch.as_tensor((Iv - self._imu) / self._isd, device=dev)
        tr, va = validation_split(len(Xv), self.val_fraction, self.random_state)
        rng = np.random.default_rng(self.random_state)

        def loss(ii):
            it = torch.as_tensor(ii, device=dev)
            return F.mse_loss(net(Xt[it], self._cond(torch, self.grid_shape, it, It, dev)), Ft[it])

        self.history, self.info = fit_torch(
            net, train_batches=lambda ep: minibatches(tr, self.batch_size, rng),
            val_batches=lambda: minibatches(va, self.batch_size), batch_loss=loss,
            epochs=self.epochs, lr=self.lr, weight_decay=self.weight_decay,
            patience=self.patience, verbose=verbose, label=f"FieldEmulator[{self.arch}]")
        self._fit_device = dev
        self._net = net.eval()
        self.fitted = True
        return self

    # ---- predict ----

    def predict_fields(self, X: np.ndarray, input_fields: Optional[np.ndarray] = None,
                       grid_shape: Optional[Sequence[int]] = None) -> np.ndarray:
        """(N, C, *S). `grid_shape` defaults to the input fields' grid, else the training grid.

        Any architecture will RUN on another grid; only `fno` is designed to transfer across
        resolution, because its weights address frequencies rather than cells.
        """
        import torch
        self._check_fitted()
        X = self._check_X(X)
        if grid_shape is not None:
            S = check_grid_shape(grid_shape)
        elif input_fields is not None:
            S = tuple(np.asarray(input_fields).shape[2:])
        else:
            S = self.grid_shape
        Ia = self._input_fields(input_fields, len(X), S)
        dev = next(self._net.parameters()).device
        Xn = torch.as_tensor((X - self._xmu) / self._xsd, dtype=torch.float32, device=dev)
        It = None if Ia is None else torch.as_tensor((Ia - self._imu) / self._isd, device=dev)
        out = np.empty((len(X), len(self._names)) + tuple(S), dtype="f4")
        with torch.no_grad():
            for a in range(0, len(X), 32):
                it = torch.arange(a, min(a + 32, len(X)), device=dev)
                cond = self._cond(torch, S, it if (It is not None and It.shape[0] > 1) else len(it), It, dev)
                out[a:a + len(it)] = self._net(Xn[it], cond).cpu().numpy()
        out = out * self._fsd + self._fmu
        for n in self.nonneg:
            j = self._names.index(n)
            np.clip(out[:, j], 0.0, None, out=out[:, j])
        return out

    def predict_batch(self, X: np.ndarray, input_fields: Optional[np.ndarray] = None) -> BatchPrediction:
        X = self._check_X(X)
        vals = reduce_channels(self.predict_fields(X, input_fields), self.reduce)
        dist = self._gate.distance(X)
        return BatchPrediction(spec=self.spec, values=vals, in_hull=dist <= self._gate.threshold,
                               hull_distance=dist)

    # ---- persistence ----

    def _cfg(self) -> Dict[str, Any]:
        return {"grid_shape": list(self.grid_shape), "arch": self.arch,
                "input_field_names": self.input_field_names, "width": self.width,
                "depth": self.depth, "modes": self.modes, "nonneg": self.nonneg,
                "reduce": self.reduce, "epochs": self.epochs, "batch_size": self.batch_size,
                "lr": self.lr, "weight_decay": self.weight_decay,
                "val_fraction": self.val_fraction, "patience": self.patience,
                "random_state": self.random_state}

    def _save_artifacts(self, directory: Path) -> None:
        import torch
        torch.save({"state_dict": self._net.state_dict(), "cfg": self._cfg(),
                    "fit_device": getattr(self, "_fit_device", "cpu"),
                    "scalers": {"xmu": self._xmu, "xsd": self._xsd, "fmu": self._fmu,
                                "fsd": self._fsd, "imu": self._imu, "isd": self._isd},
                    "gate": self._gate, "history": self.history, "info": self.info,
                    "n_viable_train": self.n_viable_train}, Path(directory) / "field.pt")
        (Path(directory) / "history.json").write_text(json.dumps(
            {"history": self.history, "info": self.info}, indent=2, default=float))


def load_field(directory: Path, spec: SurrogateSpec, device: Optional[str] = None,
               strict: bool = True, check_env: bool = True) -> FieldEmulator:
    import torch
    from .environment import enforce_environment
    if check_env:
        enforce_environment(directory, strict=strict)
    blob = torch.load(Path(directory) / "field.pt", weights_only=False, map_location="cpu")
    m = FieldEmulator(spec, **blob["cfg"])
    s = blob["scalers"]
    m._xmu, m._xsd, m._fmu, m._fsd = s["xmu"], s["xsd"], s["fmu"], s["fsd"]
    m._imu, m._isd = s["imu"], s["isd"]
    m._gate, m.history, m.info = blob["gate"], blob["history"], blob["info"]
    m.n_viable_train = blob["n_viable_train"]
    dev = reload_device(device, blob.get("fit_device"))
    m._fit_device = blob.get("fit_device", "cpu")
    m._net = m._build(m._xmu.shape[1]).to(dev)
    m._net.load_state_dict({k: v.to(dev) for k, v in blob["state_dict"].items()})
    m._net.eval()
    m.fitted = True
    return m
