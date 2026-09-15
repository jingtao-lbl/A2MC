"""KGML sequence emulator: (theta, daily drivers) -> daily fluxes.

THE TIER IS S3 AND THE ARCHITECTURE IS NEW. `tiers.py::S3Surrogate` is a latent ROM with composed
targets; this is the recurrent, driver-conditioned form of the same tier, after Liu et al. (2024),
*Knowledge-guided machine learning can improve carbon cycle quantification in agroecosystems*, and
its open successor PyKGML. Both are "S2 plus process structure"; they differ in how the trajectory
is produced and in what the model is conditioned on.

WHY THAT CONDITIONING IS THE POINT. A ROM conditioned only on theta learns ONE site's ONE weather
history: its basis is tied to the exact window it was fitted on, so it cannot be asked about a
different year. Feeding the DAILY DRIVERS at every timestep makes the network an emulator of the
MODEL rather than of the RUN -- give it a parameter vector and any weather series and it answers.
That is the arrangement KGML uses, and it is the reason it can be fine-tuned against observations
at sites it never trained on.

WHAT IS BORROWED FROM KGML, AND WHAT IS NOT

Borrowed, and faithful to `time_series_models.py::RecoGRU_KGML`:

  * a shared GRU trunk, then per-flux branches that each see `[trunk, inputs]`;
  * HIERARCHICAL WIRING -- the NEE branch consumes the PREDICTED Ra and Rh rather than predicting
    NEE independently, so the causal order is structural and not merely encouraged;
  * a mass-balance term added to the data loss, as a RELATIVE HINGE: no penalty while the residual
    sits inside a tolerance, quadratic-free ReLU growth outside it.

Not borrowed, and each for a stated reason:

  * KGML takes GPP as an INPUT and predicts three fluxes. Here GPP is a TARGET, because a
    calibration emulator is asked what a parameter set does and cannot be handed the answer.
  * KGML's `tol_MB = 0.01`. That value belongs to ecosys, and a tolerance is a claim about how
    tightly a particular process model closes its own budget. Porting it unchecked is how a
    physics loss ends up fighting the data it is fitted to. `mass_balance_tol` has NO default for
    that reason: the caller must measure the closure and pass it.
  * pretrain-on-synthetic then finetune-on-observations. The training set here IS process-model
    output, so KGML's "physics as data" arm is already satisfied; and a calibration surrogate
    fine-tuned toward the observations could not then rank candidates against them without
    circularity. An `online_inference` emulator may legitimately do it, and this class does not.

torch is imported INSIDE methods, never at module import, so `models.surrogate` keeps importing
with no torch installed. That seam already exists for the `mlp` learner and is preserved here.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .base import BatchPrediction, HullGate, SurrogateModel
from .spec import SurrogateSpec


# =============================================================================
# Standardisation — KGML's Z_norm, kept as an explicit pair so the physics term
# can be evaluated in PHYSICAL units inside a loss computed on normalised ones.
# =============================================================================

def z_fit(a: np.ndarray, axis: Tuple[int, ...]) -> Tuple[np.ndarray, np.ndarray]:
    mu = np.nanmean(a, axis=axis, keepdims=True)
    sd = np.nanstd(a, axis=axis, keepdims=True)
    sd = np.where(sd < 1e-12, 1.0, sd)      # a constant channel must not divide by ~0
    return mu, sd


def z_apply(a: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    return (a - mu) / sd


def z_invert(a: np.ndarray, mu: np.ndarray, sd: np.ndarray) -> np.ndarray:
    return a * sd + mu


# =============================================================================
# KGMLEmulator
# =============================================================================

class KGMLEmulator(SurrogateModel):
    """(theta, drivers) -> daily flux trajectories, with branch wiring and a mass-balance hinge.

    ``fit`` wants three things the other tiers do not: the per-timestep ``drivers`` (D, F_met),
    the per-case ``trajectories`` (N, T, D), and a ``mass_balance`` declaration naming which
    targets enter the budget and with which sign.

    The scalar interface is preserved: ``predict_batch`` reduces the predicted trajectory exactly
    as ``S2Surrogate`` does, so this class is still a drop-in wherever a surrogate is consumed.
    """

    def __init__(self, spec: SurrogateSpec,
                 driver_names: Sequence[str],
                 reduce: str = "annual_mean_sum",
                 time_index: Optional[np.ndarray] = None,
                 hidden: int = 64, layers: int = 2, dropout: float = 0.2,
                 branch_of: Optional[Dict[str, List[str]]] = None,
                 mass_balance: Optional[Dict[str, float]] = None,
                 mass_balance_scale: Optional[Sequence[str]] = None,
                 mass_balance_tol: Optional[float] = None,
                 mass_balance_weight: float = 1.0,
                 nonneg: Optional[Sequence[str]] = None,
                 epochs: int = 60, batch_size: int = 32, lr: float = 1e-3,
                 chunk_days: int = 365, random_state: int = 0,
                 device: Optional[str] = None) -> None:
        if spec.tier != "S3":
            raise ValueError(f"KGMLEmulator is an S3 architecture, spec says tier {spec.tier!r}")
        super().__init__(spec)
        names = [t.name for t in spec.targets]

        self.driver_names = list(driver_names)
        self.reduce = reduce
        self.time_index = None if time_index is None else np.asarray(time_index)
        self.hidden, self.layers, self.dropout = hidden, layers, dropout
        self.branch_of = {k: list(v) for k, v in (branch_of or {}).items()}
        self.mass_balance = dict(mass_balance or {})
        # The DENOMINATOR of the relative hinge, declared rather than inferred. KGML uses
        # |Ra + Rh|, and that is not incidental: respiration is bounded away from zero all year
        # while GPP hits exactly zero in winter. Measured on this ensemble, |GPP| as the scale
        # gives a p99 relative residual of 74748 against 0.91 for |Ra + Rh|, so the wrong choice
        # makes the hinge either inert or explosive depending on the tolerance picked to survive it.
        self.mass_balance_scale = list(mass_balance_scale or [])
        self.mass_balance_tol = mass_balance_tol
        self.mass_balance_weight = mass_balance_weight
        self.nonneg = list(nonneg or [])
        self.epochs, self.batch_size, self.lr = epochs, batch_size, lr
        self.chunk_days, self.random_state = chunk_days, random_state
        self.device = device

        for child, parents in self.branch_of.items():
            if child not in names:
                raise ValueError(f"branch_of names {child!r}, not a target ({names})")
            for p in parents:
                if p not in names:
                    raise ValueError(f"branch_of[{child!r}] names {p!r}, not a target")
                if p in self.branch_of:
                    raise ValueError(
                        f"{p!r} is itself a branch child; chained branches are not supported "
                        f"because the forward order would be ambiguous")
        for t in self.mass_balance:
            if t not in names:
                raise ValueError(f"mass_balance names {t!r}, not a target ({names})")
        for t in self.mass_balance_scale:
            if t not in names:
                raise ValueError(f"mass_balance_scale names {t!r}, not a target ({names})")
        if self.mass_balance and not self.mass_balance_scale:
            raise ValueError(
                "mass_balance was declared without `mass_balance_scale`. The hinge is RELATIVE, "
                "so it needs a denominator, and the denominator must be bounded away from zero "
                "over the whole year or the term is inert where the scale vanishes. KGML uses "
                "the respiration terms for exactly that reason.")
        if self.mass_balance and self.mass_balance_tol is None:
            raise ValueError(
                "mass_balance was declared without `mass_balance_tol`. A tolerance is a claim "
                "about how tightly THIS process model closes its own budget; KGML's 0.01 belongs "
                "to ecosys. Measure the residual on the training trajectories and pass it, or a "
                "physics term will fight the data it is fitted to.")
        for t in self.nonneg:
            if t not in names:
                raise ValueError(f"nonneg names {t!r}, not a target ({names})")

        self._names = names
        self._order = [n for n in names if n not in self.branch_of] + list(self.branch_of)
        self._net: Any = None
        self._xmu = self._xsd = self._ymu = self._ysd = None
        self._gate = HullGate()
        self.history: List[Dict[str, float]] = []
        self.n_viable_train = 0

    # ---- torch pieces, built lazily ----

    def _build(self, n_in: int):
        import torch
        from torch import nn

        names, branch_of, hidden = self._names, self.branch_of, self.hidden
        layers, dropout = self.layers, self.dropout

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.trunk = nn.GRU(n_in, hidden, layers, dropout=dropout, batch_first=True)
                self.drop = nn.Dropout(dropout)
                self.branch = nn.ModuleDict()
                self.head = nn.ModuleDict()
                for n in names:
                    extra = len(branch_of.get(n, []))
                    # a plain branch sees [trunk, inputs]; a wired one additionally sees its
                    # parents' PREDICTED values, which is KGML's hierarchical arm
                    self.branch[n] = nn.GRU(n_in + hidden + extra, hidden, 1, batch_first=True)
                    self.head[n] = nn.Linear(hidden, 1)

            def forward(self, x):
                h, _ = self.trunk(x)
                h = self.drop(h)
                out: Dict[str, Any] = {}
                for n in names:
                    if n in branch_of:
                        continue
                    o, _ = self.branch[n](torch.cat([h, x], dim=2))
                    out[n] = self.head[n](self.drop(o))
                for n, parents in branch_of.items():
                    o, _ = self.branch[n](torch.cat([h, x] + [out[p] for p in parents], dim=2))
                    out[n] = self.head[n](self.drop(o))
                return torch.cat([out[n] for n in names], dim=2)

        return Net()

    def _chunks(self, n_days: int) -> List[Tuple[int, int]]:
        """Year-length windows. KGML trains on whole multi-year sequences because it has 100 of
        them; here there are thousands of cases, so a shorter window buys far more gradient steps
        per epoch at the cost of not propagating state across a year boundary."""
        c = self.chunk_days
        return [(s, min(s + c, n_days)) for s in range(0, n_days, c)]

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: np.ndarray,
            viable: Optional[np.ndarray] = None,
            trajectories: Optional[np.ndarray] = None,
            drivers: Optional[np.ndarray] = None,
            val_fraction: float = 0.1,
            verbose: bool = True) -> "KGMLEmulator":
        import torch
        from torch import nn

        if trajectories is None or drivers is None:
            raise ValueError("KGMLEmulator.fit needs both `trajectories` (N, T, D) and "
                             "`drivers` (D, F_met); without drivers it is a theta-only ROM.")
        X = self._check_X(X)
        T = np.asarray(trajectories, dtype="f4")
        M = np.asarray(drivers, dtype="f4")
        if T.shape[1] != len(self._names):
            raise ValueError(f"trajectories have {T.shape[1]} targets, spec declares "
                             f"{len(self._names)}")
        if M.shape[0] != T.shape[2]:
            raise ValueError(f"drivers have {M.shape[0]} timesteps, trajectories have {T.shape[2]}")
        if M.shape[1] != len(self.driver_names):
            raise ValueError(f"drivers have {M.shape[1]} columns, driver_names lists "
                             f"{len(self.driver_names)}")

        if viable is None:
            viable = np.all(np.isfinite(T).reshape(len(T), -1), axis=1)
        viable = np.asarray(viable, dtype=bool)
        Xv, Tv = X[viable], T[viable]
        self.n_viable_train = int(viable.sum())
        self._gate.fit(Xv)

        self._xmu, self._xsd = z_fit(Xv, axis=(0,))
        self._mmu, self._msd = z_fit(M, axis=(0,))
        self._ymu, self._ysd = z_fit(Tv, axis=(0, 2))            # per target
        Xn = z_apply(Xv, self._xmu, self._xsd).astype("f4")
        Mn = z_apply(M, self._mmu, self._msd).astype("f4")
        Yn = z_apply(Tv, self._ymu, self._ysd).astype("f4")

        dev = torch.device(self.device or ("cuda" if torch.cuda.is_available() else "cpu"))
        torch.manual_seed(self.random_state)
        n_in = Xn.shape[1] + Mn.shape[1]
        self._net = self._build(n_in).to(dev)

        wins = self._chunks(T.shape[2])
        rng = np.random.default_rng(self.random_state)
        idx = rng.permutation(len(Xn))
        n_val = max(1, int(round(val_fraction * len(idx))))
        val_i, tr_i = idx[:n_val], idx[n_val:]

        mb_sign = torch.tensor([self.mass_balance.get(n, 0.0) for n in self._names],
                               dtype=torch.float32, device=dev)
        mb_scale = torch.tensor([1.0 if n in self.mass_balance_scale else 0.0
                                 for n in self._names], dtype=torch.float32, device=dev)
        use_mb = bool(self.mass_balance) and float(mb_sign.abs().sum()) > 0
        ymu_t = torch.tensor(self._ymu.reshape(1, -1, 1), dtype=torch.float32, device=dev)
        ysd_t = torch.tensor(self._ysd.reshape(1, -1, 1), dtype=torch.float32, device=dev)
        Mn_t = torch.tensor(Mn, device=dev)

        def batch(ii, s, e):
            xb = torch.tensor(Xn[ii], device=dev)                       # (B, P)
            L = e - s
            xseq = xb[:, None, :].expand(-1, L, -1)                     # theta broadcast in time
            mseq = Mn_t[s:e][None].expand(len(ii), -1, -1)              # drivers broadcast in case
            return torch.cat([xseq, mseq], dim=2), torch.tensor(Yn[ii][:, :, s:e], device=dev)

        opt = torch.optim.Adam(self._net.parameters(), lr=self.lr)
        mse = nn.MSELoss()
        relu = nn.ReLU()
        best, best_state = float("inf"), None

        for ep in range(self.epochs):
            self._net.train()
            rng.shuffle(tr_i)
            tot = totd = totm = 0.0
            nb = 0
            for b0 in range(0, len(tr_i), self.batch_size):
                ii = tr_i[b0:b0 + self.batch_size]
                for (s, e) in wins:
                    xb, yb = batch(ii, s, e)
                    pred = self._net(xb).transpose(1, 2)                # (B, T, L)
                    ld = mse(pred, yb)
                    lm = torch.zeros((), device=dev)
                    if use_mb:
                        # physics in PHYSICAL units: un-normalise, then a RELATIVE hinge, exactly
                        # PyKGML's `ReLU(|sum| - tol*|scale|)` shape
                        phys = z_invert(pred, ymu_t, ysd_t)
                        resid = (phys * mb_sign.view(1, -1, 1)).sum(dim=1)
                        scale = (phys * mb_scale.view(1, -1, 1)).sum(dim=1)
                        lm = torch.mean(relu(resid.abs()
                                             - self.mass_balance_tol * scale.abs().clamp(min=1e-6)))
                    loss = ld + self.mass_balance_weight * lm
                    opt.zero_grad(); loss.backward()
                    torch.nn.utils.clip_grad_norm_(self._net.parameters(), 5.0)
                    opt.step()
                    tot += float(loss.detach()); totd += float(ld.detach())
                    totm += float(lm.detach()); nb += 1

            self._net.eval()
            with torch.no_grad():
                vl = 0.0; vn = 0
                for b0 in range(0, len(val_i), self.batch_size):
                    ii = val_i[b0:b0 + self.batch_size]
                    for (s, e) in wins:
                        xb, yb = batch(ii, s, e)
                        vl += float(mse(self._net(xb).transpose(1, 2), yb)); vn += 1
                vl /= max(vn, 1)
            self.history.append({"epoch": ep, "train": tot / nb, "data": totd / nb,
                                 "mass_balance": totm / nb, "val": vl})
            if vl < best:
                best = vl
                best_state = {k: v.detach().clone() for k, v in self._net.state_dict().items()}
            if verbose and (ep % 5 == 0 or ep == self.epochs - 1):
                print(f"  epoch {ep:3d}  train {tot/nb:.4f}  (data {totd/nb:.4f}, "
                      f"mb {totm/nb:.4f})  val {vl:.4f}", flush=True)

        if best_state is not None:
            self._net.load_state_dict(best_state)          # early-stopping by best validation
        self.fitted = True
        return self

    # ---- predict ----

    def predict_trajectories(self, X: np.ndarray, drivers: np.ndarray) -> np.ndarray:
        """(N, T, D). `drivers` is passed explicitly because an emulator may be asked about
        weather it was never trained on -- which is the capability the tier exists for."""
        import torch
        self._check_fitted()
        X = self._check_X(X)
        M = np.asarray(drivers, dtype="f4")
        Xn = z_apply(X, self._xmu, self._xsd).astype("f4")
        Mn = z_apply(M, self._mmu, self._msd).astype("f4")
        dev = next(self._net.parameters()).device
        Mn_t = torch.tensor(Mn, device=dev)
        out = np.empty((len(X), len(self._names), M.shape[0]), dtype="f4")
        self._net.eval()
        with torch.no_grad():
            for b0 in range(0, len(Xn), 64):
                xb = torch.tensor(Xn[b0:b0 + 64], device=dev)
                for (s, e) in self._chunks(M.shape[0]):
                    xseq = xb[:, None, :].expand(-1, e - s, -1)
                    mseq = Mn_t[s:e][None].expand(len(xb), -1, -1)
                    p = self._net(torch.cat([xseq, mseq], dim=2)).transpose(1, 2)
                    out[b0:b0 + 64, :, s:e] = p.cpu().numpy()
        out = z_invert(out, self._ymu.reshape(1, -1, 1), self._ysd.reshape(1, -1, 1))
        for n in self.nonneg:
            j = self._names.index(n)
            np.clip(out[:, j, :], 0.0, None, out=out[:, j, :])
        return out

    def predict_batch(self, X: np.ndarray, drivers: Optional[np.ndarray] = None) -> BatchPrediction:
        from .tiers import REDUCERS
        if drivers is None:
            raise ValueError("KGMLEmulator.predict_batch needs `drivers`; it is conditioned on them")
        traj = self.predict_trajectories(X, drivers)
        vals = REDUCERS[self.reduce](traj, self.time_index)
        dist = self._gate.distance(self._check_X(X))
        return BatchPrediction(spec=self.spec, values=vals,
                               in_hull=dist <= self._gate.threshold, hull_distance=dist)

    # ---- persistence ----

    def _save_artifacts(self, directory: Path) -> None:
        import torch
        torch.save({"state_dict": self._net.state_dict(),
                    "cfg": {"driver_names": self.driver_names, "reduce": self.reduce,
                            "time_index": None if self.time_index is None
                            else self.time_index.tolist(),
                            "hidden": self.hidden, "layers": self.layers,
                            "dropout": self.dropout, "branch_of": self.branch_of,
                            "mass_balance": self.mass_balance,
                            "mass_balance_scale": self.mass_balance_scale,
                            "mass_balance_tol": self.mass_balance_tol,
                            "mass_balance_weight": self.mass_balance_weight,
                            "nonneg": self.nonneg, "chunk_days": self.chunk_days,
                            "random_state": self.random_state},
                    "scalers": {"xmu": self._xmu, "xsd": self._xsd,
                                "mmu": self._mmu, "msd": self._msd,
                                "ymu": self._ymu, "ysd": self._ysd},
                    "gate": self._gate, "history": self.history,
                    "n_viable_train": self.n_viable_train},
                   directory / "kgml.pt")
        (directory / "history.json").write_text(json.dumps(self.history, indent=2))


def load_kgml(directory: Path, spec: SurrogateSpec,
              device: Optional[str] = None, strict: bool = True) -> KGMLEmulator:
    """Rebuild a saved emulator. Kept here rather than in `tiers.load` so that module keeps
    importing with no torch installed.

    The net is placed on the SAME device rule `fit` uses (cuda when present) rather than left on
    CPU. That is not only a speed question: cuDNN's GRU and the CPU kernel do not agree bit for
    bit, so a reloaded model silently landing on CPU predicts slightly differently from the one
    that was saved -- measured at 3.8e-4 absolute on a small fixture, which is far above float32
    noise and would read as a corrupted artifact.

    ``strict`` governs the environment check only (``tiers.load`` uses the same word for the same
    purpose): a MAJOR version change in a library this emulator was built with refuses, because
    torch does not promise that a `state_dict` written by one major version loads into the next.
    """
    import torch

    from .environment import enforce_environment
    enforce_environment(directory, strict=strict)

    blob = torch.load(Path(directory) / "kgml.pt", weights_only=False,
                      map_location="cpu")
    cfg = dict(blob["cfg"])
    ti = cfg.pop("time_index")
    m = KGMLEmulator(spec, time_index=None if ti is None else np.asarray(ti), **cfg)
    s = blob["scalers"]
    m._xmu, m._xsd = s["xmu"], s["xsd"]
    m._mmu, m._msd = s["mmu"], s["msd"]
    m._ymu, m._ysd = s["ymu"], s["ysd"]
    m._gate = blob["gate"]
    m.history = blob["history"]
    m.n_viable_train = blob["n_viable_train"]
    n_in = m._xmu.shape[1] + m._mmu.shape[1]
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    m.device = str(dev)
    m._net = m._build(n_in)
    m._net.load_state_dict({k: v.to(dev) for k, v in blob["state_dict"].items()})
    m._net.to(dev).eval()
    m.fitted = True
    return m
