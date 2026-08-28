"""S0 and S1 — the tier axis. The learner family is a separate axis (learners.py).

Gated ascent (docs/41 section 4): a tier may not be built until the tier below
has FAILED a written acceptance test. S2 (trajectory) and S3 (knowledge-guided
sequence model) are deliberately absent until that failure is on record.

  S0  point prediction only. Ranking, screening, sensitivity structure.
      No intervals, no viability. Cheap enough to refit constantly.

  S1  two-stage: viability classifier, then per-target regressors on the viable
      subset only, with split-conformal predictive intervals and an
      extrapolation gate.

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
    else:
        raise NotImplementedError(f"tier {spec.tier!r} has no loader yet")

    if len(m._models) != len(spec.targets):
        raise ValueError(
            f"artifact has {len(m._models)} regressors, spec declares "
            f"{len(spec.targets)} targets")
    m.fitted = True
    return m
