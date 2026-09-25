"""A deep operator network: parameters and an input function to an output field at ANY coordinates.

    theta (N, P) [+ input functions sampled at fixed sensors (N, C_in, n_sensors)]
        ->  output values (N, C, M) at query coordinates (M, coord_dim)

DeepONet (Lu et al., 2021) splits the map in two. A BRANCH network reads everything that describes
the case, the parameters and the input function at its sensors, and returns coefficients; a TRUNK
network reads a coordinate and returns basis functions; the output is their inner product plus a
bias, one basis per output channel:

    u_c(x) = sum_k  branch_{c,k}(theta, a) * trunk_{c,k}(x)  +  b_c

What that buys, and why it sits beside the FNO rather than replacing it:

  * the query points are free. The trunk is a function of the coordinate, so a trained network is
    evaluated wherever it is asked, on an irregular set of monitoring points, a finer grid, or a
    single location, with no interpolation step;
  * the input function need not live on the output grid. The FNO in `fields.py` needs its input
    field and its output on the same grid; here the sensors and the query points are unrelated.

The price is that DeepONet does not share the FNO's grid structure, so for a dense field on a
regular grid the FNO is usually the stronger learner. Choose by where the data lives.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .base import BatchPrediction, HullGate, SurrogateModel
from .fields import _check_structured_spec
from .spec import SurrogateSpec
from ._nn import (REDUCTIONS, blocks, channel_stats, column_stats, fit_torch, minibatches,
                  reduce_channels, refuse_nonfinite, reload_device, resolve_device, validation_split)


class DeepONetEmulator(SurrogateModel):
    """theta [+ input function] -> output channels at arbitrary coordinates. See the module docstring."""

    def __init__(self, spec: SurrogateSpec, coord_dim: int,
                 input_function_names: Sequence[str] = (), n_sensors: int = 0, basis: int = 64,
                 branch_hidden: Sequence[int] = (128, 128), trunk_hidden: Sequence[int] = (128, 128),
                 nonneg: Optional[Sequence[str]] = None, reduce: str = "mean", epochs: int = 500,
                 batch_size: int = 32, lr: float = 1e-3, weight_decay: float = 1e-5,
                 val_fraction: float = 0.15, patience: int = 50, random_state: int = 0,
                 device: Optional[str] = None) -> None:
        self.nonneg = list(nonneg or [])
        self._names = _check_structured_spec(spec, self.nonneg, "DeepONetEmulator")
        super().__init__(spec)
        if int(coord_dim) < 1:
            raise ValueError(f"coord_dim must be at least 1, got {coord_dim}")
        self.input_function_names = list(input_function_names)
        if bool(self.input_function_names) != (int(n_sensors) > 0):
            raise ValueError("declare input functions and their sensor count together: "
                             "input_function_names and n_sensors > 0, or neither")
        if int(basis) < 1:
            raise ValueError(f"basis must be at least 1, got {basis}")
        if reduce not in REDUCTIONS:
            raise ValueError(f"reduce must be one of {REDUCTIONS}, got {reduce!r}")
        self.coord_dim, self.n_sensors, self.basis = int(coord_dim), int(n_sensors), int(basis)
        self.branch_hidden = [int(h) for h in branch_hidden]
        self.trunk_hidden = [int(h) for h in trunk_hidden]
        self.reduce = reduce
        self.epochs, self.batch_size, self.lr = int(epochs), int(batch_size), float(lr)
        self.weight_decay, self.val_fraction = float(weight_decay), float(val_fraction)
        self.patience, self.random_state, self.device = int(patience), int(random_state), device
        self._net: Any = None
        self._gate = HullGate()
        self.history: List[Dict[str, float]] = []
        self.info: Dict[str, Any] = {}
        self.n_viable_train = 0
        self._amu = self._asd = None
        self._train_coords: Optional[np.ndarray] = None

    # ---- network ----

    def _build(self, n_theta: int):
        B = blocks()
        torch, nn = B.torch, B.nn
        C, K = len(self._names), self.basis
        n_branch = n_theta + len(self.input_function_names) * self.n_sensors
        branch_hidden, trunk_hidden, coord_dim = self.branch_hidden, self.trunk_hidden, self.coord_dim

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.branch = B.MLP(n_branch, branch_hidden, C * K, act="gelu")
                self.trunk = B.MLP(coord_dim, trunk_hidden, C * K, act="tanh")
                self.bias = nn.Parameter(torch.zeros(C))

            def forward(self, case_in, coords):                 # (B, n_branch), (M, coord_dim)
                b = self.branch(case_in).view(case_in.shape[0], C, K)
                t = torch.tanh(self.trunk(coords)).view(coords.shape[0], C, K)
                return torch.einsum("bck,mck->bcm", b, t) + self.bias.view(1, C, 1)

        return Net()

    # ---- inputs ----

    def _functions(self, input_functions, n: int) -> Optional[np.ndarray]:
        if not self.input_function_names:
            if input_functions is not None:
                raise ValueError("input_functions given, but this emulator declares none")
            return None
        if input_functions is None:
            raise ValueError(f"this emulator reads input functions {self.input_function_names}")
        a = np.asarray(input_functions, dtype="f4")
        want = (n, len(self.input_function_names), self.n_sensors)
        if a.shape != want:
            raise ValueError(f"input_functions must be {want}, got {a.shape}")
        if not np.isfinite(a).all():
            raise ValueError("input_functions contain NaN or inf")
        return a

    def _coords(self, coords) -> np.ndarray:
        c = np.asarray(coords, dtype="f4")
        if c.ndim == 1 and self.coord_dim == 1:
            c = c[:, None]
        if c.ndim != 2 or c.shape[1] != self.coord_dim:
            raise ValueError(f"coords must be (M, {self.coord_dim}), got {c.shape}")
        if not np.isfinite(c).all():
            raise ValueError("coords contain NaN or inf")
        return c

    def _case_inputs(self, torch, X, A, dev):
        Xn = ((X - self._xmu) / self._xsd).astype("f4")
        if A is not None:
            An = ((A - self._amu) / self._asd).reshape(len(A), -1)
            Xn = np.concatenate([Xn, An], axis=1)
        return torch.as_tensor(Xn, device=dev)

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: Optional[np.ndarray] = None,
            viable: Optional[np.ndarray] = None, coords: Optional[np.ndarray] = None,
            values: Optional[np.ndarray] = None, input_functions: Optional[np.ndarray] = None,
            verbose: bool = False) -> "DeepONetEmulator":
        import torch
        import torch.nn.functional as F

        if coords is None or values is None:
            raise ValueError("DeepONetEmulator.fit needs `coords` (M, coord_dim) and `values` "
                             "(N, C, M); Y is unused")
        X = self._check_X(X)
        c = self._coords(coords)
        V = np.asarray(values, dtype="f4")
        want = (len(X), len(self._names), len(c))
        if V.shape != want:
            raise ValueError(f"values must be {want}, got {V.shape}")
        A = self._functions(input_functions, len(X))
        if viable is None:
            viable = np.isfinite(V.reshape(len(V), -1)).all(axis=1)
        viable = np.asarray(viable, dtype=bool)
        refuse_nonfinite("DeepONetEmulator values", V[viable], rows=np.flatnonzero(viable))
        Xv, Vv = X[viable], V[viable]
        Av = None if A is None else A[viable]
        self.n_viable_train = len(Xv)
        if self.n_viable_train < 4:
            raise ValueError(f"only {self.n_viable_train} viable cases; need >= 4")
        self._gate.fit(Xv)

        self._xmu, self._xsd = column_stats(Xv)
        self._vmu, self._vsd = channel_stats(Vv)
        if Av is not None:
            self._amu, self._asd = channel_stats(Av)
        lo, hi = c.min(axis=0), c.max(axis=0)
        self._cmin, self._crange = lo, np.where(hi - lo < 1e-12, 1.0, hi - lo).astype("f4")
        self._train_coords = c
        dev = resolve_device(self.device)
        torch.manual_seed(self.random_state)
        self._net = self._build(Xv.shape[1]).to(dev)
        net = self._net
        Ct = torch.as_tensor((c - self._cmin) / self._crange, device=dev)
        Bt = self._case_inputs(torch, Xv, Av, dev)
        Vt = torch.as_tensor((Vv - self._vmu) / self._vsd, device=dev)
        tr, va = validation_split(len(Xv), self.val_fraction, self.random_state)
        rng = np.random.default_rng(self.random_state)

        def loss(ii):
            it = torch.as_tensor(ii, device=dev)
            return F.mse_loss(net(Bt[it], Ct), Vt[it])

        self.history, self.info = fit_torch(
            net, train_batches=lambda ep: minibatches(tr, self.batch_size, rng),
            val_batches=lambda: minibatches(va, self.batch_size), batch_loss=loss,
            epochs=self.epochs, lr=self.lr, weight_decay=self.weight_decay,
            patience=self.patience, verbose=verbose, label="DeepONetEmulator")
        self._fit_device = dev
        net.eval()
        self.fitted = True
        return self

    # ---- predict ----

    def predict_at(self, X: np.ndarray, coords: np.ndarray,
                   input_functions: Optional[np.ndarray] = None) -> np.ndarray:
        """(N, C, M) at any `coords`, including points never in the training set."""
        import torch
        self._check_fitted()
        X = self._check_X(X)
        c = self._coords(coords)
        A = self._functions(input_functions, len(X))
        dev = next(self._net.parameters()).device
        Ct = torch.as_tensor((c - self._cmin) / self._crange, device=dev)
        out = np.empty((len(X), len(self._names), len(c)), dtype="f4")
        with torch.no_grad():
            for a in range(0, len(X), 256):
                Bt = self._case_inputs(torch, X[a:a + 256], None if A is None else A[a:a + 256], dev)
                out[a:a + len(Bt)] = self._net(Bt, Ct).cpu().numpy()
        out = out * self._vsd + self._vmu
        for n in self.nonneg:
            j = self._names.index(n)
            np.clip(out[:, j], 0.0, None, out=out[:, j])
        return out

    def predict_batch(self, X: np.ndarray,
                      input_functions: Optional[np.ndarray] = None) -> BatchPrediction:
        """Reduced over the TRAINING coordinates, the only point set the scalar is defined on."""
        X = self._check_X(X)
        vals = reduce_channels(self.predict_at(X, self._train_coords, input_functions), self.reduce)
        dist = self._gate.distance(X)
        return BatchPrediction(spec=self.spec, values=vals, in_hull=dist <= self._gate.threshold,
                               hull_distance=dist)

    # ---- persistence ----

    def _cfg(self) -> Dict[str, Any]:
        return {"coord_dim": self.coord_dim, "input_function_names": self.input_function_names,
                "n_sensors": self.n_sensors, "basis": self.basis,
                "branch_hidden": self.branch_hidden, "trunk_hidden": self.trunk_hidden,
                "nonneg": self.nonneg, "reduce": self.reduce, "epochs": self.epochs,
                "batch_size": self.batch_size, "lr": self.lr, "weight_decay": self.weight_decay,
                "val_fraction": self.val_fraction, "patience": self.patience,
                "random_state": self.random_state}

    def _save_artifacts(self, directory: Path) -> None:
        import torch
        torch.save({"state_dict": self._net.state_dict(), "cfg": self._cfg(),
                    "fit_device": getattr(self, "_fit_device", "cpu"),
                    "scalers": {"xmu": self._xmu, "xsd": self._xsd, "vmu": self._vmu,
                                "vsd": self._vsd, "amu": self._amu, "asd": self._asd,
                                "cmin": self._cmin, "crange": self._crange},
                    "train_coords": self._train_coords, "gate": self._gate,
                    "history": self.history, "info": self.info,
                    "n_viable_train": self.n_viable_train}, Path(directory) / "deeponet.pt")
        (Path(directory) / "history.json").write_text(json.dumps(
            {"history": self.history, "info": self.info}, indent=2, default=float))


def load_deeponet(directory: Path, spec: SurrogateSpec, device: Optional[str] = None,
                  strict: bool = True, check_env: bool = True) -> DeepONetEmulator:
    import torch
    from .environment import enforce_environment
    if check_env:
        enforce_environment(directory, strict=strict)
    blob = torch.load(Path(directory) / "deeponet.pt", weights_only=False, map_location="cpu")
    m = DeepONetEmulator(spec, **blob["cfg"])
    s = blob["scalers"]
    m._xmu, m._xsd, m._vmu, m._vsd = s["xmu"], s["xsd"], s["vmu"], s["vsd"]
    m._amu, m._asd, m._cmin, m._crange = s["amu"], s["asd"], s["cmin"], s["crange"]
    m._train_coords = blob["train_coords"]
    m._gate, m.history, m.info = blob["gate"], blob["history"], blob["info"]
    m.n_viable_train = blob["n_viable_train"]
    dev = reload_device(device, blob.get("fit_device"))
    m._fit_device = blob.get("fit_device", "cpu")
    m._net = m._build(m._xmu.shape[1]).to(dev)
    m._net.load_state_dict({k: v.to(dev) for k, v in blob["state_dict"].items()})
    m._net.eval()
    m.fitted = True
    return m
