"""S0 and S1 — the tier axis. The learner family is a separate axis (learners.py).

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

Both accept ANY learner family (`rf`, `gbm`, `gp`, `mlp`, or a custom `Learner`).
The tier decides WHAT is emulated and how uncertainty is calibrated; the learner
decides WITH WHAT. Keeping them orthogonal is what lets `compare_learners` pick
the family on evidence instead of taste.

Why S1 is two-stage: fitting one regressor across a regime boundary is what
produced the 2025 Kougarok Fineroot_PFT7 R2 = 0.48. A dead stand and a living
one are not two ends of a continuum, and asking one regressor to span them
degrades it everywhere, not just at the boundary.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any, Dict, List, Optional

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

    This is what a `year_end` scalar becomes once the tape's within-year CUMULATIVE
    series has been de-cumulated into a daily flux: the year-end cumulative value is
    that year's sum of daily fluxes.
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

    **Normalised conformal.** When the learner exposes a native sigma (`rf`,
    `gp`, `mlp`), the nonconformity score is |y - yhat| / sigma(x) and the
    interval is yhat +/- q * sigma(x). The interval then WIDENS where the model
    is unsure instead of being one constant width everywhere — which is the
    whole point for a calibration that drives to box edges. Families without a
    sigma (`gbm`) fall back to a constant half-width, and `normalized` records
    which happened.

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
        if not 0 < calibration_fraction < 1:
            raise ValueError(
                f"calibration_fraction must be in (0, 1), got {calibration_fraction}")
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
        self.random_state = random_state
        self._clf: Any = None
        self._models: List[Learner] = []
        self._q: np.ndarray = np.array([])     # conformal quantile per target
        self.normalized: bool = False
        self._gate = HullGate(k=hull_k, quantile=hull_quantile)
        self.n_viable_train = 0

    # ---- fit ----

    def fit(self, X: np.ndarray, Y: np.ndarray,
            viable: Optional[np.ndarray] = None) -> "S1Surrogate":
        X = self._check_X(X)
        Y = np.atleast_2d(np.asarray(Y, dtype=float))
        if Y.shape[0] != X.shape[0]:
            raise ValueError(f"X has {X.shape[0]} rows, Y has {Y.shape[0]}")

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
        if self.n_viable_train < 4:
            raise ValueError(
                f"only {self.n_viable_train} viable rows; S1 needs >= 4 to split "
                "fit/calibration. Use S0 or gather more data.")
        self._gate.fit(Xv)

        rng = np.random.default_rng(self.random_state)
        idx = rng.permutation(self.n_viable_train)
        n_cal = max(1, int(round(self.calibration_fraction * self.n_viable_train)))
        n_cal = min(n_cal, self.n_viable_train - 1)
        cal_idx, fit_idx = idx[:n_cal], idx[n_cal:]

        self._models, qs = [], []
        probe = _fresh(self.learner, **self.learner_kw)
        self.normalized = bool(probe.supports_std)

        for j, t in enumerate(self.spec.targets):
            y = Yv[:, j]
            fin = np.isfinite(y)
            fi, ci = fit_idx[fin[fit_idx]], cal_idx[fin[cal_idx]]
            if len(fi) < 2:
                raise ValueError(
                    f"target {t.name!r}: only {len(fi)} finite rows in the fit split")
            lr = _fresh(self.learner, **self.learner_kw)
            lr.fit(Xv[fi], apply_transform(y[fi], t.transform))
            self._models.append(lr)

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
            # plain (1-alpha) quantile under-covers on small calibration sets,
            # which is exactly our regime.
            n = len(scores)
            lvl = min(1.0, np.ceil((n + 1) * (1 - self.alpha)) / n)
            qs.append(float(np.quantile(scores, lvl, method="higher")))
        self._q = np.asarray(qs, dtype=float)
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
            if self.normalized:
                sig = np.maximum(np.asarray(lr.predict_std(X), dtype=float),
                                 _SIGMA_FLOOR)
                half[:, j] = self._q[j] * sig
            else:
                half[:, j] = self._q[j]

        # Intervals live in NATIVE units because the conformal scores were
        # measured there. Applying a half-width in transformed space and
        # inverting would give an asymmetric band with no guarantee attached.
        if self._clf is not None:
            viab = self._clf.predict_proba(X)[:, list(self._clf.classes_).index(1)]
        else:
            viab = np.ones(len(X))

        dist = self._gate.distance(X)
        return BatchPrediction(
            spec=self.spec, values=vals, lower=vals - half, upper=vals + half,
            viability=viab, in_hull=dist <= self._gate.threshold,
            hull_distance=dist)

    @property
    def conformal_quantile(self) -> Dict[str, float]:
        """Per-target conformal quantile.

        In native units when `normalized` is False; a MULTIPLIER on sigma(x)
        when True, so it is not directly comparable across the two modes.
        """
        self._check_fitted()
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
                     "n_viable_train": self.n_viable_train},
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
    coefficient-weighted basis. Two consequences worth stating: the learner axis
    stays orthogonal to the tier axis, so `rf`, `gbm`, `gp` and `mlp` all work
    here, and a recurrent learner is a future entry on that axis rather than a
    different tier.

    Viability, the extrapolation gate and split-conformal intervals are S1's and
    are reused rather than re-derived. The conformal score is measured on the
    REDUCED scalar, because that is the quantity whose interval a caller acts
    on; a band on a 4000-step series is a different object and is not claimed.
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
        rel = np.abs(red[ok] - ref[ok]) / np.maximum(1.0, np.abs(ref[ok]))
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
            m = len(resid)
            lvl = min(1.0, np.ceil((m + 1) * (1 - self.alpha)) / m)
            qs.append(float(np.quantile(resid, lvl, method="higher")))
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
        reduction. `Reco = RA + RH` is the worked case: EcoSIM computes ecosystem
        respiration as autotrophic plus heterotrophic, so a surrogate that fits Reco
        independently is free to contradict its own components.

    `nonneg`   [target, ...]
        Declared targets are clamped at zero. A truncated ROM basis reconstructs a
        smooth series that can dip below zero where the true flux approaches it, which
        is not a small error but an inadmissible value. Violations are COUNTED at fit
        time and kept on the model, because a constraint that silently repairs a
        prediction hides how often the unconstrained model was wrong.

    WHAT THIS TIER DOES NOT CLAIM. It is not a PINN and adds no PDE residual; EcoSIM has
    no governing equation to differentiate. It does not pretrain on one corpus and
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
                    scale = np.maximum(1.0, np.abs(lhs[ok]))
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

def load(directory: Path, expect: Optional["Provenance"] = None,
         strict: bool = True) -> SurrogateModel:
    """Load a saved surrogate, refusing a spec/artifact or provenance mismatch.

    ``expect`` is the provenance the CALLER believes it is operating under: the
    model commit, parameter list, base file and — the one that has already bitten
    this project — the **scoring convention**. When supplied, any field populated
    on both sides and differing is a refusal under ``strict`` (the default), or a
    warning otherwise.

    Why this is a gate and not a helper. A surrogate is bound to the tuple it was
    trained against, exactly as a RAG profile is bound to a source commit. The
    leap-calendar fix (v2.213) changed how EcoSIM targets are reduced on
    2026-07-30, so an artifact trained before it is scored against a *different
    objective* than the one now in force. Nothing about that artifact looks
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
