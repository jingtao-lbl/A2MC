#!/usr/bin/env python
"""Assert an EcoSIM case's SCORING calendar matches the calendar it actually ran on.

WHY THIS EXISTS. On 2026-09-05 an entire 4,097-case round was scored over the WRONG ELEVEN YEARS
and nothing caught it. `use_cases/EcoSIM_TeRaCON/config/ecosim_teracon_config.sh` set

    export A2MC_VALIDATION_START_YEAR="2012"   # from every target's window_years

but that variable is the year of the tape's **record 0**, not the first scored year. The run starts
in 2000. `models/ecosim/backend.py::_year_blocks` therefore labelled record 0 as 2012, and
`window_years: [2012, 2022]` selected the tape's first eleven years -- calendar 2000-2010, the
establishment period -- instead of the observation window.

TWO CONCEPTS, TWO KEYS, AND THE NAME OF THE VARIABLE INVITES CONFLATING THEM:

    start_year   / $A2MC_VALIDATION_START_YEAR   the SIMULATION start; record 0's calendar year
    window_years                                 the COMPARISON window; which years are scored

Both of TeRaCON's years were individually right. They were in the wrong slots.

WHY IT WAS SILENT, which is the part that makes a checker necessary rather than nice to have.
2000 and 2012 have IDENTICAL leap patterns over 23 years -- six leap years each, offset by a
multiple of four -- so `year_blocks` produced byte-identical block boundaries and only the labels
moved. Coverage stayed complete, `_select_years` raised nothing, no warning fired. The only visible
symptom was that `Fs` disagreed with the other two targets, and `Fs` disagreed only because its
target block carries an explicit `start_year: 2000` that bypasses the env var.

WHAT IT CHECKS, against `runfile.nml`'s `start_date`, which is what the model actually ran:

  1. $A2MC_VALIDATION_START_YEAR == the run's start year.                          ERROR
  2. targets.yaml top-level `start_year` == the run's start year.                  ERROR
  3. each target's own `start_year`, where present, == the run's start year.       ERROR
  4. every target's `window_years` lies inside the run's span.                     ERROR
  5. a target with NO `start_year` of its own, which silently depends on the env
     var whose name caused this.                                                   WARN
  6. every target's `window_years` lies inside the PRODUCTION leg, not the spin-up. ERROR
     Only applies when `forc_periods` has two or more triplets, where the last is production.

Check 5 is a warning rather than an error because depending on the env var is legal and currently
normal; it is reported because it is the fragility that turned a one-line config typo into a
round-wide scoring error, and because the one target that had it was the one target that survived.

EXIT: 0 clean, 1 warnings only, 2 errors.

Run:  source use_cases/<Case>/config/<case>_config.sh
      python tools/check_ecosim_validation_years.py [--case-dir DIR] [--targets FILE]

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from pathlib import Path


def run_start_year(case_dir: Path | None, namelist: Path | None) -> tuple[int, Path]:
    """The year the model ACTUALLY started, from `start_date` in the run namelist.

    The history tape carries no `time` variable, so the namelist is the only source of truth --
    which is precisely why nothing downstream could cross-check the env var.
    """
    cands = []
    if case_dir:
        cands += sorted(glob.glob(str(Path(case_dir) / "runfile.nml")))
    if namelist:
        cands.append(str(namelist))
    for c in cands:
        if not os.path.exists(c):
            continue
        txt = Path(c).read_text(errors="replace")
        m = re.search(r"start_date\s*=\s*['\"](\d{4})", txt)
        if m:
            return int(m.group(1)), Path(c)
    raise SystemExit("could not read `start_date` from any of: %s" % (cands or "<none given>"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--case-dir", default=None,
                    help="a materialized case dir holding runfile.nml (default: case 0 under "
                         "$A2MC_OUTPUT_DIR, else the base namelist)")
    ap.add_argument("--targets", default=os.environ.get("A2MC_VALIDATION_TARGETS"))
    ap.add_argument("--namelist", default=os.environ.get("A2MC_ECOSIM_BASE_NAMELIST"))
    a = ap.parse_args()

    import yaml

    case_dir = a.case_dir
    if case_dir is None and os.environ.get("A2MC_OUTPUT_DIR"):
        hits = sorted(glob.glob(os.path.join(os.environ["A2MC_OUTPUT_DIR"], "*case0")))
        case_dir = hits[0] if hits else None

    ry, src = run_start_year(Path(case_dir) if case_dir else None,
                             Path(a.namelist) if a.namelist else None)
    if not a.targets:
        raise SystemExit("no targets file ($A2MC_VALIDATION_TARGETS or --targets)")
    doc = yaml.safe_load(Path(a.targets).read_text())
    targets = doc.get("targets") or {}

    errors, warns = [], []
    print("run start year : %d   (from %s)" % (ry, src))

    env = os.environ.get("A2MC_VALIDATION_START_YEAR")
    if env in (None, ""):
        warns.append("$A2MC_VALIDATION_START_YEAR is unset; targets without their own "
                     "`start_year` fall back to fixed 365-record blocking, which slips a day "
                     "per leap year on EcoSIM's real calendar.")
    elif int(env) != ry:
        errors.append("$A2MC_VALIDATION_START_YEAR=%s but the run starts in %d. That variable is "
                      "record 0's calendar year, NOT the first scored year -- the scored window is "
                      "`window_years`. Every target lacking its own `start_year` is being reduced "
                      "over the WRONG years." % (env, ry))

    top = doc.get("start_year")
    if top is not None and int(top) != ry:
        errors.append("targets.yaml top-level start_year=%s but the run starts in %d." % (top, ry))

    # THE SIMULATED SPAN IS NOT `forc_periods`' LAST YEAR, and this checker got that wrong on its
    # first run. `forc_periods` is (y0, y1, REPEATS) TRIPLETS -- up to five of them
    # (EcoSIMCtrlMod.F90:126) -- and the forcing is RECYCLED, so the run is longer than any one
    # triplet's range and its calendar years are NOT the forcing's calendar years. Measured:
    # EcoSIM_Lusignan runs `2006, 2015, 1, 2006, 2023, 1` from a 1996 start = 10 + 18 = 28 simulated
    # years, i.e. 1996-2023. Reading only the first pair called its last year 2015 and reported
    # three ERRORS on a correct case. That is the same conflation of two calendar quantities this
    # tool exists to catch, made by the tool itself, which is why the span is now DERIVED.
    # READ `forc_periods` FROM THE SAME FILE THAT GAVE `start_date` (`src`), not only from a
    # materialized case. Until 2026-09-12 this looked exclusively at `<case_dir>/runfile.nml`, while
    # `start_date` fell back to the BASE namelist -- so before Phase 0, when no case has been
    # materialized, `trips` was empty and checks 4 and 6 SILENTLY DID NOT RUN. The tool printed
    # "scoring calendar matches the run" having evaluated only the anchors. That is the worst
    # possible moment for them to be inert: pre-Phase-0 is when the calendar is still being decided
    # and when a fix is free. Measured on EcoSIM_Kougarok 2026-09-12, where a window sitting 47
    # years inside the spin-up returned a clean pass.
    span_hi = None
    trips = []
    for cand in ([os.path.join(case_dir, "runfile.nml")] if case_dir else []) + [str(src)]:
        if not os.path.exists(cand):
            continue
        m = re.search(r"^\s*forc_periods\s*=\s*([0-9,\s]+)", Path(cand).read_text(errors="replace"), re.M)
        if m:
            nums = [int(x) for x in re.findall(r"\d+", m.group(1))]
            trips = [tuple(nums[i:i + 3]) for i in range(0, len(nums) - 2, 3)]
            break
    prod_lo = None
    if trips:
        nyears = sum((y1 - y0 + 1) * max(1, rep) for y0, y1, rep in trips)
        span_hi = ry + nyears - 1
        print("forc_periods   : %s  -> %d simulated year(s), %d-%d"
              % (", ".join("%d-%d x%d" % t for t in trips), nyears, ry, span_hi))
        # THE SPAN IS NOT ENOUGH: a window can sit inside it and still be scoring the SPIN-UP.
        # With two or more triplets the LAST one is the production leg and everything before it is
        # spin-up, normally a RECYCLED block replayed many times. A window landing there scores
        # replayed weather while every count, boundary and coverage figure stays correct -- the
        # same silence as the $A2MC_VALIDATION_START_YEAR defect this tool was written for, reached
        # from the other direction: that one moves the anchor under a fixed run, this one moves the
        # run under a fixed anchor. Measured on EcoSIM_Kougarok 2026-09-12: 60 spin-up years
        # (2000-2002 recycled x20) then a 2000-2016 production leg, from a 2000 start, put the
        # 2012-2016 window 47 years inside the spin-up. Checks 1-4 ALL PASSED -- the anchors agreed
        # and the window was inside the span. The fix there was to move `start_date` back to 1940
        # so the production leg lands on the real years, which is the Lusignan pattern.
        if len(trips) >= 2:
            spin_years = sum((y1 - y0 + 1) * max(1, rep) for y0, y1, rep in trips[:-1])
            prod_lo = ry + spin_years
            print("                 spin-up %d-%d (%d yr), PRODUCTION %d-%d"
                  % (ry, prod_lo - 1, spin_years, prod_lo, span_hi))

    for name, spec in targets.items():
        sy = spec.get("start_year")
        if sy is None:
            warns.append("target `%s` has no `start_year`; it depends on "
                         "$A2MC_VALIDATION_START_YEAR, whose NAME reads as the validation window's "
                         "start. Pin it explicitly." % name)
        elif int(sy) != ry:
            errors.append("target `%s` start_year=%s but the run starts in %d." % (name, sy, ry))
        wy = spec.get("window_years")
        if wy:
            lo, hi = int(wy[0]), int(wy[1])
            if lo < ry:
                errors.append("target `%s` window_years starts %d, before the run's %d."
                              % (name, lo, ry))
            if span_hi is not None and hi > span_hi:
                errors.append("target `%s` window_years ends %d, after the run's last "
                              "SIMULATED year %d (derived from forc_periods triplets, not from "
                              "any single triplet's range)." % (name, hi, span_hi))
            if prod_lo is not None and lo < prod_lo:
                errors.append("target `%s` window_years starts %d, which is inside the SPIN-UP "
                              "(%d-%d) rather than the production leg (%d-%d). The window is "
                              "inside the run's span, so checks 1-4 pass, but it would be scored "
                              "against recycled forcing. Move `start_date` back by the spin-up "
                              "length so production lands on the real years."
                              % (name, lo, ry, prod_lo - 1, prod_lo, span_hi))

    for e in errors:
        print("ERROR  " + e)
    for w in warns:
        print("WARN   " + w)
    if errors:
        print("\n%d error(s), %d warning(s) -- the scoring calendar does NOT match the run."
              % (len(errors), len(warns)))
        return 2
    if warns:
        print("\nclean, with %d warning(s)." % len(warns))
        return 1
    print("\nscoring calendar matches the run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
