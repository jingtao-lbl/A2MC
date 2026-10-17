#!/usr/bin/env python3
"""A round cannot leave Phase 0 without its full ensemble's run record in the Phase-0 stem folder.

visibility: public

THE RULE (`phase0-design`, Step 3). Testing runs -- gates, reruns, probes, V0 arms -- are recorded in
the case's run ledger (`memory/run_records_r{RR}.json` and its `SIMULATIONS_r{RR}.md`). The full
Phase-0 ensemble is NOT a ledger row: it is submitted under `A2MC_UNTRACKED_JOB`, whose declaration
says its record is the Phase-0 stem folder. This checker makes that declaration hold. The round's
newest Phase-0 stem must carry a `run_tracking/` subfolder with:

  * a submission record   `SUBMISSION_r{RR}.md`       the command line, environment and outcome
  * the launcher           at least one `*.sh`          the script as submitted
  * the watcher record     a state file (`*state*.json`) and a log digest (`*.digest.log`)

WHEN IT APPLIES. Only once the round's offline state has moved PAST `design` -- the handoff to
Phase 1 is the moment the record must be complete -- and only for Phase-0 stems dated on or after
`CUTOFF`, so rounds closed before the rule existed are not re-litigated.

Exit 0 clean, 1 a violation (blocking in pre-commit check 31).

Usage:  python3 tools/check_phase0_run_tracking.py [--case-dir use_cases/<Case>] [--staged]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUTOFF = "20261015"          # Phase-0 stems dated before this are exempt
STEM_RE = re.compile(r"^(\d{8})[a-z]+_phase0_design_r(\d{2})_")


def phase0_stems(case: Path, rnd: int) -> list[Path]:
    pr = case / "memory" / "phase_results"
    if not pr.is_dir():
        return []
    out = []
    for d in pr.iterdir():
        m = STEM_RE.match(d.name)
        if d.is_dir() and m and int(m.group(2)) == rnd:
            out.append(d)
    return sorted(out, key=lambda d: d.name)


def missing(run_tracking: Path, rnd: int) -> list[str]:
    if not run_tracking.is_dir():
        return ["the run_tracking/ subfolder itself"]
    gaps = []
    if not (run_tracking / f"SUBMISSION_r{rnd:02d}.md").is_file():
        gaps.append(f"SUBMISSION_r{rnd:02d}.md (command line, environment, outcome)")
    if not list(run_tracking.rglob("*.sh")):
        gaps.append("the launcher as submitted (*.sh)")
    if not list(run_tracking.rglob("*state*.json")):
        gaps.append("a watcher state file (*state*.json)")
    if not list(run_tracking.rglob("*.digest.log")):
        gaps.append("a watcher log digest (*.digest.log)")
    return gaps


def check_case(case: Path) -> list[str]:
    problems = []
    for sf in sorted((case / "memory").glob("workflow_state_offline_r*.json")):
        try:
            st = json.loads(sf.read_text())
        except (OSError, ValueError):
            continue
        rnd, phase = st.get("calibration_round"), st.get("current_phase")
        if not isinstance(rnd, int) or phase in (None, "design"):
            continue
        stems = phase0_stems(case, rnd)
        if not stems:
            continue
        newest = stems[-1]
        if STEM_RE.match(newest.name).group(1) < CUTOFF:
            continue
        gaps = missing(newest / "run_tracking", rnd)
        if gaps:
            problems.append(f"{case.name} round {rnd} is at '{phase}', but its Phase-0 stem "
                            f"{newest.name}/run_tracking/ lacks: " + "; ".join(gaps))
    return problems


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--case-dir", type=Path, help="one case; default every case under use_cases/")
    ap.add_argument("--staged", action="store_true",
                    help="only the cases with a staged workflow_state or phase_results change")
    a = ap.parse_args(argv)
    if a.case_dir:
        cases = [a.case_dir if a.case_dir.is_absolute() else ROOT / a.case_dir]
    else:
        cases = sorted(p for p in (ROOT / "use_cases").iterdir() if p.is_dir())
    if a.staged:
        names = subprocess.run(["git", "-C", str(ROOT), "diff", "--cached", "--name-only"],
                               capture_output=True, text=True).stdout.split()
        touched = {n.split("/")[1] for n in names if n.startswith("use_cases/")}
        cases = [c for c in cases if c.name in touched]
    problems = [p for c in cases for p in check_case(c)]
    if not problems:
        print("check_phase0_run_tracking: every round past Phase 0 carries its ensemble's run record")
        return 0
    for p in problems:
        print(f"check_phase0_run_tracking: {p}")
    print("  A full Phase-0 ensemble is not in the run ledger; its record lives in the Phase-0 stem's "
          "run_tracking/ (phase0-design, Step 3). Archive it before the round leaves Phase 0, with "
          "the case's scripts/archive_run_tracking.py where it has one.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
