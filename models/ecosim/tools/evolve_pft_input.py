#!/usr/bin/env python
"""Evolve a version-drifted EcoSIM pft input to satisfy a newer binary.

The REMEDY paired with the generic guard ``tools/model_check_input_compat.py``:
when that guard reports INCOMPATIBLE (the built binary reads per-PFT variables an
older input file lacks), this tool adds the missing variables to the input rather
than forcing a binary rebuild at the input's commit.

Why this is legitimate and not fabrication: every added value is a real model
default, carried (with its dtype + ``units`` + ``long_name``) from a *newer,
complete* EcoSIM pft parameter table (``--donor``, e.g. an upstream
``ecosim_pftpar_YYYYMMDD.nc`` that already carries the added vars). Each source
PFT is matched to a donor row by FUNCTIONAL ANALOGY using EcoSIM's own type flags
(ICTYP photosynthesis, INTYP N-fixation, IGTYP root profile, ISTYP phenology),
so a C4 grass draws from a C4 grass, a C3 legume from a C3 N-fixer, etc. The
chosen analogs + match scores are printed for review; override any with
``--analog SRCNAME=DONORNAME``.

Discovery of the missing set is automatic and shares the guard's contract: it
reads the binary's required per-PFT vars from ``spec.input_reader_sources`` via
``spec.input_read_pattern`` over ``--checkout``, and diffs against the input.

Typical use (BioCON test1_ex1 vs the api-2dea74d9 binary — 17 missing vars):
    python models/ecosim/tools/evolve_pft_input.py \
        --input  Offline/.../ds_input__pft_test__ex1.nc \
        --checkout ~/EcoSIM \
        --donor  input_data/ecosim_pftpar_20260520.nc \
        --out    Offline/.../ds_input__pft_test__ex1__evolved.nc

Then re-verify:
    python tools/model_check_input_compat.py --model ecosim \
        --checkout <...> --param-file <the --out file>   # -> COMPATIBLE

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional

REPO = Path(__file__).resolve().parents[3]

# Type-flag vars used for functional-analog scoring, most→least discriminating.
# ICTYP (C3/C4) and INTYP (N-fixation pathway) are decisive; IGTYP/ISTYP refine.
_FLAG_WEIGHTS = [("ICTYP", 100), ("INTYP", 40), ("IGTYP", 10), ("ISTYP", 5)]


def _names(ds) -> List[str]:
    ds.set_auto_mask(False)
    return [b"".join(r).decode(errors="ignore").strip() for r in ds.variables["pfts"][:]]


def _required_vars(checkout: Path, spec) -> set:
    read_re = re.compile(spec.input_read_pattern)
    req: set = set()
    for rel in spec.input_reader_sources:
        req |= set(read_re.findall((checkout / rel).read_text(errors="ignore")))
    return req


def _score(dvars, di, ivars, ii) -> int:
    """Analog score: sum of weights for matching type flags (higher = better)."""
    s = 0
    for flag, w in _FLAG_WEIGHTS:
        if flag in dvars and flag in ivars:
            try:
                if int(dvars[flag][di]) == int(ivars[flag][ii]):
                    s += w
            except Exception:
                pass
    return s


def _auto_analogs(inp, donor, overrides: Dict[str, str]):
    inames, dnames = _names(inp), _names(donor)
    dvars, ivars = donor.variables, inp.variables
    mapping = {}
    for ii, iname in enumerate(inames):
        if iname in overrides:
            dname = overrides[iname]
            if dname not in dnames:
                raise SystemExit(f"--analog {iname}={dname}: '{dname}' not in donor")
            mapping[iname] = (dname, dnames.index(dname), "override")
            continue
        best_di, best_s = None, -1
        for di in range(len(dnames)):
            s = _score(dvars, di, ivars, ii)
            if s > best_s:
                best_di, best_s = di, s
        mapping[iname] = (dnames[best_di], best_di, f"score={best_s}")
    return mapping, inames


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, help="the drifted pft input .nc to evolve")
    ap.add_argument("--checkout", required=True, help="EcoSIM source tree of the BUILT binary")
    ap.add_argument("--donor", required=True, help="newer complete pft table .nc (has the added vars)")
    ap.add_argument("--out", required=True, help="output evolved .nc (input is left untouched)")
    ap.add_argument("--analog", action="append", default=[],
                    help="override a mapping: SRCNAME=DONORNAME (repeatable)")
    ap.add_argument("--dry-run", action="store_true", help="report the plan; write nothing")
    args = ap.parse_args()

    sys.path.insert(0, str(REPO))
    import importlib
    importlib.import_module("models.ecosim")
    from models import registry
    spec = registry.get_model("ecosim").spec
    import netCDF4 as nc

    inp = nc.Dataset(args.input)
    donor = nc.Dataset(args.donor)
    have = set(inp.variables)
    required = _required_vars(Path(args.checkout), spec)
    missing = sorted(required - have)
    if not missing:
        print("Nothing to do — the input already has every var the binary reads.")
        return 0
    donor_missing = [v for v in missing if v not in donor.variables]
    if donor_missing:
        raise SystemExit(f"donor lacks {len(donor_missing)} of the missing vars: {donor_missing}\n"
                         f"  pick a newer --donor that carries them.")

    overrides = dict(a.split("=", 1) for a in args.analog)
    mapping, inames = _auto_analogs(inp, donor, overrides)

    print(f"binary requires {len(required)} vars; input has {len(have)}; MISSING {len(missing)}")
    print(f"adding {len(missing)}: {missing}\n")
    print("functional-analog mapping (source PFT -> donor row):")
    for n in inames:
        dname, di, how = mapping[n]
        print(f"  {n:10s} -> {dname:10s} ({how})")
    if args.dry_run:
        print("\n[dry-run] no file written.")
        return 0

    shutil.copy(args.input, args.out)
    out = nc.Dataset(args.out, "a")
    for v in missing:
        dvar = donor.variables[v]
        dtype = dvar.dtype
        vals = []
        for n in inames:
            _, di, _ = mapping[n]
            x = float(dvar[di])
            vals.append(int(round(x)) if dtype.kind in "iu" else x)
        nv = out.createVariable(v, dtype, ("npfts",))
        for attr in ("units", "long_name"):
            if hasattr(dvar, attr):
                nv.setncattr(attr, getattr(dvar, attr))
        nv.setncattr("source", "evolve_pft_input from " + Path(args.donor).name
                     + " analogs " + ",".join(f"{n}:{mapping[n][0]}" for n in inames))
        nv[:] = vals
    out.close(); inp.close(); donor.close()
    print(f"\nwrote {args.out} (+{len(missing)} vars). Re-verify with tools/model_check_input_compat.py.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
