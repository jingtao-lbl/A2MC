#!/usr/bin/env python
"""Sensitivity indices computed DIRECTLY on a space-filling ensemble — no surrogate, no special design.

WHY THIS IS THE PRIMARY PHASE-1 INSTRUMENT FOR A SPACE-FILLING ROUND.

A2MC's two familiar analyzers both require a design this round does not have. `sobol.analyze` needs
the Saltelli A/B/AB cross-sampling; `morris.analyze` needs trajectories. A scrambled Sobol' SEQUENCE
(``--method sobol_seq``) has neither, and — the dangerous part — **neither analyzer errors on it**.
Both reshape the rows and return plausible numbers computed from a structure that is not there.

The estimators here are *given-data* methods: they accept an arbitrary `(X, Y)` cloud and estimate
sensitivity from it. That buys three things over routing through a surrogate:

  1. **No surrogate error.** The surrogate route was measured to inflate the dominant total index by
     25% at this round's scale (16 params, 4096 points; dev log `20260827d`). These estimators read
     the simulator's own output.
  2. **No gate.** The surrogate build is paused until the ensemble reaches the observational bands
     (`docs/41`, `scripts/check_surrogate_gate.py`). These methods are outside that gate by
     construction — they interpolate nothing.
  3. **Independent cross-checks.** Three estimators resting on different principles agreeing is
     stronger evidence than one estimator's number.

WHAT IT DOES NOT GIVE YOU. No second-order indices S_ij, and no clean first-order/total split of the
kind `sobol.analyze` produces. If those are needed, that is the surrogate route's job and it is
gated. **Also: the three metrics are NOT on a common scale** — delta is a moment-independent
distributional distance, RBD-FAST estimates a first-order variance share, PAWN a CDF distance. Only
the RANKING is comparable across them, which is why the consensus below is computed on RANKS.

THE INERT TAIL IS NOT RANKED. In a 16-parameter round most parameters do nothing, and their relative
order is noise. Ranking noise produces a table that looks informative and is not, and it corrupts a
rank correlation computed over all parameters (measured: that statistic FALLS as the estimate
improves, because half its weight is on the inert tail — `20260827d`). So the noise floor is
MEASURED by permuting Y and seeing what delta an irrelevant input earns on this design at this n;
parameters below that floor are reported as `[noise]` and their order must not be read as a ranking.
(Delta's own bootstrap CI was tried first and is NOT sufficient — see `noise_floor` for why it
called 15 of 16 inputs significant on a test where 3 mattered.)

Usage::

    source use_cases/<Case>/config/<case>_config.sh
    python scripts/given_data_sensitivity.py --y-matrix <Y csv> --out <dir>

Generic: everything model-specific arrives through the param list, the X matrix and the Y matrix.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import warnings
from pathlib import Path
from typing import Any, Dict, List

import numpy as np

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

# Each entry: (label, what the number MEANS, the key holding the per-input score).
# Kept explicit rather than inferred, because the three return different key sets and guessing
# which key is "the" score is how an estimator silently gets read as another.
ESTIMATORS = {
    "delta":    ("Borgonovo delta — moment-independent distributional distance", "delta"),
    "rbd_fast": ("RBD-FAST — first-order variance share", "S1"),
    "pawn":     ("PAWN — median KS distance between conditional and unconditional CDFs", "median"),
}


def load_y(path: Path):
    with Path(path).open() as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path} has no rows")
    targets = [c for c in rows[0] if c not in ("case", "status")]
    return rows, targets


def build_xy(rows, targets, X_all, target: str):
    """Rows usable for THIS target: completed, in-matrix, and finite in this column.

    Filtered per target rather than once globally: a case can produce a valid Si and a NaN Mn, and
    dropping it from every target would discard data the other targets can use.
    """
    xs, ys, dropped = [], [], 0
    for r in rows:
        if r.get("status") != "COMPLETED":
            dropped += 1
            continue
        i = int(r["case"]) - 1
        if i < 0 or i >= len(X_all):
            dropped += 1
            continue
        try:
            v = float(r[target])
        except (TypeError, ValueError):
            dropped += 1
            continue
        if not np.isfinite(v):
            dropped += 1
            continue
        xs.append(X_all[i])
        ys.append(v)
    return np.array(xs, dtype=float), np.array(ys, dtype=float), dropped


def run_estimators(problem, X, Y, resamples: int) -> Dict[str, Any]:
    """Run each estimator, tolerating one failing without losing the others."""
    from SALib.analyze import delta as _delta, pawn as _pawn, rbd_fast as _rbd

    out: Dict[str, Any] = {}
    calls = {"delta": (_delta, {"num_resamples": resamples}),
             "rbd_fast": (_rbd, {}),
             "pawn": (_pawn, {})}
    for name, (mod, kw) in calls.items():
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                res = mod.analyze(problem, X, Y, print_to_console=False, **kw)
            out[name] = {k: np.asarray(v, dtype=float)
                         for k, v in res.items() if k != "names"}
        except Exception as e:                                   # noqa: BLE001
            # Report rather than abort: losing one estimator still leaves a consensus of two,
            # and which one failed is itself information.
            out[name] = {"_error": str(e)[:200]}
            print(f"    WARNING: {name} failed ({type(e).__name__}: {str(e)[:110]})")
    return out


def consensus_ranks(res: Dict[str, Any], n_inputs: int) -> np.ndarray:
    """Mean rank across the estimators that succeeded. Rank 1 = most influential.

    On RANKS, not values, because the three metrics are not on a common scale — averaging a delta
    with an S1 with a PAWN median would produce a number of no defined meaning.
    """
    ranks = []
    for name, (_desc, key) in ESTIMATORS.items():
        d = res.get(name, {})
        if "_error" in d or key not in d:
            continue
        v = np.abs(np.asarray(d[key], dtype=float))
        order = np.argsort(-v)
        r = np.empty(n_inputs, dtype=float)
        r[order] = np.arange(1, n_inputs + 1)
        ranks.append(r)
    if not ranks:
        return np.full(n_inputs, np.nan)
    return np.mean(ranks, axis=0)


def noise_floor(problem, X, Y, n_perm: int, seed: int) -> float:
    """The delta an IRRELEVANT input earns on this design at this n — measured, not assumed.

    WHY A PERMUTATION NULL AND NOT DELTA'S OWN CONFIDENCE INTERVAL. The first version of this
    check used `delta - delta_conf > 0`, and on a 593-row test where exactly THREE of sixteen
    inputs mattered it called **fifteen** of them distinguishable. The bootstrap CI describes the
    stability of the estimate under resampling, not its bias: at finite n every input earns a
    small positive delta because conditioning on any variable perturbs the empirical conditional
    distribution a little. A check that cannot return "noise" is not a check
    ([[feedback_a_check_that_cannot_fail]]).

    Permuting Y destroys every X-Y relationship while preserving both marginals, the sample size
    and the design's own geometry — so the deltas it produces are exactly what an irrelevant input
    earns here. The floor is the MAXIMUM over all inputs and all permutations, which makes it a
    family-wise threshold: it controls the chance that ANY of the 16 clears it by luck, not just a
    nominated one.
    """
    from SALib.analyze import delta as _delta

    rng = np.random.default_rng(seed)
    worst = 0.0
    for _ in range(max(1, n_perm)):
        Yp = rng.permutation(Y)
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = _delta.analyze(problem, X, Yp, num_resamples=10, print_to_console=False)
            worst = max(worst, float(np.max(np.asarray(r["delta"], dtype=float))))
        except Exception:                                        # noqa: BLE001
            continue
    return worst


def distinguishable(res: Dict[str, Any], n_inputs: int, floor: float) -> np.ndarray:
    """Inputs whose delta clears the measured noise floor. The rest are the inert tail."""
    d = res.get("delta", {})
    if "_error" in d or "delta" not in d:
        return np.full(n_inputs, True)          # cannot test -> do not silently exclude
    return np.asarray(d["delta"], dtype=float) > floor


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    env = os.environ.get
    ap.add_argument("--y-matrix", required=True)
    ap.add_argument("--x-matrix", default=env("A2MC_ENSEMBLE_MATRIX_FILE"))
    ap.add_argument("--param-list", default=env("A2MC_PARAM_LIST_FILE"))
    ap.add_argument("--resamples", type=int, default=50,
                    help="bootstrap resamples for delta's confidence interval")
    ap.add_argument("--permutations", type=int, default=5,
                    help="Y-permutations used to MEASURE the noise floor (0 disables "
                         "the inert-tail test, which then reports every input as signal)")
    ap.add_argument("--seed", type=int, default=123)
    ap.add_argument("--targets", nargs="*", default=None)
    ap.add_argument("--top", type=int, default=8, help="rows to print per target")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    for flag, val in (("--x-matrix", a.x_matrix), ("--param-list", a.param_list)):
        if not val:
            raise SystemExit(f"{flag} unset (source the site config)")

    from scripts.create_adapter_parameter_sample import parse_pft_param_list   # noqa: E402

    names, lo, hi = parse_pft_param_list(a.param_list)
    names = list(names)
    problem = {"num_vars": len(names), "names": names,
               "bounds": [[float(x), float(y)] for x, y in zip(lo, hi)]}
    X_all = np.loadtxt(a.x_matrix)
    if X_all.shape[1] != len(names):
        raise SystemExit(f"REFUSING: matrix has {X_all.shape[1]} columns, param list has "
                         f"{len(names)} parameters")
    rows, ycols = load_y(Path(a.y_matrix))
    wanted = a.targets or ycols

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"design    : {X_all.shape[0]} x {X_all.shape[1]}   Y rows: {len(rows)}")
    print("estimators: " + ", ".join(f"{k} ({v[0].split(' — ')[0]})" for k, v in ESTIMATORS.items()))
    print("NOTE: the three metrics are NOT on a common scale; only the RANKING is comparable.\n")

    records: List[Dict[str, Any]] = []
    summary: Dict[str, Any] = {}
    for t in wanted:
        X, Y, dropped = build_xy(rows, ycols, X_all, t)
        if len(X) < 3 * len(names):
            print(f"  {t}: SKIPPED — only {len(X)} usable rows for {len(names)} parameters; "
                  f"a given-data estimate here would be noise")
            summary[t] = {"skipped": True, "n_usable": int(len(X))}
            continue
        res = run_estimators(problem, X, Y, a.resamples)
        cr = consensus_ranks(res, len(names))
        floor = noise_floor(problem, X, Y, a.permutations, a.seed) if a.permutations else 0.0
        dis = distinguishable(res, len(names), floor)

        for j, nm in enumerate(names):
            rec = {"target": t, "parameter": nm, "consensus_rank": float(cr[j]),
                   "distinguishable_from_noise": bool(dis[j]), "n_usable_rows": int(len(X))}
            for est, (_d, key) in ESTIMATORS.items():
                d = res.get(est, {})
                rec[est] = float(d[key][j]) if (key in d and "_error" not in d) else None
            records.append(rec)

        order = np.argsort(cr)
        n_dis = int(dis.sum())
        print(f"  {t}  ({len(X)} usable rows, {dropped} dropped; "
              f"{n_dis}/{len(names)} clear the measured noise floor delta>{floor:.4f})")
        for j in order[:a.top]:
            mark = " " if dis[j] else "  [noise]"
            bits = "  ".join(
                f"{e}={records[-len(names) + j][e]:.4f}" if records[-len(names) + j][e] is not None
                else f"{e}=n/a" for e in ESTIMATORS)
            print(f"      rank {cr[j]:4.1f}  {names[j]:32s} {bits}{mark}")
        summary[t] = {"n_usable": int(len(X)), "n_dropped": int(dropped),
                      "noise_floor_delta": float(floor), "n_distinguishable": n_dis,
                      "top_by_consensus": [names[j] for j in order if dis[j]][:a.top],
                      "estimators_ok": [e for e in ESTIMATORS
                                        if "_error" not in res.get(e, {"_error": 1})]}

    with (out / "given_data_sensitivity.csv").open("w", newline="") as fh:
        cols = ["target", "parameter", "consensus_rank", "distinguishable_from_noise",
                *ESTIMATORS, "n_usable_rows"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(records)
    (out / "given_data_sensitivity_summary.json").write_text(json.dumps(
        {"design": list(X_all.shape), "n_parameters": len(names),
         "estimators": {k: v[0] for k, v in ESTIMATORS.items()},
         "scale_note": "metrics are NOT on a common scale; consensus is computed on RANKS",
         "per_target": summary,
         "x_matrix": str(a.x_matrix), "y_matrix": str(a.y_matrix)}, indent=2))
    print(f"\nwrote {out}/given_data_sensitivity.csv and .../_summary.json")
    print("REPORTING RULE: this supports a RANKING of which parameters matter. It does NOT support "
          "a variance-share\n  claim, and the inert tail marked [noise] must not be reported as an "
          "ordering.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
