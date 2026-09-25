"""KGML sequence emulator: (theta, per-step drivers) -> per-step target trajectories.

THE TIER IS S3 AND THE ARCHITECTURE IS NEW. `tiers.py::S3Surrogate` is a latent ROM with composed
targets; this is the recurrent, driver-conditioned form of the same tier, after Liu et al. (2024),
*Knowledge-guided machine learning can improve carbon cycle quantification in agroecosystems*, and
its open successor PyKGML. Both are "S2 plus process structure"; they differ in how the trajectory
is produced and in what the model is conditioned on.

WHY THAT CONDITIONING IS THE POINT. A ROM conditioned only on theta learns ONE driver history: its
basis is tied to the exact window it was fitted on, so it cannot be asked about a different period.
Feeding the DRIVERS at every timestep makes the network an emulator of the MODEL rather than of the
RUN -- give it a parameter vector and any driver series and it answers.
That is the arrangement KGML uses, and it is the reason it can be fine-tuned against observations
at sites it never trained on.

WHAT IS BORROWED FROM KGML, AND WHAT IS NOT

Borrowed, and faithful to `time_series_models.py::RecoGRU_KGML`:

  * a shared recurrent trunk, then per-target branches that each see `[trunk, inputs]`;
  * HIERARCHICAL WIRING -- a derived target's branch consumes its parents' PREDICTED values rather
    than predicting the derived target independently (in KGML, a net flux from its component
    fluxes), so the causal order is structural and not merely encouraged;
  * a mass-balance term added to the data loss, as a RELATIVE HINGE: no penalty while the residual
    sits inside a tolerance, quadratic-free ReLU growth outside it.

Not borrowed, and each for a stated reason:

  * KGML takes one process output as an INPUT and predicts the others. Here every emulated output
    is a TARGET, because a calibration emulator is asked what a parameter set does and cannot be
    handed part of the answer.
  * KGML's `tol_MB = 0.01`. That value belongs to the process model KGML was built on, and a
    tolerance is a claim about how tightly a particular process model closes its own budget.
    Porting it unchecked is how a physics loss ends up fighting the data it is fitted to.
    `mass_balance_tol` has NO default for that reason: the caller must measure the closure and pass
    it.
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
import math
import warnings
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
    """(theta, drivers) -> per-step target trajectories, with branch wiring and a mass-balance hinge.

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
                 cell: str = "gru",
                 nhead: int = 4,
                 tcn_kernel: int = 3,
                 branch_of: Optional[Dict[str, List[str]]] = None,
                 mass_balance: Optional[Dict[str, float]] = None,
                 mass_balance_scale: Optional[Sequence[str]] = None,
                 mass_balance_tol: Optional[float] = None,
                 mass_balance_weight: float = 1.0,
                 anomaly_weight: float = 0.0,
                 diff_weight: float = 0.0,
                 spatial_graph: Optional[Sequence[Tuple[str, str]]] = None,
                 nonneg: Optional[Sequence[str]] = None,
                 epochs: int = 60, batch_size: int = 32, lr: float = 1e-3,
                 patience: Optional[int] = None,
                 chunk_days: int = 365, random_state: int = 0,
                 device: Optional[str] = None) -> None:
        if spec.tier != "S3":
            raise ValueError(f"KGMLEmulator is an S3 architecture, spec says tier {spec.tier!r}")
        super().__init__(spec)
        names = [t.name for t in spec.targets]

        self.driver_names = list(driver_names)
        self.anomaly_weight = float(anomaly_weight)
        self.diff_weight = float(diff_weight)
        self.reduce = reduce
        self.time_index = None if time_index is None else np.asarray(time_index)
        self.hidden, self.layers, self.dropout = hidden, layers, dropout
        # The sequence encoder is a choice; the trunk-plus-branches shape, the hierarchical wiring
        # and the physics terms are all encoder-agnostic.
        #   gru / lstm    recurrent, causal by construction
        #   transformer   self-attention over the window, CAUSALLY MASKED (see _build)
        #   tcn           dilated temporal convolutions, CAUSALLY PADDED (see _build)
        cell = str(cell).lower()
        if cell not in ("gru", "lstm", "transformer", "tcn"):
            raise ValueError(f"cell must be 'gru', 'lstm', 'transformer' or 'tcn', got {cell!r}")
        if cell == "tcn" and int(tcn_kernel) < 2:
            raise ValueError(f"tcn_kernel must be at least 2, got {tcn_kernel}")
        self.cell = cell
        self.nhead = int(nhead)
        self.tcn_kernel = int(tcn_kernel)
        self.branch_of = {k: list(v) for k, v in (branch_of or {}).items()}
        # Message passing over a DECLARED graph of targets. Edges are undirected pairs of target
        # names; every target additionally attends to itself. Off unless a graph is given.
        self.spatial_graph = [tuple(e) for e in (spatial_graph or [])]
        if self.spatial_graph:
            unknown = {n for e in self.spatial_graph for n in e} - set(names)
            if unknown:
                raise ValueError(f"spatial_graph names targets that do not exist: {sorted(unknown)}")
            if self.branch_of:
                raise ValueError("spatial_graph and branch_of cannot be combined: a hierarchical "
                                 "branch consumes its parents' PREDICTED values, which are produced "
                                 "after the graph layer would mix them. Declare one or the other.")
        # nhead has TWO consumers, and the guard covered one of them until 2026-09-22: the
        # transformer encoder (`nn.TransformerEncoderLayer(d_model, nhead, ...)`) and the graph
        # attention layer (`GraphAttention(hidden, adj, dropout)` -> `nn.MultiheadAttention(d_model,
        # nhead, ...)`), both in `_build`. A `cell="gru"` model with a spatial_graph and an
        # indivisible pair therefore constructed cleanly and died part-way through the first fit on
        # torch's own bare `AssertionError: embed_dim must be divisible by num_heads` -- exactly the
        # shape this check exists to replace with a refusal where the object is built.
        if self.hidden % self.nhead and (self.cell == "transformer" or self.spatial_graph):
            who = "transformer" if self.cell == "transformer" else "spatial_graph"
            raise ValueError(f"{who} needs hidden divisible by nhead; "
                             f"got hidden={self.hidden}, nhead={self.nhead}")
        self.mass_balance = dict(mass_balance or {})
        # The DENOMINATOR of the relative hinge, declared rather than inferred. It must stay bounded
        # away from zero over the whole record: where the scale reaches zero (a flux that stops
        # seasonally, for example) the relative residual is unbounded, so the wrong choice makes the
        # hinge either inert or explosive depending on the tolerance picked to survive it. KGML
        # divides by component terms that never reach zero for this reason.
        self.mass_balance_scale = list(mass_balance_scale or [])
        self.mass_balance_tol = mass_balance_tol
        self.mass_balance_weight = mass_balance_weight
        self.nonneg = list(nonneg or [])
        self.epochs, self.batch_size, self.lr = epochs, batch_size, lr
        #: Stop after this many epochs with no validation improvement. `None` runs the whole budget,
        #: which is what every fit before 2026-09-22 did -- and all of them ended with their best
        #: epoch at or one before the last, i.e. the BUDGET decided the fit rather than the data.
        self.patience = None if patience is None else int(patience)
        #: Set by `fit`: epochs_run, best_epoch, best_val, stopped_by_patience. The record that
        #: separates "converged" from "ran out of budget", which a score cannot.
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
                "over the whole record, or the term is inert where the scale vanishes.")
        if self.mass_balance and self.mass_balance_tol is None:
            raise ValueError(
                "mass_balance was declared without `mass_balance_tol`. A tolerance is a claim "
                "about how tightly THIS process model closes its own budget, so a value published "
                "for another model does not transfer. Measure the residual on the training "
                "trajectories and pass it, or a physics term will fight the data it is fitted to.")
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
        self.fit_info_: Dict[str, Any] = {}

    # ---- torch pieces, built lazily ----

    def _build(self, n_in: int):
        import torch
        from torch import nn

        names, branch_of, hidden = self._names, self.branch_of, self.hidden
        layers, dropout = self.layers, self.dropout
        nhead = self.nhead
        tcn_kernel = self.tcn_kernel

        class CausalTransformer(nn.Module):
            """Self-attention encoder with nn.GRU's call contract: (B,T,D) -> ((B,T,H), None).

            THE MASK IS NOT OPTIONAL. An unmasked encoder lets step t attend to steps after it, so
            the fit would use information an artifact consumed step by step cannot have; the result
            is a smoother, not an emulator. A recurrent cell is causal by construction and gets this
            for free, which is why the mask has no counterpart above.
            """

            def __init__(self, d_in: int, d_model: int, n_layers: int, p_drop: float):
                super().__init__()
                self.proj = nn.Linear(d_in, d_model)
                enc = nn.TransformerEncoderLayer(d_model, nhead, dim_feedforward=4 * d_model,
                                                 dropout=p_drop, batch_first=True,
                                                 norm_first=True, activation="gelu")
                self.enc = nn.TransformerEncoder(enc, n_layers, enable_nested_tensor=False)
                self.d_model = d_model

            def _positions(self, T: int, device, dtype):
                # Sinusoidal, built per call: a learned table would cap the window length, and
                # chunk length is a fit-time choice.
                pos = torch.arange(T, device=device, dtype=dtype).unsqueeze(1)
                i = torch.arange(0, self.d_model, 2, device=device, dtype=dtype)
                w = torch.exp(-math.log(10000.0) * i / self.d_model)
                pe = torch.zeros(T, self.d_model, device=device, dtype=dtype)
                pe[:, 0::2] = torch.sin(pos * w)
                pe[:, 1::2] = torch.cos(pos * w)
                return pe.unsqueeze(0)

            def forward(self, x):
                T = x.shape[1]
                h = self.proj(x)
                h = h + self._positions(T, h.device, h.dtype)
                mask = torch.triu(torch.ones(T, T, device=h.device, dtype=torch.bool), diagonal=1)
                return self.enc(h, mask=mask), None

        class CausalTCN(nn.Module):
            """Dilated temporal convolutions with nn.GRU's call contract: (B,T,D) -> ((B,T,H), None).

            CAUSAL BY LEFT PADDING ONLY. A convolution padded on both sides centres its kernel on
            step t and reads the steps after it, which is the same leak an unmasked attention
            encoder has, and just as invisible to a whole-window accuracy score. Each block doubles
            the dilation, so memory reaches back `receptive_field` steps and no further: unlike a
            recurrent cell, nothing older than that can inform a prediction.
            """

            def __init__(self, d_in: int, d_model: int, n_layers: int, p_drop: float):
                super().__init__()
                self.inp = nn.Conv1d(d_in, d_model, 1)
                self.c1 = nn.ModuleList()
                self.c2 = nn.ModuleList()
                self.pads: List[int] = []
                for i in range(max(1, n_layers)):
                    dil = 2 ** i
                    self.c1.append(nn.Conv1d(d_model, d_model, tcn_kernel, dilation=dil))
                    self.c2.append(nn.Conv1d(d_model, d_model, tcn_kernel, dilation=dil))
                    self.pads.append((tcn_kernel - 1) * dil)
                self.drop = nn.Dropout(p_drop)
                self.receptive_field = 1 + 2 * sum(self.pads)

            def forward(self, x):
                import torch.nn.functional as F
                h = self.inp(x.transpose(1, 2))
                for c1, c2, pad in zip(self.c1, self.c2, self.pads):
                    r = h
                    h = self.drop(F.gelu(c1(F.pad(h, (pad, 0)))))
                    h = self.drop(F.gelu(c2(F.pad(h, (pad, 0)))))
                    h = h + r
                return h.transpose(1, 2), None

        if self.cell == "transformer":
            def RNN(d_in, d_model, n_layers, dropout=0.0, batch_first=True):
                return CausalTransformer(d_in, d_model, n_layers, dropout)
        elif self.cell == "tcn":
            def RNN(d_in, d_model, n_layers, dropout=0.0, batch_first=True):
                return CausalTCN(d_in, d_model, n_layers, dropout)
        else:
            RNN = nn.LSTM if self.cell == "lstm" else nn.GRU

        # Adjacency over the target axis: self-loops always, declared edges both ways. `None` when
        # no graph is declared, which is what switches the layer off.
        adj = None
        if self.spatial_graph:
            idx = {n: i for i, n in enumerate(names)}
            a = torch.eye(len(names), dtype=torch.bool)
            for u, v in self.spatial_graph:
                a[idx[u], idx[v]] = True
                a[idx[v], idx[u]] = True
            adj = a

        class GraphAttention(nn.Module):
            """One masked attention pass over the TARGET axis, applied per timestep.

            Each target attends to its declared neighbours and itself, and nowhere else: the mask
            is the declared graph, so a target cannot draw on one it is not connected to. Applied
            as a residual, so an untrained layer leaves the branch representation unchanged.
            """

            def __init__(self, d_model: int, mask: "torch.Tensor", p_drop: float):
                super().__init__()
                self.attn = nn.MultiheadAttention(d_model, nhead, dropout=p_drop, batch_first=True)
                self.norm = nn.LayerNorm(d_model)
                self.register_buffer("block", ~mask)     # True where attention is FORBIDDEN

            def forward(self, z):                        # z: (B, T, L, H)
                B, T, L, H = z.shape
                flat = z.reshape(B * T, L, H)
                mixed, _ = self.attn(flat, flat, flat, attn_mask=self.block, need_weights=False)
                return self.norm(flat + mixed).reshape(B, T, L, H)

        class Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.trunk = RNN(n_in, hidden, layers, dropout=dropout, batch_first=True)
                self.drop = nn.Dropout(dropout)
                self.branch = nn.ModuleDict()
                self.head = nn.ModuleDict()
                for n in names:
                    extra = len(branch_of.get(n, []))
                    # a plain branch sees [trunk, inputs]; a wired one additionally sees its
                    # parents' PREDICTED values, which is KGML's hierarchical arm
                    self.branch[n] = RNN(n_in + hidden + extra, hidden, 1, batch_first=True)
                    self.head[n] = nn.Linear(hidden, 1)
                self.graph = None if adj is None else GraphAttention(hidden, adj, dropout)

            def forward(self, x):
                h, _ = self.trunk(x)
                h = self.drop(h)
                out: Dict[str, Any] = {}
                if self.graph is not None:
                    reps = [self.branch[n](torch.cat([h, x], dim=2))[0] for n in names]
                    z = self.graph(torch.stack(reps, dim=2))         # (B, T, L, H)
                    return torch.cat([self.head[n](self.drop(z[:, :, i]))
                                      for i, n in enumerate(names)], dim=2)
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
        """Windows of `chunk_days` steps. Whole multi-year sequences suit a small number of cases; with
        many cases a shorter window buys far more gradient steps per epoch, at the cost of not
        propagating state across a window boundary."""
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
        best_epoch, since, stopped_by_patience = -1, 0, False

        # ONE definition of the objective, used by BOTH the optimiser and the checkpoint rule.
        # Until 2026-09-22 the training loss carried the anomaly, first-difference and
        # mass-balance terms while the validation loss was a bare MSE, so the checkpoint was
        # selected on a DIFFERENT objective from the one the fit was driving towards -- the exact
        # thing `_nn.fit_torch`'s docstring forbids ("THE VALIDATION CRITERION IS THE TRAINING
        # LOSS ... A validation loss that leaves out terms the training loss carries selects a
        # different checkpoint"). That module's own loop passes a single `batch_loss` to both
        # sides; this class has its own loop because it steps per time window, so it has to keep
        # the two in step by construction instead, which is what these closures are for.
        # Consequence for what is already on disk: every fit made before this date, including the
        # 20260916a loss ablation, chose its weights by level-only MSE whatever its training
        # objective was.
        def data_loss(pred, yb):
            ld = mse(pred, yb)
            if self.anomaly_weight:
                # Targets SHAPE rather than level. Y is standardised per target over cases AND
                # time, so the denominator is dominated by between-case spread and a prediction at
                # roughly the right level already scores well. Removing each window's own mean
                # leaves only the within-case variation.
                ld = ld + self.anomaly_weight * mse(
                    pred - pred.mean(dim=1, keepdim=True),
                    yb - yb.mean(dim=1, keepdim=True))
            if self.diff_weight:
                # Targets step-to-step change, which a level-matching prediction gets wrong even
                # when its mean is right.
                ld = ld + self.diff_weight * mse(pred[:, 1:] - pred[:, :-1],
                                                 yb[:, 1:] - yb[:, :-1])
            return ld

        def mb_loss(pred):
            if not use_mb:
                return torch.zeros((), device=dev)
            # physics in PHYSICAL units: un-normalise, then a RELATIVE hinge, exactly PyKGML's
            # `ReLU(|sum| - tol*|scale|)` shape
            phys = z_invert(pred, ymu_t, ysd_t)
            resid = (phys * mb_sign.view(1, -1, 1)).sum(dim=1)
            scale = (phys * mb_scale.view(1, -1, 1)).sum(dim=1)
            return torch.mean(relu(resid.abs()
                                   - self.mass_balance_tol * scale.abs().clamp(min=1e-6)))

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
                    ld, lm = data_loss(pred, yb), mb_loss(pred)
                    loss = ld + self.mass_balance_weight * lm
                    opt.zero_grad(); loss.backward()
                    torch.nn.utils.clip_grad_norm_(self._net.parameters(), 5.0)
                    opt.step()
                    tot += float(loss.detach()); totd += float(ld.detach())
                    totm += float(lm.detach()); nb += 1

            self._net.eval()
            with torch.no_grad():
                vl = vd = 0.0; vn = 0
                for b0 in range(0, len(val_i), self.batch_size):
                    ii = val_i[b0:b0 + self.batch_size]
                    for (s, e) in wins:
                        xb, yb = batch(ii, s, e)
                        pred = self._net(xb).transpose(1, 2)
                        # `val` is the OBJECTIVE and is what the checkpoint rule below reads.
                        # `val_data` is the plain level MSE, kept beside it because it is the
                        # quantity every fit before 2026-09-22 recorded under `val`, so a history
                        # written then and one written now stay comparable.
                        vl += float(data_loss(pred, yb) + self.mass_balance_weight * mb_loss(pred))
                        vd += float(mse(pred, yb)); vn += 1
                vl /= max(vn, 1); vd /= max(vn, 1)
            self.history.append({"epoch": ep, "train": tot / nb, "data": totd / nb,
                                 "mass_balance": totm / nb, "val": vl, "val_data": vd})
            # A NON-FINITE VALIDATION LOSS IS REFUSED, not carried. NaN never compares less than
            # `best`, so the checkpoint would silently stay at "none" and the LAST epoch's weights
            # would be returned as though they had been selected. `_nn.fit_torch` refuses this for
            # the same reason; this loop is separate and did not.
            if not math.isfinite(vl):
                raise FloatingPointError(
                    f"KGMLEmulator: validation loss is {vl} at epoch {ep}. A non-finite validation "
                    f"loss never improves on the best checkpoint, so continuing would return the "
                    f"last epoch silently. Check the viable rows for NaN trajectories and the "
                    f"drivers for NaN or inf.")
            if vl < best:
                best, best_epoch, since = vl, ep, 0
                best_state = {k: v.detach().clone() for k, v in self._net.state_dict().items()}
            else:
                since += 1
            if verbose and (ep % 5 == 0 or ep == self.epochs - 1):
                print(f"  epoch {ep:3d}  train {tot/nb:.4f}  (data {totd/nb:.4f}, "
                      f"mb {totm/nb:.4f})  val {vl:.4f}", flush=True)
            if self.patience and since >= self.patience:
                stopped_by_patience = True
                break

        if best_state is not None:
            self._net.load_state_dict(best_state)          # early-stopping by best validation

        # THE FIT SAYS WHETHER IT FINISHED OR WAS STOPPED. A validation curve whose minimum is the
        # LAST epoch has not converged -- it ran out of budget -- and the two are indistinguishable
        # from the score alone. Measured 2026-09-22 across every fit this class has produced: the
        # miniLEO baseline's best epoch was 29 of 29, the Lusignan KGML fit's 39 of 39, and both
        # loss-ablation arms' 28 of 29, while `20260916g` recorded that "both had converged ... so
        # it was not capacity and not under-training" and pivoted the investigation to the objective
        # on that basis. `_nn.fit_torch` warns for exactly this; this loop is separate and did not.
        self.fit_info_ = {"epochs_run": len(self.history),
                          "best_epoch": best_epoch,
                          "best_val": best if best_state is not None else float("nan"),
                          "stopped_by_patience": stopped_by_patience}
        if best_state is not None and not stopped_by_patience and best_epoch == self.epochs - 1:
            warnings.warn(
                f"KGMLEmulator: the epoch budget ended this fit while validation was still "
                f"improving -- the best epoch IS the last one ({best_epoch} of {self.epochs - 1}). "
                f"The fit was stopped, not converged, so a poor score here is not evidence about "
                f"capacity, the objective or the architecture. Raise `epochs` (and set `patience` "
                f"so the budget is not the thing that decides) before drawing a conclusion.",
                RuntimeWarning)
        self.fitted = True
        return self

    # ---- predict ----

    def predict_trajectories(self, X: np.ndarray, drivers: np.ndarray) -> np.ndarray:
        """(N, T, D). `drivers` is passed explicitly because an emulator may be asked about
        drivers it was never trained on -- which is the capability the tier exists for."""
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
                            "hidden": self.hidden, "layers": self.layers, "cell": self.cell,
                            "nhead": self.nhead, "tcn_kernel": self.tcn_kernel,
                            "dropout": self.dropout, "branch_of": self.branch_of,
                            "mass_balance": self.mass_balance,
                            "mass_balance_scale": self.mass_balance_scale,
                            "mass_balance_tol": self.mass_balance_tol,
                            "mass_balance_weight": self.mass_balance_weight,
                            "anomaly_weight": self.anomaly_weight,
                            "diff_weight": self.diff_weight,
                            "spatial_graph": [list(e) for e in self.spatial_graph],
                            "nonneg": self.nonneg, "chunk_days": self.chunk_days,
                            "patience": self.patience,
                            "random_state": self.random_state,
                            # THE DEVICE THE FIT RAN ON, recorded so a reload can reproduce it.
                            # cuDNN's recurrent kernels and the CPU ones do not agree bit for
                            # bit (~4e-4 on this model), so a CPU-fitted artifact reloaded onto a
                            # GPU predicts measurably differently from the thing that was saved,
                            # and nothing in the artifact said which one it had been.
                            "fit_device": str(next(self._net.parameters()).device)},
                    "scalers": {"xmu": self._xmu, "xsd": self._xsd,
                                "mmu": self._mmu, "msd": self._msd,
                                "ymu": self._ymu, "ysd": self._ysd},
                    "gate": self._gate, "history": self.history,
                    "n_viable_train": self.n_viable_train},
                   directory / "kgml.pt")
        (directory / "history.json").write_text(json.dumps(self.history, indent=2))


def load_kgml(directory: Path, spec: SurrogateSpec, device: Optional[str] = None,
              strict: bool = True, check_env: bool = True) -> KGMLEmulator:
    """Rebuild a saved emulator. `tiers.load` dispatches here by the class name in `tier.json`,
    after its provenance and environment checks; the loader lives in this module so `tiers.py`
    keeps importing with no torch installed. Called directly, it checks the environment but not
    provenance, and it builds the emulator on the `spec` it is given.

    The net is placed on the SAME device rule `fit` uses (cuda when present) rather than left on
    CPU. That is not only a speed question: cuDNN's GRU and the CPU kernel do not agree bit for
    bit, so a reloaded model silently landing on CPU predicts differently from the one that was
    saved, by more than float32 noise, which would read as a corrupted artifact.

    ``strict`` governs the environment check only (``tiers.load`` uses the same word for the same
    purpose): a MAJOR version change in a library this emulator was built with refuses, because
    torch does not promise that a `state_dict` written by one major version loads into the next.
    ``check_env=False`` skips that check, for a caller such as ``tiers.load`` that has run it.
    """
    import torch

    from .environment import enforce_environment
    if check_env:
        enforce_environment(directory, strict=strict)

    blob = torch.load(Path(directory) / "kgml.pt", weights_only=False,
                      map_location="cpu")
    cfg = dict(blob["cfg"])
    ti = cfg.pop("time_index")
    fit_device = cfg.pop("fit_device", None)          # absent in artifacts written before v2.436
    m = KGMLEmulator(spec, time_index=None if ti is None else np.asarray(ti), **cfg)
    s = blob["scalers"]
    m._xmu, m._xsd = s["xmu"], s["xsd"]
    m._mmu, m._msd = s["mmu"], s["msd"]
    m._ymu, m._ysd = s["ymu"], s["ysd"]
    m._gate = blob["gate"]
    m.history = blob["history"]
    m.n_viable_train = blob["n_viable_train"]
    n_in = m._xmu.shape[1] + m._mmu.shape[1]
    # DEVICE ORDER: an explicit argument, then the device the FIT used, then whatever is here.
    # Reloading a CPU-fitted emulator onto a GPU changes its predictions by more than float32
    # noise, so "cuda when available" was reintroducing exactly the drift the build skill's step 4
    # warns about. An artifact from before this was recorded still falls back to the old rule,
    # which is why the fallback is kept rather than refused.
    want = device or fit_device or ("cuda" if torch.cuda.is_available() else "cpu")
    if str(want).startswith("cuda") and not torch.cuda.is_available():
        warnings.warn(
            f"this emulator was fitted on {want} and no GPU is available here, so it is being "
            f"reloaded on the CPU. Recurrent kernels do not agree bit for bit across the two, so "
            f"expect small differences from the saved model's own predictions.",
            RuntimeWarning)
        want = "cpu"
    dev = torch.device(want)
    m.device = str(dev)
    m._net = m._build(n_in)
    m._net.load_state_dict({k: v.to(dev) for k, v in blob["state_dict"].items()})
    m._net.to(dev).eval()
    m.fitted = True
    return m
