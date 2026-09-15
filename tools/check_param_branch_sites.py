#!/usr/bin/env python
"""Enumerate EVERY source site that reads a model parameter, with its enclosing subroutine.

Author: Jing Tao with Claude on Perlmutter

WHY THIS EXISTS. On 2026-09-12 a CHL analysis cited `StomatesMod.F90:556` and reasoned from the
`fCHLMESO` factor on that line. Line 556 is inside `C4Photosynthesis`. Every record at the site is
`ICTYP = 3`, so the line that actually executes is `:415`, inside `C3Photosynthesis`, which carries
no `fCHLMESO` term at all. The conclusion survived; the citation was to code that never ran.

The existing rule (`feedback_param_description_can_lie_verify_in_source`) says to verify a
parameter's meaning in the source equations, and that rule WAS followed. It does not say the thing
that would have helped: **verify WHICH BRANCH RUNS.** When a model carries parallel implementations
selected by a type flag -- C3 vs C4 photosynthesis, growth habit, phenology type -- grepping the
variable name returns every branch, and reading the first hit reads a coin flip.

WHAT IT DOES. Given a parameter, it resolves the Fortran variable it is read into, finds every site
that reads that variable, maps each to its enclosing `subroutine`/`function`, and REFUSES to let a
single-line citation stand when more than one distinct routine appears. It does not know which
branch is live -- only the run's own type flags do -- so it names the flags in the parameter file
and makes the reader choose, rather than choosing for them.

EXIT: 0 = single site, citing it is safe. 1 = MULTIPLE routines read it; a one-line citation is a
      coin flip until the selecting flag is resolved. 2 = not found.

Run:  python tools/check_param_branch_sites.py CHL --model-path $A2MC_MODEL_PATH \
          [--pft-file <the case's pft_file_in>]
"""
from __future__ import annotations
import argparse, os, re, subprocess, sys
from pathlib import Path

# Type flags that select whole parallel code paths. Naming these is the point: a parameter read
# under one of them has as many meanings as the flag has values.
PATHWAY_FLAGS = ["ICTYP", "IGTYP", "IWTYP", "IPTYP", "INTYP", "IBTYP", "IRTYP", "IDTYP", "IDTBLG"]


def sh(cmd, cwd):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True).stdout


def fortran_name(param, root):
    """`ncd_getvar(pft_nfid, 'CHL', loc, LeafProtein2Chl_pft(...))` -> LeafProtein2Chl_pft."""
    out = sh(["git", "grep", "-hn", f"'{param}'"], root)
    for line in out.splitlines():
        m = re.search(r"ncd_getvar\([^,]+,\s*'%s'\s*,.*?,\s*([A-Za-z_]\w*)" % re.escape(param), line)
        if m:
            return m.group(1)
    return None


def enclosing_routine(path: Path, lineno: int) -> str:
    """Walk BACKWARDS to the nearest subroutine/function header. A forward scan finds the NEXT
    routine, which is the off-by-one that makes this kind of tool confidently wrong."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return "?"
    for i in range(min(lineno, len(lines)) - 1, -1, -1):
        m = re.match(r"\s*(?:recursive\s+)?(?:pure\s+)?(?:elemental\s+)?"
                     r"(?:subroutine|function)\s+([A-Za-z_]\w*)", lines[i], re.I)
        if m:
            return m.group(1)
    return "<module scope>"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("param", help="the parameter as named in the parameter FILE, e.g. CHL")
    ap.add_argument("--model-path", default=os.environ.get("A2MC_MODEL_PATH"),
                    help="the model checkout (default $A2MC_MODEL_PATH)")
    ap.add_argument("--pft-file", default=None, help="a case's pft_file_in; reports its type flags")
    a = ap.parse_args()
    if not a.model_path:
        raise SystemExit("no --model-path and $A2MC_MODEL_PATH is unset")
    root = a.model_path

    var = fortran_name(a.param, root)
    if not var:
        print(f"'{a.param}' is not read by any ncd_getvar call under {root}")
        return 2
    print(f"parameter file name : {a.param}")
    print(f"Fortran variable    : {var}\n")

    # Read sites = every USE, excluding the declaration/allocate/pointer-association plumbing.
    out = sh(["git", "grep", "-n", var, "--", "*.F90"], root)
    sites = []
    for line in out.splitlines():
        f, ln, txt = line.split(":", 2)
        if re.search(r"=>|allocate\(|call destroy|::|^\s*!", txt):
            continue
        sites.append((f, int(ln), txt.strip()))

    by_routine = {}
    for f, ln, txt in sites:
        r = enclosing_routine(Path(root) / f, ln)
        by_routine.setdefault(r, []).append((f, ln, txt))

    for r, hits in sorted(by_routine.items()):
        print(f"  {r}")
        for f, ln, txt in hits:
            print(f"      {f}:{ln}   {txt[:110]}")

    if a.pft_file:
        try:
            import netCDF4, numpy as np
            with netCDF4.Dataset(a.pft_file) as d:
                print("\n  this case's pathway flags:")
                for fl in PATHWAY_FLAGS:
                    if fl in d.variables:
                        print(f"      {fl:8s} = {np.asarray(d[fl][:]).ravel()}")
        except Exception as e:                                   # noqa: BLE001
            print(f"\n  (could not read {a.pft_file}: {e})")

    n = len(by_routine)
    if n > 1:
        print(f"\nMULTIPLE ({n}) routines read {var}. A single-line citation is a COIN FLIP until you")
        print("say which pathway this case's type flags select. Name the routine, not just the line.")
        return 1
    print(f"\nsingle site -- citing it is unambiguous.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
