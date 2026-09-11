#!/usr/bin/env python3
"""Build the TODO worklist for a node-packed EcoSIM ensemble run.

The parallel of `scripts/pflotran_worklist.py`, and it exists for the same reason: the packed
runner reads case directory NAMES rather than reconstructing them from an array index, so the
worklist is what decides which cases still need doing. Re-run it any time; it rebuilds state from
the FILESYSTEM, never from claims, so a case whose worker died is simply back on the next list.

THE COMPLETION TEST IS THE FINAL RESTART, AND THAT IS THE WHOLE POINT.

EcoSIM opens its h0 history tape at INITIALISATION and appends, so the tape exists from the first
minute of a 28-year run. Testing for the tape scores three different unusable outcomes as done:

  * a wall-clock kill part-way through (BioCON R3 established this one);
  * a model failure that exits rc=0 -- measured on this very round, 2026-09-05: Lusignan R1 task 3
    drove soil organic matter negative (`orgm3 -0.1716`) at day 168 of the first spin-up year and
    EXITED ZERO. sacct recorded the step COMPLETED. Only the restart test caught it;
  * a case that never launched at all.

The restart set stamped <final year + 1> is written only after the last simulated year finishes,
so it is the one artifact that means what "done" should mean. Derive the year from the case's own
runfile.nml rather than hardcoding it:

    start_date year + sum over forc_periods triplets of (y1 - y0 + 1) * repeats

For EcoSIM_Lusignan: 1996 + (2015-2006+1)*1 + (2023-2006+1)*1 = 1996 + 10 + 18 = 2024, so the
marker is `*r.2024-01-01*`. A recycled spin-up is counted correctly because `repeats` is included.

USAGE
    source use_cases/EcoSIM_Lusignan/config/ecosim_lusignan_config.sh
    python scripts/ecosim_worklist.py --run-root "$A2MC_OUTPUT_DIR" \
           --out "$A2MC_OUTPUT_DIR/worklist_todo.txt"

Author: Jing Tao with Claude Code
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path


def final_restart_year(runfile: Path) -> int | None:
    """Derive <final year + 1> from a case's own namelist. Returns None if it cannot be read,
    which the caller must treat as 'unknown', never as 'done'."""
    try:
        txt = runfile.read_text(errors="replace")
    except OSError:
        return None
    m = re.search(r"start_date\s*=\s*'(\d{4})", txt)
    if not m:
        return None
    year = int(m.group(1))
    fp = re.search(r"forc_periods\s*=\s*([0-9,\s]+)", txt)
    if not fp:
        return None
    nums = [int(x) for x in re.findall(r"\d+", fp.group(1))]
    # (y0, y1, repeats) triplets; a trailing partial triplet is malformed input, not a default.
    if not nums or len(nums) % 3 != 0:
        return None
    total = 0
    for i in range(0, len(nums), 3):
        y0, y1, rep = nums[i], nums[i + 1], nums[i + 2]
        total += (y1 - y0 + 1) * rep
    return year + total


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-root", default=os.environ.get("A2MC_OUTPUT_DIR"))
    ap.add_argument("--out", default=None, help="default <run-root>/worklist_todo.txt")
    ap.add_argument("--pattern", default=os.environ.get("A2MC_CASE_NAME_PATTERN", "case{N}"),
                    help="case dir name pattern; only the non-{N} prefix is used to find dirs")
    ap.add_argument("--limit", type=int, default=0,
                    help="take only the first N todo cases -- use for a one-node GATE run")
    ap.add_argument("--include-baseline", action="store_true",
                    help="also list case 0 (V0). Off by default: V0 is usually run and checked "
                         "on its own before the ensemble is trusted.")
    a = ap.parse_args()
    if not a.run_root:
        print("ERROR: --run-root or $A2MC_OUTPUT_DIR required", file=sys.stderr)
        return 2
    root = Path(a.run_root)
    if not root.is_dir():
        print(f"ERROR: no run root at {root}", file=sys.stderr)
        return 2
    out = Path(a.out) if a.out else root / "worklist_todo.txt"

    prefix = a.pattern.split("{N}")[0]
    # os.scandir, not rglob: this lives on a shared filesystem where a recursive walk is both slow
    # and against the traversal rules, and one level is all that is needed.
    dirs = []
    with os.scandir(root) as it:
        for e in it:
            if e.is_dir() and e.name.startswith(prefix):
                suf = e.name[len(prefix):]
                if suf.isdigit():
                    dirs.append((int(suf), e.name))
    dirs.sort()

    todo, done, unknown = [], 0, []
    for idx, name in dirs:
        if idx == 0 and not a.include_baseline:
            continue
        d = root / name
        yr = final_restart_year(d / "runfile.nml")
        if yr is None:
            unknown.append(name)
            continue      # unknown year: cannot be scored done OR run correctly -- reported, not listed
        if any(d.glob(f"*r.{yr}-01-01*")):
            done += 1
        else:
            todo.append((name, yr))

    if a.limit and len(todo) > a.limit:
        todo = todo[:a.limit]

    # Emit "<case_name>\t<final_restart_year>". The year is derived ONCE, here, and carried
    # forward: the packed runner then needs no second copy of the rule. An earlier draft
    # re-derived it in awk inside the runner and got it wrong two ways -- it matched a COMMENT
    # line containing "forc_periods" and summed the numbers out of the prose. Two copies of one
    # derivation drift; one copy passed forward cannot ([[feedback_bind_derived_facts_to_their_source]]).
    out.write_text("\n".join(f"{n}\t{y}" for n, y in todo) + ("\n" if todo else ""))
    print(f"run root : {root}")
    print(f"case dirs: {len(dirs)}  (prefix '{prefix}')")
    print(f"  done   : {done}   (final restart present)")
    print(f"  todo   : {len(todo)}" + (f"  [limited to {a.limit}]" if a.limit else ""))
    if unknown:
        print(f"  ⚠ {len(unknown)} case(s) whose runfile.nml could not be parsed: EXCLUDED from "
              f"the worklist and NOT counted done. Without a derivable final year they can be "
              f"neither run with a completion test nor scored, so they need fixing by hand rather "
              f"than being handed to a runner that cannot check them. e.g. {unknown[:3]}")
    print(f"worklist : {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
