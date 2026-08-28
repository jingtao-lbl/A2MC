#!/usr/bin/env python3
"""Census EcoSIM divisions whose GUARD tests a different variable than the DIVISOR.

THE DEFECT THIS LOOKS FOR. On 2026-08-22 a SIGFPE killed 42 of the R3 ensemble's 50 survivors. The
faulting instruction was a `divsd` in `branchelmnttransfer`, with the divisor exactly 0.0 and MXCSR
0x1926 (ZE set, IE/OE clear -- a true divide-by-zero, not an overflow). The guard above it tested
`SeasonalNonstElms_pft(ielmc,NZ)`, while the divisor was `CPOOLT`, assigned from `AZMAX1(...)`.

`AZMAX1` returns EXACTLY `0._r8` below `tiny_val = 1e-12`. So a guard on one quantity says nothing
about a divisor derived from another through a flooring function: the guard passes, the divisor is
hard zero, and the process dies. Two such sites were found and repaired; this script is the wider
census the model log deferred.

WHAT IT IS AND IS NOT. This is a TEXTUAL scan, deliberately over-inclusive, and it reports
CANDIDATES for a human to read -- not defects. It cannot see through subroutine boundaries,
`associate` blocks, or a guard several lines above an intervening assignment. A clean run is NOT
proof the code is free of this defect; it is proof this pattern does not appear in the form scanned
for. Stated because the opposite reading is exactly the false-clean result that motivated the fix.

    python3 models/ecosim/tools/census_guarded_divisions.py [--root <EcoSIM checkout>] [--all]

Files are enumerated with `git ls-files` -- an index read, never a filesystem walk, which is
required on a shared HPC filesystem ([[feedback_nersc_no_recursive_traversal]]).

Author: Jing Tao with Claude
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys

#: Flooring helpers that can return EXACT zero. This is the property that makes a guard on a
#: DIFFERENT variable insufficient; a plain assignment does not have it.
FLOOR = re.compile(r"\b(AZMAX1(?:_s)?|AZERO)\s*\(", re.I)

#: `X = AZMAX1(...)` / `X(i,j) = AZMAX1(...)`. Captures the bare assigned name.
ASSIGN = re.compile(r"^\s*([A-Za-z]\w*)\s*(?:\([^=]*\))?\s*=\s*.*?" + FLOOR.pattern, re.I)

#: Division BY a BARE variable: `/X` or `/(X)`, but NOT `/(X+K)`.
#:
#: The parenthesised case is the whole point of the distinction and the first version got it wrong.
#: `X/(X+K)` is a Michaelis-Menten term, and at X exactly 0 it evaluates to `0/K` -- perfectly
#: finite. Matching the name INSIDE the parens flagged 10 such terms in `MicBGCFGMod.F90` alone and
#: buried the four real candidates under them. A census whose signal is swamped by a systematic
#: false positive gets ignored, which is the same outcome as not running it.
#:
#: So: after `/(` the name must be followed by `)`. After a bare `/` it must be followed by
#: anything that is not an operator continuing the expression.
_BARE  = re.compile(r"/\s*([A-Za-z]\w*)\s*(?![\w(*/+\-.])")
_PAREN = re.compile(r"/\s*\(\s*([A-Za-z]\w*)\s*\)")


def divisors(line: str) -> list[str]:
    return [m.group(1) for m in _BARE.finditer(line)] + \
           [m.group(1) for m in _PAREN.finditer(line)]


#: A routine boundary. `floored` must not survive one.
ROUTINE = re.compile(r"^\s*(?:recursive\s+)?(?:pure\s+)?(?:elemental\s+)?"
                     r"(?:subroutine|function|end\s+subroutine|end\s+function)\b", re.I)

#: Any assignment at all, used to CLEAR the floored flag when a variable is re-assigned.
PLAIN_ASSIGN = re.compile(r"^\s*([A-Za-z]\w*)\s*(?:\([^=]*\))?\s*=\s*[^=]")

#: A reassignment that floors to a PROVABLY POSITIVE constant, and therefore genuinely clears the
#: danger: `AMAX1(ZERO, ...)` where ZERO is a module `parameter` equal to 1e-15/1e-16.
#:
#: THE DISTINCTION IS NOT COSMETIC, and getting it wrong cost a false negative on a KNOWN defect.
#: `AMAX1(ZERO4Groth_pft(NZ), ...)` looks identical in shape but is NOT safe, because
#: `ZERO4Groth_pft(NZ) = ZERO * PlantPopuLive_pft(NZ)` (StartqMod.F90:86, InitPlantMod.F90:125) --
#: the threshold is SCALED BY THE LIVE PLANT POPULATION, so on a dying stand it goes to zero and the
#: floor floors to zero. That is the "guard scaled by the dying quantity" pathology already recorded
#: in `memory/model_logs/20260820a`. A first version of this rule treated any AMAX1 reassignment as
#: safe and silently declassified `PlantBranchMod.F90:2995`, one of the two repaired sites.
#:
#: So: only a bare all-caps name with no subscript counts as a positive constant. A subscripted
#: threshold is a variable, and a variable can be zero.
SAFE_FLOOR = re.compile(r"=\s*A?MAX1\s*\(\s*([A-Z][A-Z0-9_]*)\s*,", re.I)


#: A floor to a positive NUMERIC LITERAL -- `AMAX1(0.001_r8, ...)`. The safest form there is, and
#: the first version of this rule did not recognise it at all because it only accepted an all-caps
#: NAME. That flagged all three `RoughnessLength` divisions in `SurfaceRadiationMod` as candidates.
LITERAL_FLOOR = re.compile(r"=\s*A?MAX1\s*\(\s*(\d*\.?\d+(?:[eEdD][-+]?\d+)?(?:_r8)?)\s*,", re.I)

#: A POSITIVE CONSTANT TERM added outside the flooring call: `OSWT = 36.0_r8 + 840.0_r8*AZMAX1(x)`
#: is at least 36.0 however the AZMAX1 evaluates. Flagging it merely because `AZMAX1` appears on the
#: right-hand side is the same over-inclusion as the Michaelis-Menten false positive: the question
#: is never "does a flooring call appear" but "can the RESULT be zero".
CONST_OFFSET = re.compile(r"=\s*(\d*\.?\d+(?:_r8)?)\s*\+", re.I)


def clears_the_danger(code: str) -> bool:
    """True when the reassignment provably leaves the variable strictly positive."""
    if LITERAL_FLOOR.search(code):
        return True
    m = SAFE_FLOOR.search(code)
    return bool(m) and "(" not in m.group(1)


def cannot_be_zero(code: str) -> bool:
    """True when a floored RHS still cannot evaluate to zero (a positive constant is added)."""
    m = CONST_OFFSET.search(code)
    try:
        return bool(m) and float(m.group(1).replace("_r8", "")) > 0.0
    except ValueError:
        return False


def guarded_by(lines: list[str], i: int, name: str, back: int = 12) -> bool:
    """Is `name` itself tested in an `if` within `back` lines above line i?"""
    pat = re.compile(rf"\bif\b.*\b{re.escape(name)}\b", re.I)
    return any(pat.search(lines[j]) for j in range(max(0, i - back), i))


def tracked_f90(root: str, all_dirs: bool) -> list[str]:
    spec = ["*.F90"] if all_dirs else ["f90src/Plant_bgc/*.F90"]
    out = subprocess.run(["git", "-C", root, "ls-files", "--", *spec],
                         capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"git ls-files failed in {root}: {out.stderr.strip()}")
    return [l for l in out.stdout.split() if l]


#: THE SECOND IDIOM, added after the census's stated limit was confirmed twice by runtime failures.
#:
#: The AZMAX1 scan above finds a divisor FLOORED to exactly zero. It cannot find a divisor that is
#: simply a state variable which happens to be zero because the thing it describes does not exist --
#: and that is what killed 7 of the 14 unrecovered R3 cases: `vapsat(tempK)` at MiniMathMod.F90:147
#: divides by tempK twice, and SnowPhysMod calls it on `TKSnow1_snvr(L,...)`, a per-LAYER snow
#: temperature that is 0 for a layer holding no snow. The census would have missed it, and said so.
#:
#: The shared shape of both confirmed modes is an EMPTY ENTITY: a snow layer with no snow, a PFT
#: with no plants, a cohort with no biomass. EcoSIM marks these in the NAME -- the suffix says which
#: axis the variable is indexed on. So: a division by a SUBSCRIPTED variable carrying one of those
#: suffixes, with no guard on that variable nearby.
#:
#: DELIBERATELY NOISIER THAN THE FIRST SCAN. Most per-layer state is nonzero most of the time, so
#: this ranks places to look rather than naming defects. It is reported separately for that reason;
#: merging the two would bury the first scan's short, high-confidence list.
ENTITY_SUFFIX = ("_snvr", "_pft", "_vr", "_rpvr", "_brch", "_pvr", "_col")

#: Division by a SUBSCRIPTED name: `/ TKSnow1_snvr(L,NY,NX)` or `/(X_pft(NZ))`.
DIV_SUBSCRIPTED = re.compile(r"/\s*\(?\s*([A-Za-z]\w*)\s*\(")


def empty_entity_divisors(line: str) -> list[str]:
    return [m.group(1) for m in DIV_SUBSCRIPTED.finditer(line)
            if m.group(1).endswith(ENTITY_SUFFIX)]


#: THE THIRD IDIOM, and the only one that would actually have caught `vapsat`.
#:
#: Honesty first: the second idiom above does NOT find vapsat. Inside vapsat the divisor is a plain
#: dummy argument (`tempK`), not a subscripted entity, so a line scan of that body sees nothing to
#: flag. What it matches is the CALL-SITE shape, which is not where the division happens. Verified by
#: testing the real line before believing the extension worked.
#:
#: The actual defect is INTERPROCEDURAL: a small function divides by one of its own arguments, and a
#: caller hands it a state variable that is zero when its entity is empty. Neither half is a defect
#: alone -- dividing by an argument is fine if callers never pass zero, and passing a per-layer
#: variable is fine to a function that does not divide by it. The pair is the defect.
#:
#:     MiniMathMod.F90:147   ans = 2.173e-3/tempK * ... * EXP(5360*(3.661e-3 - 1/tempK))
#:     SnowPhysMod.F90:275   VapSnoSrc = vapsat(TKSnow1_snvr(L,NY,NX))     <- 0 for an empty layer
#:
#: So: find functions that divide by a dummy argument, then find calls passing an entity-suffixed
#: variable into that position. Two cheap passes joined, no call-graph library needed.
#: CALLEES THAT ARE SAFE BY CONSTRUCTION, excluded so the real hits are not buried. Measured on the
#: first whole-tree run: 76 flagged call sites, of which 61 were `safe_adb` -- the codebase's own
#: guarded-division helper, which exists precisely to damp a zero denominator. Flagging it is like
#: flagging a try/except for catching an exception. `real_truncate(x, precision)` divides by a
#: precision argument that every call site passes as a literal (1.e-3_r8), so it is not reachable
#: with zero either. Excluding both leaves the 5 `vapsat` sites visible, which is the whole point.
#:
#: This is the third time a scan in this file needed the same correction: a census whose signal is
#: buried in systematic noise gets ignored, which is the same outcome as not running it.
SAFE_CALLEES = {"safe_adb", "real_truncate", "azero"}

FUNC_DEF = re.compile(r"^\s*(?:pure\s+|elemental\s+)*function\s+(\w+)\s*\(([^)]*)\)", re.I)
FUNC_END = re.compile(r"^\s*end\s+function\b", re.I)


def divides_by_argument(root: str, files: list[str]) -> dict:
    """-> {func_name: (file, line, [argument names it divides by])}."""
    risky = {}
    for rel in files:
        try:
            lines = open(os.path.join(root, rel), errors="replace").read().splitlines()
        except OSError:
            continue
        name = None
        for i, line in enumerate(lines):
            code = line.split("!")[0]
            m = FUNC_DEF.match(code)
            if m:
                name, args, start = m.group(1), [a.strip() for a in m.group(2).split(",")], i
                body, hits = [], []
                continue
            if name and FUNC_END.match(code):
                if hits and name.lower() not in SAFE_CALLEES:
                    risky[name.lower()] = (rel, start + 1, sorted(set(hits)))
                name = None
                continue
            if name:
                for d in divisors(code) + [x.group(1) for x in DIV_SUBSCRIPTED.finditer(code)]:
                    if d in args:
                        hits.append(d)
    return risky


def unsafe_calls(root: str, files: list[str], risky: dict) -> list:
    """Calls that pass an entity-suffixed variable into a function that divides by its argument."""
    out = []
    pat = re.compile(r"\b(" + "|".join(re.escape(k) for k in risky) + r")\s*\(\s*([A-Za-z]\w*)\s*\(",
                     re.I) if risky else None
    if not pat:
        return out
    for rel in files:
        try:
            lines = open(os.path.join(root, rel), errors="replace").read().splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines):
            code = line.split("!")[0]
            if FUNC_DEF.match(code):
                continue
            for m in pat.finditer(code):
                fn, arg = m.group(1).lower(), m.group(2)
                if arg.endswith(ENTITY_SUFFIX):
                    out.append((rel, i + 1, fn, arg, risky[fn], line.strip()[:80]))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.environ.get("A2MC_MODEL_PATH"),
                    help="EcoSIM checkout (default $A2MC_MODEL_PATH)")
    ap.add_argument("--all", action="store_true",
                    help="scan every tracked .F90, not only f90src/Plant_bgc/")
    ap.add_argument("--context", type=int, default=12, help="lines to look back for a guard")
    ap.add_argument("--interprocedural", action="store_true",
                    help="scan the THIRD idiom: a function that divides by an argument, called with "
                         "a per-entity state variable that is zero when the entity is empty. This "
                         "is the one that catches vapsat.")
    ap.add_argument("--empty-entity", action="store_true",
                    help="ALSO scan the second idiom: division by a subscripted per-layer/per-PFT "
                         "state variable, which is zero when that entity is empty. Noisier by "
                         "design; reported separately.")
    a = ap.parse_args()
    if not a.root:
        sys.exit("no --root and no A2MC_MODEL_PATH")

    files = tracked_f90(a.root, a.all)
    hits, scanned = [], 0
    for rel in files:
        try:
            lines = open(os.path.join(a.root, rel), errors="replace").read().splitlines()
        except OSError:
            continue
        scanned += 1
        floored: set[str] = set()
        for i, line in enumerate(lines):
            code = line.split("!")[0]
            # RESET AT EACH ROUTINE BOUNDARY. Without this the set is file-global and a variable
            # floored in one subroutine is treated as floored 900 lines later in another. Measured:
            # H_1p_aque_mole_conc is AZMAX1-assigned at SaltChemEquilibriaMod:565 and re-floored to
            # a POSITIVE 1e-15 at :1490, and the file-global set reported :1491 as a candidate.
            if ROUTINE.match(code):
                floored.clear()
                continue
            m = ASSIGN.match(code)
            if m:
                if cannot_be_zero(code) or clears_the_danger(code):
                    floored.discard(m.group(1).upper())
                else:
                    floored.add(m.group(1).upper())
            else:
                # A PLAIN REASSIGNMENT CLEARS THE FLAG. `x = AMAX1(ZERO, ...)` with ZERO = 1e-15 is
                # a floor ABOVE zero and therefore SAFE -- the opposite of AZMAX1, which returns
                # exactly 0._r8 below tiny_val. Treating any later assignment as still-floored is
                # what produced the false positive above.
                pm = PLAIN_ASSIGN.match(code)
                if pm:
                    # Clear ONLY on a reassignment that provably floors above zero, or one with no
                    # flooring call at all. A reassignment that floors with a SUBSCRIPTED threshold
                    # keeps the flag: that threshold may itself be zero.
                    if clears_the_danger(code) or not re.search(r"A?MAX1\s*\(", code, re.I):
                        floored.discard(pm.group(1).upper())
                    else:
                        floored.add(pm.group(1).upper())
            for d in divisors(code):
                if d.upper() in floored and not guarded_by(lines, i, d, a.context):
                    hits.append((rel, i + 1, d, line.strip()[:96]))

    scope = "every tracked .F90" if a.all else "f90src/Plant_bgc/"
    print(f"scanned {scanned} file(s) under {scope} in {a.root}\n")
    if not hits:
        print("no candidate sites in the form scanned for.")
        print("NOT a proof of absence -- this is a textual scan that cannot see through subroutine")
        print("boundaries, associate blocks, or a guard beyond the context window.")
        return 0
    print(f"{len(hits)} CANDIDATE site(s) -- divisor floored by AZMAX1/AZERO, not itself guarded:\n")
    for rel, ln, d, txt in hits:
        print(f"  {rel}:{ln}\n      divisor {d}\n      {txt}")
    print("\nCANDIDATES, not defects. Read each: the guard may be outside the context window, or")
    print("the divisor may be provably positive for another reason.")

    if a.empty_entity:
        ent = []
        for rel in files:
            try:
                lines = open(os.path.join(a.root, rel), errors="replace").read().splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines):
                code = line.split("!")[0]
                for d in empty_entity_divisors(code):
                    if not guarded_by(lines, i, d, a.context):
                        ent.append((rel, i + 1, d, line.strip()[:88]))
        print(f"\n\n=== SECOND IDIOM: division by a subscripted per-entity state variable ===")
        print(f"{len(ent)} site(s), unguarded within {a.context} lines. Zero when the entity is EMPTY")
        print("(a snow layer with no snow, a PFT with no plants). This is the shape that killed 7 of")
        print("the 14 unrecovered R3 cases via vapsat(TKSnow1_snvr) -- which the first scan misses.")
        print("Ranked by file so related sites read together. NOISY BY DESIGN: most per-layer state")
        print("is nonzero most of the time, so this ranks places to look, it does not name defects.\n")
        from collections import Counter
        byfile = Counter(r for r, _, _, _ in ent)
        for f_, n in byfile.most_common(12):
            print(f"  {n:>4d}  {f_}")

    if a.interprocedural:
        risky = divides_by_argument(a.root, files)
        calls = unsafe_calls(a.root, files, risky)
        print(f"\n\n=== THIRD IDIOM: divide-by-argument reached with an empty-entity variable ===")
        print(f"{len(risky)} function(s) divide by one of their own arguments; "
              f"{len(calls)} call site(s) pass a per-entity state variable into one.\n")
        for rel, ln, fn, arg, (drel, dln, dargs), src in calls:
            print(f"  {rel}:{ln}")
            print(f"      {fn}({arg}) — {fn} divides by {dargs} at {drel}:{dln}")
            print(f"      {src}")
        if not calls:
            print("  none. NOT a proof of absence: this matches a DIRECT call whose first argument is")
            print("  a subscripted entity variable, so an argument passed through a local, or in a")
            print("  later position, is invisible to it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
