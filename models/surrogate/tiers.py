"""S0 to S3 — the tier axis. The learner family is a separate axis (learners.py).

Gated ascent (docs/41 section 4): a tier may not be built until the tier below
has FAILED a written acceptance test.

  S0  point prediction only. Ranking, screening, sensitivity structure.
      No intervals, no viability. Cheap enough to refit constantly.

  S1  two-stage: viability classifier, then per-target regressors on the viable
      subset only, with split-conformal predictive intervals and an
      extrapolation gate.

  S2  trajectory. theta -> y(t) per target through a latent ROM, reduced to the
      scalar S1 predicts so it stays a drop-in for every existing consumer.

  S3  knowledge-guided. S2 plus process STRUCTURE: targets composed from their
      components rather than fitted, and declared admissibility enforced.

All four accept ANY learner family (`ridge`, `rf`, `gbm`, `xgb`, `gp`, `mlp`, or a custom
`Learner`).
The tier decides WHAT is emulated and how uncertainty is calibrated; the learner
decides WITH WHAT. Keeping them orthogonal is what lets `compare_learners` pick
the family on evidence instead of taste.

Why S1 is two-stage: a failed or collapsed run and a viable one are not two
ends of a continuum, and asking one regressor to span a regime boundary
degrades it everywhere, not just at the boundary.

`load` rebuilds any saved surrogate: the four tier classes here by `spec.tier`, and the
architecture classes in the sibling modules (`sequence`, `multioutput`, `fields`,
`spatiotemporal`, `graphs`, `operators`) by the class name `save` writes into `tier.json`.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import copy
import inspect
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from .base import (
    BatchPrediction,
    HullGate,
    SurrogateModel,
    apply_transform,
    invert_transform,
)
from .learners import Learner, make_classifier, make_learner
from .spec import SurrogateSpec

# Floor on the normalising sigma so a collapsed epistemic estimate cannot make a
# conformal score explode (or a width vanish) by dividing by ~0.
_SIGMA_FLOOR = 1e-9


def _reduce_annual_mean_sum(traj: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Mean over years of the within-year sum. (N, T, D) -> (N, T).

    This is the per-step form of a year-end value: once a within-year CUMULATIVE
    series has been differenced into per-step values, the year-end cumulative value
    is that year's sum of per-step values.
    """
    uy = np.unique(years)
    per_year = np.stack([traj[:, :, years == y].sum(axis=2) for y in uy])   # (Y, N, T)
    return per_year.mean(axis=0)


#: Trajectory -> scalar. Each takes (N, T, D) and the timestep labels, returns (N, T).
#: A reducer belongs HERE and not on `TargetSpec`, which deliberately carries only the
#: reduced value's identity: the module's contract is that reduction happens upstream,
#: and S2 is the one tier that must undo and redo it.
REDUCERS = {
    "mean":             lambda a, _idx: a.mean(axis=2),
    "sum":              lambda a, _idx: a.sum(axis=2),
    "final":            lambda a, _idx: a[:, :, -1],
    "max":              lambda a, _idx: a.max(axis=2),
    "annual_mean_sum":  _reduce_annual_mean_sum,
}


#: Floor for a relative-error denominator, as a fraction of the column's own largest magnitude.
#: A relative check still has to divide by something when the reference value is zero, and the
#: only defensible "something" is the scale of the data rather than the literal 1.0 that used to
#: sit here -- which silently turned the check absolute for every quantity smaller than 1.
_SCALE_FLOOR_FRAC = 1e-6


def _rel_scale(ref: np.ndarray, ok: np.ndarray) -> np.ndarray:
    """Denominator for a per-target relative comparison of `ref`, masked by `ok`.

    PER TARGET, because targets carry different units: one global floor taken from a
    concentration in mol/L would make a carbon flux's check meaningless and the other way round.
    Each column's floor is `_SCALE_FLOOR_FRAC` of that column's largest finite magnitude, and a
    column that is all zeros falls back to 1.0, where relative error is undefined anyway.
    """
    ref = np.atleast_2d(ref)
    scale = np.abs(ref).astype(float)
    with np.errstate(invalid="ignore"):
        col_max = np.nanmax(np.where(np.isfinite(scale), scale, np.nan), axis=0)
    col_max = np.where(np.isfinite(col_max) & (col_max > 0.0), col_max, 1.0)
    floor = _SCALE_FLOOR_FRAC * col_max
    scale = np.maximum(scale, floor[None, :])
    scale[~np.isfinite(scale) | (scale <= 0.0)] = 1.0
    return scale[ok]


def _conformal_quantile(scores: np.ndarray, alpha: float, target: str = "") -> float:
    """The split-conformal radius for one target, or `inf` when the calibration set is too small.

    The finite-sample guarantee needs the `ceil((n+1)(1-alpha))/n` quantile of the calibration
    residuals. When `ceil((n+1)(1-alpha)) > n` -- fewer than 19 calibration rows at alpha 0.05 --
    that rank does not exist, and the honest answer is an INFINITE interval: the data cannot
    support a 95 percent statement. The code used to clamp the level to 1.0, which quietly returns
    the largest observed residual instead and under-covers, with nothing in the output saying the
    interval was not the one that was asked for.

    An infinite radius is deliberately awkward downstream. `interval_coverage` then reports
    coverage 1.0 with infinite mean width, which `validate` already names as "honest and useless,
    which is a real and acceptable outcome, but it must be visible as such" -- and visible is the
    whole point, because the alternative is an interval that looks 95 percent and is not.
    """
    scores = np.asarray(scores, dtype=float)
    n = len(scores)
    if n == 0:
        return float("inf")
    k = int(np.ceil((n + 1) * (1.0 - alpha)))
    if k > n:
        warnings.warn(
            f"conformal interval for {target or 'a target'}: {n} calibration rows cannot support "
            f"a {(1 - alpha) * 100:.0f}% interval (the guarantee needs rank {k} of {n}), so the "
            f"radius is infinite. Calibrate on at least {int(np.ceil(1 / alpha)) - 1} rows, or "
            f"raise alpha, rather than reading the widest residual as a {(1 - alpha) * 100:.0f}% "
            f"bound.",
            RuntimeWarning)
        return float("inf")
    return float(np.quantile(scores, k / n, method="higher"))


def _fresh(spec: Any, **kw: Any) -> Learner:
    """A NEW learner per target — reusing one instance would refit over itself."""
    if isinstance(spec, Learner):
        return copy.deepcopy(spec)
    return make_learner(spec, **kw)


# =============================================================================
# S0 — screening surface
# =============================================================================

class S0Surrogate(SurrogateModel):
    """Point-prediction emulator. No uncertainty, no viability, no gate.

    Use for ranking candidates and for sensitivity structure. Do NOT use it to
    rule anything out: ruling out requires honest intervals, which this tier
    does not produce, and an S0 point estimate carries no signal about whether
    it is entitled to be believed.
    """

    def __init__(self, spec: SurrogateSpec, learner: Any = "rf",
                 **learner_kw: Any) -> None:
        if spec.tier != "S0":
            raise ValueError(f"S0Surrogate requires tier 'S0', spec says {spec.tier!r}")
        super().__init__(spec)
        self.learner = learner
        self.learner_kw = learner_kw
        self._models: List[Learner] = []

    def fit(self, X: np.ndarray, Y: np.ndarray,
            viable: Optional[np.ndarray] = None) -> "S0Surrogate":
        X = self._check_X(X)
        Y = np.atleast_2d(np.asarray(Y, dtype=float))
        if Y.shape[0] != X.shape[0]:
            raise ValueError(f"X has {X.shape[0]} rows, Y has {Y.shape[0]}")

        self._models = []
        for j, t in enumerate(self.spec.targets):
            y = Y[:, j]
            m = np.isfinite(y)
            if viable is not None:
                m &= np.asarray(viable, dtype=bool)
            if m.sum() < 2:
                raise ValueError(
                    f"target {t.name!r}: only {int(m.sum())} usable rows, need >= 2")
            lr = _fresh(self.learner, **self.learner_kw)
            lr.fit(X[m], apply_transform(y[m], t.transform))
            self._models.append(lr)
        self.fitted = True
        return self

    def predict_batch(self, X: np.ndarray) -> BatchPrediction:
        self._check_fitted()
        X = self._check_X(X)
        vals = np.column_stack([
            invert_transform(self._models[j].predict(X), t.transform)
            for j, t in enumerate(self.spec.targets)])
        return BatchPrediction(spec=self.spec, values=vals)

    def sensitivity(self) -> Dict[str, Dict[str, float]]:
        """Per-target input importance, named. Lead generator, not an oracle.

        Meaning is family-dependent: impurity importance for trees (biased
        toward high-cardinality inputs, blind to interactions), inverse ARD
        length-scale for a GP. Neither is a variance-based index, so neither
        answers "which interactions matter" — that needs Sobol.
        """
        self._check_fitted()
        out: Dict[str, Dict[str, float]] = {}
        for j, t in enumerate(self.spec.targets):
            s = self._models[j].sensitivity()
            if s is not None:
                out[t.name] = {self.spec.input_names[i]: v for i, v in s.items()}
        return out

    def _save_artifacts(self, directory: Path) -> None:
        import joblib
        joblib.dump({"models": self._models, "learner": self.learner,
                     "learner_kw": self.learner_kw}, Path(directory) / "s0.joblib")


# =============================================================================
# S1 — two-stage probabilistic emulator
# =============================================================================

class S1Surrogate(SurrogateModel):
    """Viability classifier + per-target regressors + conformal intervals + gate.

    Intervals are split-conformal: fit on one part of the viable data, measure
    nonconformity on a held-out calibration part, and take the finite-sample
    quantile. Distribution-free, assuming nothing about the noise model, which
    matters because we cannot justify a Gaussian assumption on a few hundred
    points from a threshold-dominated model.

    **Normalised conformal.** When the learner exposes a native sigma (`ridge`,
    `rf`, `gp`, `mlp`), the nonconformity score is |y - yhat| / sigma(x) and the
    interval is yhat +/- q * sigma(x). The interval then WIDENS where the model
    is unsure instead of being one constant width everywhere — which is the
    whole point for a calibration that drives to box edges. Families without a
    sigma (`gbm`, `xgb`) fall back to a constant half-width, and `normalized`
    records which happened.

    Coverage remains MARGINAL, not conditional. Section 2.1 of docs/41 turns on
    exactly that limitation: coverage measured in-distribution says nothing
    about a region with no training points, which is why the hull gate is a
    separate, non-optional check.
    """

    def __init__(self, spec: SurrogateSpec, learner: Any = "rf",
                 classifier: Any = "rf",
                 alpha: float = 0.05, calibration_fraction: float = 0.3,
                 random_state: int = 0, hull_k: int = 5,
                 hull_quantile: float = 0.99,
                 classifier_kw: Optional[Dict[str, Any]] = None,
                 **learner_kw: Any) -> None:
        if spec.tier != "S1":
            raise ValueError(f"S1Surrogate requires tier 'S1', spec says {spec.tier!r}")
        if not 0 < alpha < 1:
            raise ValueError(f"alpha must be in (0, 1), got {alpha}")
        if not 0 <= calibration_fraction < 1:
            raise ValueError(
                f"calibration_fraction must be in [0, 1), got {calibration_fraction}")
        super().__init__(spec)
        self.learner = learner
        self.learner_kw = learner_kw
        # BOTH halves of S1 are the caller's choice. `classifier` decides the
        # alive/dead boundary and `learner` decides the numbers; hard-coding
        # either would make a bake-off compare something other than what it
        # appears to compare.
        self.classifier = classifier
        self.classifier_kw = dict(classifier_kw or {})
        self.alpha = alpha
        self.calibration_fraction = calibration_fraction
        # calibration_fraction == 0 fits every viable row and claims no conformal coverage: the
        # form a sequential search wants, where every run is too expensive to hold out.
        self.calibrated: bool = calibration_fraction > 0
        self.random_state = random_state
        self._clf: Any = None
        self._models: List[Learner] = []
        self._q: np.ndarray = np.array([])     # conformal quantile per target
        self.normalized: bool = False
        self._gate = HullGate(k=hull_k, quantile=hull_quantile)
        self.n_viable_train = 0
        # True on a copy from `believe`, whose regressors carry fake observations.
        self.believed: bool = False
        # Per target: indices into the X given to `fit` of the rows its regressor trained on, and
        # the std of those rows' values in the target's fitted (transformed) space. The indices
        # are sorted; a regressor's `training_inputs()` holds the same rows in its own order.
        self.train_rows_: Optional[List[np.ndarray]] = None
        self.target_sd_: Optional[np.ndarray] = None

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: np.ndarray,
            viable: Optional[np.ndarray] = None,
            priority: Optional[np.ndarray] = None,
            keep_best: int = 0) -> "S1Surrogate":
        """Fit the classifier on every row and one regressor per target on the viable rows.

        `priority` (N,), aligned with `X`, and `keep_best` pass through to each regressor's
        `fit`, restricted to that regressor's own fit rows, so a learner that subsamples keeps
        the `keep_best` lowest-priority rows. Refused for a learner whose `fit` takes no priority.
        """
        X = self._check_X(X)
        Y = np.atleast_2d(np.asarray(Y, dtype=float))
        if Y.shape[0] != X.shape[0]:
            raise ValueError(f"X has {X.shape[0]} rows, Y has {Y.shape[0]}")
        probe = _fresh(self.learner, **self.learner_kw)
        if priority is not None:
            priority = np.asarray(priority, dtype=float).ravel()
            if len(priority) != len(X):
                raise ValueError(
                    f"priority has {len(priority)} entries, X has {len(X)} rows; pass one "
                    "priority per row of X")
            params = inspect.signature(probe.fit).parameters
            if "priority" not in params or "keep_best" not in params:
                raise ValueError(
                    f"priority: learner family {probe.name!r} fits without a row priority; "
                    "pass priority=None or use a learner whose fit accepts priority and "
                    "keep_best (gp)")
        elif keep_best:
            raise ValueError(
                f"keep_best={keep_best} needs a priority to rank rows by; pass priority too")

        if viable is None:
            # Fallback only: a row is viable when every target is finite. The
            # ensemble should carry real labels so a crash is distinguishable
            # from merely-missing output.
            viable = np.all(np.isfinite(Y), axis=1)
        viable = np.asarray(viable, dtype=bool)

        # Stage 1: viability, trained on ALL rows including failures. That is
        # the whole reason failed runs must be retained.
        if viable.all():
            self._clf = None
        else:
            self._clf = make_classifier(
                self.classifier, random_state=self.random_state,
                **self.classifier_kw).fit(X, viable.astype(int))

        # The gate is fitted on the VIABLE region only: a query near a cluster
        # of dead runs is not "covered" for regression, since no regression
        # training point lives there.
        Xv, Yv = X[viable], Y[viable]
        self.n_viable_train = int(viable.sum())
        self.calibrated = self.calibration_fraction > 0
        if self.calibrated and self.n_viable_train < 4:
            raise ValueError(
                f"only {self.n_viable_train} viable rows; S1 needs >= 4 to split "
                "fit/calibration. Use S0 or gather more data.")
        if not self.calibrated and self.n_viable_train < 2:
            raise ValueError(
                f"only {self.n_viable_train} viable rows; S1 needs >= 2 to fit a regressor "
                "even without a calibration split.")
        self._gate.fit(Xv)

        if self.calibrated:
            rng = np.random.default_rng(self.random_state)
            idx = rng.permutation(self.n_viable_train)
            n_cal = max(1, int(round(self.calibration_fraction * self.n_viable_train)))
            n_cal = min(n_cal, self.n_viable_train - 1)
            cal_idx, fit_idx = idx[:n_cal], idx[n_cal:]
        else:
            cal_idx, fit_idx = np.array([], dtype=int), np.arange(self.n_viable_train)

        self._models, qs = [], []
        self.normalized = bool(probe.supports_std)
        viable_rows = np.flatnonzero(viable)
        pv = None if priority is None else priority[viable]
        train_rows, target_sd = [], []

        for j, t in enumerate(self.spec.targets):
            y = Yv[:, j]
            fin = np.isfinite(y)
            fi, ci = fit_idx[fin[fit_idx]], cal_idx[fin[cal_idx]]
            if len(fi) < 2:
                raise ValueError(
                    f"target {t.name!r}: only {len(fi)} finite rows in the fit split")
            lr = _fresh(self.learner, **self.learner_kw)
            if pv is None:
                lr.fit(Xv[fi], apply_transform(y[fi], t.transform))
            else:
                lr.fit(Xv[fi], apply_transform(y[fi], t.transform),
                       priority=pv[fi], keep_best=keep_best)
            self._models.append(lr)
            rows = viable_rows[fi]
            used = getattr(lr, "train_idx_", None)
            if used is not None:
                rows = rows[np.asarray(used, dtype=int)]
            rows = np.sort(rows)
            train_rows.append(rows)
            target_sd.append(float(np.std(apply_transform(Y[rows, j], t.transform))))

            if not self.calibrated:
                continue
            if len(ci) == 0:
                qs.append(np.inf)   # no calibration data -> refuse to claim coverage
                continue
            pred = invert_transform(lr.predict(Xv[ci]), t.transform)
            resid = np.abs(y[ci] - pred)
            if self.normalized:
                sig = lr.predict_std(Xv[ci])
                sig = np.maximum(np.asarray(sig, dtype=float), _SIGMA_FLOOR)
                scores = resid / sig
            else:
                scores = resid
            # Finite-sample split-conformal level. The ceil((n+1)(1-alpha))/n
            # quantile is what guarantees >= 1-alpha marginal coverage; the
            # plain (1-alpha) quantile under-covers on small calibration sets.
            qs.append(_conformal_quantile(scores, self.alpha, self.spec.targets[j].name))
        self._q = np.asarray(qs, dtype=float)
        self.train_rows_ = train_rows
        self.target_sd_ = np.asarray(target_sd, dtype=float)
        self.fitted = True
        return self

    # ---- predict ----

    def predict_batch(self, X: np.ndarray) -> BatchPrediction:
        self._check_fitted()
        X = self._check_X(X)
        vals = np.empty((len(X), len(self.spec.targets)), dtype=float)
        half = np.empty_like(vals)

        for j, t in enumerate(self.spec.targets):
            lr = self._models[j]
            vals[:, j] = invert_transform(lr.predict(X), t.transform)
            if not self.calibrated:
                continue
            if self.normalized:
                sig = np.maximum(np.asarray(lr.predict_std(X), dtype=float),
                                 _SIGMA_FLOOR)
                half[:, j] = self._q[j] * sig
            else:
                half[:, j] = self._q[j]

        # Intervals live in NATIVE units because the conformal scores were
        # measured there. Applying a half-width in transformed space and
        # inverting would give an asymmetric band with no guarantee attached.
        # An uncalibrated model claims no interval at all rather than an infinite one, which
        # a coverage check would score as covering.
        lower, upper = (vals - half, vals + half) if self.calibrated else (None, None)
        dist, inside = self.hull(X)
        return BatchPrediction(
            spec=self.spec, values=vals, lower=lower, upper=upper,
            viability=self.viability(X), in_hull=inside, hull_distance=dist)

    def viability(self, X: np.ndarray) -> np.ndarray:
        """(N,) P(viable). All ones when every training row was viable (no classifier fitted).

        A classifier fitted on a single class answers from its `classes_` alone, ones for `[1]`
        and zeros for `[0]`, because such a fit's `predict_proba` columns need not follow
        `classes_`. Otherwise label 1 must be among `classes_` and `predict_proba` must return one
        column per class; the column of label 1 is P(viable).
        """
        self._check_fitted()
        X = self._check_X(X)
        if self._clf is None:
            return np.ones(len(X))
        classes = list(np.asarray(self._clf.classes_).ravel())
        if len(classes) == 1 and classes[0] == 1:
            return np.ones(len(X))
        if len(classes) == 1 and classes[0] == 0:
            return np.zeros(len(X))
        if 1 not in classes:
            raise ValueError(
                f"viability: the classifier's classes_ {classes} contain no label 1 (viable); "
                "fit it on 0/1 viability labels")
        proba = np.asarray(self._clf.predict_proba(X), dtype=float)
        if proba.ndim != 2 or proba.shape[1] != len(classes):
            raise ValueError(
                f"viability: predict_proba returned shape {proba.shape} for classes_ {classes}; "
                "it must return one column per class, in classes_ order")
        return proba[:, classes.index(1)]

    def hull(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """(distance, inside) from the extrapolation gate fitted on the viable rows."""
        self._check_fitted()
        X = self._check_X(X)
        dist = self._gate.distance(X)
        return dist, dist <= self._gate.threshold

    def posterior(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Per-target posterior `(mean, std)`, each (N, T), in each target's FITTED space.

        That space is the target's `transform` space (log units under `log`), because it is
        where the regressor's Gaussian lives; sample or integrate there and invert afterwards.
        The std is the regressor's predictive std, which for `gp` includes the fitted noise term.
        Refused unless every regressor declares `posterior_std`: a caller integrates this std as
        a Gaussian posterior, which a tree spread, a leverage term or an ensemble disagreement is
        not.
        """
        self._check_fitted()
        X = self._check_X(X)
        for lr in self._models:
            if getattr(lr, "posterior_std", False):
                continue
            family = getattr(lr, "name", type(lr).__name__)
            what = ("has a native std that is not a predictive posterior std"
                    if getattr(lr, "supports_std", False) else "has no native std")
            raise ValueError(
                f"posterior: learner family {family!r} {what}; the acquisition integrates the "
                "std as a Gaussian posterior (docs/42 section 3), so only a family with "
                "posterior_std=True (gp) may supply one")
        mu = np.empty((len(X), len(self.spec.targets)), dtype=float)
        sd = np.empty_like(mu)
        for j, lr in enumerate(self._models):
            both = getattr(lr, "predict_mean_std", None)
            if callable(both):
                m, s = both(X)
            else:
                m, s = lr.predict(X), lr.predict_std(X)
            mu[:, j] = np.asarray(m, dtype=float)
            sd[:, j] = np.asarray(s, dtype=float)
        return mu, sd

    def trains_on(self, x: np.ndarray) -> np.ndarray:
        """(T,) bool: whether each regressor's posterior conditions on the single point `x`.

        A training input matches when it is within 1e-9 of the spec's input range of `x` in
        every dimension (L-inf). Read from each regressor's `training_inputs()`, so it reflects
        any subsample and any believed point.
        """
        self._check_fitted()
        x = self._check_X(x)
        if len(x) != 1:
            raise ValueError(f"trains_on takes one point, got {len(x)} rows")
        for t, lr in zip(self.spec.targets, self._models):
            if not callable(getattr(lr, "training_inputs", None)):
                family = getattr(lr, "name", type(lr).__name__)
                raise ValueError(
                    f"trains_on: learner family {family!r} (target {t.name!r}) exposes no "
                    "training_inputs(), so its training set cannot be checked; use gp")
        tol = 1e-9 * (np.asarray(self.spec.input_upper, dtype=float)
                      - np.asarray(self.spec.input_lower, dtype=float))
        return np.array([
            bool(np.any(np.all(np.abs(np.asarray(lr.training_inputs(), dtype=float) - x)
                               <= tol, axis=1)))
            for lr in self._models], dtype=bool)

    def believe(self, X_new: np.ndarray) -> "S1Surrogate":
        """A Kriging-believer COPY: every regressor also conditions on its own posterior mean at
        `X_new`, with hyperparameters frozen. The classifier and hull gate are shared unchanged,
        because a believed point is not a run. The copy claims no conformal coverage and refuses
        `save`, so fake observations can never persist. This model is left untouched.
        """
        self._check_fitted()
        X_new = self._check_X(X_new)
        missing = [t.name for t, lr in zip(self.spec.targets, self._models)
                   if not callable(getattr(lr, "condition_on", None))]
        if missing:
            raise NotImplementedError(
                f"believe: learner {self.learner!r} cannot condition without refitting "
                f"(targets {missing}); batch with local penalisation instead")
        out = copy.copy(self)
        out._models = [lr.condition_on(X_new, lr.predict(X_new)) for lr in self._models]
        out._q = np.array([])
        out.calibrated = False
        out.believed = True
        return out

    def save(self, directory: Path) -> Path:
        if self.believed:
            raise RuntimeError(
                "refusing to save a Kriging-believer copy: its regressors contain fake "
                "observations; save the model it was derived from")
        return super().save(directory)

    @property
    def conformal_quantile(self) -> Dict[str, float]:
        """Per-target conformal quantile.

        In native units when `normalized` is False; a MULTIPLIER on sigma(x)
        when True, so it is not directly comparable across the two modes.
        """
        self._check_fitted()
        if not self.calibrated:
            raise ValueError(
                "no conformal quantile: this model was fitted with calibration_fraction=0 "
                "or is a Kriging-believer copy")
        return {t.name: float(self._q[j]) for j, t in enumerate(self.spec.targets)}

    def sensitivity(self) -> Dict[str, Dict[str, float]]:
        self._check_fitted()
        out: Dict[str, Dict[str, float]] = {}
        for j, t in enumerate(self.spec.targets):
            s = self._models[j].sensitivity()
            if s is not None:
                out[t.name] = {self.spec.input_names[i]: v for i, v in s.items()}
        return out

    def _save_artifacts(self, directory: Path) -> None:
        import joblib
        joblib.dump({"clf": self._clf, "models": self._models, "q": self._q,
                     "normalized": self.normalized, "gate": self._gate,
                     "alpha": self.alpha, "learner": self.learner,
                     "learner_kw": self.learner_kw,
                     "classifier": self.classifier,
                     "classifier_kw": self.classifier_kw,
                     "calibration_fraction": self.calibration_fraction,
                     "n_viable_train": self.n_viable_train,
                     "train_rows": self.train_rows_, "target_sd": self.target_sd_},
                    Path(directory) / "s1.joblib")


# =============================================================================
# Loading
# =============================================================================


# =============================================================================
# S2 — trajectory emulator
# =============================================================================

class S2Surrogate(SurrogateModel):
    """theta -> y(t): a trajectory per target, reduced to the scalar S1 predicts.

    The reduction is what makes S2 a DROP-IN rather than a parallel object.
    `predict_batch` returns the same `BatchPrediction` of scalars every consumer
    already expects, obtained by reducing the predicted trajectory; the series
    itself is available from `predict_trajectories`. So `run_acceptance`, the
    cost layer and the search layer work against S2 unchanged, and a caller that
    wants shape asks for it explicitly.

    Architecture is the LATENT ROM of docs/41 section "S2 Trajectory emulator"
    (`GRU / LSTM, autoregressive, latent ROM`). Per target: centre the training
    trajectories, take the leading `n_components` singular vectors as a basis,
    and regress theta -> coefficient with ONE learner per component drawn from
    the same registry S0 and S1 use. Reconstruction is the mean plus the
    coefficient-weighted basis. The learner axis stays orthogonal to the tier
    axis, so every registry family works here. A trajectory that must respond to
    per-step drivers needs a sequence network instead: `sequence.KGMLEmulator`,
    an S3 architecture, because a basis fitted to one driver record cannot answer
    for another.

    Viability, the extrapolation gate and split-conformal intervals are S1's and
    are reused rather than re-derived. The conformal score is measured on the
    REDUCED scalar, because that is the quantity whose interval a caller acts
    on; a band on a multi-thousand-step series is a different object and is not claimed.
    """

    def __init__(self, spec: SurrogateSpec, learner: Any = "gbm",
                 n_components: int = 16, reduce: str = "mean",
                 time_index: Optional[np.ndarray] = None,
                 classifier: Any = "rf",
                 alpha: float = 0.05, calibration_fraction: float = 0.3,
                 random_state: int = 0, hull_k: int = 5,
                 hull_quantile: float = 0.99,
                 classifier_kw: Optional[Dict[str, Any]] = None,
                 **learner_kw: Any) -> None:
        if spec.tier != "S2":
            raise ValueError(f"S2Surrogate requires tier 'S2', spec says {spec.tier!r}")
        if n_components < 1:
            raise ValueError(f"n_components must be >= 1, got {n_components}")
        if reduce not in REDUCERS:
            raise ValueError(f"reduce {reduce!r} not in {tuple(REDUCERS)}")
        if reduce == "annual_mean_sum" and time_index is None:
            raise ValueError(
                "reduce='annual_mean_sum' needs `time_index`: the year label of every "
                "timestep, so within-year sums can be formed. Without it the reducer "
                "cannot know where a year ends and would silently sum the whole window.")
        super().__init__(spec)
        self.learner = learner
        self.learner_kw = learner_kw
        self.n_components = n_components
        self.reduce = reduce
        self.time_index = None if time_index is None else np.asarray(time_index)
        self.classifier = classifier
        self.classifier_kw = dict(classifier_kw or {})
        self.alpha = alpha
        self.calibration_fraction = calibration_fraction
        self.random_state = random_state
        self._clf: Any = None
        self._models: List[List[Learner]] = []   # [target][component]
        self._basis: List[np.ndarray] = []       # [target] (K, D)
        self._mean: List[np.ndarray] = []        # [target] (D,)
        self._q: np.ndarray = np.array([])
        self._gate = HullGate(k=hull_k, quantile=hull_quantile)
        self.n_viable_train = 0
        self.n_steps = 0

    # ---- reduction ----

    def _reduce(self, traj: np.ndarray) -> np.ndarray:
        """(N, T, D) trajectories -> (N, T) scalars, via the declared reducer."""
        return REDUCERS[self.reduce](traj, self.time_index)

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: np.ndarray,
            viable: Optional[np.ndarray] = None,
            trajectories: Optional[np.ndarray] = None) -> "S2Surrogate":
        """Fit on trajectories; `Y` is the reduced scalars and is used to CHECK them.

        `trajectories` is (N, T, D) in `spec.targets` order and is required: S2
        without series is S1. `Y` is not a second training signal -- it is the
        independently-produced scalar matrix, and fitting asserts that reducing
        the supplied trajectories reproduces it. That assertion is the whole
        defence against the failure this tier is most exposed to: a reducer that
        does not match the one the Y matrix was built with produces a surrogate
        that is internally consistent, plausible, and answering a different
        question than the calibration is scored on.
        """
        if trajectories is None:
            raise ValueError(
                "S2Surrogate.fit requires `trajectories` (N, T, D). A trajectory tier "
                "fitted on scalars alone is an S1 with extra steps.")
        X = self._check_X(X)
        Y = np.atleast_2d(np.asarray(Y, dtype=float))
        traj = np.asarray(trajectories, dtype=float)
        if traj.ndim != 3:
            raise ValueError(f"trajectories must be (N, T, D), got shape {traj.shape}")
        n, n_t, n_d = traj.shape
        if n != X.shape[0]:
            raise ValueError(f"X has {X.shape[0]} rows, trajectories have {n}")
        if n_t != len(self.spec.targets):
            raise ValueError(
                f"trajectories have {n_t} targets, spec declares {len(self.spec.targets)}")
        if self.time_index is not None and len(self.time_index) != n_d:
            raise ValueError(
                f"time_index has {len(self.time_index)} entries, trajectories have {n_d} steps")
        self.n_steps = n_d

        if viable is None:
            viable = np.all(np.isfinite(Y), axis=1)
        viable = np.asarray(viable, dtype=bool)

        # --- the reducer check, on the VIABLE rows only (a dead run's Y may be NaN) ---
        red = self._reduce(traj[viable])
        ref = Y[viable]
        ok = np.isfinite(red) & np.isfinite(ref)
        if not ok.any():
            raise ValueError("no finite (reduced, Y) pair to check the reducer against")
        # PER-TARGET SCALE, not a literal 1.0. The denominator used to be
        # `np.maximum(1.0, |ref|)`, which is a RELATIVE tolerance only for quantities of order 1
        # or larger and an ABSOLUTE 1e-4 for everything smaller -- so for a flux in per-second
        # units, or miniLEO's ~4.7e-4 mol/L concentrations, a reducer could disagree with the Y
        # matrix by 20 percent and pass. The floor now comes from the column's own magnitude, so
        # the check means the same thing whatever the units are, and it still protects the
        # division where a reference value is genuinely zero.
        rel = np.abs(red[ok] - ref[ok]) / _rel_scale(ref, ok)
        worst = float(rel.max())
        if worst > 1e-4:
            raise ValueError(
                f"reduce={self.reduce!r} does not reproduce the Y matrix: worst relative "
                f"disagreement {worst:.3e} over {int(ok.sum())} compared values. The "
                f"trajectories and the scalars describe different quantities; fix the reducer "
                f"or the extraction before fitting, because every downstream number would "
                f"otherwise be self-consistent and wrong.")
        self.reducer_max_rel_error = worst

        # --- viability classifier: trained on ALL rows, failures included ---
        if viable.all():
            self._clf = None
        else:
            self._clf = make_classifier(self.classifier, **self.classifier_kw)
            self._clf.fit(X, viable.astype(int))

        Xv, Tv = X[viable], traj[viable]
        self.n_viable_train = int(viable.sum())
        if self.n_viable_train < 4:
            raise ValueError(
                f"only {self.n_viable_train} viable rows; S2 needs >= 4 to split fit/calibration")
        self._gate.fit(Xv)

        rng = np.random.default_rng(self.random_state)
        perm = rng.permutation(self.n_viable_train)
        n_cal = max(1, int(round(self.calibration_fraction * self.n_viable_train)))
        cal, tr = perm[:n_cal], perm[n_cal:]

        self._models, self._basis, self._mean = [], [], []
        for j, t in enumerate(self.spec.targets):
            A = Tv[:, j, :]                                  # (Nv, D)
            mu = A[tr].mean(axis=0)
            self._mean.append(mu)
            # Economy SVD of the CENTRED training block. Components are ordered by
            # singular value, so truncation keeps the modes carrying the variance.
            k = int(min(self.n_components, len(tr), n_d))
            _, _, Vt = np.linalg.svd(A[tr] - mu, full_matrices=False)
            B = Vt[:k]                                       # (K, D)
            self._basis.append(B)
            C = (A - mu) @ B.T                               # (Nv, K) coefficients
            self._models.append([
                _fresh(self.learner, **self.learner_kw).fit(Xv[tr], C[tr, c])
                for c in range(k)])

        # --- split-conformal on the REDUCED scalar ---
        cal_traj = self._reconstruct(Xv[cal])
        cal_red = self._reduce(cal_traj)
        ref_red = self._reduce(Tv[cal])
        qs = []
        for j in range(len(self.spec.targets)):
            resid = np.abs(cal_red[:, j] - ref_red[:, j])
            resid = resid[np.isfinite(resid)]
            qs.append(_conformal_quantile(resid, self.alpha, self.spec.targets[j].name))
        self._q = np.asarray(qs, dtype=float)
        self.fitted = True
        return self

    # ---- predict ----

    def _reconstruct(self, X: np.ndarray) -> np.ndarray:
        out = np.empty((len(X), len(self.spec.targets), self.n_steps), dtype=float)
        for j in range(len(self.spec.targets)):
            C = np.column_stack([m.predict(X) for m in self._models[j]])   # (N, K)
            out[:, j, :] = self._mean[j] + C @ self._basis[j]
        return out

    def predict_trajectories(self, X: np.ndarray) -> np.ndarray:
        """(N, T, D) predicted series. The tier's reason for existing."""
        self._check_fitted()
        return self._reconstruct(self._check_X(X))

    def predict_batch(self, X: np.ndarray) -> BatchPrediction:
        self._check_fitted()
        X = self._check_X(X)
        vals = self._reduce(self._reconstruct(X))
        half = np.broadcast_to(self._q, vals.shape)
        viab = (np.ones(len(X)) if self._clf is None else
                self._clf.predict_proba(X)[:, list(self._clf.classes_).index(1)])
        dist = self._gate.distance(X)
        return BatchPrediction(
            spec=self.spec, values=vals, lower=vals - half, upper=vals + half,
            viability=viab, in_hull=dist <= self._gate.threshold, hull_distance=dist)

    # ---- persistence ----

    def _save_artifacts(self, directory: Path) -> None:
        import joblib
        joblib.dump({"clf": self._clf, "models": self._models, "basis": self._basis,
                     "mean": self._mean, "q": self._q, "gate": self._gate,
                     "alpha": self.alpha, "learner": self.learner,
                     "learner_kw": self.learner_kw, "classifier": self.classifier,
                     "classifier_kw": self.classifier_kw,
                     "calibration_fraction": self.calibration_fraction,
                     "n_components": self.n_components, "reduce": self.reduce,
                     "time_index": self.time_index, "n_steps": self.n_steps,
                     "n_viable_train": self.n_viable_train},
                    directory / "s2.joblib")


# =============================================================================
# S3 — knowledge-guided trajectory emulator
# =============================================================================

class S3Surrogate(S2Surrogate):
    """S2 plus process structure: targets DERIVED from components rather than fitted.

    The knowledge channel here is KGML's third one -- physics as WIRING -- and it is
    chosen over the soft-penalty channel deliberately. `KnowledgeGuidedLoss` states the
    reason in its own docstring: "Where a constraint can instead be made STRUCTURAL,
    prefer [it] ... which holds under any weights." A penalty makes a relation likely;
    composition makes it true by construction, at every point, for every learner,
    including the tree families that have no gradient for a penalty to use.

    TWO CHANNELS, both declared rather than inferred:

    `compose`  {derived_target: [component_target, ...]}
        The derived target is NOT fitted. Its trajectory is the SUM of its components'
        trajectories at every timestep, so the identity holds pointwise and survives
        reduction. The worked case is a total that the process model computes as the
        sum of its parts, such as a total flux made of two component fluxes: a surrogate
        that fits the total independently is free to contradict its own components.

    `nonneg`   [target, ...]
        Declared targets are clamped at zero. A truncated ROM basis reconstructs a
        smooth series that can dip below zero where the true flux approaches it, which
        is not a small error but an inadmissible value. Violations are COUNTED at fit
        time and kept on the model, because a constraint that silently repairs a
        prediction hides how often the unconstrained model was wrong.

    WHAT THIS TIER DOES NOT CLAIM. It is not a PINN and adds no PDE residual, which needs a
    governing equation that many process models do not have. It does not pretrain on one corpus and
    fine-tune on another -- the training set is already process-model output, which is
    KGML's "physics as data" arm satisfied by construction rather than by design. And
    the soft-penalty arm remains available on the `mlp` learner through
    `KnowledgeGuidedLoss`; it is orthogonal to this tier and not wired here.
    """

    def __init__(self, spec: SurrogateSpec,
                 compose: Optional[Dict[str, List[str]]] = None,
                 nonneg: Optional[List[str]] = None,
                 **kw: Any) -> None:
        if spec.tier != "S3":
            raise ValueError(f"S3Surrogate requires tier 'S3', spec says {spec.tier!r}")
        # Construct through S2's machinery with the tier temporarily relaxed: S2's own
        # guard is a tier-name check, and S3 IS an S2 with structure on top.
        object.__setattr__(spec, "tier", "S2")
        try:
            super().__init__(spec, **kw)
        finally:
            object.__setattr__(spec, "tier", "S3")

        names = [t.name for t in spec.targets]
        self.compose = {k: list(v) for k, v in (compose or {}).items()}
        self.nonneg = list(nonneg or [])
        for derived, parts in self.compose.items():
            if derived not in names:
                raise ValueError(f"compose names {derived!r}, which is not a target ({names})")
            if not parts:
                raise ValueError(f"compose[{derived!r}] is empty; a derived target needs components")
            for c in parts:
                if c not in names:
                    raise ValueError(
                        f"compose[{derived!r}] names component {c!r}, which is not a target. "
                        f"Every component must itself be a target so it is fitted and scored.")
                if c in self.compose:
                    raise ValueError(
                        f"component {c!r} of {derived!r} is itself derived; chained composition "
                        f"is not supported because the fit order would be ambiguous.")
        for t in self.nonneg:
            if t not in names:
                raise ValueError(f"nonneg names {t!r}, which is not a target ({names})")
        self._derived_idx = {names.index(k): [names.index(c) for c in v]
                             for k, v in self.compose.items()}
        self._nonneg_idx = [names.index(t) for t in self.nonneg]
        #: fraction of reconstructed timesteps the nonneg clamp had to repair, per target
        self.nonneg_violation_rate: Dict[str, float] = {}

    # ---- structure ----

    def _apply_structure(self, traj: np.ndarray, count: bool = False) -> np.ndarray:
        """Compose derived targets, then clamp. Order matters: a sum of clamped
        components is the admissible quantity, while clamping a sum would let a
        negative component hide inside a positive total."""
        out = np.array(traj, dtype=float, copy=True)
        if self._nonneg_idx:
            comp_first = [j for j in self._nonneg_idx if j not in self._derived_idx]
            if count:
                for j in comp_first:
                    name = self.spec.targets[j].name
                    self.nonneg_violation_rate[name] = float((out[:, j, :] < 0).mean())
            for j in comp_first:
                np.clip(out[:, j, :], 0.0, None, out=out[:, j, :])
        for j, parts in self._derived_idx.items():
            out[:, j, :] = out[:, parts, :].sum(axis=1)
        for j in self._nonneg_idx:
            if j in self._derived_idx:
                np.clip(out[:, j, :], 0.0, None, out=out[:, j, :])
        return out

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: np.ndarray,
            viable: Optional[np.ndarray] = None,
            trajectories: Optional[np.ndarray] = None) -> "S3Surrogate":
        """Fit the COMPONENTS; the derived targets are never regressed.

        The derived columns are still carried through S2's reducer check, which is the
        point: it asserts that the composed identity reproduces the Y matrix, so a wrong
        `compose` rule is caught exactly where a wrong reducer is.
        """
        if trajectories is not None and self._derived_idx:
            traj = np.asarray(trajectories, dtype=float)
            for j, parts in self._derived_idx.items():
                lhs, rhs = traj[:, j, :], traj[:, parts, :].sum(axis=1)
                ok = np.isfinite(lhs) & np.isfinite(rhs)
                if ok.any():
                    # Same scale rule as the reducer check above, and for the same reason: a
                    # composition identity in per-second units was being checked absolutely.
                    scale = np.maximum(np.abs(lhs[ok]),
                                       _SCALE_FLOOR_FRAC * float(np.max(np.abs(lhs[ok]))))
                    scale[scale <= 0.0] = 1.0
                    worst = float((np.abs(lhs[ok] - rhs[ok]) / scale).max())
                    if worst > 1e-4:
                        name = self.spec.targets[j].name
                        parts_n = [self.spec.targets[p].name for p in parts]
                        raise ValueError(
                            f"compose says {name} = {' + '.join(parts_n)}, but the TRAINING "
                            f"trajectories disagree by {worst:.3e} relative. The structural rule "
                            f"is wrong, or the components are not what they are named.")
        super().fit(X, Y, viable=viable, trajectories=trajectories)
        # measure how far the unconstrained reconstruction strays, on the training inputs
        self._apply_structure(super()._reconstruct(self._check_X(X)), count=True)
        return self

    # ---- predict ----

    def _reconstruct(self, X: np.ndarray) -> np.ndarray:
        return self._apply_structure(super()._reconstruct(X))

    # ---- persistence ----

    def _save_artifacts(self, directory: Path) -> None:
        super()._save_artifacts(directory)
        import joblib
        blob = joblib.load(directory / "s2.joblib")
        blob.update({"compose": self.compose, "nonneg": self.nonneg,
                     "nonneg_violation_rate": self.nonneg_violation_rate})
        joblib.dump(blob, directory / "s3.joblib")
        (directory / "s2.joblib").unlink()

#: Architectures that are not one of the tier classes in this file, by the class name
#: `SurrogateModel.save` writes into `tier.json`, to the module and function that rebuild them. Each
#: of those modules imports torch lazily, so this module still imports without torch. Dispatch is by
#: class rather than by tier because a tier is not unique to a class: `KGMLEmulator` declares S3,
#: the tier `S3Surrogate` also serves, and the two save different files.
ARCHITECTURE_LOADERS = {
    "KGMLEmulator": ("sequence", "load_kgml"),
    "VectorSurrogate": ("multioutput", "load_vector"),
    "FieldEmulator": ("fields", "load_field"),
    "SpatioTemporalEmulator": ("spatiotemporal", "load_spatiotemporal"),
    "GraphEmulator": ("graphs", "load_graph"),
    "DeepONetEmulator": ("operators", "load_deeponet"),
}


def _architecture_loader(directory: Path) -> Any:
    import importlib
    import json

    p = Path(directory) / "tier.json"
    if not p.is_file():
        return None
    cls = json.loads(p.read_text()).get("class")
    if cls not in ARCHITECTURE_LOADERS:
        return None
    mod, fn = ARCHITECTURE_LOADERS[cls]
    return getattr(importlib.import_module(f".{mod}", package=__package__), fn)


def load(directory: Path, expect: Optional["Provenance"] = None,
         strict: bool = True) -> SurrogateModel:
    """Load a saved surrogate, refusing a spec/artifact or provenance mismatch.

    ``expect`` is the provenance the CALLER believes it is operating under: the
    model commit, parameter list, base file and — the one most easily overlooked —
    the **scoring convention**. When supplied, any field populated
    on both sides and differing is a refusal under ``strict`` (the default), or a
    warning otherwise.

    Why this is a gate and not a helper. A surrogate is bound to the tuple it was
    trained against, exactly as a RAG profile is bound to a source commit. A change
    in how targets are reduced (a calendar convention, an aggregation window) means
    an artifact trained before it is scored against a *different objective* than
    the one now in force. Nothing about that artifact looks
    wrong on load: it has the right shape, the right target count, and it
    predicts plausible numbers. Without this check the mismatch surfaces only as
    a subtly wrong answer, which is the worst way to find it.

    ``expect=None`` skips the comparison, which is correct for inspection and
    for tooling that has no opinion about the convention. It is NOT correct
    before using an artifact to make a decision — pass what you expect.

    Unstamped fields are always reported, because `Provenance.mismatches`
    deliberately treats an empty field as unknown rather than as a match, so an
    unstamped artifact is *unprotected* rather than *verified*.
    """
    import joblib
    import warnings

    from .spec import Provenance  # noqa: F401  (runtime import for the annotation)
    from .environment import enforce_environment

    directory = Path(directory)
    spec = SurrogateSpec.read(directory / "spec.json")

    if expect is not None:
        bad = spec.provenance.mismatches(expect)
        if bad:
            detail = ", ".join(
                f"{f}: artifact={getattr(spec.provenance, f)!r} "
                f"expected={getattr(expect, f)!r}" for f in bad)
            msg = (f"provenance mismatch in {directory}: {detail}. This "
                   f"artifact was trained against a different setup and its "
                   f"predictions are not comparable to the current one.")
            if strict:
                raise ValueError(msg)
            warnings.warn(msg, RuntimeWarning)

    unstamped = spec.provenance.unstamped_fields()
    if unstamped:
        warnings.warn(
            f"surrogate at {directory} has unstamped provenance fields "
            f"{unstamped}; those cannot be checked, so the artifact is "
            "unprotected against a change in them, not verified against it.",
            RuntimeWarning)

    # The libraries that WROTE these pickles, against the ones about to read them. Separate from
    # provenance because it is captured rather than declared; see environment.py for why a major
    # version bump refuses and a minor one warns.
    enforce_environment(directory, strict=strict)

    # An architecture outside the four tier classes: provenance and environment were checked above,
    # so its own loader is told not to repeat the environment check.
    arch_loader = _architecture_loader(directory)
    if arch_loader is not None:
        return arch_loader(directory, spec, strict=strict, check_env=False)

    if spec.tier == "S0":
        blob = joblib.load(directory / "s0.joblib")
        m = S0Surrogate(spec, learner=blob["learner"], **blob["learner_kw"])
        m._models = blob["models"]
    elif spec.tier == "S1":
        blob = joblib.load(directory / "s1.joblib")
        m = S1Surrogate(spec, learner=blob["learner"], alpha=blob["alpha"],
                        classifier=blob.get("classifier", "rf"),
                        classifier_kw=blob.get("classifier_kw"),
                        calibration_fraction=blob["calibration_fraction"],
                        **blob["learner_kw"])
        m._clf = blob["clf"]
        m._models = blob["models"]
        m._q = blob["q"]
        m.normalized = blob["normalized"]
        m._gate = blob["gate"]
        m.n_viable_train = blob["n_viable_train"]
        m.train_rows_ = blob.get("train_rows")
        m.target_sd_ = blob.get("target_sd")
    elif spec.tier == "S2":
        blob = joblib.load(directory / "s2.joblib")
        m = S2Surrogate(spec, learner=blob["learner"], alpha=blob["alpha"],
                        n_components=blob["n_components"], reduce=blob["reduce"],
                        time_index=blob.get("time_index"),
                        classifier=blob.get("classifier", "rf"),
                        classifier_kw=blob.get("classifier_kw"),
                        calibration_fraction=blob["calibration_fraction"],
                        **blob["learner_kw"])
        m._clf = blob["clf"]
        m._models = blob["models"]
        m._basis = blob["basis"]
        m._mean = blob["mean"]
        m._q = blob["q"]
        m._gate = blob["gate"]
        m.n_steps = blob["n_steps"]
        m.n_viable_train = blob["n_viable_train"]
    elif spec.tier == "S3":
        blob = joblib.load(directory / "s3.joblib")
        m = S3Surrogate(spec, compose=blob.get("compose"), nonneg=blob.get("nonneg"),
                        learner=blob["learner"], alpha=blob["alpha"],
                        n_components=blob["n_components"], reduce=blob["reduce"],
                        time_index=blob.get("time_index"),
                        classifier=blob.get("classifier", "rf"),
                        classifier_kw=blob.get("classifier_kw"),
                        calibration_fraction=blob["calibration_fraction"],
                        **blob["learner_kw"])
        m._clf = blob["clf"]; m._models = blob["models"]; m._basis = blob["basis"]
        m._mean = blob["mean"]; m._q = blob["q"]; m._gate = blob["gate"]
        m.n_steps = blob["n_steps"]; m.n_viable_train = blob["n_viable_train"]
        m.nonneg_violation_rate = blob.get("nonneg_violation_rate", {})
    else:
        raise NotImplementedError(f"tier {spec.tier!r} has no loader yet")

    if len(m._models) != len(spec.targets):
        raise ValueError(
            f"artifact has {len(m._models)} regressors, spec declares "
            f"{len(spec.targets)} targets")
    m.fitted = True
    return m
