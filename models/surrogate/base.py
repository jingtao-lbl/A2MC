"""SurrogateModel — the emulator interface, and the extrapolation gate.

WHAT THIS IS NOT: a ``ModelBackend``. See ``models/surrogate/README.md`` and
docs/41 section 6.2. The backend interface's narrowest waist is a time series
per history variable; an S0/S1 surrogate predicts the *reduced scalar*, so
impersonating a backend would mean fabricating trajectories that reduce to the
predicted value. Instead a surrogate predicts the same ``simulated``
``{target: scalar}`` mapping that ``tools.model_evaluate_case.evaluate_model_case``
produces, and that mapping is fed to the EXISTING, unmodified
``tools.cost_functions.compute_snapshot_cost``. Physics and surrogate are then
scored by literally the same function.

Author: Jing Tao with Claude
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from .spec import SurrogateSpec


# =============================================================================
# Prediction results
# =============================================================================

@dataclass
class BatchPrediction:
    """Predictions for N input points.

    ``values`` is (N, T) in target order. ``lower``/``upper`` are the predictive
    interval and are None for tiers that do not produce one (S0). ``viability``
    is P(run is viable) and is None when the tier has no classifier.

    ``in_hull`` is the extrapolation gate's verdict. It is deliberately separate
    from the interval: an interval can look tight simply because every training
    point nearby agreed, which says nothing about a region with no training
    points at all.
    """

    spec: SurrogateSpec
    values: np.ndarray                      # (N, T)
    lower: Optional[np.ndarray] = None      # (N, T)
    upper: Optional[np.ndarray] = None      # (N, T)
    viability: Optional[np.ndarray] = None  # (N,)
    in_hull: Optional[np.ndarray] = None    # (N,) bool
    hull_distance: Optional[np.ndarray] = None  # (N,) float

    def __post_init__(self) -> None:
        self.values = np.atleast_2d(np.asarray(self.values, dtype=float))
        t = len(self.spec.targets)
        if self.values.shape[1] != t:
            raise ValueError(
                f"values has {self.values.shape[1]} columns, spec declares {t} targets")

    @property
    def n(self) -> int:
        return self.values.shape[0]

    def simulated(self, i: int = 0) -> Dict[str, float]:
        """Row ``i`` as the ``{target: scalar}`` mapping the cost layer expects.

        This is the whole point of the adopted seam: the returned dict is
        interface-identical to ``evaluate_model_case``'s third return value, so
        it can be handed straight to ``compute_snapshot_cost``.
        """
        return {t.name: float(self.values[i, j])
                for j, t in enumerate(self.spec.targets)}

    def in_band(self) -> np.ndarray:
        """(N,) bool — every banded target inside its band, on the point estimate."""
        ok = np.ones(self.n, dtype=bool)
        for j, t in enumerate(self.spec.targets):
            if t.lower is not None:
                ok &= self.values[:, j] >= t.lower
            if t.upper is not None:
                ok &= self.values[:, j] <= t.upper
        return ok

    def band_reachable(self) -> np.ndarray:
        """(N,) bool — the target box is reachable within the predictive interval.

        Deliberately more permissive than ``in_band``: a point counts if its
        INTERVAL overlaps the band, not only if its point estimate lands inside.
        This is the conservative direction for ruling out, which is the only
        direction ruling out is allowed to be used in (docs/41 section 2.1).
        Falls back to ``in_band`` when the tier has no intervals.
        """
        if self.lower is None or self.upper is None:
            return self.in_band()
        ok = np.ones(self.n, dtype=bool)
        for j, t in enumerate(self.spec.targets):
            if t.lower is not None:
                ok &= self.upper[:, j] >= t.lower
            if t.upper is not None:
                ok &= self.lower[:, j] <= t.upper
        return ok


# =============================================================================
# Extrapolation gate
# =============================================================================

@dataclass
class HullGate:
    """Refuse-rather-than-guess gate on how far a query is from training data.

    Calibration drives to the edges of the parameter box (R2's VRNXI 52 corner),
    which is exactly where an emulator is weakest, so a surrogate that silently
    extrapolates will be most confident where it is least entitled to be.

    Method: distance to the k-th nearest training point in standardised input
    space, thresholded at a quantile of the training set's own k-NN distances.

    Why not a convex hull: QHull needs more points than dimensions and its cost
    is exponential in dimension, so it is unusable at the 10-20 D of a screened
    subspace. Why not per-dimension bounds alone: a box test passes points in
    the middle of an empty diagonal corner, which is precisely the failure this
    gate exists to catch. k-NN distance degrades gracefully in both respects.
    """

    k: int = 5
    quantile: float = 0.99
    _mean: Optional[np.ndarray] = None
    _scale: Optional[np.ndarray] = None
    _train: Optional[np.ndarray] = None
    _threshold: float = np.inf

    def fit(self, X: np.ndarray) -> "HullGate":
        X = np.atleast_2d(np.asarray(X, dtype=float))
        self._mean = X.mean(axis=0)
        s = X.std(axis=0)
        # A constant column carries no distance information; scaling it by ~0
        # would explode every distance, so pin it to 1.
        s[s <= 0] = 1.0
        self._scale = s
        self._train = (X - self._mean) / self._scale
        k = min(self.k, max(1, len(self._train) - 1))
        d = self._knn_distance(self._train, exclude_self=True, k=k)
        self._threshold = float(np.quantile(d, self.quantile)) if len(d) else np.inf
        return self

    def _knn_distance(self, Z: np.ndarray, exclude_self: bool, k: int) -> np.ndarray:
        if self._train is None or len(self._train) == 0:
            return np.full(len(Z), np.inf)
        # Chunked to keep the pairwise matrix bounded for large query batches.
        out = np.empty(len(Z), dtype=float)
        step = max(1, int(2e7 // max(1, len(self._train))))
        for a in range(0, len(Z), step):
            b = min(a + step, len(Z))
            d = np.linalg.norm(Z[a:b, None, :] - self._train[None, :, :], axis=2)
            if exclude_self:
                np.fill_diagonal(d[:, a:b], np.inf)
            kk = min(k, d.shape[1] - 1) if exclude_self else min(k, d.shape[1])
            kk = max(kk, 1)
            out[a:b] = np.partition(d, kk - 1, axis=1)[:, kk - 1]
        return out

    def distance(self, X: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, dtype=float))
        Z = (X - self._mean) / self._scale
        return self._knn_distance(Z, exclude_self=False, k=self.k)

    def inside(self, X: np.ndarray) -> np.ndarray:
        return self.distance(X) <= self._threshold

    @property
    def threshold(self) -> float:
        return self._threshold


# =============================================================================
# SurrogateModel
# =============================================================================

class SurrogateModel(ABC):
    """A trained emulator of a physics model's calibration targets."""

    def __init__(self, spec: SurrogateSpec) -> None:
        self.spec = spec
        self.fitted = False

    @abstractmethod
    def fit(self, X: np.ndarray, Y: np.ndarray,
            viable: Optional[np.ndarray] = None) -> "SurrogateModel":
        """Fit on a design matrix.

        ``X``      (N, P) parameter values in ``spec.input_names`` order.
        ``Y``      (N, T) reduced target values in ``spec.targets`` order. Rows
                   for non-viable cases may be NaN and MUST be tolerated.
        ``viable`` (N,) bool, or None when every row is viable. Failed, dead and
                   crashed runs are training signal for the classifier, not
                   rows to discard (docs/41 section 7 constraint 3).
        """

    @abstractmethod
    def predict_batch(self, X: np.ndarray) -> BatchPrediction:
        """Predict for (N, P) inputs."""

    def predict(self, x: Sequence[float]) -> BatchPrediction:
        return self.predict_batch(np.atleast_2d(np.asarray(x, dtype=float)))

    def simulated(self, x: Sequence[float]) -> Dict[str, float]:
        """One point as the ``{target: scalar}`` mapping the cost layer expects."""
        return self.predict(x).simulated(0)

    # ---- Persistence ----

    def save(self, directory: Path) -> Path:
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.spec.write(directory / "spec.json")
        (directory / "tier.json").write_text(json.dumps({"class": type(self).__name__}))
        self._save_artifacts(directory)
        return directory

    @abstractmethod
    def _save_artifacts(self, directory: Path) -> None:
        """Persist the fitted estimators (joblib) alongside the spec."""

    # ---- Guards ----

    def _check_fitted(self) -> None:
        if not self.fitted:
            raise RuntimeError(f"{type(self).__name__} is not fitted")

    def _check_X(self, X: np.ndarray) -> np.ndarray:
        X = np.atleast_2d(np.asarray(X, dtype=float))
        if X.shape[1] != self.spec.n_inputs:
            raise ValueError(
                f"X has {X.shape[1]} columns, spec declares "
                f"{self.spec.n_inputs} inputs ({', '.join(self.spec.input_names[:4])}...)")
        return X


# =============================================================================
# Transforms
# =============================================================================

def apply_transform(y: np.ndarray, kind: str) -> np.ndarray:
    if kind == "identity":
        return y
    if kind == "log":
        if np.any(y[np.isfinite(y)] <= 0):
            raise ValueError("log transform requires strictly positive values")
        return np.log(y)
    if kind == "logit":
        f = y[np.isfinite(y)]
        if np.any((f <= 0) | (f >= 1)):
            raise ValueError("logit transform requires values strictly in (0, 1)")
        return np.log(y / (1.0 - y))
    raise ValueError(f"unknown transform {kind!r}")


def invert_transform(z: np.ndarray, kind: str) -> np.ndarray:
    if kind == "identity":
        return z
    if kind == "log":
        return np.exp(z)
    if kind == "logit":
        return 1.0 / (1.0 + np.exp(-z))
    raise ValueError(f"unknown transform {kind!r}")
