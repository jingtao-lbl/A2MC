"""The S2 acquisition: exact expected improvement, candidates, distances, batch pickers, and the
batch proposal built from them (scoring, admissibility, batching, cold start).

The expected improvement `E[max(0, V* - V)]` is checked three independent ways, because each
catches what the others cannot:
  * a closed form for one identity target, which pins the tail and the mirrored CDF difference
    to 1e-8 where Monte Carlo sees nothing at all;
  * 50-digit constants and a dense-breakpoint reference with its own integrand, for the log and
    logit kinks where a band edge reaches 0 or 1;
  * Monte Carlo over the joint posterior, which checks the integrand FORMULA rather than the
    quadrature, with a bound that still fails when no draw improves.

Every test names the defect it catches. Numeric bars were measured on the built code together
with the broken variant named in each docstring.
"""
from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.special import erfc, expit, logit, ndtr

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import tools.bayesian_optimization.acquisition as acq  # noqa: E402
from models.surrogate.learners import GPLearner, make_classifier  # noqa: E402
from models.surrogate.spec import Provenance, SurrogateSpec, TargetSpec  # noqa: E402
from models.surrogate.tiers import S1Surrogate  # noqa: E402
from tools.bayesian_optimization.acquisition import (  # noqa: E402
    band_probability,
    check_alignment,
    density_radius,
    expected_improvement,
    incumbent,
    local_candidates,
    local_penalisation_batch,
    maximin_batch,
    min_distance,
    native_to_unit,
    propose_batch,
    reflect_unit,
    score_candidates,
    sd_floor,
    sobol_candidates,
    unit_to_native,
)
from tools.bayesian_optimization.bo_replay import Pool, _greedy_batch  # noqa: E402
from tools.bayesian_optimization.objective import Target, violation_matrix  # noqa: E402


def _targets(obs, u):
    return [Target(f"t{i}", o, uu) for i, (o, uu) in enumerate(zip(obs, u))]


def _inv(Y, tr):
    if tr == "identity":
        return Y
    with np.errstate(over="ignore"):
        return np.exp(Y) if tr == "log" else expit(Y)


def test_the_module_resolves_the_REPO_ROOT():
    assert (acq.REPO / "CLAUDE.md").is_file(), f"acquisition.REPO resolves to {acq.REPO}"


# =============================================================================
# Test 4: closed form for one identity target
# =============================================================================

def _G(x):
    return x * ndtr(x) + np.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _closed_form_ei(k, w, V):
    """`int_0^V [Phi((t - k)/w) - Phi((-t - k)/w)] dt`: one identity target, knee `k`, width `w`.

    The first term is the upper band edge, `w [G((V - k)/w) - G(-k/w)]`; the second is the lower
    edge, `w [G(-k/w) - G(-(V + k)/w)]`. Dropping the second is off by 10% at w/V* = 0.3, z = -3.
    Accurate to 1e-12 relative on this grid against 50-digit arithmetic.
    """
    return w * (_G((V - k) / w) - _G(-k / w)) - w * (_G(-k / w) - _G(-(V + k) / w))


def test_ei_matches_the_closed_form_for_one_identity_target_above_and_below_its_band():
    """Catches a quadrature that under-resolves a knee lying above V* (drop the tail breakpoints:
    3.6e-2 to 1.0 relative error at z = 10), and the literal `Phi(b) - Phi(a)`, which rounds to 0
    whenever the prediction lies far below the band. Correct code measured 1.4e-11 worst."""
    obs, u, V = 10.0, 0.2, 1.5
    t = [Target("a", obs, u)]
    failures, n_checked = [], 0
    for r in (0.3, 0.05, 0.005, 1e-4):
        for z in (-3.0, -1.0, 0.0, 1.0, 2.0, 3.01, 5.0, 10.0):
            w = r * V
            k = V + z * w
            ref = _closed_form_ei(k, w, V)
            assert ref >= 1e-250
            for side in (+1.0, -1.0):
                mu = obs + side * k * u * obs
                got = expected_improvement([[mu]], [[w * u * obs]], t, ["identity"], V)[0]
                n_checked += 1
                rel = abs(got - ref) / ref
                if rel > 1e-8:
                    failures.append((r, z, side, f"{rel:.2e}"))
    assert n_checked == 64
    assert not failures, f"EI off the closed form by more than 1e-8 at (w/V*, z, side): {failures}"


# =============================================================================
# Test 5: log and logit, against 50-digit constants and an independent dense reference
# =============================================================================

# The constants below were computed ONCE with mpmath 1.3.0 at 50 digits and hard-coded, so the
# test has no runtime dependency on mpmath. Script (inputs are the exact float values listed).
# Each value agrees to 1.5e-20 relative or better with the same computation at half the grading
# density (`per = 8`), which checks the far-tail values more tightly than mp.quad's own error
# estimate does:
#
#   import mpmath as mp
#   mp.mp.dps = 50
#   def band(mu, sd, lo, hi, tr):
#       if tr == "identity":
#           a, b = lo, hi
#       elif tr == "log":
#           if hi <= 0: return mp.mpf(0)
#           a = mp.log(lo) if lo > 0 else mp.ninf
#           b = mp.log(hi)
#       else:
#           if hi <= 0 or lo >= 1: return mp.mpf(0)
#           a = mp.log(lo / (1 - lo)) if lo > 0 else mp.ninf
#           b = mp.log(hi / (1 - hi)) if hi < 1 else mp.inf
#       A = (a - mu) / sd if a != mp.ninf else mp.ninf
#       B = (b - mu) / sd if b != mp.inf else mp.inf
#       if A != mp.ninf and A > 0:
#           return mp.ncdf(-A) - mp.ncdf(-B)
#       return mp.ncdf(B) - mp.ncdf(A)
#   def inv(Y, tr):
#       return Y if tr == "identity" else mp.exp(Y) if tr == "log" else 1 / (1 + mp.exp(-Y))
#   def ei(case, per=16):
#       tr = case["tr"]
#       obs = [mp.mpf(x) for x in case["obs"]]; u = [mp.mpf(x) for x in case["u"]]
#       mu = [mp.mpf(x) for x in case["mu"]]; sd = [mp.mpf(x) for x in case["sd"]]
#       V = mp.mpf(case["V_star"])
#       f = lambda t: mp.fprod(band(mu[i], sd[i], obs[i]*(1 - t*u[i]), obs[i]*(1 + t*u[i]), tr[i])
#                              for i in range(len(tr)))
#       pts = {mp.mpf(0), V}
#       pts.update(V * (1 - mp.mpf(2) ** (-mp.mpf(j) / per)) for j in range(1, 60 * per))
#       for i in range(len(tr)):
#           for m in range(-60, 61):
#               pts.add(abs(inv(mu[i] + m * sd[i], tr[i]) - obs[i]) / (u[i] * obs[i]))
#           below = [1 / u[i]] if tr[i] != "identity" else []     # singular side of each kink
#           above = []
#           if tr[i] == "logit":
#               (below if obs[i] < 1 else above).append(abs(1 / obs[i] - 1) / u[i])
#           for k in below:
#               pts.add(k)
#               pts.update(k * (1 - mp.mpf(2) ** (-mp.mpf(j) / per)) for j in range(1, 60 * per))
#               pts.update(k * (1 + mp.mpf(2) ** -j) for j in range(1, 20))
#           for k in above:
#               pts.add(k)
#               pts.update(k + mp.mpf(2) ** (-mp.mpf(j) / per) / u[i] for j in range(1, 60 * per))
#       pts = sorted(p for p in pts if 0 <= p <= V)
#       return mp.quad(f, pts, method="gauss-legendre", maxdegree=10)
#   for name, (case, _) in _MP_CASES.items(): print(name, mp.nstr(ei(case), 20))
_MP_CASES = {
    "log_one_lower_edge_crosses_0": (
        dict(tr=["log"], obs=[389.0], u=[0.36], mu=[6.2635], sd=[2.5], V_star=4.0),
        1.2531973064990130257),
    "log_three_lower_edges_cross_0": (
        dict(tr=["log"] * 3, obs=[389.0, 651.7, 6.2], u=[0.36, 0.35, 0.28],
             mu=[6.4635, 6.2797, 1.9246], sd=[2.6, 0.06, 2.2], V_star=4.7),
        0.70558339138947315414),
    "logit_one_both_edges_cross": (
        dict(tr=["logit"], obs=[0.8], u=[0.28], mu=[1.3862943611198906], sd=[2.0], V_star=5.0),
        3.992077827103043421),
    "logit_two_edges_cross": (
        dict(tr=["logit"] * 2, obs=[0.2449, 0.9159], u=[0.3, 0.28], mu=[-2.13, 6.9],
             sd=[3.0, 2.5], V_star=5.14),
        2.1199647446276515509),
    "mixed_identity_log_logit": (
        dict(tr=["identity", "log", "logit"], obs=[389.0, 651.7, 0.6], u=[0.36, 0.35, 0.3],
             mu=[420.0, 6.0, 0.2], sd=[150.0, 2.2, 2.8], V_star=3.8),
        0.98816924319457606471),
    "log_prediction_far_below_band": (
        dict(tr=["log"], obs=[651.7], u=[0.35], mu=[5.7839], sd=[0.02], V_star=1.0),
        6.6909057730660024024e-43),
    # A knee above V* whose tail the linearised width misplaces, far below the band.
    "log_knee_above_V_star_narrow_fitted_tail": (
        dict(tr=["log"], obs=[100.0], u=[0.3], mu=[-0.3948], sd=[0.1], V_star=3.0),
        1.8529460622294468123e-163),
    "log_knee_above_V_star_eleven_efolds_below": (
        dict(tr=["log"], obs=[3.035], u=[0.3861], mu=[-7.434], sd=[0.438], V_star=2.557),
        1.0403855579487905421e-24),
    "logit_knee_above_V_star_far_below": (
        dict(tr=["logit"], obs=[0.3934], u=[0.2454], mu=[-13.47], sd=[0.2245], V_star=4.07),
        2.3332267985643034232e-153),
    # V* within a few 1e-5 of a kink, where the segment ending at the kink needs the grading.
    "log_V_star_just_above_kink_wide_posterior": (
        dict(tr=["log"], obs=[26.16], u=[0.2853], mu=[-14.81], sd=[2.28], V_star=3.5052),
        0.00011829733643049853333),
    "logit_log_V_star_just_below_log_kink": (
        dict(tr=["logit", "log"], obs=[0.9948, 32.55], u=[0.58, 0.4], mu=[4.776, -10.26],
             sd=[0.0032, 5.29], V_star=2.4999),
        0.013572577549063918655),
    # A wide logit posterior whose knee the linearised width places badly.
    "logit_obs_near_1_wide_posterior": (
        dict(tr=["logit"], obs=[0.99656], u=[0.02362], mu=[9.6235], sd=[2.2401], V_star=20.831),
        20.685464524617012813),
    # Observed at or above 1: the LOWER edge reaches 1 at t = (1 - 1/obs)/u (t = 0 at obs = 1),
    # and the band probability is singular on the side above that point.
    "logit_obs_exactly_1_wide_posterior": (
        dict(tr=["logit"], obs=[1.0], u=[0.3744], mu=[12.35], sd=[3.907], V_star=0.5587),
        0.55428653752573043722),
    "logit_obs_above_1_lower_edge_crosses_1": (
        dict(tr=["logit"], obs=[1.4697], u=[0.5803], mu=[10.53], sd=[3.216], V_star=8.585),
        8.0313971727430147092),
    "logit_obs_just_above_1_narrow_band": (
        dict(tr=["logit"], obs=[1.0003], u=[0.1245], mu=[10.62], sd=[4.016], V_star=0.8941),
        0.85923902506578676199),
    "logit_obs_exactly_1_with_log": (
        dict(tr=["logit", "log"], obs=[1.0, 389.0], u=[0.3, 0.36], mu=[12.35, 6.2635],
             sd=[3.9, 2.5], V_star=0.8),
        0.036809205541653811891),
}

#: docs/45 section 4.2: relative error <= 1e-8 against an independent reference wherever
#: EI >= 1e-250. Measured on these cases: worst 6.9e-11 with the code as built; with a set of
#: breakpoints removed, worst 2.3e-1 (fitted-space tail points), 3.5e-7 (fitted-space knee
#: points), and 1.3e-3 (the kink grading, or every kink breakpoint). The four observed >= 1
#: cases measured 3.3e-13 worst as built, and 5.6e-5, 1.6e-6, 1.3e-6 and 1.5e-7 when the only
#: logit kinks are `1/u` and `(1/obs - 1)/u`, which misses the lower edge reaching 1.
_MP_RTOL = 1e-8


@pytest.mark.parametrize("name", sorted(_MP_CASES))
def test_ei_matches_50_digit_constants_where_a_band_edge_crosses_0_or_1(name):
    """Catches missing kink breakpoints (the point where a band edge reaches 0 or 1 and the
    grading toward it, including the lower edge reaching 1 when a logit observation is at or
    above 1), and missing fitted-space tail and knee points, whose linearised counterparts are
    misplaced for a log or logit posterior far from its band or wide."""
    case, ref = _MP_CASES[name]
    got = expected_improvement([case["mu"]], [case["sd"]], _targets(case["obs"], case["u"]),
                               case["tr"], case["V_star"])[0]
    assert abs(got - ref) / ref <= _MP_RTOL, f"{name}: got {got!r}, 50-digit {ref!r}"


_SQ2 = math.sqrt(2.0)


def _ref_edge(x, tr):
    """Fitted-space band edge, written without the module's code: log and log1p forms."""
    if tr == "identity":
        return x
    with np.errstate(divide="ignore", invalid="ignore"):
        if tr == "log":
            return np.where(x > 0, np.log(np.where(x > 0, x, 1.0)), -np.inf)
        xs = np.clip(x, 1e-300, 1.0 - 1e-16)
        return np.where(x <= 0, -np.inf, np.where(x >= 1, np.inf, np.log(xs) - np.log1p(-xs)))


def _ref_prob(mu, sd, lo, hi, tr):
    """Band probability through erfc: Q(A) - Q(B) when A > 0, otherwise Phi(B) - Phi(A)."""
    A = (_ref_edge(lo, tr) - mu) / sd
    B = (_ref_edge(hi, tr) - mu) / sd
    upper = 0.5 * erfc(A / _SQ2) - 0.5 * erfc(B / _SQ2)
    lower = 0.5 * erfc(-B / _SQ2) - 0.5 * erfc(-A / _SQ2)
    return np.clip(np.where(A > 0, upper, lower), 0.0, None)


def _reference_ei(mu, sd, obs, u, trs, V, nodes=64):
    """Independent EI: 64-node Gauss-Legendre on a DENSE breakpoint set.

    Knee +/- 40 widths in steps of 0.5, a geometric grading toward V* (2^-1 .. 2^-59), and
    geometric grading on both sides of every kink, relative (2^-1 .. 2^-49) and in steps of
    `2^-j / u` (2^-1 .. 2^-59), with the `_ref_prob` integrand. The logit kink is
    `|1/obs - 1|/u`: the upper edge reaching 1 below observed 1, the lower edge at or above it.
    Agrees with the 50-digit constants to 1.3e-12 (asserted at 1e-11 below), and with a
    reference of 6,000 uniform segments plus fitted-space and kink grading at 64 nodes to 9.8e-12
    on the three sweep generators at their pinned seeds.
    """
    if V <= 0:
        return 0.0
    pts = [0.0, V] + [V - V * 2.0 ** -j for j in range(1, 60)]
    for i, tr in enumerate(trs):
        y = _inv(np.float64(mu[i]), tr)
        dy = sd[i] if tr == "identity" else y * sd[i] if tr == "log" else y * (1 - y) * sd[i]
        k = abs(y - obs[i]) / (u[i] * obs[i])
        pts += list(k + dy / (u[i] * obs[i]) * np.arange(-40.0, 40.5, 0.5))
        kinks = (([1.0 / u[i]] if tr != "identity" else [])
                 + ([abs(1.0 / obs[i] - 1.0) / u[i]] if tr == "logit" else []))
        for kk in kinks:
            pts += ([kk] + [kk * (1 + s * 2.0 ** -j) for j in range(1, 50) for s in (-1, 1)]
                    + [kk + s * 2.0 ** -j / u[i] for j in range(1, 60) for s in (-1, 1)])
    p = np.unique(np.clip(np.array([x for x in pts if np.isfinite(x)]), 0.0, V))
    x, wts = np.polynomial.legendre.leggauss(nodes)
    h = 0.5 * np.diff(p)
    t = (0.5 * (p[1:] + p[:-1])[:, None] + h[:, None] * x[None, :]).ravel()
    f = np.ones_like(t)
    for i, tr in enumerate(trs):
        f *= _ref_prob(mu[i], sd[i], obs[i] * (1 - t * u[i]), obs[i] * (1 + t * u[i]), tr)
    return float(((f.reshape(len(h), nodes) * wts).sum(axis=1) * h).sum())


def test_the_dense_reference_itself_matches_the_50_digit_constants():
    """A reference that shares a defect with the code under test proves nothing, so the one
    the sweep relies on is anchored to arithmetic that shares no code with either."""
    for name, (c, ref) in _MP_CASES.items():
        got = _reference_ei(c["mu"], c["sd"], c["obs"], c["u"], c["tr"], c["V_star"])
        assert abs(got - ref) / ref <= 1e-11, name


def _draw_case(rng):
    mode = rng.choice(["identity", "log", "logit", "mixed"])
    T = int(rng.integers(1, 4))
    trs = [str(mode)] * T if mode != "mixed" else [str(s) for s in
                                                   rng.choice(["identity", "log", "logit"], T)]
    obs, u, mu, sd = [], [], [], []
    for tr in trs:
        uu = rng.uniform(0.1, 0.5)
        if tr == "logit":
            o = rng.uniform(0.05, 0.95)
            m = math.log(o / (1 - o)) + rng.normal(0, 1.5)
            s = 10 ** rng.uniform(-2, 0.5)
        elif tr == "log":
            o = 10 ** rng.uniform(-2, 3)
            m = math.log(o) + rng.normal(0, 1.0)
            s = 10 ** rng.uniform(-2, 0.5)
        else:
            o = 10 ** rng.uniform(-2, 3)
            m = o * (1 + uu * rng.normal(0, 2))
            s = uu * o * 10 ** rng.uniform(-3, 0.5)
        obs.append(o)
        u.append(uu)
        mu.append(m)
        sd.append(s)
    return trs, np.array(obs), np.array(u), np.array(mu), np.array(sd), rng.uniform(0.1, 6.0)


def _draw_near_kink_case(rng):
    """Cases placed where the breakpoints matter most: V* or a knee close to a kink, log and logit
    posteriors far from their band or wide. V* stays at least 1e-5 (relative) from a kink: within
    about 1e-7, float64 rounding in obs (1 - t u), not the quadrature, sets the error (measured
    1.0e-8 to 2.9e-8 there against 40-digit arithmetic)."""
    T = int(rng.integers(1, 4))
    mode = rng.choice(["log", "logit", "mixed"])
    trs = [str(mode)] * T if mode != "mixed" else [str(s) for s in
                                                   rng.choice(["identity", "log", "logit"], T)]
    obs, u, mu, sd, kinks, knees = [], [], [], [], [], []
    for tr in trs:
        uu = rng.uniform(0.02, 0.6)
        s = 10 ** rng.uniform(-3, 0.75)
        if tr == "identity":
            o = 10 ** rng.uniform(-2, 3)
            m = o * (1 + uu * rng.normal(0, 4))
            s = uu * o * 10 ** rng.uniform(-4, 0.7)
            y = m
        elif tr == "log":
            o = 10 ** rng.uniform(-2, 3)
            m = math.log(o) + rng.choice([rng.normal(0, 1.5), rng.uniform(-12, -0.5)])
            y = math.exp(m)
            kinks.append(1 / uu)
        else:
            o = float(expit(rng.uniform(-6, 6)))
            m = math.log(o / (1 - o)) + rng.choice([rng.normal(0, 2), rng.uniform(-14, 14)])
            y = float(expit(m))
            kinks += [1 / uu, (1 / o - 1) / uu]
        obs.append(o)
        u.append(uu)
        mu.append(m)
        sd.append(s)
        knees.append(abs(y - o) / (uu * o))
    kinks = [k for k in kinks if 0 < k < 40]
    r = rng.random()
    if kinks and r < 0.4:
        V = kinks[int(rng.integers(len(kinks)))] * (
            1 + rng.choice([-1, 1]) * 10 ** rng.uniform(-5, -0.5))
    elif r < 0.75:
        V = knees[int(rng.integers(len(knees)))] * (
            1 + rng.choice([-1, 1]) * 10 ** rng.uniform(-3, -0.3))
    else:
        V = rng.uniform(0.05, 12.0)
    return (trs, np.array(obs), np.array(u), np.array(mu), np.array(sd),
            float(min(max(V, 0.02), 40.0)))


#: docs/45 section 4.2, applied to every transform. Measured worst, with the code as built:
#: 2.1e-13 on `_draw_case` (seed 12345, 266 of 300 draws compared) and 2.3e-11 on
#: `_draw_near_kink_case` (seed 2026, 148 of 200). With breakpoints removed,
#: `_draw_near_kink_case` has 7 cases above the bar without the kink grading (worst 3.0e-6),
#: 1 without the fitted-space tail points (2.0e-1), 9 without both the linearised and the
#: fitted-space tail points (1.0; 2 without the linearised ones alone), and 28 with the
#: breakpoint set that preceded the fitted-space points and the grading (9.2e-1); `_draw_case`
#: has 12 without both sets of tail points (2.6e-1; 3 without the linearised ones alone).
_SWEEP_RTOL = 1e-8


def test_ei_matches_the_dense_reference_on_a_seeded_sweep_of_all_transforms():
    """Catches missing kink breakpoints, missing fitted-space tail points and missing contracted
    tail points on cases nobody hand-picked, at the docs/45 tolerance for every transform."""
    fails, n_cmp = [], {"_draw_case": 0, "_draw_near_kink_case": 0}
    for draw, seed, n in ((_draw_case, 12345, 300), (_draw_near_kink_case, 2026, 200)):
        rng = np.random.default_rng(seed)
        for c in range(n):
            trs, obs, u, mu, sd, V = draw(rng)
            ref = _reference_ei(mu, sd, obs, u, trs, V)
            if ref < 1e-250:
                continue
            got = expected_improvement(mu[None, :], sd[None, :], _targets(obs, u), trs, V)[0]
            n_cmp[draw.__name__] += 1
            rel = abs(got - ref) / ref
            if rel > _SWEEP_RTOL:
                fails.append((draw.__name__, c, trs, f"{ref:.2e}", f"{rel:.2e}"))
    assert n_cmp["_draw_case"] >= 250 and n_cmp["_draw_near_kink_case"] >= 130, n_cmp
    assert not fails, (f"cases off the dense reference (draw, case, transforms, EI, rel): "
                       f"{fails[:10]}")


def _draw_logit_obs_at_or_above_1_case(rng):
    """A logit first target observed at exactly 1 or above it (a fraction whose observation sits
    on or past the domain edge), optionally with a second target of any transform. Half the draws
    put V* between 1e-4 and 3.2 above the point where the logit band's lower edge reaches 1."""
    T = int(rng.integers(1, 3))
    trs = ["logit"] + [str(s) for s in rng.choice(["identity", "log", "logit"], T - 1)]
    obs, u, mu, sd = [], [], [], []
    for j, tr in enumerate(trs):
        uu = rng.uniform(0.02, 0.6)
        if j == 0:
            o = 1.0 if rng.random() < 0.5 else 1.0 + 10 ** rng.uniform(-4, -0.3)
            m, s = rng.uniform(-6, 14), 10 ** rng.uniform(-3, 0.75)
        elif tr == "logit":
            o = rng.uniform(0.05, 0.95)
            m, s = math.log(o / (1 - o)) + rng.normal(0, 2), 10 ** rng.uniform(-3, 0.75)
        elif tr == "log":
            o = 10 ** rng.uniform(-2, 3)
            m, s = math.log(o) + rng.normal(0, 1.5), 10 ** rng.uniform(-3, 0.75)
        else:
            o = 10 ** rng.uniform(-2, 3)
            m, s = o * (1 + uu * rng.normal(0, 3)), uu * o * 10 ** rng.uniform(-3, 0.5)
        obs.append(o)
        u.append(uu)
        mu.append(m)
        sd.append(s)
    t0 = (1 - 1 / obs[0]) / u[0]
    V = t0 + 10 ** rng.uniform(-4, 0.5) if rng.random() < 0.5 else rng.uniform(0.02, 12.0)
    return trs, np.array(obs), np.array(u), np.array(mu), np.array(sd), float(min(V, 40.0))


def test_ei_matches_the_dense_reference_for_logit_targets_observed_at_or_above_1():
    """An observation of exactly 1 is a legitimate fraction target, and its band still meets
    (0, 1). The band's lower edge then reaches 1 at t = (1 - 1/obs)/u, and above that point the
    band probability is singular in log(t - t0). Catches breakpoints that know only the upper edge
    reaching 1: measured 6 of 148 compared cases above 1e-8 (worst 2.0e-6) at this seed, and the
    kink column without its grading from above. Correct code measured 1.5e-11 worst."""
    rng = np.random.default_rng(7)
    fails, n_cmp = [], 0
    for c in range(200):
        trs, obs, u, mu, sd, V = _draw_logit_obs_at_or_above_1_case(rng)
        ref = _reference_ei(mu, sd, obs, u, trs, V)
        if ref < 1e-250:
            continue
        got = expected_improvement(mu[None, :], sd[None, :], _targets(obs, u), trs, V)[0]
        n_cmp += 1
        rel = abs(got - ref) / ref
        if rel > _SWEEP_RTOL:
            fails.append((c, trs, obs.tolist(), f"{ref:.2e}", f"{rel:.2e}"))
    assert n_cmp >= 130, n_cmp
    assert not fails, f"cases off the dense reference (case, transforms, obs, EI, rel): {fails}"


def test_band_probability_matches_an_independent_integrand_at_domain_edges_and_far_tails():
    """Catches the literal `Phi(b) - Phi(a)` (0 for a band 12 sd above the mean), a log lower
    edge that is not dropped at lo <= 0, and a logit band not clipped to (0, 1) (both give NaN)."""
    cases = [
        ("identity", 0.0, 1.0, 12.0, 13.0), ("identity", 0.0, 1.0, -13.0, -12.0),
        ("identity", 5.0, 0.5, 4.0, 6.0),
        ("log", 0.0, 1.0, -2.0, 3.0), ("log", 0.0, 1.0, -2.0, -1.0), ("log", 1.0, 0.02, 3.0, 4.0),
        ("log", 1.0, 0.02, 1.0, 2.0),
        ("logit", 0.0, 1.0, -0.2, 0.6), ("logit", 0.0, 1.0, 0.3, 1.4),
        ("logit", 0.0, 1.0, 1.2, 2.0),
        ("logit", 0.0, 1.0, -1.0, 0.0), ("logit", -3.0, 0.1, 0.4, 0.6),
    ]
    for tr, mu, sd, lo, hi in cases:
        got = float(band_probability(mu, sd, lo, hi, tr))
        ref = float(_ref_prob(np.float64(mu), sd, np.float64(lo), np.float64(hi), tr))
        if ref == 0.0:
            assert got == 0.0, (tr, mu, sd, lo, hi, got)
        else:
            assert abs(got - ref) / ref <= 1e-12, (tr, mu, sd, lo, hi, got, ref)
    assert float(band_probability(0.0, 1.0, 12.0, 13.0, "identity")) > 1e-33
    with pytest.raises(ValueError, match="sd > 0"):
        band_probability(0.0, 0.0, -1.0, 1.0, "identity")


# =============================================================================
# Test 6: Monte Carlo cross-check
# =============================================================================

def test_ei_agrees_with_monte_carlo_over_the_joint_posterior():
    """Checks the integrand FORMULA, which the quadrature references cannot: they integrate the
    same band. Catches a band written without u_i (all 32 compared cases fail, by 439 to 8.8e3
    SE). Where at least 1,000 draws improve, |exact - MC| <= 5 SE (measured worst 2.1 SE at this
    seed, 2.4 over three seeds); where none do,
    exact <= V* ln(1e6)/N, a bound a real improvement probability above 13.8/N would break;
    between the two, exact <= V* (k + 5 sqrt(k) + 14)/N."""
    N = 400_000
    rng = np.random.default_rng(7)
    n_big = n_zero = 0
    for c in range(40):
        T = int(rng.integers(1, 4))
        trs = [str(s) for s in rng.choice(["identity", "log", "logit"], T)]
        obs, u, mu, sd = [], [], [], []
        for tr in trs:
            uu = rng.uniform(0.15, 0.45)
            if tr == "logit":
                o = rng.uniform(0.1, 0.9)
                m, s = math.log(o / (1 - o)) + rng.normal(0, 0.7), 10 ** rng.uniform(-1.5, 0.3)
            elif tr == "log":
                o = 10 ** rng.uniform(-1, 3)
                m, s = math.log(o) + rng.normal(0, 0.5), 10 ** rng.uniform(-1.5, 0.2)
            else:
                o = 10 ** rng.uniform(-1, 3)
                m, s = o * (1 + uu * rng.normal(0, 1.5)), uu * o * 10 ** rng.uniform(-1.5, 0.3)
            obs.append(o)
            u.append(uu)
            mu.append(m)
            sd.append(s)
        obs, u, mu, sd = map(np.array, (obs, u, mu, sd))
        V = rng.uniform(0.3, 4.0)

        exact = expected_improvement(mu[None], sd[None], _targets(obs, u), trs, V)[0]
        Z = rng.standard_normal((N, T))
        v = np.column_stack([np.abs(_inv(mu[i] + sd[i] * Z[:, i], tr) - obs[i]) / (u[i] * obs[i])
                             for i, tr in enumerate(trs)])
        imp = np.maximum(0.0, V - v.max(axis=1))
        k = int((imp > 0).sum())
        if k >= 1000:
            n_big += 1
            se = imp.std(ddof=1) / math.sqrt(N)
            assert abs(exact - imp.mean()) <= 5 * se, (c, trs, exact, imp.mean(), se)
        elif k == 0:
            n_zero += 1
            assert exact <= V * math.log(1e6) / N, (c, trs, exact)
        else:
            assert exact <= V * (k + 5 * math.sqrt(k) + 14) / N, (c, trs, k, exact)
    assert n_big >= 20 and n_zero >= 3, (n_big, n_zero)


# =============================================================================
# Test 7: limits and guards
# =============================================================================

def test_ei_with_sd_exactly_zero_is_finite_and_equals_the_deterministic_limit():
    """Catches a missing sd floor: an exactly zero sd puts a node at the knee, 0/0 = NaN, and
    np.argmax selects the NaN. Each transform, knee below, at, and above V*; plus a three-target
    case whose binding knee equals V*. Measured worst |EI - limit| 4.7e-12 (band-width units)."""
    n = 0
    for tr in ("identity", "log", "logit"):
        for obs in ([1e-3, 5.0, 2e6] if tr != "logit" else [0.05, 0.4, 0.93]):
            for u in (0.1, 0.35):
                for off in (-2.0, -0.6, 0.4, 1.7):
                    y = obs * (1 + off * u)
                    if (tr != "identity" and y <= 0) or (tr == "logit" and not 0 < y < 1):
                        continue
                    mu = y if tr == "identity" else math.log(y) if tr == "log" else logit(y)
                    k = abs(_inv(np.float64(mu), tr) - obs) / (u * obs)
                    for V in (0.5 * k, k, k + 0.25, 3.0):
                        got = expected_improvement([[mu]], [[0.0]], [Target("a", obs, u)],
                                                   [tr], V)[0]
                        assert np.isfinite(got) and abs(got - max(0.0, V - k)) <= 1e-9, (
                            tr, obs, u, off, V, got)
                        n += 1
    assert n >= 250

    ts = [Target("a", 389.0, 0.36), Target("b", 651.7, 0.35), Target("c", 0.6, 0.3)]
    mu = np.array([389.0 * (1 + 0.36 * 0.8), math.log(651.7 * (1 - 0.35 * 0.5)),
                   logit(0.6 * (1 + 0.3 * 0.2))])
    knee = max(abs(mu[0] - 389.0) / (0.36 * 389.0), abs(math.exp(mu[1]) - 651.7) / (0.35 * 651.7),
               abs(expit(mu[2]) - 0.6) / (0.3 * 0.6))
    for V in (knee, 1.0, 0.7):
        got = expected_improvement(mu[None], np.zeros((1, 3)), ts, ["identity", "log", "logit"],
                                   V)[0]
        assert np.isfinite(got) and abs(got - max(0.0, V - knee)) <= 1e-9, (V, got)


def test_ei_over_many_chunks_equals_ei_one_candidate_at_a_time(monkeypatch):
    """Catches a chunk boundary that skips or repeats candidates when the candidate count is not a
    multiple of the chunk size."""
    rng = np.random.default_rng(21)
    ts = [Target("a", 389.0, 0.36), Target("b", 651.7, 0.35), Target("c", 0.6, 0.3)]
    trs = ["identity", "log", "logit"]
    mu = np.column_stack([rng.normal(389.0, 120.0, 301), rng.normal(math.log(651.7), 0.8, 301),
                          rng.normal(logit(0.6), 1.5, 301)])
    sd = np.column_stack([rng.uniform(5, 150, 301), rng.uniform(0.01, 2.5, 301),
                          rng.uniform(0.01, 2.5, 301)])
    single = np.array([expected_improvement(mu[i:i + 1], sd[i:i + 1], ts, trs, 2.2)[0]
                       for i in range(301)])
    monkeypatch.setattr(acq, "_EI_CHUNK_ELEMENTS", 40 * 16 * 50.0)
    chunked = expected_improvement(mu, sd, ts, trs, 2.2)
    np.testing.assert_allclose(chunked, single, rtol=1e-14, atol=0)


def test_ei_is_non_decreasing_in_the_incumbent():
    """A worse incumbent leaves more room to improve: dEI/dV* = P(V <= V*) >= 0. Catches a
    reversed integration direction. Measured: no decrease anywhere on the grid."""
    Vs = np.linspace(0.0, 8.0, 201)
    settings = {
        "identity": (Target("a", 50.0, 0.3), [72.5, 47.0], [0.75, 19.5]),
        "log": (Target("a", 50.0, 0.3), [math.log(50) + 0.9, math.log(50) - 0.1], [0.02, 2.5]),
        "logit": (Target("a", 0.4, 0.3), [logit(0.4) + 1.2, logit(0.4) - 2.0], [0.05, 2.8]),
    }
    for tr, (t, mus, sds) in settings.items():
        for m in mus:
            for s in sds:
                ei = np.array([expected_improvement([[m]], [[s]], [t], [tr], v)[0] for v in Vs])
                assert np.all(np.diff(ei) >= 0.0), (tr, m, s)
                assert ei[-1] > 0.0


def test_ei_is_zero_without_integrating_when_the_incumbent_is_not_positive(monkeypatch):
    """No V can improve on V* <= 0. A guard-contract test: the early return must fire before
    any band probability is evaluated (removing it still returns 0 by clipping, which a value
    check alone could not see)."""
    def boom(*a, **k):
        raise AssertionError("band_probability evaluated for V* <= 0")
    monkeypatch.setattr(acq, "band_probability", boom)
    t = [Target("a", 10.0, 0.2)]
    for V in (0.0, -1.0):
        out = expected_improvement([[10.0], [12.0]], [[1.0], [0.5]], t, ["identity"], V)
        assert out.shape == (2,) and np.all(out == 0.0)


def test_ei_refuses_a_non_finite_incumbent_and_a_negative_observation():
    """Catches the removal of either guard: a NaN V* then surfaces as a RuntimeError about a
    non-finite result instead of a refusal naming the incumbent, and a negative observation,
    whose band edges are inverted, is scored without any error."""
    t = [Target("a", 10.0, 0.2)]
    for V in (float("nan"), float("inf"), None):
        with pytest.raises(ValueError, match="V_star"):
            expected_improvement([[10.0]], [[1.0]], t, ["identity"], V)
    with pytest.raises(ValueError, match="observed is -10.0 < 0"):
        expected_improvement([[-10.0]], [[1.0]], [Target("neg", -10.0, 0.2)], ["identity"], 1.0)
    with pytest.raises(ValueError, match="observed is -10.0 < 0"):
        sd_floor([Target("neg", -10.0, 0.2)], ["identity"])


def test_ei_refuses_a_non_finite_result_instead_of_returning_it(monkeypatch):
    """A NaN acquisition value is what np.argmax selects first, so a non-finite EI must raise,
    never be returned. The integrand is sabotaged at one node of one candidate, because every
    input check upstream already passes."""
    real = acq.band_probability

    def one_nan(mu, sd, lo, hi, transform):
        p = np.array(real(mu, sd, lo, hi, transform), dtype=float)
        p[1, 3] = np.nan
        return p

    monkeypatch.setattr(acq, "band_probability", one_nan)
    with pytest.raises(RuntimeError, match="non-finite for 1 of 3 candidates"):
        expected_improvement([[10.0], [11.0], [12.0]], [[1.0]] * 3, [Target("a", 10.0, 0.2)],
                             ["identity"], 1.0)


def test_ei_refuses_a_non_finite_posterior_mean_or_a_negative_sd():
    """Refused at entry with a message naming the input, rather than surfacing later as a
    non-finite result about the integral."""
    t = [Target("a", 10.0, 0.2)]
    for bad in (np.nan, np.inf):
        with pytest.raises(ValueError, match="mu has non-finite"):
            expected_improvement([[10.0], [bad]], [[1.0], [1.0]], t, ["identity"], 1.0)
    for bad in (np.nan, -1e-3):
        with pytest.raises(ValueError, match="sd must be finite and >= 0"):
            expected_improvement([[10.0], [11.0]], [[1.0], [bad]], t, ["identity"], 1.0)


def test_ei_chunks_stay_within_the_element_budget_with_graded_kinks(monkeypatch):
    """The chunk size is computed from a count of breakpoint columns before any is built, so a
    count that misses a column set (the kink grading adds 12 per graded kink) lets one chunk
    exceed the budget. Catches that drift: every chunk's (candidates x segments x nodes) array
    must fit, on a mix whose log and logit kinks are all graded, from below and from above."""
    ts = [Target("a", 389.0, 0.36), Target("b", 651.7, 0.35), Target("c", 0.6, 0.3),
          Target("d", 1.0, 0.3)]
    trs = ["identity", "log", "logit", "logit"]
    V = 3.5
    assert [[side for _, side in acq._graded_kinks(t.observed, t.uncertainty, tr, V)]
            for t, tr in zip(ts, trs)] == [[], [-1], [-1, -1], [-1, 1]]
    rng = np.random.default_rng(3)
    mu = np.column_stack([rng.normal(389.0, 120.0, 400), rng.normal(math.log(651.7), 0.8, 400),
                          rng.normal(logit(0.6), 1.5, 400), rng.normal(logit(0.9), 2.0, 400)])
    sd = np.column_stack([rng.uniform(5, 150, 400), rng.uniform(0.01, 2.5, 400),
                          rng.uniform(0.01, 2.5, 400), rng.uniform(0.01, 3.0, 400)])
    budget = 60_000.0
    monkeypatch.setattr(acq, "_EI_CHUNK_ELEMENTS", budget)
    sizes = []
    real = acq._breakpoints

    def spy(*args):
        bp = real(*args)
        sizes.append(bp.shape[0] * (bp.shape[1] - 1) * 16)
        return bp

    monkeypatch.setattr(acq, "_breakpoints", spy)
    expected_improvement(mu, sd, ts, trs, V)
    assert len(sizes) > 1 and max(sizes) <= budget, (len(sizes), max(sizes))


def test_sd_floor_scales_with_the_band_for_identity_only():
    """The identity floor is 1e-12 band-widths whatever the units; a fixed 1e-12 would be 1e-6
    band-widths on a target whose band is 1e-6 wide."""
    ts = [Target("a", 2e6, 0.25), Target("b", 1e-3, 0.5), Target("c", 0.4, 0.3)]
    np.testing.assert_allclose(sd_floor(ts, ["identity", "identity", "log"]),
                               [1e-12 * 0.25 * 2e6, 1e-12 * 0.5 * 1e-3, 1e-12], rtol=1e-15)
    np.testing.assert_allclose(sd_floor(ts, ["logit", "log", "logit"]), [1e-12] * 3, rtol=0)


def _spec(targets):
    return SurrogateSpec(name="align", use_mode="offline_search", tier="S1",
                         input_names=("x",), input_lower=(0.0,), input_upper=(1.0,),
                         targets=tuple(targets), provenance=Provenance(model="test_model"))


def test_check_alignment_refuses_a_reordered_renamed_or_differently_banded_spec():
    """Posterior columns are matched to bands by POSITION, so a reordered spec scores every
    target against another target's band. Catches the removal of the name check or of either
    band side's check, and a tolerance looser than the contracted relative 1e-9 (the bands are
    perturbed by 1e-8); the aligned spec (with one side undeclared) must pass."""
    ts = [Target("NPP", 389.0, 0.36), Target("Fs", 6.2, 0.28)]
    check_alignment(_spec([TargetSpec("NPP", 389.0, ts[0].lo, ts[0].hi),
                           TargetSpec("Fs", 6.2, None, ts[1].hi)]), ts)
    with pytest.raises(ValueError, match="names and order"):
        check_alignment(_spec([TargetSpec("Fs"), TargetSpec("NPP")]), ts)
    with pytest.raises(ValueError, match="names and order"):
        check_alignment(_spec([TargetSpec("NPP"), TargetSpec("F_s")]), ts)
    with pytest.raises(ValueError, match="names and order"):
        check_alignment(_spec([TargetSpec("NPP")]), ts)
    with pytest.raises(ValueError, match="'Fs': spec upper"):
        check_alignment(_spec([TargetSpec("NPP", 389.0, ts[0].lo, ts[0].hi),
                               TargetSpec("Fs", 6.2, ts[1].lo, ts[1].hi * (1 + 1e-8))]), ts)
    with pytest.raises(ValueError, match="'NPP': spec lower"):
        check_alignment(_spec([TargetSpec("NPP", 389.0, ts[0].lo * (1 - 1e-8), None),
                               TargetSpec("Fs", 6.2, None, None)]), ts)


def test_incumbent_is_the_best_VIABLE_finite_row():
    """Catches an incumbent taken over every row: a dead run never sets V*."""
    V = np.array([0.4, np.nan, 1.3, 0.9, 0.9, 0.2])
    viable = np.array([False, True, True, True, True, False])
    assert incumbent(V, viable) == (0.9, 3)
    with pytest.raises(ValueError, match="cold-start"):
        incumbent(V, np.zeros(6, bool))
    with pytest.raises(ValueError, match="cold-start"):
        incumbent([np.nan, np.inf], [True, True])


# =============================================================================
# Unit cube and candidates
# =============================================================================

def test_unit_cube_map_round_trips_and_refuses_a_fixed_parameter():
    lo, hi = np.array([0.5, -2.0, 10.0]), np.array([1.5, 2.0, 1010.0])
    X = np.array([[0.5, -2.0, 10.0], [1.5, 2.0, 1010.0], [1.0, 0.0, 510.0]])
    U = native_to_unit(X, lo, hi)
    np.testing.assert_allclose(U, [[0, 0, 0], [1, 1, 1], [0.5, 0.5, 0.5]], atol=1e-15)
    np.testing.assert_allclose(unit_to_native(U, lo, hi), X, rtol=1e-15)
    with pytest.raises(ValueError, match="fixed parameter"):
        native_to_unit(X, lo, np.array([1.5, -2.0, 1010.0]))


def test_sobol_candidates_refuse_a_non_power_of_two_and_are_seed_deterministic():
    """Catches a scan that silently loses Sobol' balance (scipy only warns), and an ignored seed."""
    for n in (0, 3, 1000, 4095):
        with pytest.raises(ValueError, match="power-of-two"):
            sobol_candidates(4, n, seed=0)
    a, b, c = (sobol_candidates(5, 256, seed=s) for s in (3, 3, 4))
    assert a.shape == (256, 5) and np.all((a >= 0) & (a < 1))
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)


def test_reflect_unit_folds_at_the_faces_and_is_the_identity_inside():
    """Catches clipping, which maps 1.2 to the face at 1.0 instead of 0.8."""
    np.testing.assert_allclose(reflect_unit([1.2, -0.3, 2.5, -1.7, 3.9, 4.0, -2.0]),
                               [0.8, 0.3, 0.5, 0.3, 0.1, 0.0, 0.0], atol=1e-12)
    inside = np.concatenate([[0.0, 1.0], np.random.default_rng(0).random(500)])
    assert np.array_equal(reflect_unit(inside), inside)
    wide = reflect_unit(np.random.default_rng(1).normal(0, 5, size=(200, 3)))
    assert np.all((wide >= 0) & (wide <= 1))


def test_local_candidates_centre_on_the_k_lowest_V_VIABLE_rows_only():
    """Catches centres chosen over every row (the three lowest-V rows are dead), centres taken
    from the wrong end of the ranking, and a NaN V treated as a centre."""
    rng = np.random.default_rng(5)
    U_obs = rng.random((30, 4))
    V = rng.uniform(1.0, 5.0, 30)
    V[[3, 7, 11]] = [0.1, 0.2, 0.3]
    viable = np.ones(30, bool)
    viable[[3, 7, 11]] = False
    V[20] = np.nan
    expected = set(np.flatnonzero(viable & np.isfinite(V))[
        np.argsort(V[viable & np.isfinite(V)])[:5]].tolist())

    U, labels = local_candidates(U_obs, V, viable, n_total=50, k=5, scales=(1e-4,), seed=2)
    assert U.shape == (50, 4) and set(labels.tolist()) == {"local_sd0.0001"}
    nearest = np.argmin(np.linalg.norm(U[:, None, :] - U_obs[None, :, :], axis=2), axis=1)
    assert set(nearest.tolist()) == expected
    assert np.all(np.bincount(nearest, minlength=30)[sorted(expected)] == 10)


def test_local_candidates_count_labels_and_the_empty_case():
    rng = np.random.default_rng(6)
    U_obs, V = rng.random((4, 3)), rng.random(4)
    U, labels = local_candidates(U_obs, V, np.ones(4, bool), n_total=100, k=10)
    per = math.ceil(100 / (4 * 3))
    assert U.shape == (4 * per * 3, 3)
    assert ([int((labels == f"local_sd{s}").sum()) for s in ("0.01", "0.03", "0.1")]
            == [4 * per] * 3)
    U0, l0 = local_candidates(U_obs, V, np.zeros(4, bool), n_total=100)
    assert U0.shape == (0, 3) and l0.shape == (0,)


def test_local_candidates_follow_the_seed_and_draw_independent_noise_at_each_scale():
    """Catches an ignored seed (a fixed or fresh generator: equal seeds must give equal sets and
    different seeds different ones), and a generator re-seeded for each scale, which draws the
    same standard-normal noise at every scale so the scales are perfectly correlated. Centres sit
    at 0.5 and scales are at most 3e-4, so no draw is reflected and `(U - 0.5) / scale` recovers
    the noise to about 1e-12; measured max |difference| between the two scales' noise 3.7 as
    built, 3.7e-13 with the per-scale re-seeding."""
    U_obs, V = np.full((3, 4), 0.5), np.array([1.0, 2.0, 3.0])
    viable = np.ones(3, bool)
    a, la = local_candidates(U_obs, V, viable, n_total=60, k=3, scales=(1e-4, 3e-4), seed=11)
    b, _ = local_candidates(U_obs, V, viable, n_total=60, k=3, scales=(1e-4, 3e-4), seed=11)
    c, _ = local_candidates(U_obs, V, viable, n_total=60, k=3, scales=(1e-4, 3e-4), seed=12)
    assert np.array_equal(a, b)
    assert not np.array_equal(a, c)
    noise = [(a[la == label] - 0.5) / s for label, s in (("local_sd0.0001", 1e-4),
                                                         ("local_sd0.0003", 3e-4))]
    assert noise[0].shape == noise[1].shape == (30, 4)
    assert np.all(np.abs(a - 0.5) < 0.01), "a draw was reflected; the noise is not recoverable"
    assert np.max(np.abs(noise[0] - noise[1])) > 0.5


def test_local_candidates_put_almost_no_coordinate_exactly_on_a_face():
    """Catches clipping instead of reflection. Measured on this fixture: 0% of rows with an
    exact-face coordinate under reflection, 28.7% under clipping (51.5% at sd 0.1)."""
    rng = np.random.default_rng(0)
    U_obs, V = rng.random((50, 8)), rng.random(50)
    U, _ = local_candidates(U_obs, V, np.ones(50, bool), n_total=600, seed=1)
    on_face = np.any((U == 0.0) | (U == 1.0), axis=1)
    assert np.all((U >= 0) & (U <= 1))
    assert on_face.mean() <= 0.01, f"{on_face.mean():.1%} of local candidates sit on a face"


# =============================================================================
# Distances
# =============================================================================

def _brute_min_distance(A, B, metric):
    out = np.full(len(A), np.inf)
    for i, a in enumerate(A):
        for b in B:
            d = (np.max(np.abs(a - b)) if metric == "linf"
                 else math.sqrt(float(np.sum((a - b) ** 2))))
            out[i] = min(out[i], d)
    return out


def test_min_distance_equals_brute_force_under_any_budget_and_chunks_more_as_it_shrinks(
        monkeypatch):
    """Catches a chunk step that ignores the dimension or the second matrix, so the pairwise
    array exceeds the element budget (budget 60 on 23 x 5 rows builds 115 elements), and a
    chunked minimum that differs from the unchunked one."""
    rng = np.random.default_rng(9)
    A, B = rng.random((37, 5)), rng.random((23, 5))
    sizes = []
    real = acq._pairwise

    def spy(a, b, metric):
        sizes.append(a.shape[0] * b.shape[0] * a.shape[1])
        return real(a, b, metric)

    monkeypatch.setattr(acq, "_pairwise", spy)
    counts = []
    for budget in (1e6, 400.0, 60.0, 5.0):
        for metric in ("linf", "euclidean"):
            sizes.clear()
            got = min_distance(A, B, metric=metric, budget=budget)
            np.testing.assert_allclose(got, _brute_min_distance(A, B, metric), rtol=1e-14)
            assert max(sizes) <= budget, (budget, max(sizes))
        counts.append(len(sizes))
    assert counts == sorted(counts) and len(set(counts)) == len(counts), counts
    assert np.all(np.isinf(min_distance(A, np.empty((0, 5)))))


def test_min_distance_and_maximin_refuse_None_and_non_finite_coordinates():
    """`np.asarray(None, dtype=float)` is a NaN scalar, so an unguarded None `B` with one column
    gives NaN distances, and a maximin whose picks then come out in index order ([0, 1, 2, 3]
    below instead of [0, 2, 1, 3]). A NaN coordinate likewise has no distance to anything."""
    U = np.array([[0.1], [0.5], [0.9], [0.3]])
    assert maximin_batch(U, np.empty((0, 1)), 4).tolist() == [0, 2, 1, 3]
    with pytest.raises(ValueError, match="None"):
        min_distance(U, None)
    with pytest.raises(ValueError, match="U_anchor is None"):
        maximin_batch(U, None, 4)
    with pytest.raises(ValueError, match="finite"):
        min_distance(U, np.array([[0.2], [np.nan]]))
    with pytest.raises(ValueError, match="finite"):
        min_distance(np.array([[np.inf]]), U)
    with pytest.raises(ValueError, match="finite"):
        maximin_batch(U, np.array([[np.nan]]), 2)


def test_density_radius_is_the_median_kth_nearest_OTHER_candidate():
    """Catches counting a candidate as its own nearest neighbour (distance 0) and an off-by-one
    k. On a larger set the same statistic is taken over the seeded subsample."""
    def brute(U, k):
        kth = []
        for i in range(len(U)):
            d = sorted(np.max(np.abs(U[i] - U[j])) for j in range(len(U)) if j != i)
            kth.append(d[min(k, len(U) - 1) - 1])
        return float(np.median(kth))

    rng = np.random.default_rng(11)
    U = rng.random((60, 3))
    for k in (1, 3, 10):
        assert density_radius(U, k=k) == pytest.approx(brute(U, k), rel=1e-15)


def test_density_radius_subsamples_the_queries_but_searches_every_candidate_for_neighbours():
    """docs/45 section 4.5 defines the radius over the candidate set, so the subsample may bound
    the number of QUERIES only. Catches neighbours searched within the subsample, which inflates
    the radius by about (n / max_rows)^(1/p): measured 2.27 times here (n/max_rows = 4096/64, p = 6,
    about 2.0 expected), against an exact match for the full search."""
    rng = np.random.default_rng(12)
    big = rng.random((4096, 6))
    rows = np.sort(np.random.default_rng(4).choice(4096, 64, replace=False))
    kth = []
    for i in rows:
        d = np.max(np.abs(big - big[i]), axis=1)
        d[i] = np.inf
        kth.append(np.sort(d)[4])
    assert density_radius(big, k=5, max_rows=64, seed=4) == pytest.approx(np.median(kth), rel=1e-15)
    with pytest.raises(ValueError, match="finite"):
        density_radius(np.array([[0.1, 0.2], [np.nan, 0.3], [0.5, 0.5]]), k=1)


# =============================================================================
# Batch pickers
# =============================================================================

def _brute_maximin(U, anchors, q, w, adm):
    adm = adm.copy()
    picks = []
    for _ in range(q):
        best, best_j = -np.inf, None
        refs = list(anchors) + [U[i] for i in picks]
        for j in range(len(U)):
            if not adm[j]:
                continue
            score = w[j] if not refs else w[j] * min(
                math.sqrt(float(np.sum((U[j] - r) ** 2))) for r in refs)
            if score > best:
                best, best_j = score, j
        if best_j is None:
            break
        picks.append(best_j)
        adm[best_j] = False
    return picks


def test_maximin_batch_equals_brute_force_greedy_with_weights_admissibility_and_anchors():
    """Catches a maximin that leaves the anchors (observed rows) out of the distance, ignores the
    weights or the admissible mask, or spaces picks by L-inf instead of Euclidean distance."""
    rng = np.random.default_rng(13)
    for rep in range(6):
        U = rng.random((80, 4))
        anchors = rng.random((0 if rep == 0 else 15, 4))
        w = rng.uniform(0.2, 1.0, 80) if rep % 2 else np.ones(80)
        adm = rng.random(80) > 0.3
        got = maximin_batch(U, anchors, 7, weights=w, admissible=adm)
        assert got.tolist() == _brute_maximin(U, anchors, 7, w, adm), rep


def test_maximin_batch_ties_go_to_the_lowest_index_and_the_batch_stops_when_candidates_run_out():
    U = np.array([[0.0, 0.0], [1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    assert maximin_batch(U, [[0.5, 0.5]], 4).tolist() == [0, 1, 2, 3]      # every step a tie
    assert maximin_batch(U, np.empty((0, 2)), 4).tolist() == [0, 3, 1, 2]
    assert maximin_batch(U, np.empty((0, 2)), 1, weights=[1.0, 3.0, 3.0, 2.0]).tolist() == [1]
    got = maximin_batch(U, [[0.5, 0.5]], 10, admissible=[True, False, True, False])
    assert got.tolist() == [0, 2]


# The picker as it stood before the fix, copied verbatim, so the fix is measured against it.
def _old_greedy_batch(pool, cand, a, q):
    Z = (pool.X[cand] - pool.X.mean(0)) / np.where(pool.X.std(0) > 0, pool.X.std(0), 1.0)
    a = a.astype(float).copy()
    out = []
    for _ in range(min(q, len(cand))):
        i = int(np.argmax(a))
        out.append(cand[i])
        d = np.linalg.norm(Z - Z[i], axis=1)
        a *= 1.0 - np.exp(-0.5 * (d / max(np.median(d), 1e-9)) ** 2)
        a[i] = -np.inf
    return np.array(out)


def _pool(X):
    n = len(X)
    return Pool(cases=np.arange(1, n + 1), X=np.asarray(X, float), Yt=np.zeros((n, 1)),
                V=np.ones(n), viable=np.ones(n, bool), targets=[Target("a", 1.0, 0.1)])


def test_local_penalisation_never_repeats_a_coordinate_and_reports_the_shortfall():
    """A taken pick's twin gets penalty 0, and `-inf * 0 = nan` made the old picker select the
    taken index again. Catches a mask applied before the penalty and a picker that keeps an
    exact twin of a pick admissible."""
    X = [[0.0], [0.0], [1.0], [1.0]]
    a = np.array([1.0, 0.5, 0.8, 0.4])
    with np.errstate(invalid="ignore"):
        old = _old_greedy_batch(_pool(X), np.arange(4), a, 4)
    assert old.tolist() == [0, 2, 1, 0], "the frozen old picker no longer shows the defect"

    Z = np.array(X)
    idx, shortfall = local_penalisation_batch(Z, a, 4)
    assert idx.tolist() == [0, 2] and shortfall == 2
    assert len({tuple(Z[i]) for i in idx}) == len(idx)
    assert _greedy_batch(_pool(X), np.arange(4), a, 4).tolist() == [0, 2]

    idx, shortfall = local_penalisation_batch(np.array([[0.0], [0.5], [2.0]]),
                                              [1.0, 0.9, 0.1], 3, min_separation=0.6)
    assert idx.tolist() == [0, 2] and shortfall == 1
    idx, shortfall = local_penalisation_batch(np.array([[0.0], [1.0], [2.0]]),
                                              [-np.inf, 0.2, -np.inf], 3)
    assert idx.tolist() == [1] and shortfall == 2
    with pytest.raises(ValueError, match="1 NaN and 0 \\+inf"):
        local_penalisation_batch(Z, [np.nan, 1.0, 0.5, 0.2], 2)
    with pytest.raises(ValueError, match="0 NaN and 1 \\+inf"):
        local_penalisation_batch(Z, [np.inf, 1.0, 0.5, 0.2], 2)


def test_local_penalisation_measures_min_separation_as_a_euclidean_distance_in_Z():
    """In 1-D every metric agrees, so the metric is only testable in more dimensions. Candidate 1
    is 0.707 from the first pick in Euclidean distance but 0.5 in L-inf (and 0.5 squared), so with
    min_separation 0.6 it stays admissible, and outranks candidate 2 after the penalty, only when
    the separation is Euclidean. Catches an L-inf or squared-distance separation, which drops
    candidate 1 and returns [0, 2] with a shortfall of 1."""
    Z = np.array([[0.0, 0.0], [0.5, 0.5], [3.0, 3.0]])
    idx, shortfall = local_penalisation_batch(Z, [1.0, 0.9, 0.1], 3, min_separation=0.6)
    assert idx.tolist() == [0, 1, 2] and shortfall == 0
    idx, shortfall = local_penalisation_batch(Z, [1.0, 0.9, 0.1], 3, min_separation=0.8)
    assert idx.tolist() == [0, 2] and shortfall == 1


def test_local_penalisation_refuses_a_non_finite_coordinate():
    """A NaN row's distance to a pick is NaN, the median of the distances is then NaN, and
    `max(nan, 1e-9)` is NaN, so every penalised alpha becomes NaN and the picks fall back to index
    order: [0, 2, 3] below, dropping row 1 and ignoring that alpha ranks row 3 above row 2.
    Catches the missing guard."""
    Z = np.array([[0.0, 0.0], [np.nan, 0.5], [1.0, 1.0], [2.0, 0.0]])
    with pytest.raises(ValueError, match="non-finite coordinates in 1 row"):
        local_penalisation_batch(Z, [1.0, 0.9, 0.2, 0.8], 4)
    Z[1] = [np.inf, 0.5]
    with pytest.raises(ValueError, match="non-finite coordinates in 1 row"):
        local_penalisation_batch(Z, [1.0, 0.9, 0.2, 0.8], 4)
    Z[1] = [5.0, 5.0]
    assert local_penalisation_batch(Z, [1.0, 0.9, 0.2, 0.8], 4)[0].tolist() == [0, 1, 3, 2]


def test_the_replay_picker_returns_exactly_the_old_picks_on_distinct_coordinates():
    """The fix concerns duplicated coordinates only, so the wrapper must not move a single replay
    pick where coordinates are distinct. Candidates are a strict subset of the pool, so a wrapper
    standardising by the candidates instead of the pool is caught (fixture 4 differs). The second
    loop adds a near twin of every other candidate at 1e-4 standardised units and draws the whole
    candidate set, so a wrapper passing any min_separation above 1e-4 drops a twin the old picker
    takes (measured: 2e-4 and 0.05 each drop 20 of the 40 picks on every fixture)."""
    for seed in range(20):
        rng = np.random.default_rng(seed)
        pool = _pool(rng.random((60, 3)))
        cand = np.sort(rng.choice(60, 25, replace=False))
        a = rng.random(25)
        Z = (pool.X[cand] - pool.X.mean(0)) / pool.X.std(0)
        d = np.linalg.norm(Z[:, None] - Z[None], axis=2)[np.triu_indices(25, 1)]
        assert d.min() > 1e-6 * np.median(d)
        assert np.array_equal(_greedy_batch(pool, cand, a, 8),
                              _old_greedy_batch(pool, cand, a, 8)), seed

    for seed in range(20):
        rng = np.random.default_rng(100 + seed)
        base = rng.random((20, 3))
        sd = base.std(0)
        step = rng.normal(size=base.shape)
        twins = base + 1e-4 * sd * step / np.linalg.norm(step, axis=1, keepdims=True)
        pool = _pool(np.vstack([base, twins]))
        cand = np.arange(40)
        a = rng.random(40)
        old = _old_greedy_batch(pool, cand, a, 40)
        new = _greedy_batch(pool, cand, a, 40)
        assert sorted(old.tolist()) == list(range(40)), seed
        assert np.array_equal(new, old), seed


# =============================================================================
# propose_batch: scoring, admissibility, batching and cold start
# =============================================================================

_quiet = pytest.mark.filterwarnings("ignore::sklearn.exceptions.ConvergenceWarning",
                                    "ignore:.*unstamped provenance")


def _search_spec(names, obs, transforms=None, p=2, lower=None, upper=None):
    transforms = transforms or ["identity"] * len(names)
    return SurrogateSpec(
        name="search", use_mode="offline_search", tier="S1",
        input_names=tuple(f"x{i + 1}" for i in range(p)),
        input_lower=tuple(lower if lower is not None else [0.0] * p),
        input_upper=tuple(upper if upper is not None else [1.0] * p),
        targets=tuple(TargetSpec(n, float(o), transform=tr)
                      for n, o, tr in zip(names, obs, transforms)),
        provenance=Provenance(model="test_model"))


def _fit_gp(spec, X, Y, viable=None):
    viable = np.ones(len(X), bool) if viable is None else viable
    return S1Surrogate(spec, learner=GPLearner(n_restarts=0), classifier="rf",
                       calibration_fraction=0).fit(X, Y, viable)


def _V(Y, targets):
    obs = np.array([t.observed for t in targets])
    u = np.array([t.uncertainty for t in targets])
    return np.max(np.abs(np.asarray(Y) - obs) / (u * obs), axis=1)


def _box_f(X):
    return np.column_stack([np.exp(2 * X[:, 0]), 1 + 2 * X[:, 1] + 0.3 * np.sin(5 * X[:, 1])])


def _box_problem():
    """docs/45 test 1: observed at x = (0.75, 0.25) with u = (0.06, 0.0375), a feasible box of
    0.33% of the unit square."""
    obs = _box_f(np.array([[0.75, 0.25]]))[0]
    ts = [Target("y1", obs[0], 0.06), Target("y2", obs[1], 0.0375)]
    return ts, _search_spec(["y1", "y2"], obs)


def _candidates(X_unit, V, viable, n_cand, seed):
    """The candidate set `propose_batch` scores: the scan, then the local set."""
    U_loc, _ = local_candidates(X_unit, V, viable, n_total=n_cand, seed=seed + 1)
    return np.vstack([sobol_candidates(X_unit.shape[1], n_cand, seed), U_loc])


def _ball(P, r):
    """Most picks inside any pick's closed L-inf ball of radius r (the pick itself included)."""
    return int((np.max(np.abs(P[:, None, :] - P[None, :, :]), axis=2) <= r).sum(axis=1).max())


#: Bounds on which unit and native coordinates differ in both offset and scale per dimension.
_LO, _HI = np.array([10.0, -5.0]), np.array([30.0, 45.0])


def _scaled_box_problem():
    """The box problem on bounds `_LO`-`_HI`: native `_LO + u (_HI - _LO)` has the targets the
    unit problem has at u, so fixtures are built in unit coordinates and fitted natively."""
    ts, _ = _box_problem()
    return ts, _search_spec(["y1", "y2"], [t.observed for t in ts], lower=_LO, upper=_HI)


def _believe_spy(model, calls):
    """A copy of `model` whose `believe`, and every believed copy's, appends its argument to
    `calls` and then conditions exactly as `S1Surrogate.believe` does."""
    def install(m):
        def believe(X_new):
            calls.append(np.array(X_new, dtype=float))
            return install(S1Surrogate.believe(m, X_new))
        m.believe = believe
        return m
    return install(copy.copy(model))


# -----------------------------------------------------------------------------
# Test 1: sequential search on a 2-D problem with a known feasible box
# -----------------------------------------------------------------------------

@_quiet
@pytest.mark.parametrize("arm", ["correct", "alpha_constant", "improvement_sign_flipped"])
def test_sequential_search_reaches_a_small_feasible_box_and_broken_acquisitions_do_not(
        arm, monkeypatch):
    """docs/42 test 1, pinned by docs/45 section 5: 5 uniform initial points per replicate, q = 1,
    24 evaluations, n_cand 512, a fresh Sobol' seed each iteration, 10 replicates. Bars: at least
    9/10 replicates reach the box (best V <= 1) AND median best V <= 0.6. Measured on the built
    code: correct 10/10, median 0.008; alpha constant 3/10, median 2.742; improvement sign flipped
    (alpha = P(viable) E[max(0, V - V*)]) 1/10, median 4.503. Each broken arm misses both bars, so
    the test catches an acquisition that ignores the posterior or rewards a worse V."""
    real = acq.expected_improvement
    if arm == "alpha_constant":
        monkeypatch.setattr(acq, "expected_improvement",
                            lambda mu, sd, targets, transforms, V_star, n_nodes=16:
                            np.ones(len(mu)))
    elif arm == "improvement_sign_flipped":
        def flipped(mu, sd, targets, transforms, V_star, n_nodes=16):
            # E[max(0, V - V*)] = E[V] - V* + E[max(0, V* - V)], and E[V] = B - E[max(0, B - V)]
            # for any B no posterior draw of V exceeds.
            big = 1e4
            return (real(mu, sd, targets, transforms, V_star)
                    - real(mu, sd, targets, transforms, big) + (big - V_star))
        monkeypatch.setattr(acq, "expected_improvement", flipped)

    ts, spec = _box_problem()
    best = []
    for rep in range(10):
        X = np.random.default_rng(rep).random((5, 2))
        Y = _box_f(X)
        for it in range(19):
            prop = propose_batch(_fit_gp(spec, X, Y), ts, [0, 0], [1, 1], X, _V(Y, ts),
                                 np.ones(len(X), bool), q=1, n_cand=512, seed=rep * 1000 + it)
            assert len(prop.unit) == 1, (arm, rep, it, prop.status)
            X = np.vstack([X, prop.native])
            Y = np.vstack([Y, _box_f(prop.native)])
        best.append(_V(Y, ts).min())
    best = np.array(best)
    reached, median = int((best <= 1.0).sum()), float(np.median(best))
    meets_bars = reached >= 9 and median <= 0.6
    if arm == "correct":
        assert meets_bars, (reached, median)
    else:
        assert not meets_bars, (arm, reached, median)


# -----------------------------------------------------------------------------
# Test 2: a batch on an infeasible target must not concentrate
# -----------------------------------------------------------------------------

def _interior_problem():
    ts = [Target("y1", math.exp(1.5), 0.12), Target("y2", 1.0, 0.2)]
    return ts, _search_spec(["y1", "y2"], [math.exp(1.5), 1.0])


def _interior_f(X):
    return np.column_stack([np.exp(2 * X[:, 0]),
                            3 + 4 * ((X[:, 0] - 0.4) ** 2 + (X[:, 1] - 0.6) ** 2)])


@_quiet
@pytest.mark.parametrize("noise", [0.0, 0.03])
def test_a_batch_against_an_infeasible_target_does_not_concentrate(noise):
    """docs/42 test 2, pinned by docs/45 section 5: y2 >= 3 against a band around 1, so no point
    is feasible and alpha peaks in one interior basin; 20 training points, with and without
    observation noise of 3% of each band's half-width, seeds 0-19, q = 5, n_cand 1024.
    Concentration is the most picks inside any pick's L-inf ball of the `r_sep` the guard used;
    the bar is at most 2 of 5. Catches a missing diversity guard (`r_sep = 0`) and a batch of the
    greedy top-q by alpha (no conditioning, no guard). Measured, both noise levels: correct 20/20
    seeds within the bar (every ball holds 1 pick); guard disabled and greedy top-q each 0/20.
    Every pick binds on y2. Noise-free, 15 of 100 picks are maximin after the believer's alpha
    collapses; with noise all 100 are argmax."""
    ts, spec = _interior_problem()
    obs = np.array([t.observed for t in ts])
    u = np.array([t.uncertainty for t in ts])
    over_bar = {"correct": 0, "guard_disabled": 0, "greedy_top_q": 0}
    for seed in range(20):
        X = np.random.default_rng(seed).random((20, 2))
        Y = _interior_f(X)
        if noise:
            Y = Y + np.random.default_rng(1000 + seed).standard_normal(Y.shape) * noise * u * obs
        V = _V(Y, ts)
        model = _fit_gp(spec, X, Y)
        prop = propose_batch(model, ts, [0, 0], [1, 1], X, V, np.ones(20, bool), q=5,
                             n_cand=1024, seed=seed)
        r = prop.r_sep
        assert prop.status == "ok" and len(prop.unit) == 5 and r > 0, (seed, prop.status)
        assert prop.binding.tolist() == ["y2"] * 5, (seed, prop.binding)
        src = prop.pick_source.tolist()
        n_arg = src.count("argmax")
        assert n_arg >= 1 and src == ["argmax"] * n_arg + ["maximin"] * (5 - n_arg), (seed, src)
        if noise:
            assert n_arg == 5, (seed, src)
        over_bar["correct"] += _ball(prop.unit, r) > 2

        off = propose_batch(model, ts, [0, 0], [1, 1], X, V, np.ones(20, bool), q=5,
                            n_cand=1024, seed=seed, r_sep=0.0)
        over_bar["guard_disabled"] += _ball(off.unit, r) > 2

        U = _candidates(X, V, np.ones(20, bool), 1024, seed)
        sc = score_candidates(model, ts, U, [0, 0], [1, 1], prop.V_star)
        adm = np.flatnonzero((min_distance(U, X) > 1e-6) & sc["in_hull"])
        top = adm[np.argsort(-sc["alpha"][adm], kind="stable")[:5]]
        over_bar["greedy_top_q"] += _ball(U[top], r) > 2
    assert over_bar["correct"] == 0, over_bar
    assert over_bar["guard_disabled"] >= 18 and over_bar["greedy_top_q"] >= 18, over_bar


# -----------------------------------------------------------------------------
# Test 3: every observation failed, so never propose blindly
# -----------------------------------------------------------------------------

def _greedy_maximin_reference(C, anchors, q, weights=None):
    """Greedy maximin written with loops: each step the candidate maximising
    weight * (Euclidean distance to the nearest anchor or earlier pick), lowest index on ties."""
    w = np.ones(len(C)) if weights is None else np.asarray(weights, float)
    refs = [np.asarray(a, float) for a in anchors]
    picks = []
    for _ in range(q):
        best, best_j = -1.0, None
        for j in range(len(C)):
            if j in picks:
                continue
            d = min(math.sqrt(float(np.dot(C[j] - r, C[j] - r))) for r in refs)
            if w[j] * d > best:
                best, best_j = w[j] * d, j
        picks.append(best_j)
        refs.append(C[best_j])
    return picks


def test_cold_start_with_every_observation_failed_is_greedy_maximin_away_from_the_failures():
    """docs/42 test 3, pinned by docs/45 section 5: p = 8, 20 uniform failures, q = 5,
    n_cand 4096, seed 0, no surrogate. The picks must EQUAL a greedy maximin over the same
    scrambled Sobol' points that counts the failures in the distance, which catches a maximin
    that leaves the failures out (it clears the percentile bar alone: 0.689 against 0.675), and
    their smallest nearest-failure distance must clear the 95th percentile of 400 seeded uniform
    5-sets, which catches the first q candidates (0.545). Measured as built: 1.052."""
    from scipy.stats import qmc

    p, q = 8, 5
    F = np.random.default_rng(0).random((20, p))
    prop = propose_batch(None, [Target("y", 1.0, 0.1)], np.zeros(p), np.ones(p), F,
                         np.full(20, np.nan), np.zeros(20, bool), q=q, n_cand=4096, seed=0)
    assert prop.status == "cold_start" and prop.batching == "cold_start:maximin"
    assert prop.pick_source.tolist() == ["maximin"] * q
    assert prop.in_hull.tolist() == [None] * q and np.isnan(prop.V_star)
    assert prop.V_star_index is None and prop.shortfall == 0
    assert prop.counts == {"n_candidates": 4096, "n_too_close": 0, "n_out_of_hull": 0,
                           "n_admissible": 4096}

    C = qmc.Sobol(d=p, scramble=True, seed=0).random(4096)
    got = [int(np.flatnonzero(np.all(C == u, axis=1))[0]) for u in prop.unit]
    assert got == _greedy_maximin_reference(C, F, q)

    def nearest_failure(P):
        return float(np.sqrt(((P[:, None, :] - F[None, :, :]) ** 2).sum(axis=2)).min())

    null = [nearest_failure(np.random.default_rng(s).random((q, p))) for s in range(400)]
    assert nearest_failure(prop.unit) >= np.quantile(null, 0.95)


@_quiet
def test_cold_start_weights_maximin_by_P_viable_when_both_outcomes_were_observed():
    """docs/45 section 4.6. With no surrogate and both outcomes observed, maximin is weighted by
    an rf classifier fitted on every observed row (seeded by the proposal seed); with a surrogate
    and 2-3 viable rows, by the surrogate's own P(viable). Catches a cold start that ignores
    P(viable) and proposes pure maximin into the failed region (the picks then differ), and one
    that uses the wrong source of P(viable)."""
    ts, spec = _box_problem()
    rng = np.random.default_rng(21)
    X = rng.random((30, 2))
    viable = X[:, 0] + X[:, 1] < 0.9
    Y = np.where(viable[:, None], _box_f(X), np.nan)
    V = np.where(viable, _V(np.nan_to_num(Y, nan=1.0), ts), np.nan)
    assert viable.sum() >= 4

    prop = propose_batch(None, ts, [0, 0], [1, 1], X, V, viable, q=4, n_cand=256, seed=5)
    assert prop.batching == "cold_start:feasibility_maximin(acquisition_classifier)"
    C = sobol_candidates(2, 256, 5)
    clf = make_classifier("rf", random_state=5).fit(X, viable.astype(int))
    w = clf.predict_proba(C)[:, list(clf.classes_).index(1)]
    assert (w > 0).sum() >= 4
    ref = _greedy_maximin_reference(C, X, 4, weights=w)
    assert np.array_equal(prop.unit, C[ref])
    np.testing.assert_allclose(prop.p_viable, w[ref], rtol=0, atol=0)
    assert ref != _greedy_maximin_reference(C, X, 4)

    keep = np.flatnonzero(viable)[:3]
    few = viable.copy()
    few[np.flatnonzero(viable)[3:]] = False
    model = _fit_gp(spec, X, np.where(few[:, None], _box_f(X), np.nan), few)
    V3 = np.where(few, V, np.nan)
    prop3 = propose_batch(model, ts, [0, 0], [1, 1], X, V3, few, q=4, n_cand=256, seed=5)
    assert prop3.batching == "cold_start:feasibility_maximin(surrogate_viability)"
    w3 = model.viability(C)
    assert (w3 > 0).sum() >= 4
    ref3 = _greedy_maximin_reference(C, X, 4, weights=w3)
    assert np.array_equal(prop3.unit, C[ref3])
    np.testing.assert_allclose(prop3.p_viable, w3[ref3], rtol=0, atol=0)
    assert ref3 != _greedy_maximin_reference(C, X, 4)
    assert prop3.V_star == V[keep].min() and prop3.status == "cold_start"


# -----------------------------------------------------------------------------
# Test 8: alpha = P(viable) x EI, not EI, drives the picks
# -----------------------------------------------------------------------------

class _LinearViability:
    """A classifier stub: P(viable) = x1, with predict_proba columns in `classes_` order."""

    def __init__(self, classes):
        self.classes_ = np.array(classes)

    def predict_proba(self, X):
        p1 = np.clip(np.asarray(X)[:, 0], 0.0, 1.0)
        return np.column_stack([p1 if c == 1 else 1.0 - p1 for c in self.classes_])


@_quiet
@pytest.mark.parametrize("classes", [[0, 1], [1, 0]])
def test_picks_follow_P_viable_times_EI_not_EI_alone(classes):
    """y = 1 + 2 x1 against a band around 1, observed only at x1 >= 0.3, so EI is largest at
    x1 = 0, where the stub makes P(viable) = 0; alpha = x1 EI peaks near x1 = 0.15. The hull gate
    is opened so only alpha decides. Catches ranking by EI alone (the picks then sit at x1 < 0.05)
    and a P(viable) column taken regardless of `classes_` order. Measured as built: picks at
    x1 = 0.151-0.157 with EI 0.62-0.64, against a largest EI of 1.25 at x1 = 0."""
    ts = [Target("y", 1.0, 0.5)]
    spec = _search_spec(["y"], [1.0])
    rng = np.random.default_rng(8)
    X = np.column_stack([rng.uniform(0.3, 1.0, 30), rng.random(30)])
    Y = (1 + 2 * X[:, 0])[:, None]
    model = S1Surrogate(spec, learner=GPLearner(n_restarts=0),
                        calibration_fraction=0).fit(X, Y, np.ones(30, bool))
    model._clf = _LinearViability(classes)
    model._gate._threshold = np.inf
    prop = propose_batch(model, ts, [0, 0], [1, 1], X, _V(Y, ts), np.ones(30, bool), q=3,
                         n_cand=256, seed=0)
    assert np.all((prop.unit[:, 0] > 0.1) & (prop.unit[:, 0] < 0.2)), prop.unit
    assert prop.status == "ok" and prop.pick_source.tolist() == ["argmax"] * 3
    np.testing.assert_allclose(prop.p_viable, prop.unit[:, 0], rtol=1e-12)
    np.testing.assert_allclose(prop.alpha, prop.p_viable * prop.ei, rtol=1e-12)

    line = np.column_stack([np.linspace(0, 1, 101), np.full(101, 0.5)])
    sc = score_candidates(model, ts, line, [0, 0], [1, 1], prop.V_star)
    assert line[np.argmax(sc["ei"]), 0] < 0.05 and sc["alpha"][np.argmax(sc["ei"])] == 0.0
    assert np.all(prop.ei < 0.6 * sc["ei"].max())


# -----------------------------------------------------------------------------
# Test 10: hull exclusion and counts
# -----------------------------------------------------------------------------

@_quiet
def test_an_out_of_hull_argmax_is_reported_never_proposed_and_the_counts_add_up():
    """docs/42 section 6: an argmax outside the training hull is an extrapolation, not a
    proposal. A real fitted surrogate with its gate threshold set just below the unconstrained
    argmax's hull distance: that candidate must not be proposed, diagnostics must report it, and
    the counts must equal an independent recount. A threshold of -inf gives all_out_of_hull with
    no picks; a threshold admitting 3 candidates gives 3 distinct picks and a shortfall of 2.
    Catches admissibility that ignores `in_hull`. In the gated case, also catches a default
    `r_sep` derived from every candidate instead of the admissible ones, and a scan-versus-local
    diagnostic that ranks candidates the hull excluded (the excluded argmax is the best of its
    own set, so that set's best would stay at the excluded alpha)."""
    ts, spec = _box_problem()
    X = np.random.default_rng(10).random((12, 2))
    Y = _box_f(X)
    V = _V(Y, ts)
    model = _fit_gp(spec, X, Y)
    U = _candidates(X, V, np.ones(12, bool), 256, 0)
    labels = np.array(["sobol"] * 256 + local_candidates(X, V, np.ones(12, bool), n_total=256,
                                                         seed=1)[1].tolist())
    too_close = min_distance(U, X) <= 1e-6

    def propose(q=3, **kw):
        return propose_batch(model, ts, [0, 0], [1, 1], X, V, np.ones(12, bool), q=q,
                             n_cand=256, seed=0, **kw)

    model._gate._threshold = np.inf
    free = propose()
    top = free.diagnostics["unconstrained_argmax"]
    assert top["in_hull"] and np.array_equal(free.unit[0], U[top["index"]])

    model._gate._threshold = 0.999 * top["hull_distance"]
    gated = propose()
    dist, inside = model.hull(U)
    assert gated.counts == {"n_candidates": len(U), "n_too_close": int(too_close.sum()),
                            "n_out_of_hull": int((~inside).sum()),
                            "n_admissible": int((~too_close & inside).sum())}
    assert 0 < gated.counts["n_out_of_hull"] < len(U)
    moved = gated.diagnostics["unconstrained_argmax"]
    assert moved["index"] == top["index"] and not moved["in_hull"]
    assert moved["alpha"] == top["alpha"] and moved["hull_distance"] > model._gate.threshold
    assert not any(np.array_equal(u, U[top["index"]]) for u in gated.unit)
    assert gated.in_hull.tolist() == [True] * len(gated.unit) and len(gated.unit) == 3
    assert np.all(gated.hull_distance <= model._gate.threshold)
    assert np.all(gated.alpha < top["alpha"])

    admissible = ~too_close & inside
    assert admissible.sum() < len(U) - too_close.sum()
    assert gated.r_sep == density_radius(U[admissible], seed=0)
    alpha = score_candidates(model, ts, U, [0, 0], [1, 1], gated.V_star)["alpha"]
    sets = gated.diagnostics["scan_vs_local"]["sets"]
    assert set(sets) == {"sobol", "local", *labels[256:].tolist()}
    for label, entry in sets.items():
        member = admissible & ((labels != "sobol") if label == "local" else (labels == label))
        assert entry["n_admissible"] == int(member.sum()) > 0, label
        assert member[entry["best_index"]], label
        assert entry["best_alpha"] == pytest.approx(alpha[member].max(), rel=1e-12), label
    assert sets[labels[top["index"]]]["best_alpha"] < top["alpha"]

    model._gate._threshold = -np.inf
    none = propose()
    assert none.status == "all_out_of_hull" and none.batching == "none"
    assert none.unit.shape == (0, 2) and none.native.shape == (0, 2) and none.shortfall == 3
    assert none.counts["n_out_of_hull"] == none.counts["n_candidates"] == len(U)
    assert none.counts["n_admissible"] == 0
    assert none.diagnostics["unconstrained_argmax"]["alpha"] == top["alpha"]

    model._gate._threshold = float(np.sort(dist)[2])
    few = propose(q=5, r_sep=0.0)
    assert few.counts["n_admissible"] == 3 and len(few.unit) == 3 and few.shortfall == 2
    assert len({tuple(u) for u in few.unit}) == 3 and few.in_hull.tolist() == [True] * 3


# -----------------------------------------------------------------------------
# Test 11: the degenerate paths pick by maximin, never by an argmax over zeros
# -----------------------------------------------------------------------------

@_quiet
def test_degenerate_no_viable_probability_and_collapse_all_pick_by_maximin():
    """Three ways alpha stops ranking candidates, each with its own status: EI underflowing to 0
    everywhere (a posterior 5 band-widths out with sd 1e-6 band-widths), P(viable) = 0
    everywhere, and a believer whose EI collapses after pick 1 (status ok, collapse recorded at
    pick 2). The maximin picks must equal a loop-written greedy maximin over the admissible
    candidates, against the observed rows (and pick 1 after a collapse). Catches an argmax over
    zeros, which takes the lowest admissible indices instead, and a collapse maximin that leaves
    pick 1 out of its anchors: the collapse fixture keeps its observations out of a disk around
    the feasible box, so pick 1 lands in the largest hole, and passes r_sep = 0 so the guard does
    not remove pick 1's neighbours. There the maximin with and without pick 1 differ in all
    three picks."""
    ts, spec = _box_problem()
    X = np.random.default_rng(10).random((12, 2))
    Y = _box_f(X)
    V = _V(Y, ts)
    model = _fit_gp(spec, X, Y)
    obs = np.array([t.observed for t in ts])
    u = np.array([t.uncertainty for t in ts])
    U = _candidates(X, V, np.ones(12, bool), 256, 0)
    _, inside = model.hull(U)
    adm = np.flatnonzero((min_distance(U, X) > 1e-6) & inside)

    under = copy.copy(model)
    under.posterior = lambda Xq: (np.tile(obs * (1 + 5 * u), (len(Xq), 1)),
                                  np.tile(1e-6 * u * obs, (len(Xq), 1)))
    zero_p = copy.copy(model)
    zero_p.viability = lambda Xq: np.zeros(len(Xq))

    def propose(m):
        return propose_batch(m, ts, [0, 0], [1, 1], X, V, np.ones(12, bool), q=4, n_cand=256,
                             seed=0)

    ref = adm[_brute_maximin(U[adm], X, 4, np.ones(len(adm)), np.ones(len(adm), bool))]
    assert not np.array_equal(ref, adm[:4])
    for m, status, batching in ((under, "degenerate", "maximin_degenerate@1"),
                                (zero_p, "no_viable_probability",
                                 "maximin_no_viable_probability@1")):
        prop = propose(m)
        assert np.array_equal(prop.unit, U[ref]), status
        assert (prop.status, prop.batching) == (status, batching)
        assert prop.pick_source.tolist() == ["maximin"] * 4
        assert np.all(prop.alpha == 0.0)

    R = np.random.default_rng(0).random((400, 2))
    Xh = R[np.linalg.norm(R - [0.75, 0.25], axis=1) > 0.3][:12]
    Yh = _box_f(Xh)
    Vh = _V(Yh, ts)
    hole = _fit_gp(spec, Xh, Yh)
    off = Vh.min() + 5.0
    flat = copy.copy(hole)
    flat.posterior = lambda Xq: (np.tile(obs * (1 + off * u), (len(Xq), 1)),
                                 np.tile(1e-6 * u * obs, (len(Xq), 1)))
    collapsing = copy.copy(hole)
    collapsing.believe = lambda Xn: flat
    col = propose_batch(collapsing, ts, [0, 0], [1, 1], Xh, Vh, np.ones(12, bool), q=4,
                        n_cand=256, seed=0, r_sep=0.0)
    Uh = _candidates(Xh, Vh, np.ones(12, bool), 256, 0)
    sc = score_candidates(hole, ts, Uh, [0, 0], [1, 1], Vh.min())
    ok = (min_distance(Uh, Xh) > 1e-6) & sc["in_hull"]
    first = int(np.flatnonzero(ok)[np.argmax(sc["alpha"][ok])])
    rest = np.flatnonzero(ok & (np.max(np.abs(Uh - Uh[first]), axis=1) > 1e-6))
    ones, every = np.ones(len(rest)), np.ones(len(rest), bool)
    with_pick_1 = rest[_brute_maximin(Uh[rest], np.vstack([Xh, Uh[first]]), 3, ones, every)]
    without = rest[_brute_maximin(Uh[rest], Xh, 3, ones, every)]
    assert len(set(with_pick_1.tolist()) & set(without.tolist())) == 0
    assert np.array_equal(col.unit, np.vstack([Uh[first], Uh[with_pick_1]]))
    assert (col.status, col.batching) == ("ok", "kriging_believer+maximin_after_collapse@2")
    assert col.pick_source.tolist() == ["argmax", "maximin", "maximin", "maximin"]
    assert len({"degenerate", "no_viable_probability", col.status}) == 3


@_quiet
def test_the_collapse_switch_is_a_relative_floor_on_alpha_not_underflow_to_zero():
    """docs/45 section 4.5: the remaining picks turn to maximin once max alpha_j <= degenerate_rel
    (1e-6) times alpha_1, a relative floor, so the switch does not wait for alpha to underflow. A
    believer stub scales P(viable) by a constant c, so pick 2's alpha is c times the base alpha,
    with c chosen so the largest alpha the guard leaves is 0.5e-6 or 2e-6 times alpha_1. At
    0.5e-6 the batch collapses at pick 2 and its maximin picks equal a loop-written reference
    against the observed rows and pick 1 in UNIT coordinates; at 2e-6 pick 2 is still an argmax.
    alpha_1 is 2.41, outside [0.5, 2], so an absolute floor of 1e-6 disagrees with the relative
    one at one of the two ratios. The bounds are not the unit square, so collapse anchors taken
    in native units move the maximin picks. Catches a floor at alpha <= 0 and an absolute floor
    (neither collapses at pick 2 of the 0.5e-6 batch), a floor at the wrong scale such as
    degenerate_rel * alpha_1**2 (the 2e-6 batch collapses), and native collapse anchors."""
    ts, spec = _scaled_box_problem()
    span = _HI - _LO
    Xu = np.random.default_rng(10).random((12, 2))
    X, Y = _LO + Xu * span, _box_f(Xu)
    V = _V(Y, ts)
    model = _fit_gp(spec, X, Y)
    U = _candidates(Xu, V, np.ones(12, bool), 256, 0)
    alpha = score_candidates(model, ts, U, _LO, _HI, V.min())["alpha"]
    ok = np.flatnonzero((min_distance(U, Xu) > 1e-6) & model.hull(_LO + U * span)[1])
    first = int(ok[np.argmax(alpha[ok])])
    rest = ok[np.max(np.abs(U[ok] - U[first]), axis=1) > 0.05]
    alpha_1, left = float(alpha[first]), float(alpha[rest].max() / alpha[first])
    assert not 0.5 <= alpha_1 <= 2.0, alpha_1

    for ratio, q in ((0.5e-6, 3), (2e-6, 2)):
        c = ratio / left
        believed = copy.copy(model)
        believed.viability = lambda Xq, c=c: c * model.viability(Xq)
        stub = copy.copy(model)
        stub.believe = lambda Xn, b=believed: b
        prop = propose_batch(stub, ts, _LO, _HI, X, V, np.ones(12, bool), q=q, n_cand=256,
                             seed=0, r_sep=0.05)
        by_pick = prop.diagnostics["max_alpha_by_pick"]
        assert by_pick[1] / by_pick[0] == pytest.approx(ratio, rel=1e-6), by_pick
        np.testing.assert_allclose(prop.unit[0], U[first], rtol=0, atol=1e-12)
        if ratio < 1e-6:
            ref = rest[_greedy_maximin_reference(U[rest], np.vstack([Xu, U[first]]), 2)]
            assert (prop.status, prop.batching) == ("ok",
                                                    "kriging_believer+maximin_after_collapse@2")
            assert prop.pick_source.tolist() == ["argmax", "maximin", "maximin"]
            np.testing.assert_allclose(prop.unit[1:], U[ref], rtol=0, atol=1e-12)
        else:
            assert (prop.status, prop.batching) == ("ok", "kriging_believer")
            assert prop.pick_source.tolist() == ["argmax", "argmax"]
            assert prop.alpha[1] == pytest.approx(c * alpha[rest].max(), rel=1e-6)


@_quiet
def test_argmax_ties_go_to_the_lowest_candidate_index():
    """docs/45 section 4.5 step 2: ties go to the lowest candidate index, the Sobol' order being
    itself seeded. A stub posterior sitting on every observation with a one-band-width sd, and a
    constant P(viable), give every candidate exactly the same alpha (asserted), so pick 1 must be
    the first admissible candidate and pick 2, under a believer that changes nothing, the first
    admissible candidate outside the guard around pick 1. Catches an argmax that breaks ties
    toward the highest index."""
    ts, spec = _box_problem()
    X = np.random.default_rng(10).random((12, 2))
    Y = _box_f(X)
    V = _V(Y, ts)
    model = _fit_gp(spec, X, Y)
    obs = np.array([t.observed for t in ts])
    u = np.array([t.uncertainty for t in ts])
    flat = copy.copy(model)
    flat.posterior = lambda Xq: (np.tile(obs, (len(Xq), 1)), np.tile(u * obs, (len(Xq), 1)))
    flat.viability = lambda Xq: np.full(len(Xq), 0.5)
    flat.believe = lambda Xn: flat
    U = _candidates(X, V, np.ones(12, bool), 256, 0)
    sc = score_candidates(flat, ts, U, [0, 0], [1, 1], V.min())
    assert np.all(sc["alpha"] == sc["alpha"][0]) and sc["alpha"][0] > 0
    adm = np.flatnonzero((min_distance(U, X) > 1e-6) & sc["in_hull"])
    second = adm[np.max(np.abs(U[adm] - U[adm[0]]), axis=1) > 0.05][0]
    prop = propose_batch(flat, ts, [0, 0], [1, 1], X, V, np.ones(12, bool), q=2, n_cand=256,
                         seed=0, r_sep=0.05)
    assert (prop.status, prop.batching) == ("ok", "kriging_believer")
    assert prop.pick_source.tolist() == ["argmax", "argmax"]
    assert np.array_equal(prop.unit, U[[adm[0], second]])


# -----------------------------------------------------------------------------
# Test 12: one incumbent, the physics V*, for the whole batch
# -----------------------------------------------------------------------------

@_quiet
def test_every_pick_is_scored_against_the_physics_incumbent():
    """docs/45 decision 3.2 A. Pick 1 has a posterior-mean V below V*, so a believer update
    V* <- min(V*, V_mean) would lower the incumbent for pick 2. Checked two ways: the recorded
    V_star_used, and pick 2's alpha recomputed independently under the model believed at pick 1
    against the physics V*. Catches the canonical believer update of option 3.2 B."""
    ts, spec = _box_problem()
    X = np.random.default_rng(0).random((8, 2))
    Y = _box_f(X)
    V = _V(Y, ts)
    model = _fit_gp(spec, X, Y)
    prop = propose_batch(model, ts, [0, 0], [1, 1], X, V, np.ones(8, bool), q=4, n_cand=512,
                         seed=3)
    assert prop.V_star == V.min() and prop.V_star_index == int(np.argmin(V))
    assert prop.V_mean[0] < prop.V_star
    assert prop.V_star_used.tolist() == [V.min()] * 4
    believed = model.believe(prop.native[:1])
    again = score_candidates(believed, ts, prop.unit[1:2], [0, 0], [1, 1], V.min())
    np.testing.assert_allclose(again["alpha"], prop.alpha[1:2], rtol=1e-9)
    assert prop.status == "ok" and prop.pick_source.tolist() == ["argmax"] * 4


# -----------------------------------------------------------------------------
# Test 16: the scan-versus-local diagnostic
# -----------------------------------------------------------------------------

def _bowl_problem():
    """A narrow bowl centred in the largest hole of the 64-point scan of seed 0, observed on a
    ring at the hole's radius and at 20 random rows well outside it: `(ts, X, Y, model)`."""
    ts = [Target("y", 1.0, 0.02)]
    spec = _search_spec(["y"], [1.0])
    S = sobol_candidates(2, 64, 0)
    grid = np.stack(np.meshgrid(np.linspace(0.25, 0.75, 201), np.linspace(0.25, 0.75, 201)),
                    axis=-1).reshape(-1, 2)
    hole = min_distance(grid, S, "euclidean")
    c, radius = grid[np.argmax(hole)], float(hole.max())
    ang = np.linspace(0, 2 * np.pi, 7)[:-1] + 0.3
    ring = c + radius * np.column_stack([np.cos(ang), np.sin(ang)])
    R = np.random.default_rng(100).random((200, 2))
    X = np.vstack([R[np.linalg.norm(R - c, axis=1) > 2 * radius][:20], ring])
    Y = (1 + 30 * ((X - c) ** 2).sum(axis=1))[:, None]
    model = S1Surrogate(spec, learner=GPLearner(n_restarts=0),
                        calibration_fraction=0).fit(X, Y, np.ones(len(X), bool))
    return ts, X, Y, model


@_quiet
def test_scan_versus_local_diagnostic_shows_a_narrow_peak_the_scan_misses():
    """A bowl centred in the largest hole of a 64-point scan, observed on a ring at the hole's
    radius, so every scan point lies at or beyond the ring and only perturbations of the ring rows
    reach inside it. The recorded local/scan ratio of best admissible alpha must be far above 1
    (measured 1036). Catches a local set that returns its centres unperturbed: those duplicate
    observed rows, none is admissible, and the ratio is NaN."""
    ts, X, Y, model = _bowl_problem()
    prop = propose_batch(model, ts, [0, 0], [1, 1], X, _V(Y, ts), np.ones(len(X), bool), q=1,
                         n_cand=64, seed=0)
    d = prop.diagnostics["scan_vs_local"]
    assert d["sets"]["sobol"]["best_alpha"] > 0 and d["sets"]["local"]["n_admissible"] > 0
    assert d["ratio_local_to_scan"] > 10, d
    assert d["ratio_local_to_scan"] == d["sets"]["local"]["best_alpha"] / d["sets"]["sobol"][
        "best_alpha"]
    assert prop.candidate_set[0].startswith("local_sd")
    assert prop.alpha[0] == d["sets"]["local"]["best_alpha"]


# -----------------------------------------------------------------------------
# score_candidates fields, and the refusals
# -----------------------------------------------------------------------------

@_quiet
def test_score_candidates_maps_the_cube_and_reports_native_predictions_violation_and_sd_ratio():
    """Checked against the surrogate's own posterior at the NATIVE points: catches a missing
    unit-to-native map, a prediction left in log space, a V_mean or binding target computed off
    anything but the native prediction, and an sd ratio not taken against the training std in
    the fitted space."""
    ts = [Target("a", 2.0, 0.3), Target("b", 5.0, 0.4)]
    lower, upper = np.array([1.0, -1.0]), np.array([3.0, 2.0])
    spec = _search_spec(["a", "b"], [2.0, 5.0], ["identity", "log"], lower=lower, upper=upper)
    rng = np.random.default_rng(4)
    X = lower + rng.random((25, 2)) * (upper - lower)
    Y = np.column_stack([2 + 0.4 * X[:, 0] - 0.3 * X[:, 1],
                         np.exp(1 + 0.3 * X[:, 0] + 0.2 * X[:, 1])])
    model = _fit_gp(spec, X, Y)
    U = np.random.default_rng(5).random((40, 2))
    V_star = float(_V(Y, ts).min())
    sc = score_candidates(model, ts, U, lower, upper, V_star)

    native = lower + U * (upper - lower)
    mu, sd = model.posterior(native)
    np.testing.assert_allclose(sc["predicted"], np.column_stack([mu[:, 0], np.exp(mu[:, 1])]),
                               rtol=1e-12)
    V_ref, _, bind = violation_matrix(sc["predicted"], ["a", "b"], ts)
    np.testing.assert_allclose(sc["V_mean"], V_ref, rtol=1e-12)
    assert sc["binding"].tolist() == [["a", "b"][k] for k in bind]
    assert len(set(sc["binding"].tolist())) == 2
    np.testing.assert_allclose(sc["ei"], expected_improvement(mu, sd, ts, ["identity", "log"],
                                                              V_star), rtol=1e-12)
    np.testing.assert_allclose(sc["alpha"], sc["p_viable"] * sc["ei"], rtol=1e-12)
    tsd = [np.std(Y[:, 0]), np.std(np.log(Y[:, 1]))]
    np.testing.assert_allclose(sc["sd_ratio"], sd / tsd, rtol=1e-12)
    dist, inside = model.hull(native)
    assert np.array_equal(sc["hull_distance"], dist) and np.array_equal(sc["in_hull"], inside)


@_quiet
def test_propose_batch_refuses_a_non_GP_learner_on_every_path():
    """docs/42 section 3 and docs/45 decision 3.3 A: an rf spread is not a posterior std. The
    refusal must name the family and must not depend on which path would run, so it is checked
    with enough viable rows for the acquisition and with 3, where the cold start never touches
    the posterior. Catches a refusal left to `posterior()`, which the cold start skips."""
    ts, spec = _box_problem()
    X = np.random.default_rng(7).random((30, 2))
    Y = _box_f(X)
    V = _V(Y, ts)
    three = np.zeros(30, bool)
    three[:3] = True
    rf3 = S1Surrogate(spec, learner="rf", calibration_fraction=0).fit(
        X, np.where(three[:, None], Y, np.nan), three)
    with pytest.raises(ValueError, match=r"'rf'.*docs/42 section 3"):
        propose_batch(rf3, ts, [0, 0], [1, 1], X, np.where(three, V, np.nan), three, q=2,
                      n_cand=64)
    rf = S1Surrogate(spec, learner="rf", calibration_fraction=0).fit(X, Y, np.ones(30, bool))
    with pytest.raises(ValueError, match=r"'rf'.*docs/42 section 3"):
        propose_batch(rf, ts, [0, 0], [1, 1], X, V, np.ones(30, bool), q=2, n_cand=64)


@_quiet
def test_propose_batch_refuses_an_incumbent_the_regressors_never_trained_on():
    """Expected improvement over V* is only meaningful if the posterior has seen the row that
    set V*. The best row is appended after the fit, so no regressor holds it. Then only the y2
    regressor misses it: the y1 regressor of a fit on every row is kept, and the refusal must
    still fire and name y2 alone. Catches the missing `trains_on` check, which would score EI
    against a V* the posterior knows nothing about, and a check that passes when ANY regressor
    trained on the incumbent instead of every one."""
    ts, spec = _box_problem()
    X = np.random.default_rng(6).random((10, 2))
    X[-1] = [0.75, 0.25]
    Y = _box_f(X)
    V = _V(Y, ts)
    assert int(np.argmin(V)) == 9
    model = _fit_gp(spec, X[:-1], Y[:-1])
    with pytest.raises(ValueError, match="incumbent .*row 9.*not in the training set"):
        propose_batch(model, ts, [0, 0], [1, 1], X, V, np.ones(10, bool), q=2, n_cand=64)
    propose_batch(model, ts, [0, 0], [1, 1], X[:-1], V[:-1], np.ones(9, bool), q=2, n_cand=64)

    partial = _fit_gp(spec, X, Y)
    partial._models[1] = model._models[1]
    assert partial.trains_on(X[9]).tolist() == [True, False]
    with pytest.raises(ValueError, match=r"row 9.* regressor\(s\) for \['y2'\], so"):
        propose_batch(partial, ts, [0, 0], [1, 1], X, V, np.ones(10, bool), q=2, n_cand=64)


def _lp_linf_reference(Z, alpha, q, sep):
    """Local penalisation written with loops: the Euclidean penalty of `local_penalisation_batch`,
    with every candidate within `sep` (L-inf, inclusive) of a pick dropped after the penalty."""
    a = [float(x) for x in alpha]
    alive = [True] * len(Z)
    picks = []
    while len(picks) < q and any(alive):
        i = max((j for j in range(len(Z)) if alive[j]), key=lambda j: (a[j], -j))
        picks.append(i)
        d = [math.sqrt(float(np.sum((Z[j] - Z[i]) ** 2))) for j in range(len(Z))]
        med = max(float(np.median(d)), 1e-9)
        a = [a[j] * (1.0 - math.exp(-0.5 * (d[j] / med) ** 2)) for j in range(len(Z))]
        alive[i] = False
        for j in range(len(Z)):
            if float(np.max(np.abs(Z[j] - Z[i]))) <= sep:
                alive[j] = False
    return picks


@_quiet
@pytest.mark.parametrize("error", [ValueError, NotImplementedError])
@pytest.mark.parametrize("fixture", ["box_q4_n256", "bowl_q6_n64"])
def test_a_believe_failure_hands_the_remaining_picks_to_local_penalisation(fixture, error):
    """docs/45 section 4.5 fallback: when `believe()` raises, ValueError for a kernel matrix that
    is not positive definite or NotImplementedError for a learner that cannot condition without
    refitting, the batch continues with the fixed local-penalisation picker over the alpha of the
    last scoring, among the candidates the guard left, and says so. Its picks keep the same
    diversity guard as the argmax picks: pairwise more than `r_sep` apart in L-inf. Catches a
    fallback that lets either error escape, one that restarts from candidates the guard had
    dropped, and one that measures the guard radius as a Euclidean distance (the bowl, whose
    alpha is sharply peaked, then takes picks 0.072 apart in L-inf against r_sep 0.082) or drops
    it (0.030)."""
    if fixture == "box_q4_n256":
        ts, spec = _box_problem()
        X = np.random.default_rng(10).random((12, 2))
        Y = _box_f(X)
        model = _fit_gp(spec, X, Y)
        q, n_cand = 4, 256
    else:
        ts, X, Y, model = _bowl_problem()
        q, n_cand = 6, 64
    V = _V(Y, ts)
    viable = np.ones(len(X), bool)

    def refuse(Xn):
        raise error("believe: the regressor cannot condition on this point")

    failing = copy.copy(model)
    failing.believe = refuse
    prop = propose_batch(failing, ts, [0, 0], [1, 1], X, V, viable, q=q, n_cand=n_cand, seed=0)
    U = _candidates(X, V, viable, n_cand, 0)
    sc = score_candidates(model, ts, U, [0, 0], [1, 1], prop.V_star)
    ok = (min_distance(U, X) > 1e-6) & sc["in_hull"]
    first = int(np.flatnonzero(ok)[np.argmax(sc["alpha"][ok])])
    sep = max(prop.r_sep, 1e-6)
    rest = np.flatnonzero(ok & (np.max(np.abs(U - U[first]), axis=1) > sep))
    lp = _lp_linf_reference(U[rest], sc["alpha"][rest], q - 1, sep)
    assert np.array_equal(prop.unit, np.vstack([U[first], U[rest[lp]]]))
    assert prop.status == "ok" and prop.shortfall == 0
    assert prop.batching == "kriging_believer+local_penalisation_after_believe_failed@2"
    assert any(f"({error.__name__}:" in note for note in prop.notes), prop.notes
    assert prop.pick_source.tolist() == ["argmax"] + ["local_penalisation"] * (q - 1)
    linf = np.max(np.abs(prop.unit[:, None, :] - prop.unit[None, :, :]), axis=2)
    assert linf[np.triu_indices(q, 1)].min() > prop.r_sep > 0


@_quiet
def test_cold_start_fills_with_plain_maximin_once_no_candidate_has_P_viable_above_zero():
    """With a surrogate on 3 viable rows whose P(viable) is positive on only a few candidates,
    the weighted maximin takes those, then plain maximin (against the observed rows and those
    picks) fills the batch, and the batching label says where. Catches a batch cut short at the
    positive-weight candidates, and a weighted maximin that keeps zero-weight candidates, whose
    ties at score 0 go to the lowest index."""
    ts, spec = _box_problem()
    rng = np.random.default_rng(21)
    X = rng.random((30, 2))
    few = np.zeros(30, bool)
    few[np.flatnonzero(X[:, 0] + X[:, 1] < 0.9)[:3]] = True
    Y = np.where(few[:, None], _box_f(X), np.nan)
    V = np.where(few, _V(np.nan_to_num(Y, nan=1.0), ts), np.nan)
    model = copy.copy(_fit_gp(spec, X, Y, few))
    model.viability = lambda Xq: np.where(np.asarray(Xq)[:, 0] > 0.99, 0.5, 0.0)
    prop = propose_batch(model, ts, [0, 0], [1, 1], X, V, few, q=4, n_cand=256, seed=5)

    C = sobol_candidates(2, 256, 5)
    pos = np.flatnonzero(C[:, 0] > 0.99)
    assert 1 <= len(pos) < 4
    first = pos[_greedy_maximin_reference(C[pos], X, len(pos))]
    rest = np.setdiff1d(np.arange(256), first)
    fill = rest[_greedy_maximin_reference(C[rest], np.vstack([X, C[first]]), 4 - len(pos))]
    assert np.array_equal(prop.unit, C[np.concatenate([first, fill])])
    assert prop.shortfall == 0
    assert prop.batching == (f"cold_start:feasibility_maximin(surrogate_viability)"
                             f"+maximin_fill@{len(pos) + 1}")
    assert prop.p_viable.tolist() == [0.5] * len(pos) + [0.0] * (4 - len(pos))


# -----------------------------------------------------------------------------
# The classifier labels of a cold start without a surrogate
# -----------------------------------------------------------------------------

@_quiet
def test_the_cold_start_classifier_learns_the_viability_labels_not_the_finite_V_rows():
    """docs/45 section 4.6: the acquisition-owned classifier stands in for the surrogate's, which
    `S1Surrogate.fit` trains on the viability labels of every row. A viable row whose V is not
    finite (a completed run with a target missing) is not a viable OBSERVATION, so it does not
    count toward the path choice, but its viability label is known. Here 11 rows are viable and
    only 1 has a finite V. Catches labels taken from `viable & isfinite(V)`, which trains 10
    viable rows as failures (the picks then differ) and, when every row is viable, fits a
    classifier where plain maximin belongs."""
    ts, _ = _box_problem()
    X = np.random.default_rng(21).random((30, 2))
    viable = X[:, 0] + X[:, 1] < 0.9
    V = np.full(30, np.nan)
    V[np.flatnonzero(viable)[0]] = _V(_box_f(X[viable][:1]), ts)[0]
    assert viable.sum() >= 4 and np.isfinite(V).sum() == 1

    C = sobol_candidates(2, 256, 5)
    prop = propose_batch(None, ts, [0, 0], [1, 1], X, V, viable, q=4, n_cand=256, seed=5)
    assert prop.batching == "cold_start:feasibility_maximin(acquisition_classifier)"
    assert prop.diagnostics["n_viable"] == 1 and prop.V_star == np.nanmin(V)

    def weighted_reference(labels):
        clf = make_classifier("rf", random_state=5).fit(X, labels.astype(int))
        w = clf.predict_proba(C)[:, list(clf.classes_).index(1)]
        return C[_greedy_maximin_reference(C, X, 4, weights=w)]

    assert np.array_equal(prop.unit, weighted_reference(viable))
    assert not np.array_equal(prop.unit, weighted_reference(viable & np.isfinite(V)))

    everyone = propose_batch(None, ts, [0, 0], [1, 1], X, V, np.ones(30, bool), q=4,
                             n_cand=256, seed=5)
    assert everyone.batching == "cold_start:maximin"
    assert np.array_equal(everyone.unit, C[_greedy_maximin_reference(C, X, 4)])


#: case: (viable observations, extra keywords, status, batching)
_PATHS = {
    "4_viable": (4, {}, "ok", "kriging_believer"),
    "4_viable_min_viable_acquisition_5": (4, {"min_viable_acquisition": 5}, "cold_start",
                                          "cold_start:feasibility_maximin(surrogate_viability)"),
    "2_viable": (2, {}, "cold_start", "cold_start:feasibility_maximin(surrogate_viability)"),
    "1_viable": (1, {}, "cold_start", "cold_start:feasibility_maximin(acquisition_classifier)"),
}


@_quiet
@pytest.mark.parametrize("case", sorted(_PATHS))
def test_the_path_is_chosen_by_the_number_of_viable_observations(case):
    """docs/45 section 4.6, on one fixture with a fitted surrogate always passed. Exactly
    `min_viable_acquisition` (4) viable observations take the acquisition path; 4 with
    min_viable_acquisition=5, and 2, the fewest a GP fits on, are a cold start weighted by the
    surrogate's P(viable); 1 (the surrogate itself fitted on 2 rows, since it cannot fit on
    fewer) is a cold start that ignores the surrogate, fits its own classifier and proposes
    exactly what model=None proposes. Catches the boundary taken as `n_viable <=
    min_viable_acquisition` (4 turns into a cold start), a surrogate used below 2 viable
    observations (1 is weighted by the surrogate and its picks change), and a surrogate dropped
    at exactly 2."""
    k, kw, status, batching = _PATHS[case]
    ts, spec = _box_problem()
    X = np.random.default_rng(21).random((30, 2))
    region = np.flatnonzero(X[:, 0] + X[:, 1] < 0.9)
    fit_rows = np.zeros(30, bool)
    fit_rows[region[:max(k, 2)]] = True
    model = _fit_gp(spec, X, np.where(fit_rows[:, None], _box_f(X), np.nan), fit_rows)
    viable = np.zeros(30, bool)
    viable[region[:k]] = True
    V = np.where(viable, _V(_box_f(X), ts), np.nan)

    prop = propose_batch(model, ts, [0, 0], [1, 1], X, V, viable, q=3, n_cand=256, seed=5, **kw)
    assert (prop.status, prop.batching) == (status, batching)
    assert prop.diagnostics["n_viable"] == k and len(prop.unit) == 3
    alone = propose_batch(None, ts, [0, 0], [1, 1], X, V, viable, q=3, n_cand=256, seed=5, **kw)
    assert alone.batching == "cold_start:feasibility_maximin(acquisition_classifier)"
    assert np.array_equal(prop.unit, alone.unit) == (k == 1)


# -----------------------------------------------------------------------------
# The separation rule: no candidate on an observed row, and what each count holds
# -----------------------------------------------------------------------------

def _rows_as_set(A):
    return sorted(tuple(r) for r in np.asarray(A).tolist())


@_quiet
def test_a_candidate_on_an_observed_row_is_never_proposed_and_each_count_is_defined():
    """docs/45 section 4.4. Failed runs sit exactly on three candidates: the batch's own argmax
    (a scan point), the best local candidate, and a candidate outside the hull. With q larger
    than the candidate set and r_sep = 0, every admissible candidate is proposed once and the
    three never are. The counts must equal an independent recount: `n_too_close` over the
    observed rows, `n_out_of_hull` over ALL candidates (the far one is both too close and out of
    hull), and `n_admissible`. Catches a separation rule that is not applied (the argmax and the
    best local candidate are proposed again), and an out-of-hull count taken only over the
    candidates clear of the observed rows."""
    ts, spec = _box_problem()
    X = np.random.default_rng(10).random((12, 2))
    Y = _box_f(X)
    V = _V(Y, ts)
    model = _fit_gp(spec, X, Y)
    kw = dict(n_cand=16, seed=0, local_k=2, local_scales=(0.05,))
    U_loc, _ = local_candidates(X, V, np.ones(12, bool), n_total=16, k=2, scales=(0.05,), seed=1)
    U = np.vstack([sobol_candidates(2, 16, 0), U_loc])
    assert U.shape == (32, 2)
    sc = score_candidates(model, ts, U, [0, 0], [1, 1], V.min())
    inside = sc["in_hull"]
    scan_best = int(np.argmax(np.where(inside[:16], sc["alpha"][:16], -np.inf)))
    local_best = 16 + int(np.argmax(np.where(inside[16:], sc["alpha"][16:], -np.inf)))
    far = int(np.argmax(sc["hull_distance"]))
    assert inside[scan_best] and inside[local_best] and not inside[far]
    free = propose_batch(model, ts, [0, 0], [1, 1], X, V, np.ones(12, bool), q=1, **kw)
    assert np.array_equal(free.unit[0], U[scan_best]), "the scan's best is no longer the argmax"

    on = [scan_best, local_best, far]
    X_obs = np.vstack([X, U[on]])
    V_obs = np.concatenate([V, np.full(3, np.nan)])
    viable = np.concatenate([np.ones(12, bool), np.zeros(3, bool)])
    prop = propose_batch(model, ts, [0, 0], [1, 1], X_obs, V_obs, viable, q=40, r_sep=0.0, **kw)

    too_close = min_distance(U, X_obs) <= 1e-6
    assert sorted(np.flatnonzero(too_close).tolist()) == sorted(on)
    pairwise = np.max(np.abs(U[:, None, :] - U[None, :, :]), axis=2)
    assert pairwise[np.triu_indices(32, 1)].min() > 1e-6
    admissible = ~too_close & inside
    assert prop.counts == {"n_candidates": 32, "n_too_close": 3,
                           "n_out_of_hull": int((~inside).sum()),
                           "n_admissible": int(admissible.sum())}
    assert prop.status == "ok" and prop.shortfall == 40 - int(admissible.sum())
    assert _rows_as_set(prop.unit) == _rows_as_set(U[admissible])
    assert not any(np.array_equal(u, U[i]) for u in prop.unit for i in on)


def test_a_cold_start_never_proposes_a_candidate_on_an_observed_row():
    """docs/45 section 4.6: a cold start is admissible by `min_separation` alone. Failed runs sit
    exactly on the first two maximin picks of a first batch and on scan point 0; with q equal to
    the scan size, every other scan point is proposed and those three are not, whether the batch
    is plain maximin (only failures) or weighted by the acquisition classifier (one viable row
    as well). Catches a cold start that treats every scan point as admissible."""
    p = 2
    F = np.random.default_rng(3).random((5, p))
    ts = [Target("y", 1.0, 0.1)]
    C = sobol_candidates(p, 64, 0)
    first = propose_batch(None, ts, [0, 0], [1, 1], F, np.full(5, np.nan), np.zeros(5, bool),
                          q=2, n_cand=64, seed=0)
    on = sorted({int(np.flatnonzero(np.all(C == u, axis=1))[0]) for u in first.unit} | {0})
    assert len(on) == 3
    X_obs = np.vstack([F, C[on]])
    too_close = min_distance(C, X_obs) <= 1e-6
    assert np.flatnonzero(too_close).tolist() == on

    for n_live, batching in ((0, "cold_start:maximin"),
                             (1, "cold_start:feasibility_maximin(acquisition_classifier)")):
        viable = np.zeros(8, bool)
        viable[:n_live] = True
        V = np.where(viable, 3.0, np.nan)
        prop = propose_batch(None, ts, [0, 0], [1, 1], X_obs, V, viable, q=64, n_cand=64, seed=0)
        assert prop.batching.startswith(batching), prop.batching
        assert prop.counts == {"n_candidates": 64, "n_too_close": 3, "n_out_of_hull": 0,
                               "n_admissible": 61}
        assert len(prop.unit) == 61 and prop.shortfall == 3
        assert _rows_as_set(prop.unit) == _rows_as_set(C[~too_close])


@_quiet
def test_when_every_candidate_is_too_close_nothing_is_proposed_and_no_picker_is_named():
    """min_separation 2 exceeds every unit-cube L-inf distance, so every candidate lies within it
    of an observed row: status "ok" (nothing is wrong with the model), batching "none", no picks,
    a shortfall of q, and counts and a note that say why. Catches a batching label naming the
    Kriging believer, which never ran, and a hull verdict reported instead."""
    ts, spec = _box_problem()
    X = np.random.default_rng(10).random((12, 2))
    Y = _box_f(X)
    model = _fit_gp(spec, X, Y)
    prop = propose_batch(model, ts, [0, 0], [1, 1], X, _V(Y, ts), np.ones(12, bool), q=3,
                         n_cand=64, seed=0, min_separation=2.0)
    assert (prop.status, prop.batching) == ("ok", "none")
    assert prop.unit.shape == (0, 2) and prop.shortfall == 3
    n = prop.counts["n_candidates"]
    assert prop.counts["n_too_close"] == n > 64 and prop.counts["n_admissible"] == 0
    assert any("no candidate is admissible" in note for note in prop.notes), prop.notes


# -----------------------------------------------------------------------------
# Non-unit bounds: native coordinates to the surrogate, unit coordinates to every distance
# -----------------------------------------------------------------------------

@_quiet
def test_on_non_unit_bounds_the_surrogate_sees_native_points_and_distances_see_unit_ones():
    """docs/45 sections 4.3-4.5 on bounds x1 in [10, 30], x2 in [-5, 45], where unit and native
    coordinates differ; on the unit square they coincide and no mapping is tested. Failed runs
    sit exactly on two candidates, the admissible argmax and the best local candidate, given in
    NATIVE units. Checked: `believe` receives each earlier pick in native units; `native` is the
    map of `unit`; the counts, pick 1 and the local set's best alpha equal a recount built on
    unit coordinates; pick 2's alpha equals a rescoring under the model believed at pick 1.
    Catches believing the unit coordinate (the recorded argument is then the unit row), observed
    rows kept native for the separation distance (nothing is too close and the old argmax is
    proposed again) or for the local centres (the local set changes), and `native` left equal to
    `unit`. Observed rows kept native everywhere fail at the bounds check."""
    ts, spec = _scaled_box_problem()
    span = _HI - _LO
    Xu = np.random.default_rng(10).random((12, 2))
    Y = _box_f(Xu)
    V = _V(Y, ts)
    model = _fit_gp(spec, _LO + Xu * span, Y)
    U = _candidates(Xu, V, np.ones(12, bool), 256, 0)
    local = np.arange(len(U)) >= 256
    sc = score_candidates(model, ts, U, _LO, _HI, V.min())
    inside = sc["in_hull"]
    clear = (min_distance(U, Xu) > 1e-6) & inside
    on = [int(np.flatnonzero(m)[np.argmax(sc["alpha"][m])]) for m in (clear, clear & local)]
    assert local[on[1]] and on[0] != on[1]
    U_obs = np.vstack([Xu, U[on]])
    V_obs = np.concatenate([V, [np.nan, np.nan]])
    viable = np.concatenate([np.ones(12, bool), [False, False]])

    calls = []
    prop = propose_batch(_believe_spy(model, calls), ts, _LO, _HI, _LO + U_obs * span, V_obs,
                         viable, q=3, n_cand=256, seed=0)
    assert (prop.status, prop.batching) == ("ok", "kriging_believer") and len(prop.unit) == 3
    np.testing.assert_allclose(prop.native, _LO + prop.unit * span, rtol=1e-15, atol=0)
    assert len(calls) == 2
    for j, arg in enumerate(calls):
        assert np.array_equal(arg, prop.native[j:j + 1]), (j, arg, prop.unit[j])

    too_close = min_distance(U, U_obs) <= 1e-6
    assert sorted(np.flatnonzero(too_close).tolist()) == sorted(on)
    admissible = ~too_close & inside
    assert prop.counts == {"n_candidates": len(U), "n_too_close": 2,
                           "n_out_of_hull": int((~inside).sum()),
                           "n_admissible": int(admissible.sum())}
    best = int(np.flatnonzero(admissible)[np.argmax(sc["alpha"][admissible])])
    np.testing.assert_allclose(prop.unit[0], U[best], rtol=0, atol=1e-12)
    assert not any(np.allclose(p, U[i], rtol=0, atol=1e-12) for p in prop.unit for i in on)
    loc = prop.diagnostics["scan_vs_local"]["sets"]["local"]
    assert loc["best_alpha"] == pytest.approx(sc["alpha"][admissible & local].max(), rel=1e-9)
    again = score_candidates(model.believe(prop.native[:1]), ts, prop.unit[1:2], _LO, _HI,
                             V.min())
    np.testing.assert_allclose(again["alpha"], prop.alpha[1:2], rtol=1e-8)


@_quiet
def test_on_non_unit_bounds_a_cold_start_classifies_native_points_and_spaces_unit_ones():
    """docs/45 section 4.6 on the bounds of the test above. Without a surrogate, the acquisition
    classifier is fitted on the native observed rows and asked about native candidates, while
    maximin and the separation rule measure distance in the unit cube, so a failed run placed
    exactly on scan point 7 is too close. With a surrogate on 3 viable rows, its viability is
    asked about native candidates. The picks must equal loop-written weighted maximin references
    built that way. Catches a classifier asked about unit candidates or fitted on unit rows, a
    surrogate asked about unit candidates, maximin or the separation rule measured against
    native observed rows, and `native` left equal to `unit`."""
    ts, spec = _scaled_box_problem()
    span = _HI - _LO
    Xu = np.random.default_rng(21).random((30, 2))
    region = Xu[:, 0] + Xu[:, 1] < 0.9
    C = sobol_candidates(2, 256, 5)
    C_native = _LO + C * span

    U_obs = np.vstack([Xu, C[7:8]])
    X_obs = _LO + U_obs * span
    labels = np.concatenate([region, [False]])
    prop = propose_batch(None, ts, _LO, _HI, X_obs, np.where(labels, 1.0, np.nan), labels, q=4,
                         n_cand=256, seed=5)
    clf = make_classifier("rf", random_state=5).fit(X_obs, labels.astype(int))
    w = clf.predict_proba(C_native)[:, list(clf.classes_).index(1)]
    ref = _greedy_maximin_reference(C, U_obs, 4, weights=w)
    assert ref != _greedy_maximin_reference(C, U_obs, 4) and 7 not in ref
    assert prop.batching == "cold_start:feasibility_maximin(acquisition_classifier)"
    assert prop.counts == {"n_candidates": 256, "n_too_close": 1, "n_out_of_hull": 0,
                           "n_admissible": 255}
    assert np.array_equal(prop.unit, C[ref])
    np.testing.assert_allclose(prop.native, C_native[ref], rtol=1e-15, atol=0)
    assert np.array_equal(prop.p_viable, w[ref])

    few = np.zeros(30, bool)
    few[np.flatnonzero(region)[:3]] = True
    Y = np.where(few[:, None], _box_f(Xu), np.nan)
    model = _fit_gp(spec, _LO + Xu * span, Y, few)
    V3 = np.where(few, _V(np.nan_to_num(Y, nan=1.0), ts), np.nan)
    prop3 = propose_batch(model, ts, _LO, _HI, _LO + Xu * span, V3, few, q=4, n_cand=256, seed=5)
    w3 = model.viability(C_native)
    ref3 = _greedy_maximin_reference(C, Xu, 4, weights=w3)
    assert ref3 != _greedy_maximin_reference(C, Xu, 4)
    assert prop3.batching == "cold_start:feasibility_maximin(surrogate_viability)"
    assert np.array_equal(prop3.unit, C[ref3])
    assert np.array_equal(prop3.p_viable, w3[ref3])


# -----------------------------------------------------------------------------
# Input refusals
# -----------------------------------------------------------------------------

def _refusal_call(case):
    """`(model, targets, lower, upper, X_obs, V_obs, viable_obs, q, extra)` for one case."""
    ts, spec = _box_problem()
    X = np.random.default_rng(7).random((30, 2))
    Y = _box_f(X)
    V = _V(Y, ts)
    viable = np.ones(30, bool)
    lower, upper, q, extra = [0, 0], [1, 1], 2, {}
    if case == "targets_reversed_cold_start_path":
        viable = np.zeros(30, bool)
        viable[:3] = True
        Y = np.where(viable[:, None], Y, np.nan)
        V = np.where(viable, V, np.nan)
    model = _fit_gp(spec, X, Y, viable)
    if case == "observed_row_outside_the_bounds":
        X = X.copy()
        X[4] = [1.2, 0.5]
    elif case.startswith("q_"):
        q = {"q_0": 0, "q_1.5": 1.5, "q_True": True}[case]
    elif case == "seed_not_an_integer":
        extra = {"seed": 1.5}
    elif case.startswith("targets_reversed"):
        ts = ts[::-1]
    elif case == "bounds_with_a_third_input":
        lower, upper, X = [0, 0, 0], [1, 1, 1], np.hstack([X, X[:, :1]])
    elif case == "surrogate_not_fitted":
        model = S1Surrogate(spec, learner=GPLearner(n_restarts=0), classifier="rf",
                            calibration_fraction=0)
    return model, ts, lower, upper, X, V, viable, q, extra


_REFUSALS = {
    "observed_row_outside_the_bounds":
        r"1 observed row\(s\) lie outside the bounds \(first rows \[4\]\)",
    "q_0": r"q is 0; propose at least one",
    "q_1.5": r"q is 1\.5; propose at least one",
    "q_True": r"q is True; propose at least one",
    "seed_not_an_integer": r"seed is 1\.5; pass an integer",
    "targets_reversed_acquisition_path": r"names and order must agree",
    "targets_reversed_cold_start_path": r"names and order must agree",
    "bounds_with_a_third_input": r"the surrogate has 2 inputs but the bounds have 3",
    "surrogate_not_fitted": r"the S1Surrogate is not fitted; fit it on the observed rows first",
}


@_quiet
@pytest.mark.parametrize("case", sorted(_REFUSALS))
def test_propose_batch_refuses_inputs_it_cannot_search_over(case):
    """Each refusal fires at entry with a message naming the input, before any path runs. Catches
    the removal of any of these checks: an observed row outside the bounds would sit outside the
    search cube (the batch proceeds), q = 0 returns an empty batch and q = 1.5 or True a batch of
    one, a float seed reaches the Sobol' scan, and reversed targets on the cold-start path, which
    never scores a posterior, would never meet the alignment check at all. A bounds count that
    disagrees with the surrogate would otherwise fail later with a message about the classifier's
    inputs, and an unfitted surrogate with a RuntimeError from `trains_on` that does not say what
    to do."""
    model, ts, lower, upper, X, V, viable, q, extra = _refusal_call(case)
    with pytest.raises(ValueError, match=_REFUSALS[case]):
        propose_batch(model, ts, lower, upper, X, V, viable, q=q, n_cand=64, **extra)
