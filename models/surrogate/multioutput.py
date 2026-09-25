"""Surrogates for a SHORT OUTPUT VECTOR: learners that predict every target jointly.

Every learner in `learners.py` is single-output, and `S1Surrogate` fits one per target. That
discards whatever the targets share. When the outputs of a process model are driven by common
mechanisms (several outputs controlled by the same process, or bound by the same balance), a
joint learner can borrow strength across them: a correlated output is effectively extra training
data for its neighbours.

Two joint learners, and the S1-equivalent surrogate that wraps them:

  MultiOutputMLPLearner   one network with a shared trunk and one output per target, as a deep
                          ensemble for an epistemic spread.
  MultiOutputGPLearner    an intrinsic coregionalisation model (ICM; Alvarez, Rosasco & Lawrence,
                          2012): one ARD Matern-5/2 kernel over inputs, times a learned positive
                          definite matrix B over targets. B IS the learned between-target
                          covariance, so `coregionalization()` reports which targets move together.
  VectorSurrogate         tier S1: viability classifier + joint regressor + split-conformal
                          intervals per target + the extrapolation gate. The same contract as
                          `S1Surrogate`, with one regressor instead of one per target.

A separate surrogate class rather than a learner option on `S1Surrogate`, because S1 fits a
regressor per target on that target's own finite rows. A joint learner needs rows where it can see
every target, so both the row selection and the saved layout differ, and folding that into S1 would
change a class every existing S1 artifact depends on.

Two training defaults, each for a one-clause reason:

  * the GP's ARD length-scales start at sqrt(d) in standardised input units, so training points
    are correlated with one another at the start however many inputs there are;
  * the MLP trains in minibatches with a validation checkpoint, and warns when the epoch budget
    rather than the validation loss ended a fit.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import math
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .base import BatchPrediction, HullGate, SurrogateModel
from .learners import make_classifier
from .spec import SurrogateSpec
from ._nn import fit_torch, minibatches, refuse_nonfinite, validation_split


# =============================================================================
# Multi-output MLP (deep ensemble)
# =============================================================================

class MultiOutputMLPLearner:
    """(N, P) -> (N, T) with a shared trunk; a deep ensemble for `predict_std`."""

    multi_output = True
    supports_std = True
    name = "mlp_multi"

    def __init__(self, hidden: Sequence[int] = (128, 128), n_models: int = 5,
                 epochs: int = 500, batch_size: int = 64, lr: float = 1e-3,
                 weight_decay: float = 1e-4, val_fraction: float = 0.15,
                 patience: int = 50, random_state: int = 0, device: str = "cpu") -> None:
        self.hidden = tuple(int(h) for h in hidden)
        self.n_models = int(n_models)
        self.epochs, self.batch_size, self.lr = int(epochs), int(batch_size), float(lr)
        self.weight_decay, self.val_fraction = float(weight_decay), float(val_fraction)
        self.patience, self.random_state, self.device = int(patience), int(random_state), device
        self._nets: List[Any] = []
        self.history: List[List[Dict[str, float]]] = []
        self.info: List[Dict[str, Any]] = []

    def _build(self, d_in: int, d_out: int):
        from torch import nn
        layers: List[Any] = []
        prev = d_in
        for h in self.hidden:
            layers += [nn.Linear(prev, h), nn.GELU()]
            prev = h
        layers.append(nn.Linear(prev, d_out))
        # nn.Sequential, not a locally defined Module subclass, so the fitted learner pickles.
        return nn.Sequential(*layers).to(self.device)

    def fit(self, X: np.ndarray, Y: np.ndarray) -> "MultiOutputMLPLearner":
        import torch
        X = np.asarray(X, dtype=float)
        Y = np.atleast_2d(np.asarray(Y, dtype=float))
        if Y.shape[0] != X.shape[0]:
            raise ValueError(f"X has {X.shape[0]} rows, Y has {Y.shape[0]}")
        refuse_nonfinite("MultiOutputMLPLearner Y", Y)
        self._mu = X.mean(axis=0)
        sd = X.std(axis=0); sd[sd <= 0] = 1.0
        self._sd = sd
        self._ymu = Y.mean(axis=0)
        ysd = Y.std(axis=0); ysd[ysd <= 0] = 1.0
        self._ysd = ysd
        Z = torch.tensor((X - self._mu) / self._sd, dtype=torch.float32, device=self.device)
        T = torch.tensor((Y - self._ymu) / self._ysd, dtype=torch.float32, device=self.device)
        tr, va = validation_split(len(Z), self.val_fraction, self.random_state)

        self._nets, self.history, self.info = [], [], []
        for k in range(self.n_models):
            torch.manual_seed(self.random_state + k)
            net = self._build(Z.shape[1], T.shape[1])
            rng = np.random.default_rng(self.random_state + k)
            hist, info = fit_torch(
                net,
                train_batches=lambda ep, rng=rng: minibatches(tr, self.batch_size, rng),
                val_batches=lambda: minibatches(va, max(len(va), 1)),
                batch_loss=lambda ii, net=net: torch.nn.functional.mse_loss(net(Z[ii]), T[ii]),
                epochs=self.epochs, lr=self.lr, weight_decay=self.weight_decay,
                patience=self.patience, label=f"mlp_multi member {k}")
            net.eval()
            self._nets.append(net)
            self.history.append(hist)
            self.info.append(info)
        return self

    def _forward(self, X: np.ndarray) -> np.ndarray:
        import torch
        Z = torch.tensor((np.asarray(X, dtype=float) - self._mu) / self._sd,
                         dtype=torch.float32, device=self.device)
        with torch.no_grad():
            out = np.stack([n(Z).cpu().numpy() for n in self._nets], axis=0)   # (K, N, T)
        return out * self._ysd + self._ymu

    def predict(self, X: np.ndarray) -> np.ndarray:
        return self._forward(X).mean(axis=0)

    def predict_std(self, X: np.ndarray) -> np.ndarray:
        return self._forward(X).std(axis=0)


# =============================================================================
# Multi-output GP (intrinsic coregionalisation model)
# =============================================================================

def _matern52(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    d2 = (np.sum(A * A, axis=1)[:, None] + np.sum(B * B, axis=1)[None, :] - 2.0 * A @ B.T)
    r = np.sqrt(np.maximum(d2, 0.0))
    s5 = math.sqrt(5.0) * r
    return (1.0 + s5 + 5.0 / 3.0 * r * r) * np.exp(-s5)


class MultiOutputGPLearner:
    """Exact ICM Gaussian process: K = B (x) Kx + diag(noise_t) (x) I, fitted by marginal likelihood.

    Tolerates MISSING target values: the likelihood is built over the observed (row, target) pairs
    only, so a row missing one target still informs the others through B.

    Cost is cubic in the number of observed pairs, so rows are subsampled to `max_points`, loudly.
    """

    multi_output = True
    supports_std = True
    name = "gp_multi"

    def __init__(self, rank: Optional[int] = None, max_points: int = 600,
                 n_iter: int = 300, lr: float = 0.05, random_state: int = 0) -> None:
        self.rank = rank
        self.max_points = int(max_points)
        self.n_iter, self.lr, self.random_state = int(n_iter), float(lr), int(random_state)
        self.n_used = 0
        self.nll_history: List[float] = []

    def fit(self, X: np.ndarray, Y: np.ndarray) -> "MultiOutputGPLearner":
        import torch

        X = np.asarray(X, dtype=float)
        Y = np.atleast_2d(np.asarray(Y, dtype=float))
        if Y.shape[0] != X.shape[0]:
            raise ValueError(f"X has {X.shape[0]} rows, Y has {Y.shape[0]}")
        keep = np.isfinite(Y).any(axis=1) & np.isfinite(X).all(axis=1)
        X, Y = X[keep], Y[keep]
        if len(X) > self.max_points:
            idx = np.random.default_rng(self.random_state).choice(len(X), self.max_points,
                                                                 replace=False)
            warnings.warn(f"MultiOutputGPLearner: subsampled {len(X)} -> {self.max_points} rows "
                          "(cubic cost). Raise max_points or use mlp_multi.", RuntimeWarning)
            X, Y = X[idx], Y[idx]
        n, d = X.shape
        T = Y.shape[1]
        self.n_used = n
        self._mu = X.mean(axis=0)
        sd = X.std(axis=0); sd[sd <= 0] = 1.0
        self._sd = sd
        self._ymu = np.nanmean(Y, axis=0)
        ysd = np.nanstd(Y, axis=0); ysd[~np.isfinite(ysd) | (ysd <= 0)] = 1.0
        self._ysd = ysd
        Z = (X - self._mu) / self._sd
        Yn = (Y - self._ymu) / self._ysd

        obs = np.argwhere(np.isfinite(Yn))              # (m, 2): (row, target)
        rows, tgts = obs[:, 0], obs[:, 1]
        y = Yn[rows, tgts]
        r = self.rank or T

        dt = torch.float64
        Zt = torch.tensor(Z, dtype=dt)
        yt = torch.tensor(y, dtype=dt)
        rows_t = torch.tensor(rows)
        tgts_t = torch.tensor(tgts)
        g = torch.Generator().manual_seed(self.random_state)
        # sqrt(d), not 1: see the module docstring.
        log_ls = torch.full((d,), 0.5 * math.log(d), dtype=dt, requires_grad=True)
        W = (0.3 * torch.randn(T, r, generator=g, dtype=dt)).requires_grad_(True)
        raw_kappa = torch.full((T,), math.log(math.expm1(0.5)), dtype=dt, requires_grad=True)
        raw_noise = torch.full((T,), math.log(math.expm1(0.1)), dtype=dt, requires_grad=True)
        params = [log_ls, W, raw_kappa, raw_noise]
        opt = torch.optim.Adam(params, lr=self.lr)
        sp = torch.nn.functional.softplus

        def kernel_x(A, Bm, ls):
            As, Bs = A / ls, Bm / ls
            d2 = (As * As).sum(1)[:, None] + (Bs * Bs).sum(1)[None, :] - 2.0 * As @ Bs.T
            rr = torch.sqrt(d2.clamp_min(1e-12))
            s5 = math.sqrt(5.0) * rr
            return (1.0 + s5 + 5.0 / 3.0 * rr * rr) * torch.exp(-s5)

        def build():
            ls = torch.exp(log_ls)
            Bm = W @ W.T + torch.diag(sp(raw_kappa))
            Kx = kernel_x(Zt, Zt, ls)
            K = Bm[tgts_t][:, tgts_t] * Kx[rows_t][:, rows_t]
            K = K + torch.diag(sp(raw_noise)[tgts_t] + 1e-6)
            return K, Bm, ls

        self.nll_history = []
        m = len(y)
        for it in range(self.n_iter):
            K, _, _ = build()
            L = self._cholesky(torch, K)
            alpha = torch.cholesky_solve(yt[:, None], L)[:, 0]
            nll = 0.5 * yt @ alpha + torch.log(torch.diagonal(L)).sum() + 0.5 * m * math.log(2 * math.pi)
            opt.zero_grad()
            nll.backward()
            opt.step()
            self.nll_history.append(float(nll.detach()))

        with torch.no_grad():
            K, Bm, ls = build()
            L = self._cholesky(torch, K)
            alpha = torch.cholesky_solve(yt[:, None], L)[:, 0]
        self._Z = Z
        self._rows, self._tgts = rows, tgts
        self._ls = ls.numpy()
        self._B = Bm.numpy()
        self._noise = sp(raw_noise).detach().numpy()
        self._L = L.numpy()
        self._alpha = alpha.numpy()
        return self

    @staticmethod
    def _cholesky(torch, K):
        jitter = 0.0
        for _ in range(6):
            try:
                return torch.linalg.cholesky(K + jitter * torch.eye(len(K), dtype=K.dtype))
            except RuntimeError:
                jitter = 1e-6 if jitter == 0.0 else jitter * 10.0
        raise RuntimeError("MultiOutputGPLearner: covariance not positive definite even with jitter 1e-1")

    def _cross(self, X: np.ndarray) -> np.ndarray:
        Zs = (np.asarray(X, dtype=float) - self._mu) / self._sd
        return _matern52(Zs / self._ls, self._Z / self._ls)          # (N*, n)

    def predict(self, X: np.ndarray) -> np.ndarray:
        Kx = self._cross(X)[:, self._rows]                              # (N*, m)
        T = self._B.shape[0]
        out = np.empty((len(Kx), T))
        for t in range(T):
            out[:, t] = (Kx * self._B[t, self._tgts]) @ self._alpha
        return out * self._ysd + self._ymu

    def predict_std(self, X: np.ndarray) -> np.ndarray:
        from scipy.linalg import solve_triangular
        Kx = self._cross(X)[:, self._rows]
        T = self._B.shape[0]
        out = np.empty((len(Kx), T))
        for t in range(T):
            ks = Kx * self._B[t, self._tgts]                            # (N*, m)
            v = solve_triangular(self._L, ks.T, lower=True)             # (m, N*)
            var = self._B[t, t] + self._noise[t] - np.sum(v * v, axis=0)
            out[:, t] = np.sqrt(np.maximum(var, 1e-12))
        return out * self._ysd

    def coregionalization(self) -> np.ndarray:
        """The learned between-target CORRELATION matrix (B normalised to unit diagonal)."""
        s = np.sqrt(np.diag(self._B))
        return self._B / np.outer(s, s)

    def lengthscales(self) -> np.ndarray:
        return np.asarray(self._ls)


MULTI_OUTPUT_LEARNERS = {"mlp_multi": MultiOutputMLPLearner, "gp_multi": MultiOutputGPLearner}


def make_multi_output_learner(spec: Any, **kw: Any) -> Any:
    if isinstance(spec, str):
        if spec not in MULTI_OUTPUT_LEARNERS:
            raise ValueError(f"unknown multi-output learner {spec!r}; choose from "
                             f"{sorted(MULTI_OUTPUT_LEARNERS)}")
        return MULTI_OUTPUT_LEARNERS[spec](**kw)
    if getattr(spec, "multi_output", False):
        return spec
    raise TypeError(f"cannot resolve a multi-output learner from {spec!r}")


# =============================================================================
# VectorSurrogate — S1 with a joint regressor
# =============================================================================

class VectorSurrogate(SurrogateModel):
    """Viability classifier + ONE joint regressor + per-target split-conformal intervals + gate."""

    def __init__(self, spec: SurrogateSpec, learner: Any = "mlp_multi", classifier: Any = "rf",
                 alpha: float = 0.05, calibration_fraction: float = 0.3,
                 random_state: int = 0, hull_k: int = 5, hull_quantile: float = 0.99,
                 classifier_kw: Optional[Dict[str, Any]] = None, **learner_kw: Any) -> None:
        if spec.tier != "S1":
            raise ValueError(f"VectorSurrogate requires tier 'S1', spec says {spec.tier!r}")
        if not 0 < alpha < 1:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        if not 0 < calibration_fraction < 1:
            raise ValueError(f"calibration_fraction must be in (0, 1), got {calibration_fraction}")
        if any(t.transform != "identity" for t in spec.targets):
            raise ValueError("VectorSurrogate fits every target jointly in native units; a per-target "
                             "transform is not supported. Transform Y before fitting instead.")
        super().__init__(spec)
        self.learner, self.learner_kw = learner, dict(learner_kw)
        self.classifier, self.classifier_kw = classifier, dict(classifier_kw or {})
        self.alpha, self.calibration_fraction = alpha, calibration_fraction
        self.random_state, self.hull_k, self.hull_quantile = random_state, hull_k, hull_quantile
        self._model: Any = None
        self._clf: Any = None
        self._q = np.array([])
        self._gate = HullGate(k=hull_k, quantile=hull_quantile)
        self.n_viable_train = 0
        self.n_dropped_incomplete = 0

    def fit(self, X: np.ndarray, Y: np.ndarray,
            viable: Optional[np.ndarray] = None) -> "VectorSurrogate":
        from .tiers import _SIGMA_FLOOR

        X = self._check_X(X)
        Y = np.atleast_2d(np.asarray(Y, dtype=float))
        if Y.shape != (X.shape[0], len(self.spec.targets)):
            raise ValueError(f"Y must be ({X.shape[0]}, {len(self.spec.targets)}), got {Y.shape}")
        if viable is None:
            viable = np.all(np.isfinite(Y), axis=1)
        viable = np.asarray(viable, dtype=bool)
        self._clf = None if viable.all() else make_classifier(
            self.classifier, random_state=self.random_state, **self.classifier_kw
        ).fit(X, viable.astype(int))

        complete = viable & np.all(np.isfinite(Y), axis=1)
        self.n_dropped_incomplete = int((viable & ~complete).sum())
        if self.n_dropped_incomplete:
            warnings.warn(f"VectorSurrogate: {self.n_dropped_incomplete} viable row(s) miss at least "
                          "one target and are left out of the joint fit.", RuntimeWarning)
        Xv, Yv = X[complete], Y[complete]
        self.n_viable_train = len(Xv)
        if self.n_viable_train < 4:
            raise ValueError(f"only {self.n_viable_train} complete viable rows; need >= 4")
        self._gate.fit(Xv)

        idx = np.random.default_rng(self.random_state).permutation(self.n_viable_train)
        n_cal = min(self.n_viable_train - 2,
                    max(1, int(round(self.calibration_fraction * self.n_viable_train))))
        cal, fit = idx[:n_cal], idx[n_cal:]
        kw = dict(self.learner_kw)
        if isinstance(self.learner, str):
            kw.setdefault("random_state", self.random_state)
        self._model = make_multi_output_learner(self.learner, **kw).fit(Xv[fit], Yv[fit])

        pred = self._model.predict(Xv[cal])
        resid = np.abs(Yv[cal] - pred)
        if self._model.supports_std:
            resid = resid / np.maximum(self._model.predict_std(Xv[cal]), _SIGMA_FLOOR)
        n = len(cal)
        k = math.ceil((n + 1) * (1 - self.alpha))
        if k > n:
            # The finite-sample quantile does not exist: ceil((n+1)(1-alpha)) exceeds the number of
            # calibration scores, and the only interval with the guarantee is unbounded. Capping at
            # the largest score instead gives coverage n/(n+1), below nominal, silently.
            warnings.warn(f"VectorSurrogate: {n} calibration rows cannot support a {1 - self.alpha:.0%} "
                          f"interval (needs ceil((n+1)(1-alpha)) <= n, i.e. n >= "
                          f"{math.ceil((1 - self.alpha) / self.alpha)}); intervals are unbounded.",
                          RuntimeWarning)
            self._q = np.full(len(self.spec.targets), np.inf)
        else:
            self._q = np.sort(resid, axis=0)[k - 1]
        self.fitted = True
        return self

    def predict_batch(self, X: np.ndarray) -> BatchPrediction:
        from .tiers import _SIGMA_FLOOR

        self._check_fitted()
        X = self._check_X(X)
        vals = self._model.predict(X)
        if self._model.supports_std:
            half = self._q[None, :] * np.maximum(self._model.predict_std(X), _SIGMA_FLOOR)
        else:
            half = np.broadcast_to(self._q[None, :], vals.shape)
        viab = (np.ones(len(X)) if self._clf is None
                else self._clf.predict_proba(X)[:, list(self._clf.classes_).index(1)])
        dist = self._gate.distance(X)
        return BatchPrediction(spec=self.spec, values=vals, lower=vals - half, upper=vals + half,
                               viability=viab, in_hull=dist <= self._gate.threshold,
                               hull_distance=dist)

    def _save_artifacts(self, directory: Path) -> None:
        import joblib
        joblib.dump({"learner": self.learner if isinstance(self.learner, str) else None,
                     "learner_kw": self.learner_kw, "classifier": self.classifier
                     if isinstance(self.classifier, str) else None,
                     "classifier_kw": self.classifier_kw, "alpha": self.alpha,
                     "calibration_fraction": self.calibration_fraction,
                     "random_state": self.random_state, "hull_k": self.hull_k,
                     "hull_quantile": self.hull_quantile, "model": self._model, "clf": self._clf,
                     "q": self._q, "gate": self._gate, "n_viable_train": self.n_viable_train,
                     "n_dropped_incomplete": self.n_dropped_incomplete},
                    Path(directory) / "vector.joblib")


def load_vector(directory: Path, spec: SurrogateSpec, device: Optional[str] = None,
                strict: bool = True, check_env: bool = True) -> VectorSurrogate:
    import joblib
    from .environment import enforce_environment
    if check_env:
        enforce_environment(directory, strict=strict)
    b = joblib.load(Path(directory) / "vector.joblib")
    m = VectorSurrogate(spec, learner=b["learner"] or "mlp_multi",
                        classifier=b["classifier"] or "rf", alpha=b["alpha"],
                        calibration_fraction=b["calibration_fraction"],
                        random_state=b["random_state"], hull_k=b["hull_k"],
                        hull_quantile=b["hull_quantile"], classifier_kw=b["classifier_kw"],
                        **b["learner_kw"])
    m._model, m._clf, m._q, m._gate = b["model"], b["clf"], b["q"], b["gate"]
    m.n_viable_train, m.n_dropped_incomplete = b["n_viable_train"], b["n_dropped_incomplete"]
    m.fitted = True
    return m
