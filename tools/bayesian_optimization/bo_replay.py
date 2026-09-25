"""Replay validation for the BO loop -- docs/42 stage S1, the GO/NO-GO gate.

    "Seed the GPs with a subset of a completed ensemble, run the propose loop but instead of
     submitting, LOOK UP the nearest completed case, and measure iterations-to-best-V against
     random selection. If BO cannot rediscover a KNOWN optimum from data we already own, it
     will not find an unknown one. This is the go/no-go for the whole item."   -- docs/42 S1

WHAT THIS TESTS, AND WHAT IT CANNOT. It tests the SEARCH: given the same evaluation budget, does
feasibility-weighted expected improvement on `V` reach the known best region more often, and
sooner, than drawing at random from the same pool? It does not test extraction, submission, or
the physics -- every value here was produced months ago by a real run.

THE POOL IS THE ORACLE. A replay can only observe cases that were actually run, so the candidate
set is the completed ensemble and the acquisition RANKS POOL MEMBERS rather than proposing a
continuous theta and snapping to the nearest case. That is a deliberate departure from the plan's
wording and it is the more faithful of the two: snapping reports the value at the neighbour while
the acquisition believed it was buying the value at the proposal, so a snapped replay measures the
search and the snapping error together and cannot separate them. S3's dry loop proposes
continuously, where that is the real behaviour.

FAILURE-AWARENESS IS EXERCISED, NOT ASSUMED. Most of a real ensemble is dead: 81% of EcoSIM R3
returns NPP ~ 0. `--viable-if` splits the pool the way `S1Surrogate` does -- a classifier over
all observed points, per-target regressors over the VIABLE ones only -- so the acquisition is
`P(viable) * EI` as docs/42 section 4 specifies. Without the split, one regressor spans a regime
boundary, which is what produced the R2 = 0.48 that motivated the two-stage tier.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import pathlib
import sys
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

REPO = pathlib.Path(__file__).resolve().parents[2]   # tools/bayesian_optimization/ -> repo root
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from models.surrogate.learners import GPLearner  # noqa: E402
from tools.bayesian_optimization.acquisition import local_penalisation_batch  # noqa: E402
from tools.bayesian_optimization.objective import (  # noqa: E402
    Target, load_targets, violation_matrix)


# =============================================================================
# The pool
# =============================================================================

@dataclass
class Pool:
    """Every case that can be observed, with its inputs and its already-known answer."""
    cases: np.ndarray            # (n,)   case numbers
    X: np.ndarray                # (n, p) parameter rows
    Yt: np.ndarray               # (n, k) per-target simulated values
    V: np.ndarray                # (n,)   the true violation, the replay's oracle
    viable: np.ndarray           # (n,)   bool
    targets: List[Target]
    param_names: List[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.cases)

    def true_top(self, k: int) -> np.ndarray:
        """Indices of the k best pool members by V -- the region the loop must reach."""
        return np.argsort(self.V, kind="stable")[:k]


def parse_viable_if(expr: Optional[str]) -> Optional[Tuple[str, str, float]]:
    """`"NPP>1.0"` -> `("NPP", ">", 1.0)`. Deliberately tiny: a general expression parser here
    would be a place for a silent mistake in the one rule that decides what counts as a run."""
    if not expr:
        return None
    for op in (">=", "<=", ">", "<"):
        if op in expr:
            name, _, val = expr.partition(op)
            return name.strip(), op, float(val)
    raise SystemExit(f"REFUSING: --viable-if {expr!r} has no comparison operator (>, >=, <, <=)")


def build_pool(x_matrix, y_matrix, targets_yaml, target_names: Sequence[str],
               viable_if: Optional[str] = None,
               baseline_case: int = 0) -> Pool:
    """Join the design matrix to the scored outputs under A2MC's case convention.

    `scripts/materialize_adapter_ensemble.py:216` builds case `i` from `X[i - 1]`, so the mapping
    is 1-based and case `baseline_case` is the unperturbed V0, which HAS NO MATRIX ROW. Under
    `i - 1` that case indexes -1, which in numpy is the LAST row of the design -- a silent join
    error that would attach the wrong parameters to a real result.
    """
    X_all = np.loadtxt(x_matrix)
    if X_all.ndim != 2:
        raise SystemExit(f"REFUSING: {x_matrix} did not load as a 2-D matrix (got {X_all.shape})")

    rows = list(csv.DictReader(pathlib.Path(y_matrix).open()))
    if not rows:
        raise SystemExit(f"REFUSING: {y_matrix} has no rows")

    targets = load_targets(targets_yaml, target_names)
    cols = [f for f in rows[0] if f not in ("case", "status")]

    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return float("nan")

    cases = np.array([int(r["case"]) for r in rows])
    Yall = np.array([[_f(r[c]) for c in cols] for r in rows], dtype=float)
    V, _, _ = violation_matrix(Yall, cols, targets)
    Yt = Yall[:, [cols.index(t.name) for t in targets]]

    keep = np.isfinite(V) & (cases != baseline_case)
    idx = cases[keep] - 1
    bad = idx[(idx < 0) | (idx >= len(X_all))]
    if len(bad):
        raise SystemExit(
            f"REFUSING: {len(bad)} case number(s) fall outside the {len(X_all)}-row design "
            f"matrix under the 1-based convention (first few: {bad[:5].tolist()}). Either the "
            f"matrix is the wrong round's or the baseline case number is not {baseline_case}.")

    rule = parse_viable_if(viable_if)
    if rule is None:
        viable = np.ones(int(keep.sum()), dtype=bool)
    else:
        name, op, thr = rule
        if name not in [t.name for t in targets]:
            raise SystemExit(f"REFUSING: --viable-if names {name!r}, not a scored target "
                             f"({[t.name for t in targets]})")
        col = Yt[keep][:, [t.name for t in targets].index(name)]
        viable = {">": col > thr, ">=": col >= thr,
                  "<": col < thr, "<=": col <= thr}[op]

    return Pool(cases=cases[keep], X=X_all[idx], Yt=Yt[keep], V=V[keep],
                viable=viable, targets=targets)


# =============================================================================
# Acquisition: P(viable) * E[max(0, V* - V)]
# =============================================================================

def _fit_models(pool: Pool, obs: np.ndarray, rng: np.random.Generator, n_restarts: int):
    """Per-target GPs on the VIABLE observed points, plus a viability classifier on all of them.

    Returns `(gps, clf)`. Either may be None when the observed set cannot support it, and the
    caller must handle that rather than proceeding with a model fitted to one class.
    """
    from sklearn.ensemble import RandomForestClassifier

    Xo, vo = pool.X[obs], pool.viable[obs]
    clf = None
    if vo.any() and (~vo).any():
        clf = RandomForestClassifier(n_estimators=200, random_state=int(rng.integers(1 << 30)),
                                     n_jobs=-1).fit(Xo, vo)

    alive = obs[pool.viable[obs]]
    if len(alive) < 5:
        return None, clf
    gps = []
    for j in range(len(pool.targets)):
        gps.append(GPLearner(n_restarts=n_restarts, max_points=4000,
                             random_state=int(rng.integers(1 << 30))
                             ).fit(pool.X[alive], pool.Yt[alive, j]))
    return gps, clf


def acquisition(pool: Pool, gps, clf, cand: np.ndarray, V_star: float,
                n_mc: int, rng: np.random.Generator) -> np.ndarray:
    """`alpha(theta) = P(viable) * E[max(0, V* - V(theta))]`, by Monte Carlo over the joint
    per-target posterior.

    The expectation is taken over TARGET VALUES and the max is applied inside the sample, never
    to a fitted `V`. `V` is a max, hence non-smooth, hence a poor thing to fit a GP to
    (docs/42 section 3) -- and modelling it directly would also lose `argmax_i`, the binding target.
    """
    Xc = pool.X[cand]
    mu = np.stack([g.predict(Xc) for g in gps], axis=1)                    # (m, k)
    sd = np.stack([np.maximum(g.predict_std(Xc), 1e-12) for g in gps], axis=1)

    obs = np.array([t.observed for t in pool.targets])
    unc = np.array([t.uncertainty for t in pool.targets])

    z = rng.standard_normal((n_mc, len(cand), len(pool.targets)))
    draws = mu[None, :, :] + sd[None, :, :] * z
    Vs = np.max(np.abs(draws - obs) / (unc * obs), axis=2)                 # (n_mc, m)
    ei = np.mean(np.maximum(0.0, V_star - Vs), axis=0)

    if clf is None:
        return ei
    p = clf.predict_proba(Xc)
    p_viable = p[:, list(clf.classes_).index(True)] if True in clf.classes_ else np.zeros(len(cand))
    return p_viable * ei


# =============================================================================
# The loops
# =============================================================================

def run_bo(pool: Pool, n_seed: int, q: int, n_iter: int, seed: int,
           n_mc: int = 256, n_cand: int = 3000, n_restarts: int = 0,
           verbose: bool = False) -> np.ndarray:
    """One BO replay. Returns best-V-so-far after each EVALUATION (length n_seed + q*n_iter).

    The curve is shorter when the pool runs out, or when a batch runs out of candidates whose
    coordinates differ from every earlier pick in it: `_greedy_batch` never picks two pool rows
    with identical inputs, so a pool with duplicated rows can yield fewer than `q` per batch.
    `gate` reads each curve at `min(budget, len(curve))`.

    `n_cand` subsamples the candidate pool each iteration: scoring 14,799 candidates through a GP
    posterior every batch dominates the runtime and buys nothing, since the acquisition surface is
    smooth in theta and a few thousand draws locate its maximum region. Random per iteration, so
    no part of the pool is permanently invisible.
    """
    rng = np.random.default_rng(seed)
    n = len(pool)
    obs = rng.choice(n, size=n_seed, replace=False)
    curve = list(np.minimum.accumulate(pool.V[obs]))

    for it in range(n_iter):
        V_star = float(pool.V[obs].min())
        rest = np.setdiff1d(np.arange(n), obs, assume_unique=False)
        if len(rest) == 0:
            break
        cand = rest if len(rest) <= n_cand else rng.choice(rest, n_cand, replace=False)

        gps, clf = _fit_models(pool, obs, rng, n_restarts)
        if gps is None:
            # Not enough viable points to regress on yet. Fall back to the classifier alone --
            # pure feasibility search -- rather than proposing blindly or crashing.
            if clf is None:
                pick = rng.choice(cand, size=min(q, len(cand)), replace=False)
            else:
                p = clf.predict_proba(pool.X[cand])
                pv = (p[:, list(clf.classes_).index(True)]
                      if True in clf.classes_ else np.zeros(len(cand)))
                pick = cand[np.argsort(-pv)[:q]]
        else:
            a = acquisition(pool, gps, clf, cand, V_star, n_mc, rng)
            # Constant liar: take the batch's top-q by acquisition, but penalise candidates
            # that are close to an already-picked one, so a batch does not spend all q draws on
            # one peak. Distance in the standardised design space.
            pick = _greedy_batch(pool, cand, a, q)

        obs = np.concatenate([obs, pick])
        curve.extend(np.minimum.accumulate(
            np.minimum(pool.V[pick], curve[-1] if curve else np.inf)))
        if verbose:
            print(f"    iter {it + 1:3d}  n_obs {len(obs):5d}  best V {curve[-1]:.4f}")
    return np.array(curve)


def _greedy_batch(pool: Pool, cand: np.ndarray, a: np.ndarray, q: int) -> np.ndarray:
    """Local-penalisation batching: take the argmax, then damp the acquisition near it.

    The plan names constant-liar / Kriging-believer, whose fake observation requires
    re-conditioning the GP q times per batch. Local penalisation is its cheap stand-in and the
    plan names it as the fallback; it is used here because the replay refits from scratch each
    ITERATION anyway, so a within-batch refit would multiply the cost of the gate by q for a
    diversity effect this achieves directly.

    A thin wrapper over `acquisition.local_penalisation_batch`, standardising by the WHOLE pool
    and with `min_separation=0`: picks are identical to the unwrapped loop whenever candidate
    coordinates are distinct, and a pool row with exactly the coordinates of a pick is never
    picked again. Returns pool indices, fewer than `q` when the candidates run out. A NaN or
    `+inf` acquisition value is refused rather than ranked; `acquisition` floors the posterior sd
    and `Target` refuses a zero observation or a non-positive uncertainty, so neither arises from
    it. A non-finite pool coordinate is refused too, since its distance to every pick is NaN.
    """
    Z = (pool.X[cand] - pool.X.mean(0)) / np.where(pool.X.std(0) > 0, pool.X.std(0), 1.0)
    idx, _ = local_penalisation_batch(Z, a, q, min_separation=0.0)
    return np.asarray(cand)[idx]


def run_random(pool: Pool, n_total: int, seed: int) -> np.ndarray:
    """The baseline the gate is measured against: draw `n_total` from the same pool."""
    rng = np.random.default_rng(seed)
    pick = rng.choice(len(pool), size=min(n_total, len(pool)), replace=False)
    return np.minimum.accumulate(pool.V[pick])


def run_exploit(pool: Pool, n_seed: int, q: int, n_iter: int, seed: int,
                n_cand: int = 3000, n_restarts: int = 0) -> np.ndarray:
    """A HARDER baseline than random: the same GPs, ranked by posterior MEAN `V` alone.

    Random is a weak bar on a pool this size, so beating it proves little on its own. This one
    isolates the acquisition's uncertainty term: same models, same budget, no exploration. If BO
    cannot beat pure exploitation either, the expected-improvement machinery is not earning its
    place and the honest answer is to rank the pool with a surrogate and stop.
    """
    rng = np.random.default_rng(seed)
    n = len(pool)
    obs = rng.choice(n, size=n_seed, replace=False)
    curve = list(np.minimum.accumulate(pool.V[obs]))
    obsv = np.array([t.observed for t in pool.targets])
    uncv = np.array([t.uncertainty for t in pool.targets])

    for _ in range(n_iter):
        rest = np.setdiff1d(np.arange(n), obs)
        if len(rest) == 0:
            break
        cand = rest if len(rest) <= n_cand else rng.choice(rest, n_cand, replace=False)
        gps, clf = _fit_models(pool, obs, rng, n_restarts)
        if gps is None:
            pick = rng.choice(cand, size=min(q, len(cand)), replace=False)
        else:
            mu = np.stack([g.predict(pool.X[cand]) for g in gps], axis=1)
            Vhat = np.max(np.abs(mu - obsv) / (uncv * obsv), axis=1)
            if clf is not None:
                p = clf.predict_proba(pool.X[cand])
                pv = (p[:, list(clf.classes_).index(True)]
                      if True in clf.classes_ else np.zeros(len(cand)))
                Vhat = np.where(pv > 0.5, Vhat, np.inf)
            pick = cand[np.argsort(Vhat)[:q]]
        obs = np.concatenate([obs, pick])
        curve.extend(np.minimum.accumulate(np.minimum(pool.V[pick], curve[-1])))
    return np.array(curve)


# =============================================================================
# The gate
# =============================================================================

def hit_iteration(curve: np.ndarray, bar: float) -> Optional[int]:
    """First evaluation index at which the curve reaches `bar`, or None."""
    w = np.where(curve <= bar)[0]
    return int(w[0]) + 1 if len(w) else None


def gate(bo_curves: List[np.ndarray], rnd_curves: List[np.ndarray],
         exp_curves: List[np.ndarray], bar: float, budget: int) -> dict:
    """The GO/NO-GO verdict, with the bar fixed BEFORE the run.

    Two conditions, both required, because either alone can be met by an uninteresting mechanism:
      1. BO reaches the bar in strictly more replicates than random -- the plan's stated test;
      2. BO's median best-V at budget is no worse than pure exploitation's -- so a PASS cannot be
         bought by the surrogate alone while the acquisition contributes nothing.
    """
    def summarise(cs):
        hits = [hit_iteration(c, bar) for c in cs]
        return {
            "n": len(cs),
            "n_reached": sum(h is not None for h in hits),
            "median_evals_to_bar": (float(np.median([h for h in hits if h is not None]))
                                    if any(h is not None for h in hits) else None),
            "median_best_V": float(np.median([c[min(budget, len(c)) - 1] for c in cs])),
            "best_V_over_replicates": float(np.min([c[min(budget, len(c)) - 1] for c in cs])),
        }

    bo, rnd, exp = summarise(bo_curves), summarise(rnd_curves), summarise(exp_curves)
    c1 = bo["n_reached"] > rnd["n_reached"]
    c2 = bo["median_best_V"] <= exp["median_best_V"]
    return {
        "bar": bar, "budget": budget,
        "bo": bo, "random": rnd, "exploit_only": exp,
        "beats_random": bool(c1),
        "at_least_matches_pure_exploitation": bool(c2),
        "verdict": "GO" if (c1 and c2) else "NO-GO",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="docs/42 stage S1 -- replay validation, the GO/NO-GO gate for the BO item.")
    ap.add_argument("--x-matrix", required=True)
    ap.add_argument("--y-matrix", required=True)
    ap.add_argument("--targets", default=os.environ.get("A2MC_VALIDATION_TARGETS"))
    ap.add_argument("--only", required=True, help="comma-separated target names, in any order")
    ap.add_argument("--viable-if", help="e.g. 'NPP>1.0' -- what counts as a run that lived")
    ap.add_argument("--baseline-case", type=int, default=0)
    ap.add_argument("--n-seed", type=int, default=50)
    ap.add_argument("--q", type=int, default=5)
    ap.add_argument("--n-iter", type=int, default=30)
    ap.add_argument("--replicates", type=int, default=5)
    ap.add_argument("--top-k", type=int, default=10,
                    help="the bar: reach the true top-K of the pool by V")
    ap.add_argument("--n-mc", type=int, default=256)
    ap.add_argument("--n-cand", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--json", help="write the verdict here")
    ap.add_argument("--curves", help="write every replicate's curve to this CSV")
    a = ap.parse_args(argv)

    if not a.targets:
        raise SystemExit("REFUSING: no --targets and $A2MC_VALIDATION_TARGETS unset.")

    names = [s.strip() for s in a.only.split(",")]
    pool = build_pool(a.x_matrix, a.y_matrix, a.targets, names,
                      viable_if=a.viable_if, baseline_case=a.baseline_case)

    budget = a.n_seed + a.q * a.n_iter
    top = pool.true_top(a.top_k)
    bar = float(pool.V[top].max())

    print(f"\npool: {len(pool)} observable cases, {int(pool.viable.sum())} viable "
          f"({100 * pool.viable.mean():.1f}%)")
    print(f"true best V = {pool.V.min():.4f} (case {int(pool.cases[np.argmin(pool.V)])})")
    print(f"BAR: reach the true top-{a.top_k} by V, i.e. V <= {bar:.4f} "
          f"(cases {sorted(pool.cases[top].tolist())})")
    print(f"budget: {a.n_seed} seed + {a.q}x{a.n_iter} = {budget} evaluations "
          f"({100 * budget / len(pool):.2f}% of the pool)")
    p_rand = 1.0 - np.prod([(len(pool) - a.top_k - i) / (len(pool) - i) for i in range(budget)])
    print(f"P(random {budget} draws hit the top-{a.top_k}) = {p_rand:.3f}\n")

    bo_c, rnd_c, exp_c = [], [], []
    for r in range(a.replicates):
        t0 = time.time()
        bo_c.append(run_bo(pool, a.n_seed, a.q, a.n_iter, a.seed + r,
                           n_mc=a.n_mc, n_cand=a.n_cand))
        exp_c.append(run_exploit(pool, a.n_seed, a.q, a.n_iter, a.seed + r, n_cand=a.n_cand))
        rnd_c.append(run_random(pool, budget, a.seed + r))
        print(f"  replicate {r + 1}/{a.replicates}: bo {bo_c[-1][-1]:.4f}  "
              f"exploit {exp_c[-1][-1]:.4f}  random {rnd_c[-1][-1]:.4f}  "
              f"({time.time() - t0:.0f}s)")

    verdict = gate(bo_c, rnd_c, exp_c, bar, budget)
    print(f"\n{'':22s} {'reached bar':>12s} {'median evals':>13s} {'median best V':>14s}")
    for k in ("bo", "exploit_only", "random"):
        d = verdict[k]
        med = d["median_evals_to_bar"]
        med_s = "--" if med is None else f"{med:.0f}"
        reached = f"{d['n_reached']}/{d['n']}"
        print(f"  {k:20s} {reached:>12s} {med_s:>13s} {d['median_best_V']:14.4f}")
    print(f"\n  beats random ................ {verdict['beats_random']}")
    print(f"  matches pure exploitation ... {verdict['at_least_matches_pure_exploitation']}")
    print(f"\n  VERDICT: {verdict['verdict']}")

    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(verdict, indent=2))
        print(f"\nwrote {a.json}")
    if a.curves:
        with pathlib.Path(a.curves).open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["method", "replicate", "evaluation", "best_V"])
            for nm, cs in (("bo", bo_c), ("exploit_only", exp_c), ("random", rnd_c)):
                for r, c in enumerate(cs):
                    for i, val in enumerate(c, 1):
                        w.writerow([nm, r, i, f"{val:.6f}"])
        print(f"wrote {a.curves}")
    return 0 if verdict["verdict"] == "GO" else 10


if __name__ == "__main__":
    sys.exit(main())
