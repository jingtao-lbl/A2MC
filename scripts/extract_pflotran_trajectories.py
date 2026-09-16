#!/usr/bin/env python
"""Extract per-case OUTFLOW CONCENTRATION trajectories from a PFLOTRAN ensemble's `*-mas.dat` tapes.

The trajectory sibling of the scalar path used by `scripts/extract_flat_ensemble_targets.py`, and
the PFLOTRAN parallel of `scripts/extract_ecosim_trajectories.py`. An S2/S3 or KGML-style emulator
needs the series the scored scalars were reduced FROM, and nothing else in the kit produces it.

WHY THIS IS A PFLOTRAN SCRIPT AND NOT A GENERIC ONE. The reduce is model-specific in a way no
shared flag captures: a PFLOTRAN outflow concentration is a RATIO of two coupler columns evaluated
pointwise, the tape is fixed-width text rather than NetCDF, and the sign convention below is a
property of how PFLOTRAN reports boundary flux. Per `feedback_per_model_scripts_not_generic`,
A2MC's own machinery is generic and per-model artifact scripts are parallel.

WHAT IT WRITES. One `.npz` holding

    traj      (n_cases, n_targets, n_steps) float32   pointwise concentration, mol/L
    cases     (n_cases,)   int              case numbers, ascending
    targets   (n_targets,) str              e.g. outflow_Fe
    time_h    (n_steps,)   float32          model time in hours, the tape's own axis
    water     (n_cases, n_steps) float32    |east Water Mass|, kg/h -- the driver, see below

THE REDUCE IS THE SCORER'S, EVALUATED POINTWISE AND NOT AVERAGED:

    C_X(t) = east X [mol/h] / (east Water Mass [kg/h] / rho * 1000)        [mol/L]

which is `models/pflotran/backend.py::reduce_derived`'s expression before its time-mean. Taking the
window mean of `traj` therefore reproduces the scored scalar, and `--check-against` asserts exactly
that on a sample of cases. The `build-surrogate` skill calls this reduce-and-check rather than
reduce-and-trust: a mismatched reducer yields a surrogate that is internally consistent, plausible,
and answering a different question than the calibration is scored on, which nothing downstream sees.

TWO SIGN AND GUARD TRAPS, BOTH ALREADY PAID FOR ELSEWHERE IN THIS CASE:

  * PFLOTRAN signs the outflow NEGATIVE (mass LEAVING the domain), so the solute rate and the water
    rate are both negative and their ratio is the positive concentration.
  * The authoritative reduce guards on `w == 0`, NOT on `w > 0` (`models/pflotran/backend.py:228`).
    Guarding on the sign instead NaNs the entire series. An earlier figure script in this case did
    exactly that and produced eleven empty panels that ran without error.

THE HYDROGRAPH IS NOT A TARGET HERE. It is an NRMSE sentinel rather than a concentration, it is in
band for 100% of cases so it constrains nothing, and it was calibrated before this round. It is
written out as `water` because it is the natural DRIVER for a conditioned emulator, not as a target.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from models.pflotran.output_parser import PFLOTRANOutputParser  # noqa: E402

RHO_WATER = 997.16
SPECIES = {"Na": "Na+", "Mg": "Mg++", "Al": "Al+++", "Si": "SiO2(aq)", "P": "HPO4--",
           "K": "K+", "Ca": "Ca++", "Mn": "Mn++", "Fe": "Fe++", "DIC": "CO2(aq)"}
WATER = "east Water Mass [kg/h]"
TIME = "Time [h]"


def _columns(labels):
    """The tape column names this script needs, in target order."""
    return [TIME, WATER] + [f"east {SPECIES[k]} [mol/h]" for k in labels]


def read_case(args):
    """Return (case, time_h, water, conc[n_targets, n_steps]) or (case, None, None, None)."""
    case, case_dir, labels, n_expect = args
    p = next(Path(case_dir).glob("*-mas.dat"), None)
    if p is None:
        return case, None, None, None
    try:
        par = PFLOTRANOutputParser()
        hdr = par.parse(p)

        def col(name):
            return next((v for n, v in hdr.items() if n.strip().strip('"').strip() == name), None)

        want = _columns(labels)
        cols = [col(w) for w in want]
        if any(c is None for c in cols):
            return case, None, None, None
        series = par.read_series(p, cols)
        d = {w: np.asarray(v, dtype=np.float64) for w, v in zip(want, series.values())}
    except Exception:
        return case, None, None, None

    t = d[TIME]
    if n_expect and len(t) != n_expect:
        return case, None, None, None          # a partial tape is not a short trajectory
    litres = d[WATER] / RHO_WATER * 1000.0
    out = np.empty((len(labels), len(t)), dtype=np.float32)
    with np.errstate(divide="ignore", invalid="ignore"):
        for i, k in enumerate(labels):
            r = d[f"east {SPECIES[k]} [mol/h]"]
            out[i] = np.where(litres != 0, r / litres, np.nan)   # == 0, never > 0
    return case, t.astype(np.float32), np.abs(d[WATER]).astype(np.float32), out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--run-root", required=True, type=Path)
    ap.add_argument("--case-pattern", default="miniLEO_case{n}")
    ap.add_argument("--first", type=int, required=True)
    ap.add_argument("--last", type=int, required=True)
    ap.add_argument("--targets", nargs="+", default=list(SPECIES),
                    help="species labels; the hydrograph is deliberately not one")
    ap.add_argument("--n-steps", type=int, default=3360,
                    help="required tape length; a case with any other length is DROPPED as partial")
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--out", required=True, type=Path)
    a = ap.parse_args()

    labels = [t for t in a.targets if t in SPECIES]
    if len(labels) != len(a.targets):
        print(f"unknown target(s): {sorted(set(a.targets) - set(SPECIES))}", file=sys.stderr)
        return 2

    jobs = [(n, a.run_root / a.case_pattern.format(n=n), labels, a.n_steps)
            for n in range(a.first, a.last + 1)]
    print(f"reading {len(jobs)} cases, {len(labels)} targets, {a.workers} workers")

    cases, T, W, C = [], None, [], []
    dropped = 0
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (case, t, w, c) in enumerate(ex.map(read_case, jobs, chunksize=8), 1):
            if c is None:
                dropped += 1
            else:
                if T is None:
                    T = t
                cases.append(case); W.append(w); C.append(c)
            if i % 500 == 0:
                print(f"  {i}/{len(jobs)}  kept {len(cases)}  dropped {dropped}", flush=True)

    if not cases:
        print("no usable trajectories", file=sys.stderr)
        return 1
    traj = np.stack(C).astype(np.float32)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(a.out, traj=traj, cases=np.array(cases, dtype=np.int32),
                        targets=np.array([f"outflow_{k}" for k in labels]),
                        time_h=T, water=np.stack(W).astype(np.float32))
    print(f"\nwrote {a.out}")
    print(f"  traj {traj.shape}  (cases, targets, steps)   kept {len(cases)}  dropped {dropped}")
    print(f"  time {T[0]:.1f} to {T[-1]:.1f} h over {len(T)} steps")
    nan = int(np.isnan(traj).sum())
    print(f"  NaN cells: {nan} ({100*nan/traj.size:.4f}%) -- these are w==0 steps, not failures")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
