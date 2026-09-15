#!/usr/bin/env python
"""Extract per-case DAILY FLUX trajectories from an EcoSIM ensemble's h0 tapes.

The trajectory sibling of `scripts/extract_ecosim_outputs.py`, which extracts the reduced scalars.
An S2 (trajectory) surrogate needs the series those scalars were reduced from, and nothing else in
the kit produces it.

WHAT IT WRITES. One `.npz` holding `traj` (n_cases, n_targets, n_days) float32, the case numbers,
the target names, and the date axis, plus the `year_end` scalars recomputed from the same arrays.

THE TAPE IS WITHIN-YEAR CUMULATIVE AND THIS SCRIPT DE-CUMULATES IT. `ECO_*_col` variables reset
near zero each 1 January and rise monotonically; `reduce: year_end` takes the value at the last
record of a year, which is that year's total. The daily flux is therefore the within-year first
difference, with the year's first record kept as-is. Summing the daily flux over a year returns the
year-end value exactly, and `--self-check` asserts that rather than assuming it.

CALENDAR. EcoSIM runs a REAL Gregorian calendar, not a 365-day one, so day indices are built with
`datetime` and leap years carry 366 records. A fixed-365 stride silently drifts by one day per leap
year, which over a 28-year tape is a seven-day error by the end.

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

#: Tape variables that need composing or sign-flipping before they are a flux.
#: `ECO_RA_col` and `ECO_RH_col` are stored NEGATIVE (respiration as a loss), so a
#: positive-valued respiration flux is their negation; Reco is the negated sum.
DERIVED = {
    "Reco": (("ECO_RA_col", "ECO_RH_col"), -1.0),
    "RA":   (("ECO_RA_col",), -1.0),
    "RH":   (("ECO_RH_col",), -1.0),
}

#: Tape variables that are ALREADY an instantaneous flux and must NOT be de-cumulated, with the
#: factor converting them to the daily units the cumulative variables reduce to. `ECO_NEE_CO2_col`
#: is `umol C/m2/s`; x 12.0e-6 x 86400 = 1.0368 gives gC/m2/d, using the model's own molar mass of
#: 12.0 (`TracerPropMod.F90`). De-cumulating it would difference a flux and produce noise.
RAW = {"NEE": ("ECO_NEE_CO2_col", 12.0e-6 * 86400.0)}


def day_index(n: int, start: dt.date) -> np.ndarray:
    return np.array([start + dt.timedelta(days=i) for i in range(n)], dtype=object)


def decumulate(cum: np.ndarray, years: np.ndarray) -> np.ndarray:
    """Within-year first difference; the year's first record is kept as the first flux."""
    out = np.empty_like(cum)
    for y in np.unique(years):
        m = np.where(years == y)[0]
        seg = cum[m]
        out[m] = np.concatenate(([seg[0]], np.diff(seg)))
    return out


def one_case(args):
    case, path, tape_vars, targets, y0, y1, start = args
    import netCDF4 as nc
    try:
        with nc.Dataset(path) as d:
            raw = {v: d.variables[v][:, 0].astype("f8") for v in tape_vars}
    except Exception as exc:                       # a missing or truncated tape is data, not a crash
        return case, None, f"{type(exc).__name__}: {exc}"
    n = len(next(iter(raw.values())))
    dates = day_index(n, start)
    years = np.array([d_.year for d_ in dates])
    keep = (years >= y0) & (years <= y1)
    series = []
    for t in targets:
        if t in RAW:
            var, fac = RAW[t]
            series.append((raw[var] * fac)[keep].astype("f4"))     # already a flux
            continue
        if t in DERIVED:
            names, sign = DERIVED[t]
            cum = sign * sum(raw[v] for v in names)
        else:
            cum = raw[t]
        series.append(decumulate(cum, years)[keep].astype("f4"))
    return case, np.stack(series), None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--ensemble-root", required=True)
    ap.add_argument("--case-pattern", default="Lusignan_case{n}")
    ap.add_argument("--tape-glob", default="*.ecosim.h0.*.nc")
    ap.add_argument("--y-matrix", required=True, help="COMPLETED rows define which cases to read")
    ap.add_argument("--targets", nargs="+", default=["GPP", "Reco", "ET"])
    ap.add_argument("--tape-vars", nargs="+",
                    default=["ECO_GPP_col", "ECO_RA_col", "ECO_RH_col", "ECO_ET_col"])
    ap.add_argument("--target-vars", nargs="+", default=["ECO_GPP_col", "Reco", "ECO_ET_col"],
                    help="per target: a tape variable name, or a key of DERIVED")
    ap.add_argument("--start-date", default="1996-01-01")
    ap.add_argument("--years", nargs=2, type=int, required=True, metavar=("Y0", "Y1"))
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit", type=int, default=None, help="first N cases only (a smoke run)")
    ap.add_argument("--self-check", action="store_true",
                    help="assert the de-cumulated series sums to the tape's year_end")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if len(a.target_vars) != len(a.targets):
        raise SystemExit(f"--targets ({len(a.targets)}) and --target-vars "
                         f"({len(a.target_vars)}) must have the same length")

    root = Path(a.ensemble_root)
    start = dt.date.fromisoformat(a.start_date)
    y0, y1 = a.years

    cases = [int(r["case"]) for r in csv.DictReader(open(a.y_matrix))
             if r.get("status") == "COMPLETED"]
    if a.limit:
        cases = cases[:a.limit]

    for t in a.target_vars:
        if t in RAW and RAW[t][0] not in a.tape_vars:
            a.tape_vars = list(a.tape_vars) + [RAW[t][0]]

    jobs, missing = [], []
    for c in cases:
        d = root / a.case_pattern.format(n=c)
        tapes = sorted(d.glob(a.tape_glob))
        if not tapes:
            missing.append(c); continue
        jobs.append((c, str(tapes[0]), a.tape_vars, a.target_vars, y0, y1, start))
    print(f"cases: {len(cases)} COMPLETED, {len(jobs)} with a tape, {len(missing)} without",
          flush=True)

    got, failed = {}, {}
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for i, (case, arr, err) in enumerate(ex.map(one_case, jobs, chunksize=4), 1):
            if err:
                failed[case] = err
            else:
                got[case] = arr
            if i % 250 == 0:
                print(f"  {i}/{len(jobs)}  ok={len(got)} failed={len(failed)}", flush=True)

    if not got:
        raise SystemExit("no case produced a trajectory")
    order = sorted(got)
    traj = np.stack([got[c] for c in order])                    # (N, T, D)
    dates = [str(start + dt.timedelta(days=0))]                 # placeholder, replaced below
    n_days = traj.shape[2]
    full = day_index(10 ** 5 if False else 0, start)            # unused; axis rebuilt per window
    axis = [d_ for d_ in day_index(20000, start) if y0 <= d_.year <= y1][:n_days]

    # year_end recomputed from the SAME arrays the surrogate will train on, so the scalar the
    # surrogate reduces to is derived from its own inputs rather than carried over from elsewhere.
    yrs = np.array([d_.year for d_ in axis])
    ye = np.stack([[traj[:, t, yrs == y].sum(axis=1) for y in range(y0, y1 + 1)]
                   for t in range(traj.shape[1])])              # (T, Y, N)
    scalars = ye.mean(axis=1).T                                 # (N, T) mean annual

    if a.self_check:
        import netCDF4 as nc
        c0 = order[0]
        d0 = root / a.case_pattern.format(n=c0)
        with nc.Dataset(sorted(d0.glob(a.tape_glob))[0]) as d:
            raw = {v: d.variables[v][:, 0].astype("f8") for v in a.tape_vars}
        n = len(next(iter(raw.values())))
        allyrs = np.array([d_.year for d_ in day_index(n, start)])
        for t, tv in enumerate(a.target_vars):
            if tv in RAW:
                continue            # not cumulative, so there is no year_end to check against
            if tv in DERIVED:
                names, sign = DERIVED[tv]; cum = sign * sum(raw[v] for v in names)
            else:
                cum = raw[tv]
            tape_ye = np.mean([cum[np.where(allyrs == y)[0][-1]] for y in range(y0, y1 + 1)])
            assert abs(tape_ye - scalars[0, t]) < 1e-6 * max(1.0, abs(tape_ye)), (
                f"self-check FAILED for {a.targets[t]}: de-cumulated sum {scalars[0, t]:.6f} "
                f"!= tape year_end {tape_ye:.6f}. The trajectory does not reduce to the scalar.")
        print(f"self-check OK on case {c0}: de-cumulated sums reproduce the tape's year_end",
              flush=True)

    np.savez_compressed(a.out, traj=traj, cases=np.array(order),
                        targets=np.array(a.targets), scalars=scalars.astype("f8"),
                        dates=np.array([d_.isoformat() for d_ in axis]),
                        years=np.array([y0, y1]))
    print(f"\ntrajectories : {traj.shape}  (cases, targets, days)  float32")
    print(f"window       : {axis[0]} .. {axis[-1]}  ({n_days} days)")
    print(f"failed       : {len(failed)}" + (f"  e.g. {list(failed.items())[:2]}" if failed else ""))
    print(f"wrote        : {a.out}  ({Path(a.out).stat().st_size/1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
