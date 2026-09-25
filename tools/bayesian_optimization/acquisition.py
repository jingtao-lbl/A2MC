"""Feasibility-weighted expected improvement on the violation `V` -- docs/42 stage S2.

WHAT THIS COMPUTES. The acquisition that decides which parameter sets to run next:

    alpha(theta) = P(viable)(theta) * E[max(0, V* - V(theta))]

`V = max_i v_i` is the Chebyshev violation of `objective.py`, `V*` is the best `V` observed on the
physics model, and `P(viable)` comes from the surrogate's classifier. The surrogate models each
TARGET, never `V` (docs/42 section 3): target i has an independent Gaussian posterior
`Y_i ~ N(mu_i, sd_i)` in the space its regressor was fitted in (identity, log or logit), and
`y_i = inv_i(Y_i)` is the native value.

WHY THE EXPECTATION IS EXACT RATHER THAN SAMPLED. For a non-negative `V`,

    E[max(0, V* - V)] = int_0^{V*} P(V <= t) dt,

and `V <= t` holds exactly when every target is within `t` band-widths of its observation, so
under independence

    P(V <= t) = prod_i P( y_i in [obs_i (1 - t u_i), obs_i (1 + t u_i)] ).

Each factor is a difference of two normal CDFs once the band edges are mapped through the
target's transform. The expectation is therefore a one-dimensional integral of a known function
over `[0, V*]`, evaluated by composite Gauss-Legendre quadrature. Monte Carlo over the joint
posterior estimates the same number with sampling error that grows without bound relative to
small expectations, so it is kept as the independent cross-check in the tests, not as the method.

WHERE THE QUADRATURE NEEDS HELP. The integrand changes scale or loses analyticity at known
points, and every segment boundary is placed on one of them (clipped to `[0, V*]`):

  * each target's knee `k_i`, the violation of its posterior mean, and `k_i +/- {1, 3, 5, 8} w_i`,
    where `w_i` is the transition width in `t` (the posterior sd mapped to band-width units);
  * for a target whose knee lies above `V*`, tail points `V* - c w_i / max(1, z_i)`,
    `c in {0.5, 2, 8, 32}`, `z_i = (k_i - V*) / w_i`: the integrand then lives only within about
    `w_i / z_i` of `V*`, which the knee points, all clipped to `V*`, cannot resolve;
  * `t = 1/u_i` for log and logit targets, where the lower band edge reaches 0, and for logit
    targets `t = (1/obs_i - 1)/u_i` when `obs_i < 1`, where the upper edge reaches 1, or
    `t = (1 - 1/obs_i)/u_i` when `obs_i >= 1`, where the lower edge reaches 1. These are the only
    non-analytic points of the band probability; the identity transform has none.

`w_i` and `z_i` linearise the transform at the posterior mean, which is exact for identity and
can be far off for log and logit: a log prediction five e-folds below its band, with sd 0.3, has
a tail about 75 times wider than the linearised one. Log and logit targets therefore also get the
same points placed in the fitted space, where the posterior is Gaussian:

  * the band-edge crossings of `Y = mu_i +/- m sd_i`, `m in {1, 3, 5, 8}`, at
    `t = |inv(mu_i +/- m sd_i) - obs_i| / (u_i obs_i)`;
  * for a knee above `V*`, the crossings of `m = z'_i + c / max(1, z'_i)`, with `z'_i` the binding
    band edge's distance from `mu_i` at `t = V*` in fitted-space sd;
  * a geometric grading toward each kink from the side where the band edge is inside the domain:
    from below, `kink (1 - 4^-j)`, and for the lower edge reaching 1, from above,
    `kink + 4^-j / u_i`, `j = 1..12`, whenever a graded point falls inside `[0, V*]`. On that side
    the band probability is smooth in the logarithm of the edge's distance to the domain boundary,
    not in `t`, so a segment ending at the kink converges slowly without it.

Two further numerical rules. The band probability is evaluated in a cancellation-free form (the
mirrored CDF difference when the band lies above the mean), so a prediction far below its band is
as accurate as one far above it. And the posterior sd is floored per target (`sd_floor`), because
an exactly zero sd turns a node at the knee into 0/0.

Also here: the unit-cube map, the candidate sets (a scrambled Sobol' scan and Gaussian
perturbations of the best viable rows, reflected at the cube faces), memory-bounded nearest
distances, and the two batch pickers (greedy maximin, and local penalisation).

HOW A BATCH IS CHOSEN (`propose_batch`). Every candidate is scored once; candidates within
`min_separation` of an observed row, or outside the surrogate's hull gate, are inadmissible. Pick
j takes the admissible argmax of alpha under a Kriging-believer copy of the surrogate that
conditions on picks 1..j-1, with `V*` held at the value observed on the physics model for the
whole batch. After each pick every candidate within `r_sep` (unit-cube L-inf, derived from
candidate density) is dropped, which is what keeps a batch from crowding one basin: conditioning
alone does not, once the fitted noise keeps the posterior sd from shrinking beside a pick. When
alpha carries no ranking information (zero everywhere at pick 1, P(viable) zero everywhere, or a
later maximum below `degenerate_rel` times the first) the remaining picks are greedy maximin.
With too few viable observations for a surrogate the batch is a cold start: maximin over the
scan, weighted by P(viable) when both outcomes have been observed.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import math
import pathlib
import sys
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.special import expit, ndtr

REPO = pathlib.Path(__file__).resolve().parents[2]   # tools/bayesian_optimization/ -> repo root
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.bayesian_optimization.objective import Target  # noqa: E402


VALID_TRANSFORMS = ("identity", "log", "logit")

#: Relative sd floor: identity targets are floored at this times u*obs, log and logit at this.
_SD_FLOOR = 1e-12

#: Knee breakpoints are k +/- m*w for these m.
_KNEE_MULTIPLES = (0.0, 1.0, 3.0, 5.0, 8.0)

#: Tail breakpoints are V* - c*w/max(1, z) for these c, for targets whose knee lies above V*.
_TAIL_MULTIPLES = (0.5, 2.0, 8.0, 32.0)

#: A log/logit kink is approached from below through kink * (1 - ratio**j), j = 1..levels.
_KINK_GRADING_RATIO = 0.25
_KINK_GRADING_LEVELS = 12

#: Elements in one (candidates x quadrature nodes) array of the expected-improvement integral.
_EI_CHUNK_ELEMENTS = 1e6

#: Elements allowed in one pairwise-difference array: 2e7 float64 elements is 160 MB.
_DISTANCE_BUDGET = 2e7


# =============================================================================
# Band probability and the exact expected improvement
# =============================================================================

def _check_targets(targets: Sequence[Target], transforms: Sequence[str]) -> None:
    if len(targets) != len(transforms):
        raise ValueError(f"{len(targets)} targets but {len(transforms)} transforms; pass one "
                         f"transform per target, in target order.")
    if len(targets) == 0:
        raise ValueError("no targets: V = max_i v_i over an empty set is undefined.")
    for t, tr in zip(targets, transforms):
        if tr not in VALID_TRANSFORMS:
            raise ValueError(f"target {t.name!r}: transform {tr!r} not in {VALID_TRANSFORMS}")
        if t.observed < 0:
            raise ValueError(
                f"target {t.name!r}: observed is {t.observed} < 0, so the band "
                f"observed*(1 -/+ t*u) has its edges inverted. Score this target on a "
                f"positive reference, or exclude it.")


def band_probability(mu, sd, lo, hi, transform: str) -> np.ndarray:
    """`P(inv(Y) in [lo, hi])` for `Y ~ N(mu, sd)` in the fitted space; `lo`/`hi` are native.

    Broadcasts over its array arguments. `sd` must be strictly positive (floor it with
    `sd_floor`). Band edges outside a transform's domain are handled exactly: under `log` a band
    with `hi <= 0` has probability 0 and `lo <= 0` removes the lower tail; under `logit` the band
    is clipped to (0, 1), and a band with `hi <= 0` or `lo >= 1` has probability 0.

    The difference of CDFs is taken on the side where both terms are not close to 1: with
    `a = (lo' - mu)/sd` and `b = (hi' - mu)/sd`, `ndtr(-a) - ndtr(-b)` when `a > 0`, otherwise
    `ndtr(b) - ndtr(a)`. The literal `ndtr(b) - ndtr(a)` rounds to 0 once `a` exceeds about 8.3.
    """
    if transform not in VALID_TRANSFORMS:
        raise ValueError(f"transform {transform!r} not in {VALID_TRANSFORMS}")
    mu = np.asarray(mu, dtype=float)
    sd = np.asarray(sd, dtype=float)
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    if not np.all(sd > 0):
        raise ValueError("band_probability needs sd > 0 everywhere; floor the posterior sd "
                         "with sd_floor before integrating.")

    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        if transform == "identity":
            lo_t, hi_t = lo, hi
        elif transform == "log":
            lo_t = np.where(lo > 0, np.log(np.where(lo > 0, lo, 1.0)), -np.inf)
            hi_t = np.where(hi > 0, np.log(np.where(hi > 0, hi, 1.0)), -np.inf)
        else:
            lo_t = _logit_edge(lo)
            hi_t = _logit_edge(hi)
        a = (lo_t - mu) / sd
        b = (hi_t - mu) / sd
        p = np.where(a > 0, ndtr(-a) - ndtr(-b), ndtr(b) - ndtr(a))
    return np.maximum(p, 0.0)


def _logit_edge(x: np.ndarray) -> np.ndarray:
    """logit of a native band edge, with the edge clipped to (0, 1): -inf at or below 0, +inf at
    or above 1."""
    inside = (x > 0) & (x < 1)
    xc = np.where(inside, x, 0.5)
    return np.where(x <= 0, -np.inf, np.where(x >= 1, np.inf, np.log(xc / (1.0 - xc))))


def sd_floor(targets: Sequence[Target], transforms: Sequence[str]) -> np.ndarray:
    """(T,) smallest posterior sd the integral uses, per target, in the fitted space.

    `1e-12 * u * obs` for identity (so the floor is 1e-12 band-widths whatever the units) and
    `1e-12` for log and logit, whose fitted space is already dimensionless.
    """
    _check_targets(targets, transforms)
    return np.array([_SD_FLOOR * t.uncertainty * t.observed if tr == "identity" else _SD_FLOOR
                     for t, tr in zip(targets, transforms)], dtype=float)


def expected_improvement(mu, sd, targets: Sequence[Target], transforms: Sequence[str],
                         V_star: float, n_nodes: int = 16) -> np.ndarray:
    """(n,) `E[max(0, V* - V)]` under independent Gaussian posteriors per target.

    `mu` and `sd` are (n, T) in each target's fitted space, targets in the order of `targets`
    and `transforms`. The integral `int_0^{V*} P(V <= t) dt` is evaluated by composite
    Gauss-Legendre with `n_nodes` nodes per segment over the breakpoints in the module docstring,
    with the sd floored by `sd_floor`, in chunks of candidates.

    `V* <= 0` gives zeros: no `V` can improve on it. A non-finite `V*` is refused: when nothing
    viable has been observed there is no incumbent, and that is the caller's cold-start case.
    A non-finite result is a RuntimeError, never a value an argmax could select.

    Accuracy with the default 16 nodes, measured against independent references (a dense
    breakpoint quadrature, and 40- and 50-digit arithmetic) on seeded sweeps that place `V*` and
    the knees close to the kinks: relative error below 1e-8 wherever EI >= 1e-250, worst about
    1e-11 for identity targets and about 3e-9 for log and logit targets. The exception is
    floating-point conditioning, not the quadrature: when `V*` lies within about 1e-7 (relative)
    of a kink and the posterior concentrates there, rounding in `obs (1 - t u)` limits the
    result to between 1e-8 and 3e-8.
    """
    targets = list(targets)
    transforms = list(transforms)
    _check_targets(targets, transforms)
    T = len(targets)

    mu = np.asarray(mu, dtype=float)
    sd = np.asarray(sd, dtype=float)
    if mu.ndim == 1 and T == 1:
        mu = mu.reshape(-1, 1)
    if sd.ndim == 1 and T == 1:
        sd = sd.reshape(-1, 1)
    if mu.ndim != 2 or mu.shape[1] != T or sd.shape != mu.shape:
        raise ValueError(f"mu and sd must both be (n, {T}); got {mu.shape} and {sd.shape}")
    if V_star is None or not np.isfinite(V_star):
        raise ValueError(f"V_star is {V_star!r}; the incumbent must be a finite V observed on "
                         f"the physics model. With no viable observation, use the cold-start "
                         f"path instead of expected improvement.")
    if int(n_nodes) < 1:
        raise ValueError(f"n_nodes is {n_nodes}; need at least 1 node per segment")
    if not np.all(np.isfinite(mu)):
        raise ValueError("mu has non-finite entries; the posterior mean must be finite")
    if not (np.all(np.isfinite(sd)) and np.all(sd >= 0)):
        raise ValueError("sd must be finite and >= 0 everywhere")

    n = mu.shape[0]
    V_star = float(V_star)
    if V_star <= 0 or n == 0:
        return np.zeros(n)

    obs = np.array([t.observed for t in targets], dtype=float)
    unc = np.array([t.uncertainty for t in targets], dtype=float)
    sd = np.maximum(sd, sd_floor(targets, transforms)[None, :])
    nodes, weights = np.polynomial.legendre.leggauss(int(n_nodes))

    n_breaks = _n_breakpoints(obs, unc, transforms, V_star)
    step = max(1, int(_EI_CHUNK_ELEMENTS // ((n_breaks - 1) * len(nodes))))

    out = np.empty(n)
    for a0 in range(0, n, step):
        a1 = min(a0 + step, n)
        out[a0:a1] = _ei_chunk(mu[a0:a1], sd[a0:a1], obs, unc, transforms, V_star,
                               nodes, weights)
    if not np.all(np.isfinite(out)):
        bad = np.flatnonzero(~np.isfinite(out))
        raise RuntimeError(
            f"expected improvement is non-finite for {len(bad)} of {n} candidates (first rows "
            f"{bad[:5].tolist()}); the inputs passed every check, so this is a numerical defect "
            f"in the integral, not a value to rank.")
    return out


def _kinks(obs_i: float, unc_i: float, transform: str) -> List[Tuple[float, int]]:
    """`(t, side)` where a band edge reaches the boundary of the transform's domain.

    `side` is the side of `t` on which the band probability depends on `log|t - kink|`, and so the
    side a geometric grading approaches from (-1 below, +1 above):

      * `1/u` (log, logit), side -1: the lower edge reaches 0;
      * `(1/obs - 1)/u` (logit, observed < 1), side -1: the upper edge reaches 1;
      * `(1 - 1/obs)/u` (logit, observed >= 1), side +1: the lower edge reaches 1, below which the
        band lies outside (0, 1) and has probability 0. At observed exactly 1 this is `t = 0`.
    """
    if transform == "identity":
        return []
    ks = [(1.0 / unc_i, -1)]
    if transform == "logit":
        if obs_i < 1.0:
            ks.append(((1.0 / obs_i - 1.0) / unc_i, -1))
        else:
            ks.append(((1.0 - 1.0 / obs_i) / unc_i, +1))
    return ks


def _graded_kinks(obs_i: float, unc_i: float, transform: str,
                  V_star: float) -> List[Tuple[float, int]]:
    """The kinks that get a geometric grading: those with a graded point inside `(0, V*)`."""
    return [(k, side) for k, side in _kinks(obs_i, unc_i, transform)
            if (side < 0 and k > 0 and (1.0 - _KINK_GRADING_RATIO) * k < V_star)
            or (side > 0 and k + _KINK_GRADING_RATIO ** _KINK_GRADING_LEVELS / unc_i < V_star)]


def _kink_grading(kink: float, side: int, unc_i: float) -> List[float]:
    """Graded points toward a kink from its singular side: `kink (1 - r^j)` from below, and
    `kink + r^j / u` from above, `r = _KINK_GRADING_RATIO`, `j = 1.._KINK_GRADING_LEVELS`. From
    above, `1/u` is the length over which the band edge moves by one observation."""
    js = range(1, _KINK_GRADING_LEVELS + 1)
    if side < 0:
        return [kink * (1.0 - _KINK_GRADING_RATIO ** j) for j in js]
    return [kink + _KINK_GRADING_RATIO ** j / unc_i for j in js]


def _n_breakpoints(obs, unc, transforms, V_star) -> int:
    """Column count of `_breakpoints` for these targets and this `V*`."""
    n = 2
    for i, tr in enumerate(transforms):
        n += 2 * len(_KNEE_MULTIPLES) - 1 + len(_TAIL_MULTIPLES) + len(_kinks(obs[i], unc[i], tr))
        if tr != "identity":
            n += 2 * (len(_KNEE_MULTIPLES) - 1) + len(_TAIL_MULTIPLES)
            n += _KINK_GRADING_LEVELS * len(_graded_kinks(obs[i], unc[i], tr, V_star))
    return n


def _fitted_edge(x: np.ndarray, transform: str) -> np.ndarray:
    """Forward transform of a native band edge inside the transform's domain."""
    if transform == "log":
        return np.log(x)
    return np.log(x) - np.log1p(-x)


def _native(Y: np.ndarray, transform: str) -> np.ndarray:
    """Inverse transform of a fitted-space value (log or logit)."""
    return np.exp(Y) if transform == "log" else expit(Y)


def _breakpoints(mu, sd, obs, unc, transforms, V_star) -> np.ndarray:
    """(m, B) sorted segment boundaries in [0, V*] for m candidates."""
    m = mu.shape[0]
    cols = [np.zeros(m), np.full(m, V_star)]
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        for i, tr in enumerate(transforms):
            scale = unc[i] * obs[i]
            if tr == "identity":
                y = mu[:, i]
                dy = sd[:, i]
            elif tr == "log":
                y = np.exp(mu[:, i])
                dy = y * sd[:, i]
            else:
                y = expit(mu[:, i])
                dy = y * (1.0 - y) * sd[:, i]
            k = np.abs(y - obs[i]) / scale
            w = dy / scale
            for c in _KNEE_MULTIPLES:
                cols.append(k + c * w)
                if c > 0:
                    cols.append(k - c * w)
            z = (k - V_star) / w
            above = k > V_star
            for c in _TAIL_MULTIPLES:
                cols.append(np.where(above, V_star - c * w / np.maximum(1.0, z), V_star))
            for kink, _ in _kinks(obs[i], unc[i], tr):
                cols.append(np.full(m, kink))
            if tr == "identity":
                continue

            # The same knee and tail points placed in the fitted space, where the posterior is
            # Gaussian: t at which a band edge crosses mu +/- (multiple) * sd.
            for c in _KNEE_MULTIPLES[1:]:
                for sign in (1.0, -1.0):
                    cols.append(np.abs(_native(mu[:, i] + sign * c * sd[:, i], tr) - obs[i])
                                / scale)
            side = np.sign(y - obs[i])                  # +1: the upper edge binds; -1: the lower
            edge = obs[i] * (1.0 + side * V_star * unc[i])
            z_fit = np.abs(_fitted_edge(edge, tr) - mu[:, i]) / sd[:, i]
            for c in _TAIL_MULTIPLES:
                crossing = _native(mu[:, i] - side * (z_fit + c / np.maximum(1.0, z_fit))
                                   * sd[:, i], tr)
                cols.append(np.where(above, side * (crossing - obs[i]) / scale, V_star))
            for kink, approach in _graded_kinks(obs[i], unc[i], tr, V_star):
                for point in _kink_grading(kink, approach, unc[i]):
                    cols.append(np.full(m, point))
        bp = np.stack(cols, axis=1)
    bp = np.where(np.isfinite(bp), bp, V_star)
    return np.sort(np.clip(bp, 0.0, V_star), axis=1)


def _ei_chunk(mu, sd, obs, unc, transforms, V_star, nodes, weights) -> np.ndarray:
    bp = _breakpoints(mu, sd, obs, unc, transforms, V_star)
    half = 0.5 * (bp[:, 1:] - bp[:, :-1])                      # (m, S)
    mid = 0.5 * (bp[:, 1:] + bp[:, :-1])
    m, S = half.shape
    t = (mid[:, :, None] + half[:, :, None] * nodes[None, None, :]).reshape(m, -1)
    prod = np.ones_like(t)
    for i, tr in enumerate(transforms):
        lo = obs[i] * (1.0 - t * unc[i])
        hi = obs[i] * (1.0 + t * unc[i])
        prod *= band_probability(mu[:, i, None], sd[:, i, None], lo, hi, tr)
    per_segment = (prod.reshape(m, S, len(nodes)) * weights[None, None, :]).sum(axis=2)
    return (per_segment * half).sum(axis=1)


# =============================================================================
# Incumbent and alignment guards
# =============================================================================

def incumbent(V, viable) -> Tuple[float, int]:
    """`(V*, index)`: the lowest finite `V` over viable rows, lowest index on ties.

    Rows labelled non-viable never set the incumbent. With no viable finite row there is no
    incumbent at all, which is a ValueError for the caller's cold-start path to handle.
    """
    V = np.asarray(V, dtype=float).ravel()
    viable = np.asarray(viable, dtype=bool).ravel()
    if len(V) != len(viable):
        raise ValueError(f"V has {len(V)} rows but viable has {len(viable)}")
    ok = np.flatnonzero(viable & np.isfinite(V))
    if len(ok) == 0:
        raise ValueError("no viable row with a finite V, so there is no incumbent V*; use the "
                         "cold-start path.")
    j = int(ok[np.argmin(V[ok])])
    return float(V[j]), j


def check_alignment(spec, targets: Sequence[Target]) -> None:
    """Refuse a surrogate spec whose targets do not match the objective's, by name and band.

    `spec.target_names` must equal `[t.name for t in targets]` in order: the posterior columns
    are matched to bands by position, so a reordering would score each target against another's
    band. Wherever the spec declares `lower`/`upper`, it must equal `Target.lo`/`Target.hi` to a
    relative 1e-9.
    """
    got = list(spec.target_names)
    want = [t.name for t in targets]
    if got != want:
        raise ValueError(f"surrogate spec targets {got} do not match the objective targets "
                         f"{want} (names and order must agree); rebuild the spec from the same "
                         f"target list.")
    for ts, t in zip(spec.targets, targets):
        for side, declared, band in (("lower", ts.lower, t.lo), ("upper", ts.upper, t.hi)):
            if declared is not None and not math.isclose(float(declared), band,
                                                          rel_tol=1e-9, abs_tol=0.0):
                raise ValueError(
                    f"target {t.name!r}: spec {side} {declared} differs from the objective's "
                    f"band edge {band} (observed {t.observed}, uncertainty {t.uncertainty}); "
                    f"the spec and targets.yaml disagree about the band.")


# =============================================================================
# Unit cube
# =============================================================================

def _bounds(lower, upper, p: int) -> Tuple[np.ndarray, np.ndarray]:
    lower = np.asarray(lower, dtype=float).ravel()
    upper = np.asarray(upper, dtype=float).ravel()
    if len(lower) != p or len(upper) != p:
        raise ValueError(f"bounds have {len(lower)}/{len(upper)} entries for {p} columns")
    if not (np.all(np.isfinite(lower)) and np.all(np.isfinite(upper))):
        raise ValueError("bounds must be finite")
    if np.any(upper <= lower):
        bad = np.flatnonzero(upper <= lower)
        raise ValueError(f"upper <= lower for column(s) {bad[:5].tolist()}; a fixed parameter "
                         f"has no unit-cube coordinate, so drop it from the search.")
    return lower, upper


def native_to_unit(X, lower, upper) -> np.ndarray:
    """`(X - lower) / (upper - lower)`, columnwise."""
    X = np.asarray(X, dtype=float)
    lower, upper = _bounds(lower, upper, X.shape[-1])
    return (X - lower) / (upper - lower)


def unit_to_native(U, lower, upper) -> np.ndarray:
    """`lower + U * (upper - lower)`, columnwise: the linear map a Sobol' design is sampled with."""
    U = np.asarray(U, dtype=float)
    lower, upper = _bounds(lower, upper, U.shape[-1])
    return lower + U * (upper - lower)


# =============================================================================
# Candidates
# =============================================================================

def sobol_candidates(p: int, n: int, seed) -> np.ndarray:
    """(n, p) scrambled Sobol' points in the unit cube. `n` must be a power of two, the sizes at
    which a Sobol' sequence keeps its balance properties."""
    from scipy.stats import qmc

    p, n = int(p), int(n)
    if p < 1:
        raise ValueError(f"p is {p}; need at least one dimension")
    if n < 1 or (n & (n - 1)) != 0:
        raise ValueError(f"n is {n}; a Sobol' scan must have a power-of-two size (for example "
                         f"{1 << max(0, n.bit_length() - 1)} or {1 << max(0, n.bit_length())})")
    return qmc.Sobol(d=p, scramble=True, seed=seed).random(n)


def reflect_unit(U) -> np.ndarray:
    """Fold values into [0, 1] by reflection at the faces (period 2); the identity inside.

    Clipping would put every overshooting coordinate exactly on a bound, which piles candidates
    onto the faces and corners; reflection keeps the perturbation's distance from the face.
    """
    U = np.asarray(U, dtype=float)
    if not np.all(np.isfinite(U)):
        raise ValueError("reflect_unit needs finite values")
    r = np.mod(U, 2.0)
    return np.where(r > 1.0, 2.0 - r, r)


def local_candidates(U_obs, V_obs, viable_obs, n_total: int, k: int = 10,
                     scales: Sequence[float] = (0.01, 0.03, 0.1),
                     seed=0) -> Tuple[np.ndarray, np.ndarray]:
    """Gaussian perturbations of the best viable rows, reflected into the unit cube.

    Centres are the `k` viable rows with the lowest finite `V` (stable order). Each centre gets
    `ceil(n_total / (k_used * len(scales)))` draws at each unit-cube sd in `scales`, so the set
    holds at least `n_total` rows. Returns `(U, labels)` with one label per row, `local_sd<scale>`.
    Both are empty when no row is viable.
    """
    U_obs = np.atleast_2d(np.asarray(U_obs, dtype=float))
    V_obs = np.asarray(V_obs, dtype=float).ravel()
    viable = np.asarray(viable_obs, dtype=bool).ravel()
    n, p = U_obs.shape
    if len(V_obs) != n or len(viable) != n:
        raise ValueError(f"U_obs has {n} rows, V_obs {len(V_obs)}, viable_obs {len(viable)}")
    if int(n_total) < 1 or int(k) < 1:
        raise ValueError(f"n_total ({n_total}) and k ({k}) must be at least 1")
    scales = [float(s) for s in scales]
    if not scales or not all(np.isfinite(s) and s > 0 for s in scales):
        raise ValueError(f"scales {scales} must be a non-empty list of positive numbers")

    ok = np.flatnonzero(viable & np.isfinite(V_obs))
    if len(ok) == 0:
        return np.empty((0, p)), np.array([], dtype=str)
    centres = U_obs[ok[np.argsort(V_obs[ok], kind="stable")[:int(k)]]]
    per = int(math.ceil(int(n_total) / (len(centres) * len(scales))))

    rng = np.random.default_rng(seed)
    blocks, labels = [], []
    for s in scales:
        base = np.repeat(centres, per, axis=0)
        blocks.append(reflect_unit(base + s * rng.standard_normal(base.shape)))
        labels.extend([f"local_sd{s:g}"] * len(base))
    return np.vstack(blocks), np.array(labels)


# =============================================================================
# Distances
# =============================================================================

def _pairwise(A: np.ndarray, B: np.ndarray, metric: str) -> np.ndarray:
    """(len(A), len(B)) distances; the caller bounds len(A) * len(B) * p."""
    diff = A[:, None, :] - B[None, :, :]
    if metric == "linf":
        return np.abs(diff).max(axis=2)
    return np.linalg.norm(diff, axis=2)


def min_distance(A, B, metric: str = "linf", budget: float = _DISTANCE_BUDGET) -> np.ndarray:
    """(len(A),) distance from each row of A to its nearest row of B; +inf when B is empty.

    Chunked over both A and B so that no pairwise-difference array holds more than `budget`
    float64 elements, whatever the dimension. `B` must be an array: pass an empty `(0, p)` array
    for no rows, never None. Non-finite coordinates in either are refused.
    """
    if metric not in ("linf", "euclidean"):
        raise ValueError(f"metric {metric!r} not in ('linf', 'euclidean')")
    if A is None or B is None:
        raise ValueError("min_distance needs arrays for A and B, got None; pass an empty (0, p) "
                         "array for no rows.")
    A = np.atleast_2d(np.asarray(A, dtype=float))
    p = A.shape[1]
    B = np.asarray(B, dtype=float)
    B = B.reshape(0, p) if B.size == 0 else np.atleast_2d(B)
    if B.shape[1] != p:
        raise ValueError(f"A has {p} columns but B has {B.shape[1]}")
    if not (np.all(np.isfinite(A)) and np.all(np.isfinite(B))):
        raise ValueError("min_distance needs finite coordinates in A and B; a NaN row has no "
                         "distance to anything.")
    out = np.full(len(A), np.inf)
    if len(A) == 0 or len(B) == 0:
        return out
    if budget < p:
        raise ValueError(f"budget {budget} is below the {p} elements of a single row pair")
    step_b = max(1, min(len(B), int(budget // p)))
    step_a = max(1, int(budget // (step_b * p)))
    for a0 in range(0, len(A), step_a):
        a1 = min(a0 + step_a, len(A))
        for b0 in range(0, len(B), step_b):
            b1 = min(b0 + step_b, len(B))
            d = _pairwise(A[a0:a1], B[b0:b1], metric)
            np.minimum(out[a0:a1], d.min(axis=1), out=out[a0:a1])
    return out


def density_radius(U, k: int = 10, max_rows: int = 2048, seed=0) -> float:
    """Median L-inf distance from a candidate to its k-th nearest other candidate.

    The median is taken over a seeded subsample of at most `max_rows` query rows, and each query's
    neighbours are searched among ALL candidates, so the result estimates the full set's radius
    at a cost linear in the candidate count. `k` is reduced to `n - 1` when fewer rows are
    available.
    """
    U = np.atleast_2d(np.asarray(U, dtype=float))
    n, p = U.shape
    if n < 2:
        raise ValueError(f"density_radius needs at least 2 candidates, got {n}")
    if int(k) < 1 or int(max_rows) < 1:
        raise ValueError(f"k ({k}) and max_rows ({max_rows}) must be >= 1")
    if not np.all(np.isfinite(U)):
        raise ValueError("density_radius needs finite candidate coordinates")
    rows = (np.arange(n) if n <= int(max_rows)
            else np.sort(np.random.default_rng(seed).choice(n, int(max_rows), replace=False)))
    kk = min(int(k), n - 1)
    kth = np.empty(len(rows))
    step = max(1, int(_DISTANCE_BUDGET // (n * p)))
    for a0 in range(0, len(rows), step):
        a1 = min(a0 + step, len(rows))
        d = _pairwise(U[rows[a0:a1]], U, "linf")
        d[np.arange(a1 - a0), rows[a0:a1]] = np.inf
        kth[a0:a1] = np.partition(d, kk - 1, axis=1)[:, kk - 1]
    return float(np.median(kth))


# =============================================================================
# Batch pickers
# =============================================================================

def maximin_batch(U_cand, U_anchor, q: int, weights=None, admissible=None) -> np.ndarray:
    """Greedy weighted maximin: indices into `U_cand`, at most `q`.

    Each step picks the admissible candidate maximising `weights * (Euclidean distance to the
    nearest anchor or earlier pick)`, lowest index on ties. With no anchors the first pick is the
    admissible candidate with the largest weight. Returns fewer than `q` indices when the
    admissible candidates run out.
    """
    U = np.atleast_2d(np.asarray(U_cand, dtype=float))
    n, p = U.shape
    q = int(q)
    if q < 0:
        raise ValueError(f"q is {q}; must be >= 0")
    w = np.ones(n) if weights is None else np.asarray(weights, dtype=float).ravel()
    if len(w) != n:
        raise ValueError(f"weights has {len(w)} entries for {n} candidates")
    if not (np.all(np.isfinite(w)) and np.all(w >= 0)):
        raise ValueError("weights must be finite and >= 0")
    adm = (np.ones(n, dtype=bool) if admissible is None
           else np.asarray(admissible, dtype=bool).ravel().copy())
    if len(adm) != n:
        raise ValueError(f"admissible has {len(adm)} entries for {n} candidates")
    if U_anchor is None:
        raise ValueError(f"U_anchor is None; pass np.empty((0, {p})) when there are no anchors.")

    dmin = min_distance(U, U_anchor, metric="euclidean")
    have_anchor = bool(np.isfinite(dmin).any()) if n else False
    picks: List[int] = []
    while len(picks) < q and adm.any():
        score = w if (not picks and not have_anchor) else w * dmin
        j = int(np.argmax(np.where(adm, score, -np.inf)))
        picks.append(j)
        adm[j] = False
        dmin = np.minimum(dmin, np.linalg.norm(U - U[j], axis=1))
    return np.array(picks, dtype=int)


def local_penalisation_batch(Z, alpha, q: int,
                             min_separation: float = 0.0) -> Tuple[np.ndarray, int]:
    """Greedy batch by local penalisation: `(indices, shortfall)`.

    Take the argmax of `alpha`, multiply every candidate's alpha by
    `1 - exp(-0.5 (d / max(median(d), 1e-9))^2)` with `d` the Euclidean distance in `Z` to the
    pick, and repeat. The pick, and every candidate within `min_separation` (Euclidean in `Z`,
    inclusive, so the default 0 also removes exact duplicates of the pick), is marked taken AFTER
    the penalty, which is what keeps a taken candidate from turning `-inf * 0` into a NaN that an
    argmax would select again. Stops when no finite untaken candidate remains;
    `shortfall = q - len(indices)`.

    `alpha` entries of `-inf` mark inadmissible candidates. NaN or `+inf` is refused, and so is a
    non-finite coordinate in `Z`: its distance to a pick is NaN, which makes the median and then
    every penalised alpha NaN, and the picks would fall back to index order.
    """
    Z = np.atleast_2d(np.asarray(Z, dtype=float))
    a = np.asarray(alpha, dtype=float).ravel().copy()
    q = int(q)
    if len(a) != len(Z):
        raise ValueError(f"alpha has {len(a)} entries for {len(Z)} candidates")
    if not np.all(np.isfinite(Z)):
        bad = np.flatnonzero(~np.all(np.isfinite(Z), axis=1))
        raise ValueError(f"Z has non-finite coordinates in {len(bad)} row(s) (first "
                         f"{bad[:5].tolist()}); every candidate needs a finite position, so drop "
                         f"or repair those rows before batching.")
    if np.isnan(a).any() or np.isposinf(a).any():
        raise ValueError(f"alpha has {int(np.isnan(a).sum())} NaN and "
                         f"{int(np.isposinf(a).sum())} +inf entries; an acquisition value must "
                         f"be finite, or -inf for an inadmissible candidate.")
    if q < 0:
        raise ValueError(f"q is {q}; must be >= 0")
    if not (np.isfinite(min_separation) and min_separation >= 0):
        raise ValueError(f"min_separation is {min_separation}; must be finite and >= 0")
    return _penalised_picks(Z, a, q, float(min_separation), "euclidean")


def _penalised_picks(Z: np.ndarray, a: np.ndarray, q: int, min_separation: float,
                     separation: str) -> Tuple[np.ndarray, int]:
    """The loop of `local_penalisation_batch` on validated inputs; `a` is overwritten.

    The penalty always uses the Euclidean distance in `Z`. `separation` is the metric the
    exclusion radius `min_separation` is measured in: "euclidean" (the public picker) or "linf"
    (the believe fallback of `propose_batch`, whose diversity guard is an L-inf radius).
    """
    alive = np.isfinite(a)
    picks: List[int] = []
    while len(picks) < q and alive.any():
        a[~alive] = -np.inf
        i = int(np.argmax(a))
        picks.append(i)
        d = np.linalg.norm(Z - Z[i], axis=1)
        with np.errstate(invalid="ignore"):          # -inf * 0 on taken entries, masked below
            a *= 1.0 - np.exp(-0.5 * (d / max(np.median(d), 1e-9)) ** 2)
        alive[i] = False
        if separation == "linf":
            alive &= np.max(np.abs(Z - Z[i]), axis=1) > min_separation
        else:
            alive &= d > min_separation
    return np.array(picks, dtype=int), q - len(picks)


# =============================================================================
# Scoring and the batch proposal
# =============================================================================

#: Candidate rows per posterior evaluation in `score_candidates`.
_SCORE_CHUNK_ROWS = 2048

#: Unit-cube tolerance for an observed row lying on a parameter bound.
_BOUND_TOL = 1e-9

#: Values of `Proposal.status`.
STATUSES = ("ok", "cold_start", "degenerate", "no_viable_probability", "all_out_of_hull")


def _require_search_model(model) -> None:
    """Refuse anything but a fitted S1Surrogate whose every regressor has a posterior std."""
    from models.surrogate.tiers import S1Surrogate

    if not isinstance(model, S1Surrogate):
        raise ValueError(f"model is a {type(model).__name__}; propose_batch needs a fitted "
                         f"S1Surrogate, or None for a cold start without a surrogate.")
    if not getattr(model, "fitted", False):
        raise ValueError("the S1Surrogate is not fitted; fit it on the observed rows first.")
    for t, lr in zip(model.spec.targets, model._models):
        if not getattr(lr, "posterior_std", False):
            family = getattr(lr, "name", type(lr).__name__)
            raise ValueError(
                f"target {t.name!r}: learner family {family!r} has no predictive posterior std. "
                f"The acquisition integrates the regressor's std as a Gaussian posterior "
                f"(docs/42 section 3), so only a family with posterior_std=True may drive a "
                f"search; refit the S1Surrogate with learner='gp'.")


def score_candidates(model, targets: Sequence[Target], U, lower, upper,
                     V_star: float) -> Dict[str, np.ndarray]:
    """Everything a pick is recorded with, for unit-cube candidates `U` under one surrogate.

    Returns arrays over the rows of `U`:

      * `alpha = p_viable * ei`, the acquisition;
      * `ei`, the expected improvement on `V` against `V_star` (`expected_improvement`);
      * `p_viable`, the surrogate's P(viable);
      * `hull_distance` and `in_hull`, the extrapolation gate's verdict;
      * `predicted` (n, T), the posterior mean mapped back to native units;
      * `V_mean` and `binding`, the violation of `predicted` and the name of the target that sets
        it. `V_mean` is `V` at the posterior mean, an optimistic plug-in, not `E[V]`;
      * `sd_ratio` (n, T), the posterior sd over the std of that target's training values
        (`model.target_sd_`), both in the fitted space: near 1, the prediction is at prior
        variance and the pick is driven by uncertainty, not by the mean.

    Transforms are read from `model.spec`, whose targets must align with `targets`
    (`check_alignment`). A non-finite alpha is a RuntimeError.
    """
    from models.surrogate.base import invert_transform

    check_alignment(model.spec, targets)
    targets = list(targets)
    transforms = [ts.transform for ts in model.spec.targets]
    U = np.asarray(U, dtype=float)
    if U.ndim != 2:
        raise ValueError(f"U must be (n, p); got shape {U.shape}")
    native = unit_to_native(U, lower, upper)
    n, T = len(U), len(targets)

    mu = np.empty((n, T))
    sd = np.empty((n, T))
    for a0 in range(0, n, _SCORE_CHUNK_ROWS):
        a1 = min(a0 + _SCORE_CHUNK_ROWS, n)
        mu[a0:a1], sd[a0:a1] = model.posterior(native[a0:a1])
    ei = expected_improvement(mu, sd, targets, transforms, V_star)
    if n:
        p_viable = np.asarray(model.viability(native), dtype=float)
        hull_distance, in_hull = model.hull(native)
    else:
        p_viable, hull_distance, in_hull = np.empty(0), np.empty(0), np.empty(0, dtype=bool)
    alpha = p_viable * ei
    if not np.all(np.isfinite(alpha)):
        bad = np.flatnonzero(~np.isfinite(alpha))
        raise RuntimeError(f"alpha is non-finite for {len(bad)} of {n} candidates (first rows "
                           f"{bad[:5].tolist()}); check P(viable) from the classifier.")

    predicted = np.empty((n, T))
    for j, tr in enumerate(transforms):
        predicted[:, j] = invert_transform(mu[:, j], tr)
    obs = np.array([t.observed for t in targets], dtype=float)
    unc = np.array([t.uncertainty for t in targets], dtype=float)
    with np.errstate(over="ignore", invalid="ignore"):
        v = np.abs(predicted - obs) / (unc * obs)
    V_mean = v.max(axis=1) if n else np.empty(0)
    names = np.array([t.name for t in targets], dtype=object)
    binding = names[np.argmax(v, axis=1)] if n else np.empty(0, dtype=object)

    tsd = getattr(model, "target_sd_", None)
    if tsd is None:
        sd_ratio = np.full((n, T), np.nan)
    else:
        tsd = np.asarray(tsd, dtype=float)
        with np.errstate(divide="ignore", invalid="ignore"):
            sd_ratio = np.where(tsd > 0, sd / np.where(tsd > 0, tsd, 1.0), np.nan)
    return {"alpha": alpha, "ei": ei, "p_viable": p_viable,
            "hull_distance": np.asarray(hull_distance, dtype=float),
            "in_hull": np.asarray(in_hull, dtype=bool), "predicted": predicted,
            "V_mean": V_mean, "binding": binding, "sd_ratio": sd_ratio}


@dataclass
class Proposal:
    """A batch of proposed parameter sets, and what is needed to read it.

    Per-pick arrays, in pick order (length `q'`, the number of picks, or `(q', p)` / `(q', T)`):
    `unit` and `native` coordinates; `alpha`, `ei`, `p_viable`, `hull_distance`, `in_hull`,
    `predicted`, `V_mean`, `binding` and `sd_ratio` as `score_candidates` gives them, from the
    model that chose the pick; `pick_source` ("argmax", "maximin" or "local_penalisation");
    `candidate_set` ("sobol" or a `local_sd<scale>` label); and `V_star_used`, the incumbent the
    pick was scored against, always the physics `V*`. A cold-start pick is chosen without a
    posterior: its `alpha`, `ei`, `hull_distance`, `V_mean`, `predicted` and `sd_ratio` are NaN,
    `binding` is "", `in_hull` is None (no hull applies), and `p_viable` is the weight the
    maximin used, NaN for plain maximin.

    `status` is one of `STATUSES`; `batching` says what ran and where any switch fired. Status
    "ok" with batching "none" and no picks means every candidate lay within `min_separation` of
    an observed row, so no picker ran.
    `counts` holds `n_candidates`, `n_too_close` (within `min_separation` of an observed row),
    `n_out_of_hull` (over all candidates) and `n_admissible`; `shortfall = q - q'`.
    `V_star_index` is the incumbent's row in the observations, None when there is no incumbent
    (and `V_star` is then NaN).
    """

    unit: np.ndarray
    native: np.ndarray
    alpha: np.ndarray
    ei: np.ndarray
    p_viable: np.ndarray
    hull_distance: np.ndarray
    in_hull: np.ndarray
    predicted: np.ndarray
    V_mean: np.ndarray
    binding: np.ndarray
    pick_source: np.ndarray
    candidate_set: np.ndarray
    V_star_used: np.ndarray
    sd_ratio: np.ndarray
    V_star: float
    V_star_index: Optional[int]
    status: str
    batching: str
    counts: Dict[str, int]
    shortfall: int
    r_sep: float
    seed: int
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)


def _scored_pick(sc: Dict[str, np.ndarray], k: int, unit: np.ndarray, candidate_set: str,
                 source: str, V_star_used: float) -> Dict[str, Any]:
    return {"unit": unit, "alpha": float(sc["alpha"][k]), "ei": float(sc["ei"][k]),
            "p_viable": float(sc["p_viable"][k]),
            "hull_distance": float(sc["hull_distance"][k]), "in_hull": bool(sc["in_hull"][k]),
            "predicted": sc["predicted"][k], "V_mean": float(sc["V_mean"][k]),
            "binding": str(sc["binding"][k]), "sd_ratio": sc["sd_ratio"][k],
            "candidate_set": candidate_set, "pick_source": source,
            "V_star_used": float(V_star_used)}


def _assemble(picks: List[Dict[str, Any]], p: int, T: int, lower, upper, q: int,
              **fields: Any) -> Proposal:
    m = len(picks)

    def num(key):
        return np.array([pk[key] for pk in picks], dtype=float)

    def obj(key):
        return np.array([pk[key] for pk in picks] if m else [], dtype=object)

    unit = np.array([pk["unit"] for pk in picks], dtype=float).reshape(m, p)
    return Proposal(
        unit=unit, native=unit_to_native(unit, lower, upper), alpha=num("alpha"), ei=num("ei"),
        p_viable=num("p_viable"), hull_distance=num("hull_distance"), in_hull=obj("in_hull"),
        predicted=np.array([pk["predicted"] for pk in picks], dtype=float).reshape(m, T),
        V_mean=num("V_mean"), binding=obj("binding"), pick_source=obj("pick_source"),
        candidate_set=obj("candidate_set"), V_star_used=num("V_star_used"),
        sd_ratio=np.array([pk["sd_ratio"] for pk in picks], dtype=float).reshape(m, T),
        shortfall=int(q) - m, **fields)


def _classifier_viability(clf, X: np.ndarray) -> np.ndarray:
    """P(viable) from a fitted classifier, with the single-class guard of
    `S1Surrogate.viability`: `classes_` of `[1]` gives ones and `[0]` zeros."""
    classes = list(np.asarray(clf.classes_).ravel())
    if len(classes) == 1 and classes[0] == 1:
        return np.ones(len(X))
    if len(classes) == 1 and classes[0] == 0:
        return np.zeros(len(X))
    if 1 not in classes:
        raise ValueError(f"the viability classifier's classes_ {classes} contain no label 1; fit "
                         f"it on 0/1 viability labels.")
    return np.asarray(clf.predict_proba(X), dtype=float)[:, classes.index(1)]


def _feasibility_maximin(U: np.ndarray, anchors: np.ndarray, q: int, weights,
                         admissible: np.ndarray) -> Tuple[np.ndarray, int]:
    """`(indices, n_filled)`: greedy maximin weighted by P(viable) over the candidates with
    P(viable) > 0, then plain maximin for any picks still missing, so a weight of zero never
    turns into an argmax over zeros."""
    if weights is None:
        return maximin_batch(U, anchors, q, admissible=admissible), 0
    w = np.asarray(weights, dtype=float)
    first = maximin_batch(U, anchors, q, weights=w, admissible=admissible & (w > 0))
    if len(first) == q:
        return first, 0
    rest = admissible.copy()
    rest[first] = False
    fill = maximin_batch(U, np.vstack([anchors, U[first]]), q - len(first), admissible=rest)
    return np.concatenate([first, fill]).astype(int), len(fill)


def _scan_vs_local(sc: Dict[str, np.ndarray], cset: np.ndarray,
                   admissible: np.ndarray) -> Dict[str, Any]:
    """Best alpha, its EI and V_mean over the admissible candidates of each set, and each set's
    best alpha relative to the Sobol' scan's: above 1, the scan is not finding the maximum."""
    local_labels = list(dict.fromkeys(str(c) for c in cset if str(c) != "sobol"))
    is_local = np.array([str(c) != "sobol" for c in cset], dtype=bool)
    sets: Dict[str, Dict[str, Any]] = {}
    for label in ["sobol"] + local_labels + ["local"]:
        mask = admissible & (is_local if label == "local" else (cset == label))
        if not mask.any():
            sets[label] = {"n_admissible": 0, "best_index": None, "best_alpha": float("nan"),
                           "best_ei": float("nan"), "best_V_mean": float("nan")}
            continue
        j = int(np.argmax(np.where(mask, sc["alpha"], -np.inf)))
        sets[label] = {"n_admissible": int(mask.sum()), "best_index": j,
                       "best_alpha": float(sc["alpha"][j]), "best_ei": float(sc["ei"][j]),
                       "best_V_mean": float(sc["V_mean"][j])}
    scan = sets["sobol"]["best_alpha"]
    for entry in sets.values():
        best = entry["best_alpha"]
        if not (np.isfinite(scan) and np.isfinite(best)):
            entry["ratio_to_scan"] = float("nan")
        elif scan > 0:
            entry["ratio_to_scan"] = best / scan
        else:
            entry["ratio_to_scan"] = float("inf") if best > 0 else float("nan")
    return {"sets": sets, "ratio_local_to_scan": sets["local"]["ratio_to_scan"]}


def propose_batch(model, targets: Sequence[Target], lower, upper, X_obs, V_obs, viable_obs,
                  q: int, n_cand: int = 4096, seed: int = 0, local_k: int = 10,
                  local_scales: Sequence[float] = (0.01, 0.03, 0.1),
                  min_separation: float = 1e-6, r_sep: Optional[float] = None,
                  degenerate_rel: float = 1e-6, min_viable_acquisition: int = 4) -> Proposal:
    """Choose up to `q` parameter sets to run next: a `Proposal`.

    `model` is an S1Surrogate fitted with a GP on the observations, or None. `X_obs` (n, p)
    holds EVERY observed row in native units, failures included, so no run is proposed twice;
    `V_obs` is its violation (NaN where absent) and `viable_obs` its viability label. `lower` and
    `upper` define the unit cube the search runs in. A row counts as a viable observation when
    it is labelled viable AND has a finite `V`.

    Paths, recorded in `status` and `batching`:

      * **cold start** (`status` "cold_start"), from the Sobol' scan alone, with admissibility by
        `min_separation` only and no hull gate. With no surrogate or fewer than 2 viable
        observations: greedy maximin weighted by P(viable) from a classifier fitted here on
        every observed row with `viable_obs` as its labels (as `S1Surrogate` fits its own), when
        both labels occur, and plain maximin otherwise. A viable row whose `V` is not finite is
        therefore a viable label for the classifier, though it is not a viable observation.
        With a surrogate and 2 to `min_viable_acquisition - 1` viable observations: maximin
        weighted by the surrogate's P(viable).
      * **acquisition**. `V*` is the best viable observed `V`, and every regressor must have
        trained on that row. Candidates are the scan plus `local_candidates` around the best
        viable rows; the inadmissible ones are within `min_separation` (L-inf) of an observed
        row or outside the hull gate. Every candidate is scored once (`score_candidates`), which
        also gives the scan-versus-local diagnostic. Then, for j = 1..q, the admissible argmax
        of alpha under a Kriging-believer copy conditioned on the earlier picks (`V*` fixed),
        dropping every candidate within `r_sep` or `min_separation` (L-inf) of each pick.
        `r_sep` defaults to `density_radius` of the admissible candidates.
      * the switches: at pick 1, P(viable) zero everywhere ("no_viable_probability") or alpha
        <= 0 everywhere ("degenerate") make the whole batch greedy maximin against the observed
        rows. At a later pick, a maximum alpha at most `degenerate_rel` times the first makes
        the remaining picks maximin against the observed rows and earlier picks, with status
        "ok". A `believe` that raises ValueError or NotImplementedError hands the remaining
        picks to the local-penalisation picker over the current alpha, with the same exclusion
        as the argmax picks: every candidate within `max(r_sep, min_separation)` (L-inf) of a
        pick is dropped. No admissible candidate because of the hull gate is "all_out_of_hull",
        with no picks. Every candidate within `min_separation` of an observed row is status "ok"
        with batching "none" and no picks.

    Refused (ValueError): a model that is not a fitted S1Surrogate, a regressor without a
    predictive posterior std, targets that do not align with the spec, an observed row outside
    the bounds, and an incumbent missing from a regressor's training set.
    """
    targets = list(targets)
    lower_a = np.asarray(lower, dtype=float).ravel()
    upper_a = np.asarray(upper, dtype=float).ravel()
    p = len(lower_a)
    lower_a, upper_a = _bounds(lower_a, upper_a, p)
    X_obs = np.asarray(X_obs, dtype=float)
    if X_obs.size == 0:
        X_obs = X_obs.reshape(0, p)
    if X_obs.ndim != 2 or X_obs.shape[1] != p:
        raise ValueError(f"X_obs must be (n, {p}) to match the bounds; got shape {X_obs.shape}")
    n = len(X_obs)
    V_obs = np.asarray(V_obs, dtype=float).ravel()
    viable = np.asarray(viable_obs, dtype=bool).ravel()
    if len(V_obs) != n or len(viable) != n:
        raise ValueError(f"X_obs has {n} rows, V_obs {len(V_obs)}, viable_obs {len(viable)}")
    if not np.all(np.isfinite(X_obs)):
        raise ValueError("X_obs has non-finite coordinates; every observed row needs a position.")
    U_obs = native_to_unit(X_obs, lower_a, upper_a)
    outside = np.flatnonzero(np.any((U_obs < -_BOUND_TOL) | (U_obs > 1.0 + _BOUND_TOL), axis=1))
    if len(outside):
        raise ValueError(f"{len(outside)} observed row(s) lie outside the bounds (first rows "
                         f"{outside[:5].tolist()}); the search cube must contain every "
                         f"observation, so widen the bounds or drop those rows.")
    if isinstance(q, bool) or int(q) != q or int(q) < 1:
        raise ValueError(f"q is {q!r}; propose at least one parameter set")
    q = int(q)
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError(f"seed is {seed!r}; pass an integer so the proposal is reproducible")
    seed = int(seed)
    if not (np.isfinite(min_separation) and min_separation >= 0):
        raise ValueError(f"min_separation is {min_separation}; must be finite and >= 0")
    if not (np.isfinite(degenerate_rel) and degenerate_rel >= 0):
        raise ValueError(f"degenerate_rel is {degenerate_rel}; must be finite and >= 0")
    if r_sep is not None and not (np.isfinite(r_sep) and r_sep >= 0):
        raise ValueError(f"r_sep is {r_sep}; must be finite and >= 0, or None to derive it")
    if int(min_viable_acquisition) < 2:
        raise ValueError(f"min_viable_acquisition is {min_viable_acquisition}; a GP surrogate "
                         f"needs at least 2 viable rows")
    if model is not None:
        _require_search_model(model)
        check_alignment(model.spec, targets)
        if model.spec.n_inputs != p:
            raise ValueError(f"the surrogate has {model.spec.n_inputs} inputs but the bounds "
                             f"have {p}")

    live = viable & np.isfinite(V_obs)
    n_viable = int(live.sum())
    if model is None or n_viable < int(min_viable_acquisition):
        if model is None:
            why = "no surrogate was passed"
        elif n_viable < 2:
            why = f"{n_viable} viable observation(s) with a finite V, fewer than a GP needs (2)"
        else:
            why = (f"{n_viable} viable observations with a finite V, fewer than "
                   f"min_viable_acquisition ({int(min_viable_acquisition)})")
        return _cold_start(model if n_viable >= 2 else None, targets, lower_a, upper_a, X_obs,
                           U_obs, V_obs, viable, live, q, n_cand, seed, min_separation, r_sep,
                           why)

    V_star, i_star = incumbent(V_obs, viable)
    trained = np.asarray(model.trains_on(X_obs[i_star]), dtype=bool)
    if not trained.all():
        missing = [t.name for t, ok in zip(model.spec.targets, trained) if not ok]
        raise ValueError(
            f"the incumbent (observed row {i_star}, V* = {V_star:.6g}) is not in the training "
            f"set of the regressor(s) for {missing}, so expected improvement over it would be "
            f"scored by a posterior that never saw it. Refit on every viable row, or subsample "
            f"with priority=V and keep_best >= 1.")

    U_scan = sobol_candidates(p, n_cand, seed)
    U_loc, labels = local_candidates(U_obs, V_obs, viable, n_total=n_cand, k=local_k,
                                     scales=local_scales, seed=seed + 1)
    U = np.vstack([U_scan, U_loc])
    cset = np.array(["sobol"] * len(U_scan) + [str(s) for s in labels], dtype=object)
    too_close = min_distance(U, U_obs, "linf") <= min_separation

    base = score_candidates(model, targets, U, lower_a, upper_a, V_star)
    in_hull = base["in_hull"]
    admissible = ~too_close & in_hull
    counts = {"n_candidates": int(len(U)), "n_too_close": int(too_close.sum()),
              "n_out_of_hull": int((~in_hull).sum()), "n_admissible": int(admissible.sum())}
    pool = ~too_close if (~too_close).any() else np.ones(len(U), dtype=bool)
    j_free = int(np.argmax(np.where(pool, base["alpha"], -np.inf)))
    diagnostics: Dict[str, Any] = {
        "n_observed": n, "n_viable": n_viable, "min_separation": float(min_separation),
        "degenerate_rel": float(degenerate_rel), "local_k": int(local_k),
        "local_scales": [float(s) for s in local_scales],
        "unconstrained_argmax": {
            "index": j_free, "candidate_set": str(cset[j_free]),
            "alpha": float(base["alpha"][j_free]), "ei": float(base["ei"][j_free]),
            "p_viable": float(base["p_viable"][j_free]),
            "hull_distance": float(base["hull_distance"][j_free]),
            "in_hull": bool(in_hull[j_free]), "V_mean": float(base["V_mean"][j_free])},
        "scan_vs_local": _scan_vs_local(base, cset, admissible),
        "max_alpha_by_pick": []}
    notes: List[str] = []
    T = len(targets)
    common = dict(q=q, V_star=V_star, V_star_index=int(i_star), counts=counts, seed=seed,
                  diagnostics=diagnostics, notes=notes)

    if not admissible.any() and (~too_close).any():
        notes.append(f"all {counts['n_candidates'] - counts['n_too_close']} candidates clear of "
                     f"the observed rows lie outside the hull gate: every argmax would be an "
                     f"extrapolation, so nothing is proposed.")
        return _assemble([], p, T, lower_a, upper_a, status="all_out_of_hull", batching="none",
                         r_sep=float(r_sep) if r_sep is not None else float("nan"), **common)

    if r_sep is None:
        r_sep = density_radius(U[admissible], seed=seed) if counts["n_admissible"] >= 2 else 0.0
    r_sep = float(r_sep)
    sep = max(r_sep, float(min_separation))

    status = "ok"
    batching = "kriging_believer" if counts["n_admissible"] else "none"
    picks: List[Dict[str, Any]] = []
    remaining = admissible.copy()
    model_j, alpha_1 = model, None
    for j in range(1, q + 1):
        idx = np.flatnonzero(remaining)
        if len(idx) == 0:
            break
        if j == 1:
            sc = {key: val[idx] for key, val in base.items()}
        else:
            sc = score_candidates(model_j, targets, U[idx], lower_a, upper_a, V_star)
        a_max = float(sc["alpha"].max())
        diagnostics["max_alpha_by_pick"].append(a_max)

        switch = None
        if j == 1 and np.all(sc["p_viable"] == 0):
            status = "no_viable_probability"
            switch = "maximin_no_viable_probability@1"
        elif j == 1 and a_max <= 0:
            status = "degenerate"
            switch = "maximin_degenerate@1"
        elif j == 1:
            alpha_1 = a_max
        elif a_max <= degenerate_rel * alpha_1:
            switch = f"kriging_believer+maximin_after_collapse@{j}"
            notes.append(f"max alpha at pick {j} is {a_max:.3g}, at most {degenerate_rel:g} times "
                         f"the first pick's {alpha_1:.3g}: alpha no longer ranks the candidates, "
                         f"so picks {j}..{q} are greedy maximin.")
        if switch is not None:
            anchors = np.vstack([U_obs] + [pk["unit"][None, :] for pk in picks])
            for k in maximin_batch(U[idx], anchors, q - len(picks)):
                picks.append(_scored_pick(sc, int(k), U[idx[k]], str(cset[idx[k]]), "maximin",
                                          V_star))
            batching = switch
            break

        k = int(np.argmax(sc["alpha"]))
        i = int(idx[k])
        picks.append(_scored_pick(sc, k, U[i], str(cset[i]), "argmax", V_star))
        remaining[i] = False
        remaining &= np.max(np.abs(U - U[i]), axis=1) > sep
        if len(picks) == q or not remaining.any():
            continue
        try:
            model_j = model_j.believe(unit_to_native(U[i:i + 1], lower_a, upper_a))
        except (ValueError, NotImplementedError) as exc:
            rest = np.flatnonzero(remaining)
            pos = np.searchsorted(idx, rest)
            lp, _ = _penalised_picks(U[rest], np.array(sc["alpha"][pos], dtype=float),
                                     q - len(picks), sep, "linf")
            for kk in lp:
                picks.append(_scored_pick(sc, int(pos[kk]), U[rest[kk]], str(cset[rest[kk]]),
                                          "local_penalisation", V_star))
            batching = f"kriging_believer+local_penalisation_after_believe_failed@{j + 1}"
            notes.append(f"believe() failed after pick {j} ({type(exc).__name__}: {exc}); picks "
                         f"{j + 1}..{q} use local penalisation over the alpha of pick {j}.")
            break

    if counts["n_admissible"] == 0:
        notes.append(f"no candidate is admissible: all {counts['n_candidates']} lie within "
                     f"min_separation {min_separation:g} of an observed row.")
    elif len(picks) < q:
        notes.append(f"{q - len(picks)} of {q} picks missing: no admissible candidate was left "
                     f"after the separation (r_sep {r_sep:.3g}, min_separation "
                     f"{min_separation:g}).")
    return _assemble(picks, p, T, lower_a, upper_a, status=status, batching=batching,
                     r_sep=r_sep, **common)


def _cold_start(model, targets, lower, upper, X_obs, U_obs, V_obs, viable, live, q, n_cand, seed,
                min_separation, r_sep, why: str) -> Proposal:
    """The cold-start batch of `propose_batch`, over the Sobol' scan alone."""
    p, n, T = U_obs.shape[1], len(U_obs), len(targets)
    n_viable = int(live.sum())
    U = sobol_candidates(p, n_cand, seed)
    too_close = min_distance(U, U_obs, "linf") <= min_separation
    admissible = ~too_close

    classifier = None
    if model is not None:
        weights = np.asarray(model.viability(unit_to_native(U, lower, upper)), dtype=float)
        variant = "feasibility_maximin(surrogate_viability)"
    elif viable.any() and (~viable).any():
        from models.surrogate.learners import make_classifier

        classifier = make_classifier("rf", random_state=seed).fit(X_obs, viable.astype(int))
        weights = _classifier_viability(classifier, unit_to_native(U, lower, upper))
        variant = "feasibility_maximin(acquisition_classifier)"
    else:
        weights = None
        variant = "maximin"
    idx, n_fill = _feasibility_maximin(U, U_obs, q, weights, admissible)
    batching = f"cold_start:{variant}"
    if n_fill:
        batching += f"+maximin_fill@{len(idx) - n_fill + 1}"

    V_star, i_star = incumbent(V_obs, viable) if n_viable else (float("nan"), None)
    nan_T = np.full(T, np.nan)
    picks = [{"unit": U[i], "alpha": np.nan, "ei": np.nan,
              "p_viable": float(weights[i]) if weights is not None else np.nan,
              "hull_distance": np.nan, "in_hull": None, "predicted": nan_T, "V_mean": np.nan,
              "binding": "", "sd_ratio": nan_T, "candidate_set": "sobol", "pick_source": "maximin",
              "V_star_used": V_star}
             for i in idx]
    notes = [f"cold start ({why}): picks are greedy maximin over the Sobol' scan ({variant}).",
             "no hull gate is applied in a cold start: a gate fitted on so few viable rows would "
             "pin the search beside them."]
    if n_fill:
        notes.append(f"only {len(idx) - n_fill} admissible candidate(s) had P(viable) > 0; the "
                     f"other {n_fill} pick(s) are plain maximin.")
    diagnostics = {"n_observed": n, "n_viable": n_viable, "cold_start_variant": variant,
                   "classifier": "rf" if classifier is not None else None,
                   "n_filled_by_maximin": int(n_fill), "min_separation": float(min_separation),
                   "scan_vs_local": None}
    counts = {"n_candidates": int(len(U)), "n_too_close": int(too_close.sum()),
              "n_out_of_hull": 0, "n_admissible": int(admissible.sum())}
    return _assemble(picks, p, T, lower, upper, q=q, V_star=V_star,
                     V_star_index=None if i_star is None else int(i_star), status="cold_start",
                     batching=batching, counts=counts,
                     r_sep=float(r_sep) if r_sep is not None else float("nan"), seed=seed,
                     diagnostics=diagnostics, notes=notes)
