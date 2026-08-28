#!/usr/bin/env python
"""Flag an A2MC CAPABILITY change that carries no version bump and no dev log.

THE HOLE THIS CLOSES. `tools/check_dev_log_for_version.py` fires when CLAUDE.md's version has no
claiming dev log. That catches a bump without a log — and misses the opposite, which is the one that
actually happened: a change that adds a capability and **never bumps at all** passes every gate by
not claiming anything.

Measured, and this checker exists because of it. Commit `faea9be7` (2026-08-27) added a **fourth
sampling method** (`sobol_seq`) to the adapter sampler, deleted an 8,704-row design matrix, wrote two
replacement matrices and re-cut a whole calibration round — ten files — with no version bump and no
dev log. Its entire rationale lived in the commit message, which is not in the log index, is not
ranked by `prior_art.py`, and is not where anyone looks. The gap was found by the PI asking "have you
written a dev log about sobol_seq?", which is not a mechanism.

WHY IT KEYS ON CAPABILITY SIGNALS RATHER THAN ON ANY DIFF. "Touched a file under `tools/`" fires on
every typo and comment fix, and a check that is usually noise gets ignored — the same failure this
repo has already measured for monitors and for reviews. So it looks for evidence that the PUBLIC
SURFACE changed:

  * a new top-level `def` or `class`
  * a new `add_argument("--flag")`
  * a changed `choices=[...]` list   <- what `sobol_seq` actually was
  * a brand-new file in a capability directory

A pure edit to a function body, a comment, a docstring or a test triggers nothing.

EXIT CODES:  0 clean · 1 a capability change looks unlogged (WARN — advisory, see below)

**Advisory on purpose.** There are legitimate unlogged capability changes: a feature branch that
bumps at merge time (this repo's stated rule), a mid-arc commit whose log lands with the next one.
Erroring would train people to bypass it, which is how gates die. It states what it saw and lets a
human judge.

**THE RANGE IS THE HONEST AUDIT UNIT, NOT THE SINGLE COMMIT.** A perfectly disciplined arc often
lands the code in one commit and its log in the next, so `--commit` fires on the first half of a
correct sequence. Measured on this repo's own history: `--commit 5f82a939` fires, while
`--range 5f82a939^..dc4038d5` — the same work plus its follow-up log — is clean. Audit by range;
read a single-commit hit as "did the log ever arrive?", not as "this commit is wrong".

Usage::

    python tools/check_capability_change_logged.py                 # the staged index (pre-commit)
    python tools/check_capability_change_logged.py --range A..B    # audit history (PREFERRED)
    python tools/check_capability_change_logged.py --commit faea9be7

Author: Jing Tao with Claude on Perlmutter
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Tuple

REPO = Path(__file__).resolve().parents[1]

# Directories whose public surface IS an A2MC capability. `tests/`, `docs/`, `memory/` and
# `use_cases/` are deliberately absent: a test or a doc is not a capability, and case work is
# governed by the calibration-log contract instead.
CAPABILITY_PATHS = ("scripts/", "tools/", "phases/", "models/", "reasoning/", "rag/")
CAPABILITY_FILES = ("orchestrator.py",)

# Each pattern matches an ADDED line (leading '+' already stripped) that indicates the public
# surface moved. Deliberately anchored: `^def ` at column 0 is a module-level function, while an
# indented `def` is a method or a nested helper and is far more often a refactor.
SIGNALS: List[Tuple[str, str]] = [
    (r"^def [A-Za-z_]\w*\(", "new top-level function"),
    (r"^class [A-Za-z_]\w*", "new top-level class"),
    (r'add_argument\(\s*["\']--', "new CLI flag"),
    (r"choices\s*=\s*\[", "changed CLI choices list"),
]


def _git(*args: str) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def is_capability_path(path: str) -> bool:
    return path.startswith(CAPABILITY_PATHS) or path in CAPABILITY_FILES


def scan(diff_args: List[str]) -> Dict[str, object]:
    """Return what the diff did: capability signals, version bump, dev logs added."""
    name_status = _git("diff", "--name-status", *diff_args).splitlines()
    files = [ln.split("\t") for ln in name_status if ln.strip()]

    new_logs = [f[-1] for f in files
                if f[-1].startswith(("memory/dev_logs", "memory/model_logs"))
                and f[0].startswith("A")]
    bumped = False
    for ln in _git("diff", "-U0", *diff_args, "--", "CLAUDE.md").splitlines():
        if ln.startswith("+") and "**Status:**" in ln and "v2." in ln:
            bumped = True

    hits: Dict[str, List[str]] = {}
    for f in files:
        status, path = f[0], f[-1]
        if not is_capability_path(path) or not path.endswith(".py"):
            continue
        if status.startswith("A"):
            hits.setdefault(path, []).append("NEW FILE in a capability directory")
            continue
        body = _git("diff", "-U0", *diff_args, "--", path)
        for ln in body.splitlines():
            if not ln.startswith("+") or ln.startswith("+++"):
                continue
            added = ln[1:]
            for pat, label in SIGNALS:
                if re.search(pat, added):
                    if label not in hits.setdefault(path, []):
                        hits[path].append(label)
    return {"hits": hits, "bumped": bumped, "new_logs": new_logs,
            "n_files": len(files)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--range", dest="rng", help="commit range, e.g. main..HEAD")
    g.add_argument("--commit", help="a single commit to audit")
    ap.add_argument("--quiet", action="store_true", help="print only when it fires")
    a = ap.parse_args()

    if a.commit:
        diff_args = [f"{a.commit}^", a.commit]
        what = f"commit {a.commit}"
    elif a.rng:
        diff_args = [a.rng]
        what = f"range {a.rng}"
    else:
        diff_args = ["--cached"]
        what = "the staged index"

    r = scan(diff_args)
    hits, bumped, new_logs = r["hits"], r["bumped"], r["new_logs"]

    if not hits:
        if not a.quiet:
            print(f"✔ no capability-surface change detected in {what} "
                  f"({r['n_files']} file(s) touched)")
        return 0
    if bumped or new_logs:
        if not a.quiet:
            why = []
            if bumped:
                why.append("a version bump")
            if new_logs:
                why.append(f"{len(new_logs)} dev log(s)")
            print(f"✔ capability change in {what} is accompanied by {' and '.join(why)}")
        return 0

    print(f"⚠ CAPABILITY CHANGE WITH NO VERSION BUMP AND NO DEV LOG — {what}\n")
    for path, labels in sorted(hits.items()):
        print(f"    {path}")
        for lb in labels:
            print(f"        - {lb}")
    print("""
  A commit message is not a dev log: it is not in the log index, `prior_art.py` does not rank it,
  and it is not where the next reader looks. `check_dev_log_for_version.py` cannot catch this —
  it fires on a BUMP with no log, so a change that never bumps passes by not claiming anything.

  Measured: `faea9be7` added a fourth sampling method, re-cut a whole round's design across ten
  files, and carried neither. Found only because the PI asked.

  Either bump CLAUDE.md's `**Status:**` and write the log, or — if this is a feature branch that
  bumps at merge time, or a mid-arc commit whose log lands next — proceed; this is advisory.""")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
