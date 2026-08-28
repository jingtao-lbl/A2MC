#!/usr/bin/env python
"""Submit a tiny REAL EcoSIM ensemble to validate the backend against live Slurm.

2 cases at the provisional-bounds corners (lo / hi), each a short 2-year run
(forc_periods shortened from the 23-yr base), on the standalone serial binary.
This exercises write_parameter_file -> create_case -> submit_ensemble end-to-end
on real hardware (beyond the dry-run e2e test). Output tapes feed extraction +
evaluate_ecosim_case once the jobs complete.

Usage (from repo root, a2mc_env python):
    python scripts/run_ecosim_smoke_ensemble.py [--dry-run] [--years 2]

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
REPRO = Path("~/ecosim_repro")
BIN = "~/EcoSIM/build/Linux-x86_64-double-Release/bin/ecosim.f90.x"
BASE_NML = REPRO / "run_test1_ex1.nml"
BASE_PFT = REPRO / "inputs" / "ds_input__pft_test__ex1.nc"
BOUNDS = REPO / "models/ecosim/reference_bounds/ecosim_biocon_param_list.csv"
RUN_ROOT = "~/ecosim_smoke_runs"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="stage cases but do not sbatch")
    ap.add_argument("--years", type=int, default=2, help="run length in years (default 2)")
    ap.add_argument("--force", action="store_true", help="submit even if the input↔binary compat check fails")
    args = ap.parse_args()

    import sys
    sys.path.insert(0, str(REPO))
    from models.ecosim.backend import EcoSIMBackend
    from phases.phase0_design.create_parameter_sample import parse_param_list

    for p in (Path(BIN), BASE_NML, BASE_PFT):
        if not p.exists():
            print(f"MISSING prerequisite: {p}")
            return 1

    # Pre-submit gate: the input PFT file must have every var the binary reads
    # (else the run ENDRUNs mid-read — the IEBTYP version mismatch, 20260712b).
    from tools.ecosim_check_input_compat import binary_reads, file_vars
    ECOSIM_SRC = "~/EcoSIM"
    missing = sorted(binary_reads(Path(ECOSIM_SRC)) - file_vars(BASE_PFT))
    if missing and not args.force:
        print(f"ABORT: input PFT file is missing {len(missing)} vars the binary reads "
              f"(older-input/newer-binary mismatch): {missing}")
        print("  Fix the EcoSIM binary↔input version, or re-run with --force to submit anyway.")
        return 2

    be = EcoSIMBackend()
    names, lower, upper = parse_param_list(BOUNDS)
    corners = {"smoke_lo": dict(zip(names, lower)), "smoke_hi": dict(zip(names, upper))}

    cfg = {
        "A2MC_OUTPUT_DIR": RUN_ROOT,
        "A2MC_ECOSIM_BINARY": BIN,
        "A2MC_ECOSIM_BASE_NAMELIST": str(BASE_NML),
        "A2MC_HPC_ACCOUNT": "m5199",
        "A2MC_HPC_QUEUE": "shared",
        "A2MC_HPC_WALLTIME": "00:30:00",
        "A2MC_ECOSIM_MODULES": "# runtime: system libs only",
        "A2MC_DRY_RUN": "1" if args.dry_run else "",
    }

    case_dirs = []
    for name, mods in corners.items():
        pmods = {f"{n}_1": v for n, v in mods.items()}  # apply to PFT slot 1
        # Keep the base pft basename so the namelist's pft_file_in reference is repointed.
        pfile = Path(RUN_ROOT) / name / BASE_PFT.name
        pfile.parent.mkdir(parents=True, exist_ok=True)
        be.write_parameter_file(BASE_PFT, pmods, pfile)
        cd = be.create_case(name, pfile, cfg)
        # Shorten the run: forc_periods = 2000, 2000+years-1, 1
        rf = cd / "runfile.nml"
        txt = rf.read_text()
        txt = re.sub(r"forc_periods\s*=\s*\d+\s*,\s*\d+\s*,\s*\d+",
                     f"forc_periods = 2000, {2000 + args.years - 1}, 1", txt)
        rf.write_text(txt)
        case_dirs.append(cd)
        print(f"  staged {name}: {cd}  (forc_periods -> 2000..{2000 + args.years - 1})")

    ids = be.submit_ensemble(case_dirs, cfg)
    print(f"\nsubmitted {len(ids)} cases: {ids}")
    print(f"run root: {RUN_ROOT}")
    print(f"monitor: python tools/model_ensemble_status.py --model ecosim --run-root {RUN_ROOT} [--watch 60] [--failed]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
