#!/usr/bin/env python3
"""Compare two run directories' NetCDF outputs on their DATA, not their bytes.

THE FAILURE THIS EXISTS FOR. On 2026-08-22 a V0-at-equality check compared an old and a new
binary's outputs with `cmp` and reported **V0 FAIL: 20 differing files** on a healthy case. The
conclusion drawn was that a divide-by-zero fix was not inert, which would have blocked the fix.

It was the CHECK that was wrong. Exactly **two bytes** differed in a 1,841,416-byte restart, at
offset 779, and they were ASCII: `14:06:19` against `14:06:21`. A creation-time string that only
the restart files carry, two seconds apart because the two arms ran concurrently. Three restarts
matched purely because both runs happened to write them inside the same wall-second.

Measured properly: **13,337 variable arrays across 93 files, zero differences.**

A whole-file `cmp` on a format that embeds a creation timestamp can never pass except by luck. That
is the mirror of a check that cannot fail -- a check that cannot SUCCEED -- and it is just as
dangerous, because its false alarm argues for reverting a correct change.

    python3 tools/compare_netcdf_science.py <dir_a> <dir_b> [--glob '*.nc'] [--tol 0.0]

EXIT 0 identical within tolerance / 1 differs / 2 structural problem (missing files, no overlap).

Reads with auto-masking OFF: netCDF fills masked positions on read, so a masked-array comparison
can hide a difference in the stored bytes. Raw is what "bit-identical" has to mean.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import pathlib
import sys

import numpy as np

try:
    import netCDF4 as nc
except ImportError:
    sys.exit("netCDF4 is required")


def compare(a_dir: pathlib.Path, b_dir: pathlib.Path, pattern: str, tol: float):
    names = sorted(p.name for p in a_dir.glob(pattern))
    if not names:
        return 2, f"no files matching {pattern!r} in {a_dir}", []
    missing = [n for n in names if not (b_dir / n).exists()]
    rows, nfiles, nvars = [], 0, 0
    for n in names:
        if n in missing:
            continue
        da, db = nc.Dataset(a_dir / n), nc.Dataset(b_dir / n)
        da.set_auto_mask(False); db.set_auto_mask(False)
        nfiles += 1
        for v in da.variables:
            if v not in db.variables:
                rows.append((n, v, float("nan"), "absent in B")); continue
            x, y = np.asarray(da[v][:]), np.asarray(db[v][:])
            if x.shape != y.shape:
                rows.append((n, v, float("nan"), f"shape {x.shape} vs {y.shape}")); continue
            if x.size == 0 or x.dtype.kind not in "fiu":
                continue
            nvars += 1
            if np.array_equal(x, y):
                continue
            d = float(np.nanmax(np.abs(x.astype("float64") - y.astype("float64"))))
            if d > tol:
                rows.append((n, v, d, ""))
    return (1 if (rows or missing) else 0), (nfiles, nvars), (rows, missing)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("dir_a"); ap.add_argument("dir_b")
    ap.add_argument("--glob", default="*.nc")
    ap.add_argument("--tol", type=float, default=0.0,
                    help="max allowed abs difference (default 0.0 = bit-identical)")
    a = ap.parse_args()
    A, B = pathlib.Path(a.dir_a), pathlib.Path(a.dir_b)
    for d in (A, B):
        if not d.is_dir():
            print(f"✘ not a directory: {d}"); return 2
    rc, info, payload = compare(A, B, a.glob, a.tol)
    if rc == 2:
        print(f"✘ {info}"); return 2
    nfiles, nvars = info
    rows, missing = payload
    print(f"  compared {nfiles} file(s), {nvars} variable array(s), tol={a.tol}")
    if missing:
        print(f"  ✘ {len(missing)} file(s) present in A but absent in B:")
        for m in missing[:10]:
            print(f"      {m}")
    if rows:
        print(f"  ✘ {len(rows)} differing variable(s):")
        for n, v, d, note in sorted(rows, key=lambda r: -(r[2] if r[2] == r[2] else 0))[:15]:
            print(f"      {n}:{v}  {note or f'maxabs={d:.6e}'}")
        return 1
    if missing:
        return 1
    print("  ✔ IDENTICAL on the science — every compared array matches exactly.")
    print("    NOTE: this says nothing on its own. Identical output is also what running ONE binary")
    print("    twice produces, so the caller must ALSO assert the two binaries' hashes DIFFER.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
