"""Learner families — the model-class axis, orthogonal to the tier axis.

TIER answers *what is emulated* (scalar vs trajectory vs field). LEARNER answers
*with what model family*. The axes are independent, so a tier class can be fitted
with any family and the acceptance battery decides which wins, on evidence rather
than taste.

Families, and the inductive bias each brings:

  ridge Cross-validated ridge regression. Linear: the COMPLEXITY BASELINE, which
        answers whether the flexible families earn their complexity. Native std
        from leverage.

  rf    RandomForest. Axis-aligned splits REPRESENT a cliff, which matters for
        process models whose response switches regime at a parameter threshold
        (a knife-edge beyond which a run collapses).
        Native std from inter-tree spread. Cheap, tuning-free. The baseline.

  gbm   Histogram gradient boosting. Same axis-aligned bias, usually stronger
        pointwise than RF, native NaN handling. No native std.

  xgb   XGBoost gradient-boosted trees, the same algorithmic family as `gbm`.
        OPTIONAL: needs the `xgboost` package, imported at fit. For a caller who
        wants XGBoost specifically. No native std.

  gp    Gaussian process, ARD Matern-5/2 + white noise. The canonical emulator
        for computer experiments. Two things RF cannot give: a predictive
        variance that GROWS AWAY FROM DATA (exactly the extrapolation signal
        calibration needs, since it drives to box edges), and ARD length-scales
        that are themselves a sensitivity readout. Cost is O(n^3), so it
        subsamples above `max_points`, and Matern-5/2 is chosen over RBF
        precisely because RBF's smoothness prior is wrong for knife edges.

  mlp   Deep ensemble of MLPs (torch). Epistemic UQ from ensemble disagreement,
        and the only family here that accepts a CUSTOM LOSS. That is what makes
        physics-guided training possible at all: see `KnowledgeGuidedLoss` below, which implements the "physics-
        guided loss" family of Willard et al. (2022) / the review's Table 1
        (conservation, monotonicity, bounds, consistency as penalties).

Every learner is wrapped by split conformal in `tiers.py`, so honest intervals
do not depend on the family. Families that expose a native std additionally get
NORMALIZED conformal, which yields intervals that widen away from data instead
of a single constant width.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import warnings
from abc import ABC, abstractmethod
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple

import numpy as np


# =============================================================================
# Learner interface
# =============================================================================

class Learner(ABC):
    """A point predictor, optionally with a native predictive standard deviation."""

    #: True when `predict_std` returns a meaningful per-point sigma rather than None.
    supports_std: bool = False
    #: True only when `predict_std` is a predictive POSTERIOR std that may be integrated as a
    #: Gaussian, which is what an acquisition function does with it. A spread across trees, a
    #: leverage term or an ensemble disagreement is a sigma for shaping conformal scores, not one.
    posterior_std: bool = False
    name: str = "learner"

    @abstractmethod
    def fit(self, X: np.ndarray, y: np.ndarray) -> "Learner":
        ...

    @abstractmethod
    def predict(self, X: np.ndarray) -> np.ndarray:
        ...

    def predict_std(self, X: np.ndarray) -> Optional[np.ndarray]:
        """Per-point sigma, or None when the family has no native notion of one.

        This is an *epistemic* signal used to normalise conformal scores. It is
        NOT itself a calibrated interval, and must never be used as one: the
        calibration always comes from the conformal layer.
        """
        return None

    def sensitivity(self) -> Optional[Dict[str, float]]:
        """Cheap per-input importance, if the family exposes one. Lead generator only."""
        return None


# =============================================================================
# Tree families
# =============================================================================

class RFLearner(Learner):
    supports_std = True
    name = "rf"

    def __init__(self, n_estimators: int = 300, random_state: int = 0, **kw: Any) -> None:
        self.kw = dict(n_estimators=n_estimators, random_state=random_state,
                       n_jobs=-1, **kw)
        self._m: Any = None

    def fit(self, X, y):
        from sklearn.ensemble import RandomForestRegressor
        self._m = RandomForestRegressor(**self.kw).fit(X, y)
        return self

    def predict(self, X):
        return self._m.predict(X)

    def predict_std(self, X):
        # Spread across trees. A crude epistemic proxy: it reflects disagreement
        # among bootstrap fits, and collapses in regions where all trees fall
        # into the same leaf, which is why it is only used to SHAPE conformal
        # scores and never as a standalone interval.
        per_tree = np.stack([t.predict(X) for t in self._m.estimators_], axis=0)
        return per_tree.std(axis=0)

    def sensitivity(self):
        return {i: float(v) for i, v in enumerate(self._m.feature_importances_)}


class RidgeLearner(Learner):
    """Cross-validated ridge — the COMPLEXITY BASELINE, and the pair to `logistic`.

    Its job is not to win. It is to answer "are the flexible families earning
    their complexity?", which nothing else in this module can answer. If ridge
    matches `rf` or `mlp` on ranking, the response is essentially linear and the
    nonlinear fit is buying nothing but variance. The survey states the rule
    directly: preserve simple baselines to determine whether added complexity is
    actually justified.

    **Ridge rather than OLS** because `RidgeCV` CONTAINS OLS as its alpha -> 0
    limit, so it costs nothing when OLS would have sufficed and stays stable when
    it would not. That matters because a baseline which fails for a boring reason
    (blown-up coefficients under correlated inputs) is worse than no baseline: a
    strawman makes the nonlinear families look good for the wrong reason.

    Correlation is a real risk here even though a Sobol design samples inputs
    independently, for two reasons that are easy to miss: the regressors are fit
    on the VIABLE SUBSET ONLY, and filtering rows on an outcome can induce
    correlation among inputs within the retained set; and Morris trajectories and
    crossed factorial designs are not space-filling, so their columns are
    correlated by construction.

    **Not Lasso**, which is a different tool: it performs variable SELECTION, and
    under correlated inputs it arbitrarily keeps one member of a correlated group
    and zeros the others. That produces a false sensitivity story ("parameter A
    matters, parameter B does not") in a module that is explicitly building toward
    sensitivity.

    Native sigma comes from LEVERAGE, the textbook extrapolation diagnostic for a
    linear model: var(x) = s^2 (1 + z' (Z'Z + alpha I)^-1 z). Exact for OLS,
    approximate under shrinkage because ridge trades variance for bias.
    """

    supports_std = True
    name = "ridge"

    def __init__(self, alphas: Optional[Sequence[float]] = None,
                 **kw: Any) -> None:
        self.alphas = tuple(alphas) if alphas is not None else tuple(
            np.logspace(-6, 3, 20))
        self.kw = kw
        self._m: Any = None
        self._mu = self._sd = None
        self._Minv: Optional[np.ndarray] = None
        self._s2: float = 0.0

    def fit(self, X, y):
        from sklearn.linear_model import RidgeCV

        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        self._mu = X.mean(axis=0)
        sd = X.std(axis=0); sd[sd <= 0] = 1.0
        self._sd = sd
        Z = (X - self._mu) / self._sd

        # RidgeCV needs at least a few rows to cross-validate; fall back to the
        # smallest alpha (nearest OLS) rather than failing on a tiny fit split.
        cv_ok = len(Z) >= max(5, Z.shape[1] + 2)
        if cv_ok:
            self._m = RidgeCV(alphas=self.alphas, **self.kw).fit(Z, y)
            alpha = float(getattr(self._m, "alpha_", self.alphas[0]))
        else:
            from sklearn.linear_model import Ridge
            alpha = float(min(self.alphas))
            self._m = Ridge(alpha=alpha, **self.kw).fit(Z, y)

        # Leverage machinery for the predictive variance.
        M = Z.T @ Z + alpha * np.eye(Z.shape[1])
        self._Minv = np.linalg.pinv(M)
        resid = y - self._m.predict(Z)
        dof = max(1, len(Z) - Z.shape[1] - 1)
        self._s2 = float(resid @ resid) / dof
        return self

    def _z(self, X):
        return (np.atleast_2d(np.asarray(X, dtype=float)) - self._mu) / self._sd

    def predict(self, X):
        return self._m.predict(self._z(X))

    def predict_std(self, X):
        Z = self._z(X)
        lev = np.einsum("ij,jk,ik->i", Z, self._Minv, Z)   # z' M^-1 z, per row
        return np.sqrt(np.maximum(self._s2 * (1.0 + lev), 0.0))

    def sensitivity(self):
        """Normalised |coefficient| per input.

        Inputs are standardised before fitting, so coefficients are directly
        comparable across parameters with different units. Unlike tree impurity
        importance this is signed information reduced to magnitude, and unlike
        both it says nothing about interactions -- by construction, since the
        model has none.
        """
        c = np.abs(np.asarray(self._m.coef_, dtype=float).ravel())
        tot = c.sum()
        return {i: float(v / tot) for i, v in enumerate(c)} if tot > 0 else \
            {i: 0.0 for i in range(len(c))}


class GBMLearner(Learner):
    supports_std = False
    name = "gbm"

    def __init__(self, random_state: int = 0, **kw: Any) -> None:
        self.kw = dict(random_state=random_state, **kw)
        self._m: Any = None

    def fit(self, X, y):
        from sklearn.ensemble import HistGradientBoostingRegressor
        self._m = HistGradientBoostingRegressor(**self.kw).fit(X, y)
        return self

    def predict(self, X):
        return self._m.predict(X)


class XGBLearner(Learner):
    """XGBoost gradient-boosted trees. OPTIONAL: `xgboost` is not a dependency of this module.

    `gbm` (sklearn's histogram gradient boosting) is the same algorithmic family and needs nothing
    beyond scikit-learn, so it stays the default boosted learner. This entry exists for a caller who
    wants XGBoost specifically -- its regularisation terms, its GPU training, or parity with a
    published XGBoost surrogate. The import is deferred to `fit`, so registering it costs nothing
    where the package is absent, and a missing package fails loudly at the point of use.
    """

    supports_std = False
    name = "xgb"

    def __init__(self, random_state: int = 0, n_estimators: int = 600,
                 learning_rate: float = 0.05, max_depth: int = 6, subsample: float = 0.8,
                 colsample_bytree: float = 0.8, **kw: Any) -> None:
        self.kw = dict(random_state=random_state, n_estimators=n_estimators,
                       learning_rate=learning_rate, max_depth=max_depth, subsample=subsample,
                       colsample_bytree=colsample_bytree, tree_method="hist", **kw)
        self._m: Any = None

    def fit(self, X, y):
        try:
            import xgboost
        except ImportError as e:
            raise ImportError(
                "the 'xgb' learner needs the optional `xgboost` package (pip install xgboost). "
                "`gbm` is the dependency-free gradient-boosting family.") from e
        self._m = xgboost.XGBRegressor(**self.kw).fit(np.asarray(X, dtype=float),
                                                      np.asarray(y, dtype=float))
        return self

    def predict(self, X):
        return self._m.predict(np.asarray(X, dtype=float))


# =============================================================================
# Gaussian process
# =============================================================================

def _fitted_length_scale(kernel: Any) -> Optional[np.ndarray]:
    """The ARD length scales of a fitted composite kernel, or None if it has none.

    Read through `get_params()` rather than by walking `k1.k2...`, because the path depends on how
    the kernel was composed and a wrong attribute chain would raise where this is only diagnostic.
    """
    try:
        params = kernel.get_params()
    except AttributeError:                                    # pragma: no cover - not a kernel
        return None
    for key, value in params.items():
        if key.endswith("length_scale") and not key.endswith("length_scale_bounds"):
            return np.atleast_1d(np.asarray(value, dtype=float))
    return None


class GPLearner(Learner):
    """ARD Matern-5/2 GP with a learned noise term.

    Standardises X and y internally because GP hyperparameter optimisation is
    scale-sensitive and calibration inputs routinely span very different units (a
    duration in days beside a dimensionless multiplier).
    """

    supports_std = True
    posterior_std = True
    name = "gp"

    def __init__(self, nu: float = 2.5, max_points: int = 1500,
                 n_restarts: int = 2, random_state: int = 0,
                 normalize_y: bool = True,
                 length_scale0: Optional[float] = None) -> None:
        #: Starting value for every ARD length scale. `None` means sqrt(d), which is the fix for
        #: the high-dimension non-fit described in `fit`; an explicit number overrides it, and is
        #: there so a test can reproduce the old unit start rather than that value being baked in
        #: where nothing can reach it.
        self.length_scale0 = length_scale0
        self.nu = nu
        self.max_points = max_points
        self.n_restarts = n_restarts
        self.random_state = random_state
        self.normalize_y = normalize_y
        #: Set by `fit`: the start actually used, the length scales the optimiser reached, and the
        #: median relative distance between them -- the diagnostic that separates a fit from a
        #: non-fit, since a GP that never left its start scores like a bad fit and is not one.
        self.length_scale_start_: Optional[float] = None
        self.length_scale_: Optional[np.ndarray] = None
        self.length_scale_move_: float = float("nan")
        self._m: Any = None
        self._mu: Optional[np.ndarray] = None
        self._sd: Optional[np.ndarray] = None
        self.n_used = 0
        #: Sorted indices into the `X` passed to `fit` of the rows the posterior was fitted on.
        #: The same row SET as `training_inputs()` before any `condition_on`, not the same ORDER:
        #: a subsample without `priority` keeps the random draw order, so pair the two by
        #: coordinates, never by position.
        self.train_idx_: Optional[np.ndarray] = None

    def fit(self, X, y, priority=None, keep_best: int = 0):
        """Fit on `(X, y)`, subsampling to `max_points` rows when there are more.

        `priority` (n,) and `keep_best` shape that subsample: the `keep_best` rows with the
        smallest finite priority are always kept (ties to the lower index) and the other
        `max_points - keep_best` rows are drawn without replacement from the rest. A search passes
        its objective here so the incumbent cannot be subsampled away. Without `priority` the
        subsample is the plain random draw. `train_idx_` records which rows were used.
        `keep_best` must be a whole number in [0, max_points] and `priority` must have one entry
        per row of `X`, whether or not a subsample happens.
        """
        from sklearn.gaussian_process import GaussianProcessRegressor
        from sklearn.gaussian_process.kernels import (
            ConstantKernel, Matern, WhiteKernel)

        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        kb = float(keep_best)
        if not (np.isfinite(kb) and kb == int(kb)):
            raise ValueError(
                f"keep_best must be a whole number of rows, got {keep_best!r}; pass an int")
        keep_best = int(kb)
        if not 0 <= keep_best <= self.max_points:
            raise ValueError(
                f"keep_best must be in [0, max_points={self.max_points}], got {keep_best}; "
                "raise max_points or keep fewer rows")
        if priority is not None:
            priority = np.asarray(priority, dtype=float).ravel()
            if len(priority) != len(X):
                raise ValueError(
                    f"priority has {len(priority)} entries, X has {len(X)} rows; pass one "
                    "priority per row")

        # O(n^3): subsample rather than hang. Loud, because a silently
        # subsampled GP would be compared against full-data rivals in a bakeoff.
        n = len(X)
        if n > self.max_points:
            rng = np.random.default_rng(self.random_state)
            if priority is None:
                idx = rng.choice(n, self.max_points, replace=False)
                kept = ""
            else:
                finite = np.flatnonzero(np.isfinite(priority))
                best = finite[np.argsort(priority[finite], kind="stable")[:keep_best]]
                rest = np.ones(n, dtype=bool)
                rest[best] = False
                others = np.flatnonzero(rest)
                drawn = others[rng.choice(len(others), self.max_points - len(best),
                                          replace=False)]
                idx = np.sort(np.concatenate([best, drawn]))
                kept = f", keeping the {len(best)} lowest-priority rows"
            warnings.warn(
                f"GPLearner: subsampled {n} -> {self.max_points} points{kept} "
                "(cubic cost). Raise max_points or prefer a tree family.",
                RuntimeWarning)
            X, y = X[idx], y[idx]
            self.train_idx_ = np.sort(idx)
        else:
            self.train_idx_ = np.arange(n)
        self.n_used = len(X)

        self._mu = X.mean(axis=0)
        sd = X.std(axis=0)
        sd[sd <= 0] = 1.0
        self._sd = sd
        Z = (X - self._mu) / self._sd

        d = Z.shape[1]
        # THE ARD LENGTH SCALES START AT sqrt(d), NOT AT 1, and the difference is the whole fit in
        # high dimension. On standardised inputs the squared distance between two points grows like
        # 2d, so with a unit length scale in 54 dimensions every pair is effectively uncorrelated:
        # measured on EcoSIM_Lusignan, median off-diagonal kernel correlation 1.7e-8 and an
        # objective gradient of 1.5e-4, whereupon L-BFGS-B reports convergence AT THE STARTING
        # POINT and the restarts do not rescue it. Nothing warned; the learner returned R^2 -0.003
        # and looked like a family that had been tried and failed. Started at sqrt(d) the same fit
        # on the same 1,000 points returns R^2 0.881 with no restarts. The threshold measured on
        # synthetic data is between 40 and 44 inputs, so BioCON (28) and miniLEO (16) were below it
        # and Lusignan (54) above -- which is why this survived every case that had run.
        # Full account: memory/dev_logs_adapterkit/20260916j, finding C1, and 20260916k section 2.
        ls0 = float(self.length_scale0) if self.length_scale0 else float(np.sqrt(d))
        # Generous ConstantKernel bounds: with a narrow upper bound the signal
        # variance saturates against it and sklearn emits a ConvergenceWarning,
        # which means the fit was bound-limited rather than optimised.
        kernel = (ConstantKernel(1.0, (1e-4, 1e6))
                  * Matern(length_scale=np.full(d, ls0), nu=self.nu,
                           length_scale_bounds=(1e-2, 1e3))
                  + WhiteKernel(1e-3, (1e-8, 1e1)))
        self._m = GaussianProcessRegressor(
            kernel=kernel, normalize_y=self.normalize_y,
            n_restarts_optimizer=self.n_restarts,
            random_state=self.random_state).fit(Z, y)
        self.length_scale_start_ = ls0
        self.length_scale_ = _fitted_length_scale(self._m.kernel_)
        # THE SILENT HALF OF THE DEFECT, made loud. A GP whose optimiser never left its starting
        # point is not a GP that fitted badly, it is a GP that did not fit, and a score alone
        # cannot tell the two apart. sklearn raises nothing for it, so this does.
        #
        # THE MEASURE IS THE MEDIAN RELATIVE MOVE, and the bar is not arbitrary: on a 48-input
        # synthetic case the failed fit moves its length scales by a median of 5e-6 relative while
        # the working one moves by 143, eight orders of magnitude apart, so anything in between
        # separates them. An exact-equality test would MISS it -- L-BFGS-B takes one flat step and
        # stops, leaving the scales near the start rather than exactly on it.
        self.length_scale_move_ = (
            float(np.median(np.abs(self.length_scale_ - ls0) / ls0))
            if self.length_scale_ is not None and self.length_scale_.size else float("nan"))
        if self.length_scale_move_ < 1e-3:
            warnings.warn(
                f"GPLearner: the optimiser barely moved the {d} ARD length scales from their "
                f"start of {ls0:.4g} (median relative move {self.length_scale_move_:.2e}), so the "
                f"kernel is effectively the initial one and the fit carries little information "
                f"from the data. This is the high-dimension failure mode: with too small a start "
                f"the objective is flat where the optimiser begins. Check the score, and see "
                f"`length_scale0` if you set it yourself.",
                RuntimeWarning)
        return self

    def _z(self, X):
        return (np.asarray(X, dtype=float) - self._mu) / self._sd

    def predict(self, X):
        return self._m.predict(self._z(X))

    def predict_std(self, X):
        _, sd = self._m.predict(self._z(X), return_std=True)
        return sd

    def training_inputs(self) -> np.ndarray:
        """(n_used, p) native-unit inputs the posterior conditions on.

        The de-standardised stored training set: after any `max_points` subsample, and including
        points added by `condition_on`. Rows are in stored order, which is not the order of
        `train_idx_` (see there), so `training_inputs()[i]` need not be `X[train_idx_[i]]`.
        """
        if self._m is None:
            raise RuntimeError("GPLearner.training_inputs: the learner is not fitted")
        return np.asarray(self._m.X_train_, dtype=float) * self._sd + self._mu

    def predict_mean_std(self, X):
        """Posterior mean and predictive std from ONE posterior evaluation.

        The std is the predictive std of an observation: it includes the fitted WhiteKernel noise,
        so it does not fall to zero at a training point.
        """
        return self._m.predict(self._z(X), return_std=True)

    def condition_on(self, X_new, y_new) -> "GPLearner":
        """A NEW learner whose posterior also conditions on `(X_new, y_new)`, nothing refitted.

        Kernel hyperparameters, the X standardisation and the y normalisation are all FROZEN at
        the values this learner was fitted with, which is what a Kriging believer requires: the
        fake observation may shrink the posterior spread near it, and must not move the
        hyperparameters or the prior mean anywhere else. `y_new` is in this learner's own
        training space. It conditions on the stored training set (`X_train_`, possibly
        subsampled by `max_points`), never on the caller's data, so no point is counted twice.
        This learner is left untouched.
        """
        import copy
        from sklearn.gaussian_process import GaussianProcessRegressor

        if self._m is None:
            raise RuntimeError("GPLearner.condition_on: the learner is not fitted")
        g = self._m
        # sklearn stores the training targets normalised and keeps the constants only as private
        # attributes; refuse rather than silently de-normalise with the wrong ones.
        for attr in ("X_train_", "y_train_", "kernel_", "_y_train_mean", "_y_train_std"):
            if not hasattr(g, attr):
                raise RuntimeError(
                    f"GPLearner.condition_on: the fitted GaussianProcessRegressor has no {attr!r} "
                    "(sklearn internals changed); conditioning cannot freeze the normalisation")
        Xn = np.atleast_2d(np.asarray(X_new, dtype=float))
        yn = np.asarray(y_new, dtype=float).ravel()
        if len(Xn) != len(yn):
            raise ValueError(f"condition_on: {len(Xn)} points but {len(yn)} values")
        if not np.all(np.isfinite(yn)) or not np.all(np.isfinite(Xn)):
            raise ValueError("condition_on: non-finite conditioning point or value")
        Z = np.vstack([g.X_train_, self._z(Xn)])
        yz = np.concatenate([np.asarray(g.y_train_, dtype=float).ravel(),
                             (yn - g._y_train_mean) / g._y_train_std])
        gp = GaussianProcessRegressor(kernel=g.kernel_, optimizer=None, normalize_y=False,
                                      alpha=g.alpha)
        try:
            gp.fit(Z, yz)
        except np.linalg.LinAlgError as exc:
            raise ValueError(
                "condition_on: the kernel matrix is not positive definite after adding the "
                "points, typically because one duplicates a training point; separate proposals "
                "from observed points before conditioning") from exc
        gp._y_train_mean, gp._y_train_std = g._y_train_mean, g._y_train_std
        out = copy.copy(self)
        out._m = gp
        out.n_used = len(Z)
        return out

    def sensitivity(self):
        """Inverse ARD length-scale per input: short length-scale = influential.

        This is free sensitivity information no tree family provides, and unlike
        impurity importance it is not biased toward high-cardinality inputs.
        """
        ls = None
        for p, v in self._m.kernel_.get_params().items():
            if p.endswith("length_scale") and np.ndim(v) == 1:
                ls = np.asarray(v, dtype=float)
        if ls is None:
            return None
        inv = 1.0 / np.maximum(ls, 1e-12)
        return {i: float(v) for i, v in enumerate(inv / inv.sum())}


# =============================================================================
# Knowledge-guided loss (the PGNN hook)
# =============================================================================

class KnowledgeGuidedLoss:
    """Soft physics/domain penalties added to the data loss of an MLP.

    This is the "physics-guided loss" family of the review's Table 1, and the
    mechanism Liu et al. (2024) used for KGML-ag-Carbon (mass balance,
    prediction thresholds, monotone responses). It is the ONE place in this
    package where domain knowledge enters training rather than post hoc.

    NOT a PINN, and the difference is not pedantic. A PINN differentiates the
    network with respect to SPACE AND TIME and drives a PDE residual to zero;
    this penalises a relation among the OUTPUTS of a theta -> y map, and has no
    coordinates to differentiate against. Adding a PDE residual term here would
    need a governing equation, which a PDE-based process model has and many
    process models do not, plus boundary and initial conditions and a
    loss-balancing scheme. Scope, entry condition and the documented failure
    modes: `docs/41` section 4.2. It is gated two tiers away and is deliberately
    not started here.

    Two caveats carried straight from the literature and stated here so nobody
    mistakes a penalty for a guarantee:

    * "Soft physics is not guaranteed physics." A small average penalty does not
      imply the constraint holds pointwise. Where a constraint can instead be
      made STRUCTURAL, prefer a `TargetSpec.transform` (positivity via log,
      bounded fractions via logit), which holds under any weights.
    * Penalties regularise toward the constraint you impose. Imposing a wrong
      monotonicity produces a confidently wrong model, so every entry here
      should be traceable to a verified source-level mechanism, not intuition.

    Parameters
    ----------
    monotone : {input_index: +1 or -1}
        Required sign of d(output)/d(input). Enforced by penalising violations
        of the autograd gradient at the training points.
    bounds : (lo, hi)
        Admissible output range; either side may be None.
    weight : float
        Multiplier on the summed penalty (`alpha_phys` in Jeong et al.).
    """

    def __init__(self, monotone: Optional[Mapping[int, int]] = None,
                 bounds: Optional[Tuple[Optional[float], Optional[float]]] = None,
                 weight: float = 1.0) -> None:
        self.monotone = dict(monotone or {})
        self.bounds = bounds
        self.weight = float(weight)

    @property
    def active(self) -> bool:
        return bool(self.monotone) or self.bounds is not None

    def penalty(self, torch, x, pred):
        """Scalar penalty tensor. `x` must require grad when `monotone` is used."""
        total = pred.new_zeros(())
        if self.monotone:
            g, = torch.autograd.grad(pred.sum(), x, create_graph=True)
            for j, sign in self.monotone.items():
                # relu(-sign * dP/dx_j): zero when the sign is correct.
                total = total + torch.relu(-float(sign) * g[:, j]).pow(2).mean()
        if self.bounds is not None:
            lo, hi = self.bounds
            if lo is not None:
                total = total + torch.relu(lo - pred).pow(2).mean()
            if hi is not None:
                total = total + torch.relu(pred - hi).pow(2).mean()
        return self.weight * total


class MLPEnsembleLearner(Learner):
    """Deep ensemble of MLPs (torch), optionally physics-guided.

    Ensemble disagreement is the epistemic signal (Lakshminarayanan-style deep
    ensembles); it is used to normalise conformal scores, never as an interval
    on its own.

    Beyond accuracy, it is the only family here that accepts a custom loss, which
    makes it the entry point for knowledge-guided training (`KnowledgeGuidedLoss`).
    """

    supports_std = True
    name = "mlp"

    def __init__(self, hidden: Sequence[int] = (64, 64), n_models: int = 5,
                 epochs: int = 400, lr: float = 1e-3, weight_decay: float = 1e-4,
                 batch_size: Optional[int] = None, random_state: int = 0,
                 kg_loss: Optional[KnowledgeGuidedLoss] = None,
                 device: str = "cpu") -> None:
        self.hidden = tuple(hidden)
        self.n_models = n_models
        self.epochs = epochs
        self.lr = lr
        self.weight_decay = weight_decay
        self.batch_size = batch_size
        self.random_state = random_state
        self.kg_loss = kg_loss
        self.device = device
        self._nets: list = []
        self._mu = self._sd = None
        self._ymu = 0.0
        self._ysd = 1.0

    def _build(self, torch, nn, d_in: int):
        layers, prev = [], d_in
        for h in self.hidden:
            layers += [nn.Linear(prev, h), nn.Tanh()]  # Tanh: smooth 2nd deriv,
            prev = h                                    # needed for grad penalties
        layers += [nn.Linear(prev, 1)]
        return nn.Sequential(*layers).to(self.device)

    def fit(self, X, y):
        import torch
        from torch import nn

        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float).ravel()
        self._mu = X.mean(axis=0)
        sd = X.std(axis=0); sd[sd <= 0] = 1.0
        self._sd = sd
        self._ymu = float(y.mean())
        self._ysd = float(y.std()) or 1.0

        Z = torch.tensor((X - self._mu) / self._sd, dtype=torch.float32, device=self.device)
        T = torch.tensor((y - self._ymu) / self._ysd, dtype=torch.float32,
                         device=self.device).unsqueeze(1)

        need_grad = self.kg_loss is not None and bool(self.kg_loss.monotone)
        self._nets = []
        for k in range(self.n_models):
            torch.manual_seed(self.random_state + k)   # ensemble diversity = init seed
            net = self._build(torch, nn, Z.shape[1])
            opt = torch.optim.Adam(net.parameters(), lr=self.lr,
                                   weight_decay=self.weight_decay)
            n = len(Z)
            bs = self.batch_size or n
            for _ in range(self.epochs):
                perm = torch.randperm(n, device=self.device)
                for a in range(0, n, bs):
                    idx = perm[a:a + bs]
                    xb = Z[idx].clone().requires_grad_(need_grad)
                    pred = net(xb)
                    loss = nn.functional.mse_loss(pred, T[idx])
                    if self.kg_loss is not None and self.kg_loss.active:
                        # Penalties act in NATIVE output units so the declared
                        # bounds mean what the caller thinks they mean.
                        native = pred * self._ysd + self._ymu
                        loss = loss + self.kg_loss.penalty(torch, xb, native)
                    opt.zero_grad(); loss.backward(); opt.step()
            net.eval()
            self._nets.append(net)
        return self

    def _forward(self, X):
        import torch
        Z = torch.tensor((np.asarray(X, dtype=float) - self._mu) / self._sd,
                         dtype=torch.float32, device=self.device)
        with torch.no_grad():
            out = np.stack([n(Z).cpu().numpy().ravel() for n in self._nets], axis=0)
        return out * self._ysd + self._ymu

    def predict(self, X):
        return self._forward(X).mean(axis=0)

    def predict_std(self, X):
        return self._forward(X).std(axis=0)


# =============================================================================
# Factory
# =============================================================================

LEARNERS = {"ridge": RidgeLearner, "rf": RFLearner, "gbm": GBMLearner,
            "gp": GPLearner, "mlp": MLPEnsembleLearner, "xgb": XGBLearner}


def make_learner(spec: Any, **kw: Any) -> Learner:
    """Resolve a learner from a name, a class, or an already-built instance."""
    if isinstance(spec, Learner):
        return spec
    if isinstance(spec, str):
        if spec not in LEARNERS:
            raise ValueError(
                f"unknown learner {spec!r}; choose from {sorted(LEARNERS)} "
                "or pass a Learner instance")
        return LEARNERS[spec](**kw)
    if isinstance(spec, type) and issubclass(spec, Learner):
        return spec(**kw)
    raise TypeError(f"cannot resolve learner from {spec!r}")


# =============================================================================
# Viability classifiers — the OTHER half of S1, and equally the user's choice
# =============================================================================
#
# S1 answers two questions: "will this run survive?" (classification) and "if it
# does, what comes out?" (regression). Both families are the caller's choice: a
# bake-off with the classifier fixed would compare half-approaches over one hidden
# other half, and that half is the alive/dead boundary -- typically the sharpest
# structure in a process model's response.

class MLPEnsembleClassifier:
    """Deep ensemble of MLPs for the alive/dead question, optionally guided.

    The torch counterpart of `MLPEnsembleLearner`, and the reason it exists is
    not symmetry: it is the ONLY viability model here that can carry a
    knowledge-guided loss. The viability boundary is typically the sharpest
    structure in a process model's response and the region with least training
    data on either side, so being able to assert "survival must be monotone in
    this parameter" applies domain knowledge exactly where guessing is most
    expensive.

    Deliberate choices:

    * **The penalty acts on the LOGIT, not the probability.** A sigmoid
      saturates, so probability gradients vanish in precisely the confident
      regions and the penalty would quietly stop biting. Since the sigmoid is
      strictly increasing, sign(d logit/dx) == sign(dp/dx), so the constraint
      expressed is identical while the gradient stays well-scaled.
    * **`bounds` is ignored, by design.** A probability is already confined to
      [0, 1] by the sigmoid, so the constraint is STRUCTURAL and holds under any
      weights. Adding a penalty for it would be strictly worse than free. This
      is the "prefer a transform over a soft penalty" rule applying itself.
    * **Class imbalance** is handled with `pos_weight`, the BCE analogue of
      `class_weight="balanced"`, because failures are usually the minority and
      an unweighted fit would learn to call everything viable.

    Exposes the sklearn surface (`fit`, `predict_proba`, `predict`, `classes_`)
    so it drops into `S1Surrogate(classifier=...)` with no special-casing.
    """

    def __init__(self, hidden: Sequence[int] = (64, 64), n_models: int = 5,
                 epochs: int = 400, lr: float = 1e-3, weight_decay: float = 1e-4,
                 batch_size: Optional[int] = None, random_state: int = 0,
                 kg_loss: Optional[KnowledgeGuidedLoss] = None,
                 balanced: bool = True, device: str = "cpu") -> None:
        self.hidden = tuple(hidden)
        self.n_models = n_models
        self.epochs = epochs
        self.lr = lr
        self.weight_decay = weight_decay
        self.batch_size = batch_size
        self.random_state = random_state
        self.kg_loss = kg_loss
        self.balanced = balanced
        self.device = device
        self.classes_ = np.array([0, 1])
        self._nets: list = []
        self._mu = self._sd = None

    def _build(self, torch, nn, d_in: int):
        layers, prev = [], d_in
        for h in self.hidden:
            layers += [nn.Linear(prev, h), nn.Tanh()]
            prev = h
        layers += [nn.Linear(prev, 1)]          # one logit
        return nn.Sequential(*layers).to(self.device)

    def fit(self, X, y):
        import torch
        from torch import nn

        X = np.asarray(X, dtype=float)
        y = np.asarray(y).ravel().astype(float)
        self.classes_ = np.unique(y).astype(int)
        if len(self.classes_) == 1:
            # Degenerate but survivable: remember the single class and short-
            # circuit, rather than training a net that cannot learn a boundary.
            self._nets = []
            return self
        self.classes_ = np.array([0, 1])

        self._mu = X.mean(axis=0)
        sd = X.std(axis=0); sd[sd <= 0] = 1.0
        self._sd = sd
        Z = torch.tensor((X - self._mu) / self._sd, dtype=torch.float32,
                         device=self.device)
        T = torch.tensor(y, dtype=torch.float32, device=self.device).unsqueeze(1)

        pos_weight = None
        if self.balanced:
            n_pos = float(y.sum()); n_neg = float(len(y) - n_pos)
            if n_pos > 0:
                pos_weight = torch.tensor([n_neg / n_pos], dtype=torch.float32,
                                          device=self.device)
        lossfn = nn.BCEWithLogitsLoss(pos_weight=pos_weight)

        need_grad = self.kg_loss is not None and bool(self.kg_loss.monotone)
        self._nets = []
        for k in range(self.n_models):
            torch.manual_seed(self.random_state + k)
            net = self._build(torch, nn, Z.shape[1])
            opt = torch.optim.Adam(net.parameters(), lr=self.lr,
                                   weight_decay=self.weight_decay)
            n = len(Z)
            bs = self.batch_size or n
            for _ in range(self.epochs):
                perm = torch.randperm(n, device=self.device)
                for a in range(0, n, bs):
                    idx = perm[a:a + bs]
                    xb = Z[idx].clone().requires_grad_(need_grad)
                    logit = net(xb)
                    loss = lossfn(logit, T[idx])
                    if need_grad:
                        # Penalty on the logit; see the class docstring for why
                        # not on the probability. `bounds` is intentionally not
                        # applied: the sigmoid already guarantees [0, 1].
                        loss = loss + KnowledgeGuidedLoss(
                            monotone=self.kg_loss.monotone,
                            weight=self.kg_loss.weight).penalty(torch, xb, logit)
                    opt.zero_grad(); loss.backward(); opt.step()
            net.eval()
            self._nets.append(net)
        return self

    def predict_proba(self, X):
        import torch
        X = np.atleast_2d(np.asarray(X, dtype=float))
        if not self._nets:                       # single-class degenerate fit
            p = np.full(len(X), float(self.classes_[0]))
            return np.column_stack([1.0 - p, p])
        Z = torch.tensor((X - self._mu) / self._sd, dtype=torch.float32,
                         device=self.device)
        with torch.no_grad():
            # Average PROBABILITIES across members, not logits: averaging logits
            # would let one over-confident member dominate the ensemble.
            p = np.mean([torch.sigmoid(n(Z)).cpu().numpy().ravel()
                         for n in self._nets], axis=0)
        return np.column_stack([1.0 - p, p])

    def predict(self, X):
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


CLASSIFIERS = {
    "rf": ("sklearn.ensemble", "RandomForestClassifier",
           dict(n_estimators=300, n_jobs=-1, class_weight="balanced")),
    "gbm": ("sklearn.ensemble", "HistGradientBoostingClassifier", {}),
    "logistic": ("sklearn.linear_model", "LogisticRegression",
                 dict(max_iter=2000, class_weight="balanced")),
    "gp": ("sklearn.gaussian_process", "GaussianProcessClassifier", {}),
    # The torch deep ensemble. Registered last because it is the expensive one,
    # and chosen when the viability boundary itself needs domain knowledge.
    "mlp": ("models.surrogate.learners", "MLPEnsembleClassifier", {}),
}


def make_classifier(spec: Any = "rf", random_state: int = 0, **kw: Any) -> Any:
    """Resolve a viability classifier from a name or a ready sklearn estimator.

    Any object exposing `fit` / `predict_proba` / `classes_` is accepted, so a
    caller is never limited to this registry.
    """
    if spec is None:
        spec = "rf"
    if isinstance(spec, str):
        if spec not in CLASSIFIERS:
            raise ValueError(
                f"unknown classifier {spec!r}; choose from {sorted(CLASSIFIERS)} "
                "or pass a fitted-style sklearn estimator")
        mod, cls, defaults = CLASSIFIERS[spec]
        import importlib
        klass = getattr(importlib.import_module(mod), cls)
        params = dict(defaults)
        params.update(kw)
        try:
            return klass(random_state=random_state, **params)
        except TypeError:
            return klass(**params)          # a few estimators take no seed
    if hasattr(spec, "fit") and hasattr(spec, "predict_proba"):
        return spec
    raise TypeError(
        f"cannot resolve classifier from {spec!r}; pass a name from "
        f"{sorted(CLASSIFIERS)} or an estimator with fit/predict_proba")


# =============================================================================
# Guidance — what to pick when you do not want to pick
# =============================================================================

#: Per-goal suggestions. Each entry is (family, one-line reason).
#: These are PRIORS distilled from the model's known structure and the
#: literature, not measurements. `compare_learners` outranks them on contact
#: with data, and the guidance says so every time it is asked.
_GOAL_ADVICE: Dict[str, Dict[str, Any]] = {
    "screen": {
        "what": "rank many candidates cheaply, then spend runs on the best few",
        "regressor": [
            ("rf", "ranking survives moderate error; fast, tuning-free, handles cliffs"),
            ("gbm", "usually the strongest pointwise of the tree families"),
        ],
        "classifier": [("rf", "sharp alive/dead boundary; trees split on it directly")],
        "note": "intervals barely matter here, so a family without a native sigma is fine",
    },
    "sensitivity": {
        "what": "find which parameters and interactions actually drive the targets",
        "regressor": [
            ("gp", "ARD length-scales give per-input relevance for free"),
            ("rf", "impurity importance as a cross-check, biased but independent"),
        ],
        "classifier": [("rf", "importances also available for the viability side")],
        "note": ("neither gives INTERACTIONS. For those, run Sobol (SALib) over "
                 "whichever emulator wins the bake-off"),
    },
    "rule_out": {
        # gbm has no native sigma, so it can only give one constant interval
        # width. Ruling out on a constant width is exactly the over-claim
        # docs/41 section 2.1 withdrew, so it is barred here regardless of what
        # the response structure looks like.
        "exclude": ["gbm"],
        "what": "decide whether a region can be excluded (reachability / NROY)",
        "regressor": [
            ("gp", "variance grows away from data, so intervals widen honestly"),
            ("rf", "native sigma too; better on cliffs, weaker on smooth trends"),
        ],
        "classifier": [
            ("rf", "conservative near the cliff"),
            ("logistic", "better-calibrated probabilities when failures are few"),
        ],
        "note": ("REQUIRES a native sigma so conformal is normalised; `gbm` gives "
                 "one constant width and should not be used here. And no verdict "
                 "outside the hull, ever (docs/41 section 2.1)"),
    },
    "search": {
        "what": "hunt for all good configurations, e.g. TDME over the emulator",
        "regressor": [
            ("gp", "smooth surface an optimiser can descend; strong at small n"),
            ("mlp", "cheap batched prediction at the 1e5-1e6 evaluations TDME wants"),
        ],
        "classifier": [("rf", "reject dead regions before the optimiser wastes budget")],
        "note": "prediction speed matters more than fit time; a GP gets slow to PREDICT at large n",
    },
    "physics_constrained": {
        # A hard constraint, not a preference: no other family can carry a
        # custom loss, so no amount of "but the response has cliffs" may
        # introduce a tree here.
        "only": ["mlp"],
        "what": "impose monotonicity, bounds or conservation during training",
        "regressor": [("mlp", "the only family here that accepts a custom loss")],
        "classifier": [("rf", "unconstrained; the penalties apply to the regressor")],
        "note": ("soft penalties are not guarantees. Prefer a structural "
                 "TargetSpec.transform where one exists, since it holds under any weights"),
    },
}


def recommend(goal: str, n_train: Optional[int] = None,
              structure: Optional[str] = None) -> Dict[str, Any]:
    """Suggest families for a stated modelling goal, with reasons.

    For a user who does not want to choose blind. Returns the goal's intent, a
    ranked regressor list, a ranked classifier list, caveats, and any
    adjustments implied by dataset size or known response structure.

    `goal`      one of `recommend_goals()`
    `n_train`   training rows, if known -- switches advice away from the GP as
                its cubic cost bites, and away from the MLP when data is thin
    `structure` "cliff" | "smooth" | None -- what the response is believed to do

    This is a PRIOR, not a measurement. `compare_learners` settles it on data,
    and that is stated in the returned `decide_empirically` field rather than
    buried in a docstring.
    """
    if goal not in _GOAL_ADVICE:
        raise ValueError(
            f"unknown goal {goal!r}; choose from {sorted(_GOAL_ADVICE)}")
    a = _GOAL_ADVICE[goal]
    regressors = list(a["regressor"])
    caveats = [a["note"]]

    if n_train is not None:
        if n_train > 3000 and any(r == "gp" for r, _ in regressors):
            regressors = [(r, w) for r, w in regressors if r != "gp"] + [
                ("gp", f"DEMOTED: {n_train} rows exceeds the GP's comfortable "
                       "range; it will subsample (cubic cost)")]
            caveats.append(
                f"n={n_train}: the GP subsamples above max_points, so a bake-off "
                "would compare it on less data than its rivals")
        if n_train < 150 and any(r == "mlp" for r, _ in regressors):
            regressors = [(r, w) for r, w in regressors if r != "mlp"] + [
                ("mlp", f"DEMOTED: {n_train} rows is thin for a neural ensemble")]
        if n_train < 150:
            caveats.append(
                f"n={n_train}: with a 30% conformal calibration split only ~"
                f"{int(0.3 * n_train)} points set the interval width, so coverage "
                "will be coarse and the intervals wide")

    # Structure advice must be able to INTRODUCE a family, not merely reorder
    # the ones already listed. A goal whose default list happens to be all-smooth
    # (`search` = gp, mlp) would otherwise answer "the response has cliffs" by
    # changing nothing, which is worse than silence because it looks considered.
    only = a.get("only")
    excluded = set(a.get("exclude", ()))

    def _promote(preferred, reason):
        nonlocal regressors
        if only:                       # a hard constraint outranks structure
            caveats.append(
                f"structure advice suppressed: this goal admits only {only}")
            return
        have = {r for r, _ in regressors}
        for fam in preferred:
            if fam in excluded:
                caveats.append(
                    f"{fam} would suit {structure} structure but is barred for "
                    f"this goal (see above)")
                continue
            if fam not in have:
                regressors.append((fam, f"ADDED for {structure} structure: {reason}"))
        regressors.sort(key=lambda rw: rw[0] not in preferred)

    if structure == "cliff":
        _promote(("rf", "gbm"),
                 "axis-aligned splits represent a step; GP and MLP smooth across it")
        caveats.append("cliff structure: axis-aligned splits represent a step; "
                       "GP and MLP will smooth across it")
    elif structure == "smooth":
        _promote(("gp", "mlp"),
                 "a Matern prior fits a smooth response; trees look blocky")
        caveats.append("smooth structure: the GP's Matern prior fits it well and "
                       "trees will look blocky")

    # A standing caveat, on every goal: without a linear baseline in the
    # bake-off there is nothing to tell you whether the flexible families are
    # earning their complexity, and a crowned `mlp` could be losing to a
    # straight line at a thousandth of the cost.
    caveats.append(
        "always include `ridge` in the bake-off as the complexity baseline: if "
        "it matches a nonlinear family on ranking, the complexity is not "
        "earning its place")

    return {
        "goal": goal,
        "what_this_is_for": a["what"],
        "regressors": regressors,
        "classifiers": list(a["classifier"]),
        "caveats": caveats,
        "decide_empirically": (
            "These are priors, not measurements. Run "
            "validate.compare_learners(...) on your own X/Y and let the "
            "acceptance battery rank them; it outranks this table."),
    }


def recommend_goals() -> Dict[str, str]:
    """The goals `recommend()` understands, each with a one-line description."""
    return {k: v["what"] for k, v in _GOAL_ADVICE.items()}


def explain_recommendation(rec: Dict[str, Any]) -> str:
    """Human-readable form of `recommend()`."""
    out = [f"goal: {rec['goal']} — {rec['what_this_is_for']}", "",
           "  regressor (predicts the numbers):"]
    for i, (name, why) in enumerate(rec["regressors"], 1):
        out.append(f"    {i}. {name:4s}  {why}")
    out.append("  classifier (predicts alive vs dead):")
    for i, (name, why) in enumerate(rec["classifiers"], 1):
        out.append(f"    {i}. {name:4s}  {why}")
    out.append("  caveats:")
    out += [f"    - {c}" for c in rec["caveats"]]
    out += ["", f"  {rec['decide_empirically']}"]
    return "\n".join(out)
