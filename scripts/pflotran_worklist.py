#!/usr/bin/env python
"""Emit the list of PFLOTRAN ensemble cases that still need to run.

    python scripts/pflotran_worklist.py --run-root <dir> [--out <file>] [--prefix miniLEO_case]

WHY A SEPARATE COMPLETION TEST
------------------------------
"A `*-mas.dat` exists" is NOT completion. A case killed by TIMEOUT leaves a
partial tape: miniLEO_case29 timed out at 4 h having written 131 lines reaching
t=65 h, against a healthy case's 3361 lines reaching t=1680 h. Since the miniLEO
observations start at the 806 h offset, that partial tape carries no usable
Y-value at all -- so treating tape-existence as done would silently drop the
case from the resubmit list and leave a hole in the design matrix.

Completion is therefore the FINAL TIME reached, read from the tape's last row.
`--t-final` defaults to the miniLEO scenario's 1680 h; pass the deck's own value
for another case family rather than inheriting this one.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import sys


def default_prefix() -> str | None:
    """The case-name prefix, derived from the config rather than hardcoded.

    `A2MC_CASE_NAME_PATTERN` is the single source of truth for how a case
    directory is named (`miniLEO_case{N}`, `<CASE>_case{N}`, ...), so the prefix
    is that pattern with the `{N}` placeholder and anything after it removed.
    Hardcoding one case's prefix here is how a generic tool silently returns an
    empty worklist for every other case (CLAUDE.md rule 5, keep-generic).
    """
    pat = os.environ.get("A2MC_CASE_NAME_PATTERN")
    if not pat or "{N}" not in pat:
        return None
    return pat.split("{N}")[0]


def final_time(mas: pathlib.Path) -> float | None:
    """Last numeric time column in a *-mas.dat tape, or None if unreadable."""
    try:
        last = None
        with mas.open() as fh:
            for line in fh:
                s = line.strip()
                if not s or s.startswith('"') or s.startswith("#"):
                    continue
                last = s
        if last is None:
            return None
        return float(last.split()[0])
    except (OSError, ValueError, IndexError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-root", required=True)
    ap.add_argument("--prefix", default=None,
                    help="case-dir name prefix; default: derived from "
                         "$A2MC_CASE_NAME_PATTERN (source the site config first)")
    ap.add_argument("--t-final", type=float, default=1680.0,
                    help="hours the tape must reach to count as complete (miniLEO: 1680)")
    ap.add_argument("--tol", type=float, default=0.1)
    ap.add_argument("--out", help="write the incomplete case dirs here (default: stdout)")
    a = ap.parse_args()

    root = pathlib.Path(a.run_root)
    if not root.is_dir():
        print(f"ERROR: no run root at {root}", file=sys.stderr)
        return 2

    prefix = a.prefix or default_prefix()
    if not prefix:
        print("ERROR: no --prefix given and $A2MC_CASE_NAME_PATTERN is unset or carries no "
              "'{N}'. Source the site config first, or pass --prefix explicitly. Guessing a "
              "prefix would return an empty worklist that reads as 'nothing left to run'.",
              file=sys.stderr)
        return 2

    todo, done, partial = [], [], []
    for d in sorted(root.glob(f"{prefix}*")):
        if not d.is_dir():
            continue
        tapes = list(d.glob("*-mas.dat"))
        if not tapes:
            todo.append(d.name)
            continue
        t = final_time(tapes[0])
        if t is not None and t >= a.t_final - a.tol:
            done.append(d.name)
        else:
            # A partial tape is a case to RE-RUN, and its stale tape must go or
            # the next run's completion test reads the old one.
            partial.append((d.name, t))
            todo.append(d.name)

    if not (todo or done or partial):
        print(f"ERROR: no case directories match '{prefix}*' under {root}. That is a WRONG "
              f"PREFIX, not a finished ensemble -- an empty worklist and a complete one look "
              f"identical downstream.", file=sys.stderr)
        return 2

    print(f"run root : {root}", file=sys.stderr)
    print(f"prefix   : {prefix}{'' if a.prefix else '  (from $A2MC_CASE_NAME_PATTERN)'}",
          file=sys.stderr)
    print(f"complete : {len(done)}  (tape reaches t>={a.t_final})", file=sys.stderr)
    print(f"partial  : {len(partial)}  (tape exists but stops short -- re-run, tape is stale)",
          file=sys.stderr)
    print(f"to run   : {len(todo)}", file=sys.stderr)
    for name, t in partial[:10]:
        print(f"    partial {name}: t={t}", file=sys.stderr)

    text = "\n".join(todo) + ("\n" if todo else "")
    if a.out:
        pathlib.Path(a.out).write_text(text)
        print(f"wrote {len(todo)} case names -> {a.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
