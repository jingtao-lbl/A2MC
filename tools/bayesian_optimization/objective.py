"""The normalized-violation objective `V` -- docs/42 stage S0.

WHAT THIS IS FOR. A2MC already answers *"which parameter set scores best?"* by ranking on a
composite relative error (`tools/cost_functions.aggregate_costs`, method `rmsre`). It does not
answer *"does a parameter set exist that puts EVERY target inside its observational band at the
same time?"* -- which is constrained FEASIBILITY, not ranking, and needs a different objective.

    v_i(theta) = |sim_i - obs_i| / (u_i * obs_i)        v_i <= 1  <=>  target i is in band
    V(theta)   = max_i v_i(theta)                       V   <= 1  <=>  ALL targets in band

`u_i` is the FRACTIONAL `uncertainty` already carried per target in `targets.yaml`, so the band is
`observed * (1 +/- uncertainty)` and no new threshold is invented anywhere.

WHY `max` AND NOT A MEAN. A mean COMPENSATES: a target deep inside its band offsets one far
outside, so a good composite can hide a failing target. `max` cannot -- improving it requires
improving the BINDING target, and `argmax_i v_i` names which one that is, which is diagnostic
output rather than a number.

WHAT THIS DELIBERATELY DOES NOT DO.

  * It does not decide VIABILITY. A dead run is not a bad score, it is an absent one
    (docs/42 section 4), and imputing a large penalty would misrepresent the surface's shape to
    anything fitted on it. Rows whose values are missing or non-finite get `V = nan` and are
    excluded from every ranking, never ranked last.
  * It needs no "alive" threshold to be USEFUL, which is worth stating because it looks like it
    should. A dead EcoSIM case has NPP ~ 0, hence v_NPP = 389/(0.36*389) = 2.78, so V >= 2.78 on
    its own arithmetic. Dead cases sink under `V` without being told to.
  * It does not replace the composite. `rmsre` stays the right REPORTING metric; this is the
    right FEASIBILITY objective. `compare_rankings()` exists to show where they disagree, not to
    retire one.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import pathlib
import sys
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]   # tools/bayesian_optimization/ -> repo root
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from tools.cost_functions import aggregate_costs  # noqa: E402


# =============================================================================
# Targets
# =============================================================================

class Target:
    """One scored target's band. `lo`/`hi` are the band edges the violation normalizes by."""

    __slots__ = ("name", "observed", "uncertainty", "units")

    def __init__(self, name: str, observed: float, uncertainty: float, units: str = ""):
        if observed is None:
            raise ValueError(f"target {name!r}: `observed` is null")
        if uncertainty is None:
            raise ValueError(f"target {name!r}: `uncertainty` is null")
        if float(observed) == 0.0:
            # v_i divides by u*obs. A zero observation makes the normalization undefined rather
            # than large, and silently producing inf would look like a very bad case.
            raise ValueError(
                f"target {name!r}: observed is 0, so |sim-obs|/(u*obs) is undefined. A target "
                f"whose observation is zero needs an ABSOLUTE tolerance, which this objective "
                f"does not model. Exclude it or give it a non-zero reference.")
        if float(uncertainty) <= 0.0:
            raise ValueError(
                f"target {name!r}: uncertainty is {uncertainty}, must be > 0 -- it is the "
                f"half-width of the band as a FRACTION of the observation.")
        self.name = name
        self.observed = float(observed)
        self.uncertainty = float(uncertainty)
        self.units = units or ""

    @property
    def lo(self) -> float:
        return self.observed * (1.0 - self.uncertainty)

    @property
    def hi(self) -> float:
        return self.observed * (1.0 + self.uncertainty)

    def __repr__(self) -> str:
        return (f"Target({self.name}, obs={self.observed:g}, u={self.uncertainty:g}, "
                f"band=[{self.lo:g}, {self.hi:g}])")


def load_targets(path, names: Optional[Sequence[str]] = None) -> List[Target]:
    """Read scored targets from a `targets.yaml`.

    A target carrying `observed: null` is a PLACEHOLDER -- the structure is wired and the
    observation is pending ([[feedback_placeholder_targets_structure_not_values]]). It is skipped
    with a printed reason rather than dropped silently, because a quietly shorter target list
    changes `max_i` without changing anything a reader can see.
    """
    d = yaml.safe_load(pathlib.Path(path).read_text())
    raw = d.get("targets", d)
    items = ([(k, v) for k, v in raw.items() if isinstance(v, dict)]
             if isinstance(raw, dict)
             else [(t.get("name"), t) for t in raw])

    out, skipped = [], []
    for name, body in items:
        if names is not None and name not in names:
            continue
        if body.get("observed") is None:
            skipped.append((name, "observed is null (placeholder target, observation pending)"))
            continue
        try:
            out.append(Target(name, body.get("observed"), body.get("uncertainty"),
                              body.get("units", "")))
        except ValueError as e:
            skipped.append((name, str(e)))

    for name, why in skipped:
        print(f"  [skip] target {name!r}: {why}", file=sys.stderr)
    if not out:
        raise SystemExit(
            f"REFUSING: no scorable target in {path}. Every target was a placeholder or was "
            f"rejected. `V = max_i v_i` over an empty set is not 0, it is undefined.")
    if names is not None:
        missing = [n for n in names if n not in {t.name for t in out}]
        if missing:
            raise SystemExit(f"REFUSING: requested target(s) {missing} not scorable in {path}")
    return out


# =============================================================================
# The objective
# =============================================================================

def violation(sim: Dict[str, float], targets: Sequence[Target]) -> Tuple[float, Dict[str, float], str]:
    """One case -> (V, {target: v_i}, binding target name).

    `V` is nan and the binding name is "" when any target's value is missing or non-finite: an
    absent result is not a bad one, and a `max` over a set with a hole is not a maximum.
    """
    v = {}
    for t in targets:
        y = sim.get(t.name)
        if y is None or not np.isfinite(y):
            return float("nan"), {t2.name: float("nan") for t2 in targets}, ""
        v[t.name] = abs(float(y) - t.observed) / (t.uncertainty * t.observed)
    binding = max(v, key=v.get)
    return v[binding], v, binding


def violation_matrix(Y: np.ndarray, columns: Sequence[str],
                     targets: Sequence[Target]) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Vectorized `violation` over a whole ensemble.

    Returns `(V, v, binding_index)` with shapes `(n,)`, `(n, n_targets)`, `(n,)`. `binding_index`
    is -1 wherever `V` is nan, so a caller cannot index a binding target for a row that has none.
    """
    idx = [_column_index(columns, t.name) for t in targets]
    sub = np.asarray(Y, dtype=float)[:, idx]
    obs = np.array([t.observed for t in targets], dtype=float)
    unc = np.array([t.uncertainty for t in targets], dtype=float)

    v = np.abs(sub - obs) / (unc * obs)
    bad = ~np.isfinite(v).all(axis=1)
    V = np.where(bad, np.nan, np.nanmax(np.where(np.isfinite(v), v, -np.inf), axis=1))
    binding = np.where(bad, -1, np.argmax(np.where(np.isfinite(v), v, -np.inf), axis=1))
    v[bad, :] = np.nan
    return V, v, binding


def composite_rmsre(Y: np.ndarray, columns: Sequence[str],
                    targets: Sequence[Target]) -> np.ndarray:
    """The EXISTING A2MC ranking metric, for the disagreement check.

    Per-target `relative_error = |sim-obs|/obs`, aggregated by `rmsre`. Computed through
    `tools.cost_functions.aggregate_costs` rather than re-derived here, so this cannot drift from
    what the rest of A2MC ranks by ([[feedback_bind_derived_facts_to_their_source]]).
    """
    idx = [_column_index(columns, t.name) for t in targets]
    sub = np.asarray(Y, dtype=float)[:, idx]
    obs = np.array([t.observed for t in targets], dtype=float)
    rel = np.abs(sub - obs) / obs
    out = np.full(len(sub), np.nan)
    for i, row in enumerate(rel):
        if np.isfinite(row).all():
            out[i] = aggregate_costs(list(row), method="rmsre")
    return out


def _column_index(columns: Sequence[str], name: str) -> int:
    try:
        return list(columns).index(name)
    except ValueError:
        raise SystemExit(
            f"REFUSING: target {name!r} has no column in the Y matrix (columns: "
            f"{list(columns)}). The target names in `targets.yaml` and the column names in the "
            f"extracted matrix are a CONTRACT; a mismatch here would otherwise silently score "
            f"fewer targets than the case declares.")


# =============================================================================
# The S0 deliverable: where do the two rankings disagree?
# =============================================================================

def compare_rankings(V: np.ndarray, C: np.ndarray, cases: Sequence[int],
                     top: int = 10) -> dict:
    """Top-`top` by `V` and by the composite, plus how much the two orderings agree.

    `overlap` is what the S0 gate reads: a high overlap means the Chebyshev change is close to
    cosmetic on this ensemble, a low one means the two objectives genuinely differ and the
    composite has been hiding a binding target.
    """
    ok = np.isfinite(V) & np.isfinite(C)
    if not ok.any():
        raise SystemExit("REFUSING: no row has both a finite V and a finite composite.")
    cases = np.asarray(cases)
    oV = cases[ok][np.argsort(V[ok], kind="stable")][:top]
    oC = cases[ok][np.argsort(C[ok], kind="stable")][:top]
    from scipy.stats import spearmanr
    rho = float(spearmanr(V[ok], C[ok]).statistic)
    return {
        "n_scored": int(ok.sum()),
        "top_by_V": [int(c) for c in oV],
        "top_by_composite": [int(c) for c in oC],
        "overlap": len(set(oV.tolist()) & set(oC.tolist())),
        "top": int(top),
        "spearman_V_vs_composite": rho,
        "same_argmin": bool(oV[0] == oC[0]),
    }


# =============================================================================
# CLI
# =============================================================================

def _read_y_csv(path) -> Tuple[List[int], List[str], np.ndarray, List[str]]:
    rows = list(csv.DictReader(pathlib.Path(path).open()))
    if not rows:
        raise SystemExit(f"REFUSING: {path} has no rows.")
    fields = list(rows[0].keys())
    if "case" not in fields:
        raise SystemExit(f"REFUSING: {path} has no `case` column (columns: {fields}).")
    value_cols = [f for f in fields if f not in ("case", "status")]
    cases = [int(r["case"]) for r in rows]
    status = [r.get("status", "") for r in rows]

    def _f(x):
        try:
            return float(x)
        except (TypeError, ValueError):
            return float("nan")

    Y = np.array([[_f(r[c]) for c in value_cols] for r in rows], dtype=float)
    return cases, value_cols, Y, status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="docs/42 stage S0 -- the normalized-violation objective V, and the free "
                    "disagreement check against the existing composite ranking.")
    ap.add_argument("--targets", default=os.environ.get("A2MC_VALIDATION_TARGETS"),
                    help="targets.yaml (default: $A2MC_VALIDATION_TARGETS)")
    ap.add_argument("--y-matrix", required=True,
                    help="extracted Y matrix CSV: case[,status],<one column per target>")
    ap.add_argument("--only", help="comma-separated subset of target names to score")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--out", help="write the per-case V table to this CSV")
    ap.add_argument("--json", help="write the comparison summary to this JSON")
    a = ap.parse_args(argv)

    if not a.targets:
        raise SystemExit("REFUSING: no --targets and $A2MC_VALIDATION_TARGETS unset. Source the "
                         "site config, or pass the file.")

    names = [s.strip() for s in a.only.split(",")] if a.only else None
    targets = load_targets(a.targets, names)
    cases, cols, Y, status = _read_y_csv(a.y_matrix)

    V, v, binding = violation_matrix(Y, cols, targets)
    C = composite_rmsre(Y, cols, targets)
    summary = compare_rankings(V, C, cases, top=a.top)

    print(f"\ntargets ({len(targets)}), from {a.targets}")
    for t in targets:
        print(f"  {t.name:12s} obs {t.observed:10.4g}  u {t.uncertainty:.3f}  "
              f"band [{t.lo:.4g}, {t.hi:.4g}] {t.units}")

    n_feas = int(np.nansum(V <= 1.0))
    print(f"\n{len(cases)} rows, {summary['n_scored']} scored, "
          f"{len(cases) - summary['n_scored']} unscorable (missing or non-finite -- NOT ranked last)")
    print(f"jointly feasible (V <= 1): {n_feas}")

    order = np.argsort(np.where(np.isfinite(V), V, np.inf), kind="stable")[:a.top]
    print(f"\ntop {a.top} by V (lower is better; V <= 1 means ALL targets in band)")
    head = "  rank  case        V   binding   " + "  ".join(f"v[{t.name}]" for t in targets)
    print(head)
    for r, i in enumerate(order, 1):
        if not np.isfinite(V[i]):
            continue
        bn = targets[binding[i]].name
        print(f"  {r:4d}  {cases[i]:6d} {V[i]:8.3f}   {bn:9s} "
              + "  ".join(f"{v[i, j]:9.3f}" for j in range(len(targets))))

    print(f"\ntop {a.top} by the existing composite (relative_error + rmsre)")
    orderC = np.argsort(np.where(np.isfinite(C), C, np.inf), kind="stable")[:a.top]
    for r, i in enumerate(orderC, 1):
        if not np.isfinite(C[i]):
            continue
        print(f"  {r:4d}  {cases[i]:6d} {C[i]:8.4f}   (V {V[i]:7.3f}, binds "
              f"{targets[binding[i]].name})")

    print(f"\nDISAGREEMENT: {summary['overlap']}/{a.top} of the two top-{a.top} sets are shared; "
          f"spearman(V, composite) = {summary['spearman_V_vs_composite']:.4f}; "
          f"same argmin: {summary['same_argmin']}")

    if a.out:
        with pathlib.Path(a.out).open("w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["case", "status", "V", "binding", "composite_rmsre"]
                       + [f"v_{t.name}" for t in targets])
            for i, c in enumerate(cases):
                w.writerow([c, status[i],
                            "" if not np.isfinite(V[i]) else f"{V[i]:.6f}",
                            "" if binding[i] < 0 else targets[binding[i]].name,
                            "" if not np.isfinite(C[i]) else f"{C[i]:.6f}"]
                           + ["" if not np.isfinite(v[i, j]) else f"{v[i, j]:.6f}"
                              for j in range(len(targets))])
        print(f"\nwrote {a.out}")
    if a.json:
        import json
        pathlib.Path(a.json).write_text(json.dumps(summary, indent=2))
        print(f"wrote {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
