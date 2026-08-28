"""The acceptance battery — five tests that replace R2 as the gate.

The 2025 Kougarok attempt reported R2 per output and it told nobody what to do.
R2 is the wrong gate for this use, in both directions: ranking and ruling out are
WEAKER requirements than accurate point prediction, while honesty about
uncertainty is a much STRONGER one, and R2 measures neither.

  1 ranking fidelity    Spearman rho + top-K recall. The screening requirement.
  2 interval coverage   empirical vs nominal. Licenses any exclusion claim.
  3 boundary behaviour  error profiled against distance to training data.
  4 manifold respect    are predicted target COMBINATIONS producible at all?
  5 confirmation rate   measured in use, not offline. See record_confirmation.

Thresholds are supplied by the caller and should be fixed BEFORE seeing the
result, per docs/41 step C4. The battery reports; it does not silently pass.

Author: Jing Tao with Claude
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

import numpy as np

from .base import BatchPrediction, HullGate, SurrogateModel


# =============================================================================
# Test 1 — ranking fidelity
# =============================================================================

def ranking_fidelity(y_true: np.ndarray, y_pred: np.ndarray,
                     k: int = 10, lower_is_better: bool = True) -> Dict[str, float]:
    """Spearman rho and top-k recall between true and predicted orderings.

    Top-k recall is the operationally meaningful one: of the k genuinely best
    configurations, how many appear in the surrogate's own top k? That is what
    decides whether spending HPC on the surrogate's shortlist beats spending it
    at random, and it can be high even when pointwise error is poor.
    """
    from scipy.stats import spearmanr

    y_true = np.asarray(y_true, dtype=float).ravel()
    y_pred = np.asarray(y_pred, dtype=float).ravel()
    m = np.isfinite(y_true) & np.isfinite(y_pred)
    y_true, y_pred = y_true[m], y_pred[m]
    n = len(y_true)
    if n < 3:
        return {"spearman": float("nan"), "top_k_recall": float("nan"), "n": n, "k": k}

    rho = float(spearmanr(y_true, y_pred).statistic)

    k = max(1, min(k, n))
    sign = 1 if lower_is_better else -1
    best_true = set(np.argsort(sign * y_true)[:k].tolist())
    best_pred = set(np.argsort(sign * y_pred)[:k].tolist())
    return {"spearman": rho,
            "top_k_recall": len(best_true & best_pred) / k,
            "n": n, "k": k}


# =============================================================================
# Test 2 — interval coverage
# =============================================================================

def interval_coverage(y_true: np.ndarray, lower: np.ndarray, upper: np.ndarray,
                      nominal: float) -> Dict[str, float]:
    """Empirical coverage and mean interval width.

    Width is reported alongside coverage because coverage alone is trivially
    gamed: an infinitely wide interval covers everything and excludes nothing.
    A surrogate that passes coverage with enormous widths is honest and useless,
    which is a real and acceptable outcome, but it must be visible as such.
    """
    y_true = np.asarray(y_true, dtype=float).ravel()
    lower = np.asarray(lower, dtype=float).ravel()
    upper = np.asarray(upper, dtype=float).ravel()
    m = np.isfinite(y_true) & np.isfinite(lower) & np.isfinite(upper)
    if m.sum() == 0:
        return {"coverage": float("nan"), "nominal": nominal,
                "mean_width": float("nan"), "n": 0}
    inside = (y_true[m] >= lower[m]) & (y_true[m] <= upper[m])
    return {"coverage": float(inside.mean()),
            "nominal": nominal,
            "mean_width": float(np.mean(upper[m] - lower[m])),
            "n": int(m.sum())}


# =============================================================================
# Test 3 — boundary behaviour
# =============================================================================

def boundary_profile(distance: np.ndarray, abs_error: np.ndarray,
                     n_bins: int = 4) -> List[Dict[str, float]]:
    """Absolute error binned by distance to the training set.

    Calibration drives to the box edges, so the number that matters is not mean
    error but how error behaves as a query leaves the data. A rising profile is
    expected and is fine PROVIDED the gate refuses out there; a rising profile
    with a permissive gate is the failure mode this test exists to expose.
    """
    distance = np.asarray(distance, dtype=float).ravel()
    abs_error = np.asarray(abs_error, dtype=float).ravel()
    m = np.isfinite(distance) & np.isfinite(abs_error)
    distance, abs_error = distance[m], abs_error[m]
    if len(distance) == 0:
        return []
    n_bins = max(1, min(n_bins, len(distance)))
    edges = np.quantile(distance, np.linspace(0, 1, n_bins + 1))
    out: List[Dict[str, float]] = []
    for i in range(n_bins):
        lo, hi = edges[i], edges[i + 1]
        sel = (distance >= lo) & (distance <= hi) if i == n_bins - 1 else \
              (distance >= lo) & (distance < hi)
        if sel.sum() == 0:
            continue
        out.append({"bin": i, "d_lo": float(lo), "d_hi": float(hi),
                    "n": int(sel.sum()),
                    "mean_abs_error": float(abs_error[sel].mean()),
                    "median_abs_error": float(np.median(abs_error[sel]))})
    return out


# =============================================================================
# Test 4 — manifold respect
# =============================================================================

def manifold_respect(Y_train: np.ndarray, Y_pred: np.ndarray,
                     k: int = 5, quantile: float = 0.99) -> Dict[str, float]:
    """Fraction of predicted target VECTORS that the model could actually produce.

    Independent per-target regressors will happily emit a (plant_C, NPP) pair
    that lies off the model's reachable manifold, because nothing in their loss
    couples the outputs. Since that manifold is R2's central finding, a surrogate
    violating it does not merely lose accuracy, it invents a physically
    unreachable configuration and then recommends it.

    Measured with the same k-NN support test the input gate uses, applied in
    standardised OUTPUT space.
    """
    Y_train = np.atleast_2d(np.asarray(Y_train, dtype=float))
    Y_pred = np.atleast_2d(np.asarray(Y_pred, dtype=float))
    mt = np.all(np.isfinite(Y_train), axis=1)
    mp = np.all(np.isfinite(Y_pred), axis=1)
    if mt.sum() < 2 or mp.sum() == 0:
        return {"on_manifold": float("nan"), "n": int(mp.sum())}
    gate = HullGate(k=k, quantile=quantile).fit(Y_train[mt])
    inside = gate.inside(Y_pred[mp])
    return {"on_manifold": float(inside.mean()),
            "n": int(mp.sum()),
            "threshold": float(gate.threshold)}


# =============================================================================
# Classifier performance near the viability boundary
# =============================================================================

def boundary_classifier_report(viab_prob: np.ndarray, viable_true: np.ndarray,
                               band: float = 0.25) -> Dict[str, float]:
    """Classifier accuracy overall AND restricted to the uncertain band.

    A global accuracy figure is dominated by easy interior points and will look
    excellent while the boundary, the only region that decides anything, is
    unresolved. The knife-edge structure this model has (the VCMX4 collapse)
    makes that gap the normal case rather than a corner case.
    """
    p = np.asarray(viab_prob, dtype=float).ravel()
    t = np.asarray(viable_true, dtype=bool).ravel()
    if len(p) == 0:
        return {"accuracy": float("nan"), "boundary_accuracy": float("nan"), "n": 0}
    pred = p >= 0.5
    near = np.abs(p - 0.5) <= band
    return {"accuracy": float((pred == t).mean()),
            "n": int(len(p)),
            "boundary_accuracy": float((pred[near] == t[near]).mean())
            if near.sum() else float("nan"),
            "n_boundary": int(near.sum()),
            "viable_fraction": float(t.mean())}


# =============================================================================
# The battery
# =============================================================================

@dataclass
class AcceptanceReport:
    """Per-target and overall results, plus an explicit verdict per test."""

    per_target: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    overall: Dict[str, Any] = field(default_factory=dict)
    verdicts: Dict[str, bool] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.verdicts) and all(self.verdicts.values())

    def summary(self) -> str:
        lines = [f"acceptance: {'PASS' if self.passed else 'FAIL'}"]
        for name, ok in self.verdicts.items():
            lines.append(f"  [{'ok ' if ok else 'FAIL'}] {name}")
        for t, d in self.per_target.items():
            bits = []
            if "spearman" in d:
                bits.append(f"rho={d['spearman']:.3f}")
            if "top_k_recall" in d:
                bits.append(f"top{d.get('k', '')}={d['top_k_recall']:.2f}")
            if "coverage" in d:
                bits.append(f"cov={d['coverage']:.3f}/{d['nominal']:.2f}")
            if "mean_width" in d:
                bits.append(f"width={d['mean_width']:.4g}")
            lines.append(f"    {t:24s} " + "  ".join(bits))
        for n in self.notes:
            lines.append(f"  note: {n}")
        return "\n".join(lines)


def r2_score(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Coefficient of determination, for the ONLINE-INFERENCE bar only.

    Deliberately absent from the offline_search battery. The module README is explicit that "R^2 is
    not the gate. It was what the 2025 Kougarok attempt reported, and it told nobody what to do" --
    a calibration surrogate needs to RANK, and a good R2 with a bad ranking is useless to the loop.
    An online-inference surrogate has the opposite requirement: it substitutes for the physics model
    inside a coupled runtime, so its pointwise value IS the product.
    """
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    if ss_tot == 0.0:
        return float("nan")          # constant truth: R2 undefined, not 1.0
    return 1.0 - ss_res / ss_tot


# Which battery each use_mode gets, and where the bars sit.
#
# THIS TABLE IS THE THING `use_mode` PROMISED AND DID NOT DELIVER. `spec.py` says "the acceptance
# battery keys off it" and `docs/41` says it "selects the acceptance battery and its thresholds",
# but until 2026-08-27 nothing read the field: `git grep use_mode` found it in no acceptance, tier,
# base or learner code, and every threshold was a caller-supplied default. An `online_inference`
# surrogate would have been judged by the CALIBRATION bar in silence -- which docs/41 states is
# deliberately LOWER on accuracy and HIGHER on coverage, so the mismatch runs in the unsafe
# direction for a model that substitutes for physics at runtime.
#
# The asymmetry, stated in docs/41 and encoded here:
#   offline_search    lower accuracy bar (ranking suffices), HIGHER honesty bar (coverage gates)
#   online_inference  higher accuracy bar (pointwise R2 gates), coverage reported not gated
MODE_CRITERIA: Dict[str, Dict[str, Any]] = {
    "offline_search": {
        # Exactly the previous signature defaults, so this change is a no-op for every existing
        # caller. Verified by test: an offline_search report is byte-equal to the pre-change one.
        "min_spearman": 0.7,
        "min_top_k_recall": 0.5,
        "coverage_tolerance": 0.05,
        "min_on_manifold": 0.9,
        "min_r2": None,              # not gated: ranking is the requirement
        "gate_coverage": True,
    },
    "online_inference": {
        # Ranking still measured, and still gated but loosely -- a runtime emulator that inverts the
        # ordering is broken however good its R2. The binding constraint is pointwise accuracy.
        "min_spearman": 0.5,
        "min_top_k_recall": 0.3,
        "coverage_tolerance": 0.05,
        "min_on_manifold": 0.9,
        "min_r2": 0.9,               # docs/41: the runtime-emulator bar is R2 >= 0.9
        "gate_coverage": False,      # reported, not a verdict (docs/41's stated asymmetry)
    },
}


def criteria_for(use_mode: str) -> Dict[str, Any]:
    """The acceptance criteria for a use_mode. Refuses an unknown one rather than defaulting.

    Silently falling back to the calibration battery is the exact failure this table fixes.
    """
    if use_mode not in MODE_CRITERIA:
        raise ValueError(
            f"no acceptance criteria for use_mode {use_mode!r}; known: {sorted(MODE_CRITERIA)}. "
            "Add a MODE_CRITERIA entry rather than letting it fall back to another mode's bar.")
    return dict(MODE_CRITERIA[use_mode])


def run_acceptance(model: SurrogateModel,
                   X_test: np.ndarray,
                   Y_test: np.ndarray,
                   Y_train: Optional[np.ndarray] = None,
                   viable_test: Optional[np.ndarray] = None,
                   min_spearman: Optional[float] = None,
                   min_top_k_recall: Optional[float] = None,
                   coverage_tolerance: Optional[float] = None,
                   min_on_manifold: Optional[float] = None,
                   min_r2: Optional[float] = None,
                   top_k: int = 10,
                   pred: Optional[BatchPrediction] = None) -> AcceptanceReport:
    """MEASURE a fitted surrogate against a held-out set. Tests 1-4; test 5 is measured in use.

    **This function measures; it does not authorise.** `AcceptanceReport.passed` means the automated
    thresholds for this surrogate's `use_mode` were met, which is NECESSARY AND NOT SUFFICIENT for
    using the surrogate. Promotion into calibration is a human gate -- `tools/promote_surrogate.py`
    -- because the checks that decide it (does the response look physically plausible, is the
    training region the one we care about) are not thresholds.

    Thresholds default to the `MODE_CRITERIA` entry for `model.spec.use_mode`; any explicitly
    passed value overrides. `Y_train` is needed for the manifold test and may be omitted, in which
    case that test is skipped and said so.
    """
    crit = criteria_for(model.spec.use_mode)
    if min_spearman is None:
        min_spearman = crit["min_spearman"]
    if min_top_k_recall is None:
        min_top_k_recall = crit["min_top_k_recall"]
    if coverage_tolerance is None:
        coverage_tolerance = crit["coverage_tolerance"]
    if min_on_manifold is None:
        min_on_manifold = crit["min_on_manifold"]
    if min_r2 is None:
        min_r2 = crit["min_r2"]

    rep = AcceptanceReport()
    rep.overall["use_mode"] = model.spec.use_mode
    rep.overall["criteria"] = {"min_spearman": min_spearman,
                               "min_top_k_recall": min_top_k_recall,
                               "coverage_tolerance": coverage_tolerance,
                               "min_on_manifold": min_on_manifold,
                               "min_r2": min_r2,
                               "gate_coverage": crit["gate_coverage"]}
    X_test = np.atleast_2d(np.asarray(X_test, dtype=float))
    Y_test = np.atleast_2d(np.asarray(Y_test, dtype=float))

    # `pred` lets a caller supply a PRECOMPUTED prediction. The model is row-independent,
    # so predict(X[idx]) == predict(X)[idx] exactly; the bootstrap below exploits that to
    # avoid re-predicting 200 times, which is the difference between a 4-minute diagnostic
    # and a 2-second one. It is an identity, not an approximation.
    if pred is None:
        pred = model.predict_batch(X_test)
    has_intervals = pred.lower is not None and pred.upper is not None
    nominal = 1.0 - getattr(model, "alpha", float("nan"))

    rank_ok, cov_ok, acc_ok = True, True, True
    for j, t in enumerate(model.spec.targets):
        d: Dict[str, Any] = {}
        yt, yp = Y_test[:, j], pred.values[:, j]

        # Ranking is on |error| against the observed value when one is declared,
        # which is the quantity the loop actually orders candidates by. Without
        # an observed value, rank on the predicted level itself.
        if t.observed is not None:
            d.update(ranking_fidelity(np.abs(yt - t.observed),
                                      np.abs(yp - t.observed),
                                      k=top_k, lower_is_better=True))
        else:
            d.update(ranking_fidelity(yt, yp, k=top_k, lower_is_better=True))

        # Pointwise accuracy is always MEASURED and reported; whether it GATES depends on the mode.
        d["r2"] = r2_score(yt, yp)
        if min_r2 is not None and np.isfinite(d["r2"]):
            acc_ok &= d["r2"] >= min_r2

        if has_intervals:
            d.update(interval_coverage(yt, pred.lower[:, j], pred.upper[:, j], nominal))
            if np.isfinite(d.get("coverage", np.nan)):
                cov_ok &= d["coverage"] >= nominal - coverage_tolerance

        if pred.hull_distance is not None:
            d["boundary"] = boundary_profile(pred.hull_distance, np.abs(yt - yp))

        if np.isfinite(d.get("spearman", np.nan)):
            rank_ok &= (d["spearman"] >= min_spearman
                        and d["top_k_recall"] >= min_top_k_recall)
        rep.per_target[t.name] = d

    rep.verdicts["ranking_fidelity"] = bool(rank_ok)

    if min_r2 is not None:
        rep.verdicts["pointwise_accuracy"] = bool(acc_ok)
    else:
        rep.notes.append(
            "pointwise R2 measured and reported but NOT gated: this is an offline_search "
            "surrogate, whose requirement is to rank. A good R2 with a bad ranking is useless "
            "to the loop, which is why R2 is not the gate here.")

    if has_intervals:
        if crit["gate_coverage"]:
            rep.verdicts["interval_coverage"] = bool(cov_ok)
        else:
            rep.notes.append(
                "interval coverage measured but NOT gated for online_inference: the accuracy bar "
                "is the binding one for a runtime emulator. Coverage remains in per_target and a "
                "reader should still look at it.")
    else:
        rep.notes.append("tier produces no intervals; coverage not evaluated, "
                         "so this artifact may not be used to rule anything out")

    if Y_train is not None:
        man = manifold_respect(Y_train, pred.values)
        rep.overall["manifold"] = man
        if np.isfinite(man.get("on_manifold", np.nan)):
            rep.verdicts["manifold_respect"] = man["on_manifold"] >= min_on_manifold
    else:
        rep.notes.append("Y_train not supplied; manifold respect not evaluated")

    if pred.viability is not None and viable_test is not None:
        rep.overall["classifier"] = boundary_classifier_report(
            pred.viability, viable_test)

    if pred.in_hull is not None:
        rep.overall["in_hull_fraction"] = float(np.mean(pred.in_hull))
        if rep.overall["in_hull_fraction"] < 1.0:
            rep.notes.append(
                f"{100 * (1 - rep.overall['in_hull_fraction']):.1f}% of the test set "
                "is outside the training hull; those rows are extrapolation and "
                "their errors are not evidence about in-hull performance")
    return rep


# =============================================================================
# Robustness — was the verdict ROBUST, or was it LUCKY?
# =============================================================================

def _slice_prediction(pred: BatchPrediction, idx: np.ndarray) -> BatchPrediction:
    """Row-subset a BatchPrediction. Exact because every field is per-row."""
    def take(a):
        return None if a is None else np.asarray(a)[idx]
    return BatchPrediction(spec=pred.spec,
                           values=np.asarray(pred.values)[idx],
                           lower=take(pred.lower), upper=take(pred.upper),
                           viability=take(pred.viability),
                           in_hull=take(pred.in_hull),
                           hull_distance=take(pred.hull_distance))


def bootstrap_acceptance(model: SurrogateModel,
                         X_test: np.ndarray,
                         Y_test: np.ndarray,
                         Y_train: Optional[np.ndarray] = None,
                         n_boot: int = 200,
                         seed: int = 0,
                         **accept_kw: Any) -> Dict[str, Any]:
    """How often does the verdict survive a resample of the test set?

    WHY THIS EXISTS. `run_acceptance` returns ONE number per test from ONE split, and
    `AcceptanceReport.passed` is a hard threshold on it. That makes a genuinely marginal
    surrogate -- rho 0.71 against a 0.70 bar -- indistinguishable from a comfortable one, and the
    promotion gate then asks a human to authorise a result whose stability nobody measured.

    Resampling the TEST set with replacement costs no refit: the model is already fitted, so this
    is a few hundred cheap re-scorings. It answers the question a reviewer actually has -- *would
    a different draw of the same size have said the same thing?* -- which is exactly the
    robustness diagnostic Jeong et al. (2026) run as a perturbation study and A2MC had no analogue
    of.

    WHAT IT DOES NOT DO. It resamples the test set, not the TRAINING set, so it measures the
    stability of the VERDICT rather than of the fitted model. A surrogate trained on an
    unrepresentative ensemble will look stable here and still be wrong; that is the standing
    ensemble gate's job (`scripts/check_surrogate_gate.py`), not this one.

    Returns per-verdict pass RATES and per-metric quantiles. A `pass_rate` well below 1.0 on a
    report whose headline says PASS is the signal this function exists to surface.
    """
    rng = np.random.default_rng(seed)
    X_test = np.atleast_2d(np.asarray(X_test, dtype=float))
    Y_test = np.atleast_2d(np.asarray(Y_test, dtype=float))
    n = len(X_test)
    if n < 5:
        return {"n_boot": 0, "note": f"only {n} test rows; a bootstrap here would be theatre"}

    full = model.predict_batch(X_test)          # ONCE, then sliced per replicate
    verdict_hits: Dict[str, int] = {}
    metric_draws: Dict[str, List[float]] = {}
    n_ok = 0
    for _ in range(max(1, n_boot)):
        idx = rng.integers(0, n, size=n)
        try:
            rep = run_acceptance(model, X_test[idx], Y_test[idx],
                                 Y_train=Y_train,
                                 pred=_slice_prediction(full, idx), **accept_kw)
        except Exception:                                        # noqa: BLE001
            continue
        n_ok += 1
        for k, v in rep.verdicts.items():
            verdict_hits[k] = verdict_hits.get(k, 0) + int(bool(v))
        verdict_hits["ALL"] = verdict_hits.get("ALL", 0) + int(rep.passed)
        for t, d in rep.per_target.items():
            for m in ("spearman", "top_k_recall", "r2", "coverage"):
                if isinstance(d.get(m), (int, float)) and np.isfinite(d[m]):
                    metric_draws.setdefault(f"{t}.{m}", []).append(float(d[m]))

    if n_ok == 0:
        return {"n_boot": 0, "note": "every bootstrap replicate raised; nothing measured"}

    out: Dict[str, Any] = {"n_boot": n_ok, "n_test": n,
                           "pass_rate": {k: v / n_ok for k, v in verdict_hits.items()},
                           "quantiles": {}}
    for k, draws in metric_draws.items():
        a = np.asarray(draws, dtype=float)
        out["quantiles"][k] = {"p05": float(np.quantile(a, 0.05)),
                               "p50": float(np.quantile(a, 0.50)),
                               "p95": float(np.quantile(a, 0.95))}
    return out


def perturbation_stability(model: SurrogateModel,
                           X: np.ndarray,
                           eps: float = 0.10,
                           k: int = 10,
                           n_rep: int = 20,
                           seed: int = 0) -> Dict[str, Any]:
    """Does the surrogate's SHORTLIST survive a small perturbation of its inputs?

    The loop uses a surrogate to pick candidates, so the operationally meaningful stability is not
    "does the prediction move" but "does the TOP-K SET move". A surrogate whose shortlist is
    reshuffled by a 10% input jitter is proposing an ordering it cannot defend, whatever its
    Spearman on a clean test set.

    `eps` is a RELATIVE perturbation applied per input, scaled by each input's own range from the
    spec box, so a parameter spanning six orders of magnitude is not perturbed in the same
    absolute units as one spanning 0-1.

    Reported per target as mean top-k overlap in [0, 1]. Jeong et al. (2026) run the analogous
    +/-10% study and read it as a robustness ranking; here it is read as a stability check on the
    thing A2MC actually consumes.
    """
    rng = np.random.default_rng(seed)
    X = np.atleast_2d(np.asarray(X, dtype=float))
    n = len(X)
    if n < 3:
        return {"note": f"only {n} rows; top-k stability is undefined"}
    k = max(1, min(k, n))

    lo = np.asarray(model.spec.input_lower, dtype=float)
    hi = np.asarray(model.spec.input_upper, dtype=float)
    scale = np.where(hi > lo, hi - lo, 1.0)

    base = model.predict_batch(X).values
    names = model.spec.target_names
    overlaps: Dict[str, List[float]] = {t: [] for t in names}
    for _ in range(max(1, n_rep)):
        Xp = X + rng.normal(0.0, eps, size=X.shape) * scale
        Xp = np.clip(Xp, lo, hi)                    # stay inside the declared box
        pert = model.predict_batch(Xp).values
        for j, t in enumerate(names):
            a = set(np.argsort(base[:, j])[:k].tolist())
            b = set(np.argsort(pert[:, j])[:k].tolist())
            overlaps[t].append(len(a & b) / k)
    return {"eps": eps, "k": k, "n_rep": n_rep, "n": n,
            "top_k_overlap": {t: float(np.mean(v)) for t, v in overlaps.items()}}


# =============================================================================
# Test 5 — confirmation rate, measured in use
# =============================================================================

def record_confirmation(predicted: BatchPrediction, observed: Sequence[Dict[str, float]]
                        ) -> Dict[str, Any]:
    """Compare physics-confirmed results against what the surrogate predicted.

    This is the only number that decides whether the loop is better off, and it
    cannot be computed offline. Call it after every physics confirmation batch
    (docs/41 step D4) and track it as the live health metric. A falling
    confirmation rate is the signal to refit or to retire the artifact for that
    region, and a single disagreement is not a failure but the most informative
    training point available.
    """
    names = predicted.spec.target_names
    n = min(predicted.n, len(observed))
    hit = {nm: 0 for nm in names}
    total = {nm: 0 for nm in names}
    for i in range(n):
        for j, nm in enumerate(names):
            if nm not in observed[i]:
                continue
            v = float(observed[i][nm])
            if not np.isfinite(v):
                continue
            total[nm] += 1
            if predicted.lower is None or predicted.upper is None:
                continue
            if predicted.lower[i, j] <= v <= predicted.upper[i, j]:
                hit[nm] += 1
    per = {nm: (hit[nm] / total[nm] if total[nm] else float("nan")) for nm in names}
    tot = sum(total.values())
    return {"per_target": per,
            "overall": (sum(hit.values()) / tot) if tot else float("nan"),
            "n_confirmed": n}


# =============================================================================
# Learner bake-off — pick the family on evidence, not taste
# =============================================================================

def compare_learners(spec, X, Y, viable=None, learners=("rf", "gbm", "gp", "mlp"),
                     classifiers=("rf",), tier: str = "S1",
                     rank_for: str = "screen", alpha: float = 0.05,
                     test_fraction: float = 0.25,
                     random_state: int = 0, learner_kw: Optional[Dict[str, Dict]] = None,
                     **acceptance_kw) -> Dict[str, Any]:
    """Fit each learner family on the same split and score them identically.

    Which model family suits a given site is an empirical question, not a
    matter of taste: tree families represent thresholds but not smooth trends,
    a GP does the reverse and additionally gives a variance that grows away from
    data, and an MLP ensemble is the only family that can carry a
    knowledge-guided loss. Rather than picking one on priors, fit them all and
    let the acceptance battery rank them.

    ``alpha`` is an explicit parameter rather than part of ``acceptance_kw``
    because it does double duty: it sets each model's conformal level AND the
    nominal the ranking measures coverage against. Those must be the same
    number, and threading it through ``**kwargs`` let them silently diverge.

    ``rank_for`` selects the ordering, because **which family wins depends on
    what you are doing** (see `RANK_KEYS`). Screening ranks on top-k recall and
    barely cares about interval width; ruling out gates on coverage and then
    prefers the TIGHTEST honest interval, because a band wide enough to overlap
    everything excludes nothing. Never R2 or RMSE: a family that wins on RMSE
    while under-covering licenses exclusions it has not earned.

    Returns a dict with per-learner reports plus a ``ranking`` list, best first.
    Learners that fail to fit are recorded with their error rather than
    silently dropped, since a missing row would otherwise read as "not tried".
    """
    from .tiers import S0Surrogate, S1Surrogate

    X = np.atleast_2d(np.asarray(X, dtype=float))
    Y = np.atleast_2d(np.asarray(Y, dtype=float))
    learner_kw = learner_kw or {}

    rng = np.random.default_rng(random_state)
    idx = rng.permutation(len(X))
    n_test = max(1, int(round(test_fraction * len(X))))
    te, tr = idx[:n_test], idx[n_test:]
    viable = None if viable is None else np.asarray(viable, dtype=bool)

    # S1 has TWO halves and both are the caller's choice, so a bake-off that
    # varied only the regressor would compare four half-approaches over one
    # fixed other half. Crossing the two lists makes the comparison honest;
    # `classifiers=("rf",)` keeps the common case to one column.
    combos = ([(lr, cl) for lr in learners for cl in classifiers]
              if tier == "S1" else [(lr, None) for lr in learners])

    results: Dict[str, Any] = {}
    for lr_name, cl_name in combos:
        name = lr_name if (cl_name is None or len(classifiers) == 1) \
            else f"{lr_name}/{cl_name}"
        try:
            kw = dict(learner_kw.get(lr_name, {}))
            if tier == "S1":
                model = S1Surrogate(spec, learner=lr_name, classifier=cl_name,
                                    alpha=alpha, random_state=random_state, **kw)
            else:
                model = S0Surrogate(spec, learner=lr_name, **kw)
            model.fit(X[tr], Y[tr], None if viable is None else viable[tr])
            rep = run_acceptance(
                model, X[te], Y[te],
                Y_train=Y[tr] if viable is None else Y[tr][viable[tr]],
                viable_test=None if viable is None else viable[te],
                **acceptance_kw)
            tgt = list(rep.per_target.values())
            results[name] = {
                "report": rep,
                "passed": rep.passed,
                "mean_top_k_recall": float(np.nanmean(
                    [d.get("top_k_recall", np.nan) for d in tgt])),
                "mean_spearman": float(np.nanmean(
                    [d.get("spearman", np.nan) for d in tgt])),
                "mean_coverage": float(np.nanmean(
                    [d.get("coverage", np.nan) for d in tgt])),
                "mean_width": float(np.nanmean(
                    [d.get("mean_width", np.nan) for d in tgt])),
                "normalized_intervals": getattr(model, "normalized", False),
                "learner": lr_name,
                "classifier": cl_name,
                "classifier_accuracy": (
                    rep.overall.get("classifier", {}).get("boundary_accuracy",
                                                          float("nan"))),
                "model": model,
            }
        except Exception as exc:                      # noqa: BLE001 — recorded, not hidden
            results[name] = {"error": f"{type(exc).__name__}: {exc}"}

    ranking = rank_results(results, rank_for=rank_for, alpha=alpha)
    return {"results": results, "ranking": ranking, "rank_for": rank_for,
            "best": ranking[0] if ranking else None}


# =============================================================================
# Ranking keys — which family wins DEPENDS ON WHAT YOU ARE DOING
# =============================================================================
#
# A single key cannot serve every use, and pretending otherwise misleads. The
# first cut ranked on top-k recall with width only as a tiebreak, and the very
# first real bake-off showed why that is wrong: `mlp` won on top-k while
# carrying 5x the interval width of `rf`, over-covering at 0.977 against 0.95
# nominal. That is the "honest but useless" case this module warns about
# elsewhere -- and for SCREENING it is genuinely fine, because ranking is the
# product and width is irrelevant. For RULING OUT it is the opposite: an
# interval so wide it overlaps everything excludes nothing, so width IS the
# product once coverage is met.

def _cov_gap(r: Dict[str, Any], alpha: float) -> float:
    """How far short of nominal coverage, 0 when met or unmeasurable."""
    c = r.get("mean_coverage", float("nan"))
    return max(0.0, (1.0 - alpha) - c) if np.isfinite(c) else 0.0


RANK_KEYS = {
    # Ranking is the product; width is nearly irrelevant.
    "screen": lambda r, a: (-r["mean_top_k_recall"], -r["mean_spearman"],
                            _cov_gap(r, a), r["mean_width"]),
    "search": lambda r, a: (-r["mean_top_k_recall"], -r["mean_spearman"],
                            _cov_gap(r, a), r["mean_width"]),
    # Getting the response SHAPE right matters more than the top-k head.
    "sensitivity": lambda r, a: (-r["mean_spearman"], -r["mean_top_k_recall"],
                                 r["mean_width"]),
    # Coverage is a gate, not a score: miss it and nothing may be excluded.
    # Then a CONSTANT-width family is demoted, because one width everywhere
    # cannot localise where the reachable set approaches the target box. Only
    # then does tightness rank, since among honest intervals the narrow one
    # carries more information.
    "rule_out": lambda r, a: (_cov_gap(r, a), not r.get("normalized_intervals", False),
                              r["mean_width"], -r["mean_top_k_recall"]),
    # The original compromise, kept so old behaviour is reproducible.
    "balanced": lambda r, a: (-r["mean_top_k_recall"], _cov_gap(r, a),
                              r["mean_width"]),
}


def rank_results(results: Dict[str, Any], rank_for: str = "screen",
                 alpha: float = 0.05) -> List[str]:
    """Order bake-off entries for a stated use. Failed fits always sort last."""
    if rank_for not in RANK_KEYS:
        raise ValueError(
            f"unknown rank_for {rank_for!r}; choose from {sorted(RANK_KEYS)}")
    keyfn = RANK_KEYS[rank_for]

    def key(item):
        name, r = item
        if "error" in r:
            return (1,)                     # errors last, regardless of scheme
        return (0,) + tuple(float(v) for v in keyfn(r, alpha))

    return [n for n, _ in sorted(results.items(), key=key)]


def bakeoff_summary(cmp: Dict[str, Any]) -> str:
    """One line per combination, best first.

    `cliff` is the classifier's accuracy NEAR the alive/dead boundary, not
    overall: a global figure is dominated by easy interior points and would look
    excellent while the boundary that decides everything is unresolved.
    """
    lines = [f"(ranked for: {cmp.get('rank_for', 'screen')})",
             f"{'combo':14s} {'pass':5s} {'top-k':>6s} {'rho':>6s} "
             f"{'cover':>6s} {'width':>10s} {'cliff':>6s}  intervals"]
    for name in cmp["ranking"]:
        r = cmp["results"][name]
        if "error" in r:
            lines.append(f"{name:14s} ERROR  {r['error'][:56]}")
            continue
        cliff = r.get("classifier_accuracy", float("nan"))
        lines.append(
            f"{name:14s} {'yes' if r['passed'] else 'no':5s} "
            f"{r['mean_top_k_recall']:6.2f} {r['mean_spearman']:6.3f} "
            f"{r['mean_coverage']:6.3f} {r['mean_width']:10.4g} "
            f"{cliff:6.2f}  "
            f"{'normalized' if r['normalized_intervals'] else 'constant'}")
    return "\n".join(lines)
