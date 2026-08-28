#!/usr/bin/env python
"""Pre-submit input↔binary compatibility check for EcoSIM.

The EcoSIM binary reads a fixed set of PFT-file variables (via
`ncd_getvar(pft_nfid,'NAME',…)` in `PlantInfoMod.F90`). If the input PFT file is
from an OLDER EcoSIM version than the built binary, it can be missing variables
the binary requires — the run then ENDRUNs mid-read ("NetCDF: Variable not
found") after wasting an HPC submit (see `memory/dev_logs_adapterkit/20260712b`,
the IEBTYP 17-variable mismatch). This tool catches that BEFORE submit.

It parses the reads out of the source (so it tracks the actual built version) and
diffs against the input file's variables. Exit 0 = compatible; exit 2 = the input
is missing variables the binary reads (incompatible — do not submit).

EcoSIM-specific for now (the `ncd_getvar(pft_nfid,…)` reader pattern is EcoSIM's);
generalizing via a `spec` field is a distillation follow-up.

Usage:
    python tools/ecosim_check_input_compat.py \
        --checkout ~/EcoSIM \
        --param-file Offline/EcoSIM_sample_files/input/ds_input__pft_test__ex1.nc

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

_READER = "f90src/IOutils/PlantInfoMod.F90"
_READ_RE = re.compile(r"ncd_getvar\(\s*pft_nfid\s*,\s*'([A-Za-z0-9_]+)'")


def binary_reads(checkout: Path) -> set[str]:
    src = checkout / _READER
    if not src.exists():
        raise FileNotFoundError(f"EcoSIM PFT reader not found: {src}")
    return set(_READ_RE.findall(src.read_text()))


def file_vars(param_file: Path) -> set[str]:
    import netCDF4 as nc
    return set(nc.Dataset(param_file).variables)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--checkout", required=True, help="EcoSIM source-tree root (the built version)")
    ap.add_argument("--param-file", required=True, help="PFT input NetCDF to check")
    args = ap.parse_args()

    checkout, pf = Path(args.checkout), Path(args.param_file)
    if not checkout.is_dir():
        print(f"ERROR: checkout not found: {checkout}", file=sys.stderr)
        return 1
    if not pf.exists():
        print(f"ERROR: param file not found: {pf}", file=sys.stderr)
        return 1

    reads = binary_reads(checkout)
    have = file_vars(pf)
    missing = sorted(reads - have)

    print(f"binary reads {len(reads)} PFT vars (from {_READER}); input file has {len(have)} vars")
    if not missing:
        print("✔ COMPATIBLE — the input file has every PFT variable the binary reads.")
        return 0
    print(f"✘ INCOMPATIBLE — the input is missing {len(missing)} variable(s) the binary reads:")
    print("    " + ", ".join(missing))
    print("  → The input PFT file is from an older EcoSIM than the built binary. The run would")
    print("    ENDRUN ('NetCDF: Variable not found'). Rebuild the binary at the input's commit,")
    print("    or regenerate the input with these variables, before submitting.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
