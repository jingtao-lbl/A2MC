#!/usr/bin/env python
"""Case-level census for a node-packed or task-farmed EcoSIM ensemble.

WHY THIS EXISTS. A packed farm launches the binary directly, so a case carries no `job_id.txt`
and sacct sees only the NODE tasks. `tools/model_ensemble_status.py` then loses its
scheduler-reconciliation leg and reports a part-way-dead case as RUNNING forever (measured on
EcoSIM_BioCON R3: 1129 dead cases published as RUNNING against two terminal arrays). The only
case-level ground truth is THE FINAL RESTART ON DISK -- the same completion test the farm itself
uses to decide whether to skip a case, and the same one `scripts/ecosim_worklist.py` uses.

WHY IT IS HERE AND NOT IN A CASE FOLDER. The first copy was written by hand inside
EcoSIM_TeRaCON's phase_results stem; Lusignan needed the identical thing, and a script's SECOND
use is the trigger to promote it rather than copy it ([[feedback_plot_scripts_canonical_in_phase_results]]).
Everything that was case-specific in that copy -- the case-name prefix, the restart-year marker,
the case count -- is derived here from the round config and the cases' own namelists, so no
per-case edit is needed. It is a PER-MODEL script (EcoSIM's case layout), the parallel of
`scripts/ecosim_worklist.py`, not a generic A2MC tool
([[feedback_per_model_scripts_not_generic]]).

Driven from `tools/watch_slurm_array.sh`'s `-x` hook, which DISCARDS stdout and keeps only the
rc -- so this appends its own line to a census log and a `Monitor` is armed on THAT.

Enumeration is an explicit loop over the known case directories, one os.scandir per case; no
recursive walk (NERSC bounded-traversal rule).

USAGE
    source use_cases/EcoSIM_<Case>/config/<case>_config.sh
    python scripts/ecosim_case_census.py --census-log <stem>/census.log

Author: Jing Tao with Claude Code
"""
from __future__ import annotations

import argparse
import datetime
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ecosim_worklist import final_restart_year          # ONE copy of the year derivation


def tasks_running(jobs: str) -> int:
    """How many of this ensemble's scheduler tasks are RUNNING right now.

    `-r` is load-bearing: without it squeue folds a pending array into ONE line and the count is
    hundreds too small ([[feedback_never_parse_a_cli_default_output]]). A failed call returns 0,
    which SUPPRESSES the stall report -- deliberately, since a scheduler outage is not evidence
    that cases have stopped finishing. One call for a comma-separated MIX of ids is safe: Slurm
    returns rc=0 as long as at least one id is still known, so a drained array does not disable
    the detector; only ALL ids being gone does, which is the round being over.
    """
    if not jobs:
        return 0                       # unwired; the caller reports this LOUDLY, see CENSUS_UNWIRED
    try:
        out = subprocess.run(["squeue", "-j", jobs, "-r", "-h", "-t", "R", "-o", "%i"],
                             capture_output=True, text=True, timeout=30)
        return 0 if out.returncode != 0 else len([l for l in out.stdout.splitlines() if l.strip()])
    except Exception:
        return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-root", default=os.environ.get("A2MC_OUTPUT_DIR"))
    ap.add_argument("--census-log", required=True,
                    help="append the census line here; arm a Monitor on THIS file")
    ap.add_argument("--pattern", default=os.environ.get("A2MC_CASE_NAME_PATTERN", "case{N}"))
    ap.add_argument("--include-baseline", action="store_true",
                    help="count case 0 (V0). OFF by default, matching ecosim_worklist.py: V0 is "
                         "normally run and checked on its own, so counting it inflates the "
                         "denominator by one case that the farm was never given.")
    ap.add_argument("--stall-polls", type=int, default=3,
                    help="consecutive flat polls before the UNWIRED notice repeats. NOT the stall "
                         "test -- see --case-seconds; a poll count is the wrong unit for a stall.")
    ap.add_argument("--case-seconds", type=float,
                    default=float(os.environ.get("A2MC_EXPECTED_CASE_SECONDS") or 0) or None,
                    help="expected wall time of ONE case, seconds (default $A2MC_EXPECTED_CASE_"
                         "SECONDS). Without it the stall detector is DISABLED and says so.")
    ap.add_argument("--stall-grace-mult", type=float, default=1.5,
                    help="report a stall after this many expected case durations with no "
                         "completion and tasks running (default 1.5)")
    a = ap.parse_args()
    if not a.run_root:
        print("ERROR: --run-root or $A2MC_OUTPUT_DIR required", file=sys.stderr)
        return 2
    root = Path(a.run_root)
    if not root.is_dir():
        print(f"ERROR: no run root at {root}", file=sys.stderr)
        return 2

    census = Path(a.census_log)
    census.parent.mkdir(parents=True, exist_ok=True)
    prev_file = census.with_name("." + census.name + ".prev")

    prefix = a.pattern.split("{N}")[0]
    idx = []
    with os.scandir(root) as it:
        for e in it:
            if e.is_dir() and e.name.startswith(prefix):
                suf = e.name[len(prefix):]
                if suf.isdigit() and (a.include_baseline or int(suf) != 0):
                    idx.append(int(suf))
    idx.sort()

    # Derive the restart year ONCE from the first case, not per case: 4096 namelist reads every
    # poll is real filesystem load on a shared system, and the year is a property of the ROUND.
    # Cross-check a second case so a one-off malformed namelist cannot set the marker silently.
    year = None
    for n in idx[:1] + idx[len(idx) // 2:len(idx) // 2 + 1]:
        y = final_restart_year(root / f"{prefix}{n}" / "runfile.nml")
        if y is None:
            continue
        if year is not None and y != year:
            print(f"ERROR: cases disagree on the final restart year ({year} vs {y}). A census "
                  f"cannot be taken against two markers; fix the ensemble first.", file=sys.stderr)
            return 2
        year = y
    if year is None:
        print("ERROR: could not derive the final restart year from any case's runfile.nml",
              file=sys.stderr)
        return 2
    marker = f".r.{year}-01-01"

    ncases = len(idx)
    done = 0
    for n in idx:
        d = root / f"{prefix}{n}"
        try:
            if any(marker in e.name and e.name.endswith(".nc") for e in os.scandir(d)):
                done += 1
        except OSError:
            pass

    # prev holds "<count>,<flat-poll streak>,<last-progress epoch>,<last-stall-report epoch>".
    #
    # A STALL IS MEASURED IN TIME, NOT IN POLLS, and getting that wrong is what this file was
    # patched for on its first real use. The original test was "3 consecutive flat polls with
    # tasks running", which on Lusignan R1b fired at 10:32 against a run that started at 10:25 --
    # 3 polls spanning 5m41s, against cases that take an HOUR. A poll count cannot express "long
    # enough that a case should have finished", because it does not know how long a case is; the
    # first completion of any healthy run is therefore always preceded by a "stall". A monitor
    # that fires on expected quiet is tuned out along with the real events, which is the failure
    # this detector exists to avoid.
    now = int(datetime.datetime.now().timestamp())
    try:
        raw = prev_file.read_text().strip().split(",")
        prev, streak = int(raw[0]), (int(raw[1]) if len(raw) > 1 else 0)
        last_progress = int(raw[2]) if len(raw) > 2 else now
        last_stall = int(raw[3]) if len(raw) > 3 else 0
    except Exception:
        prev, streak, last_progress, last_stall = 0, 0, now, 0
    streak = streak + 1 if done == prev else 0
    # `last_progress` is the clock the stall test runs on: it advances on every completion.
    if done != prev:
        last_progress = now

    ts = datetime.datetime.now().strftime("%F %T")
    pct = done * 100 // ncases if ncases else 0
    ppct = prev * 100 // ncases if ncases else 0
    jobs = os.environ.get("A2MC_CENSUS_JOBIDS", "").strip()
    run = tasks_running(jobs)
    # The cold start: nothing has completed and nothing could have, because no task had started.
    # Hold the clock at `now` until a task is actually RUNNING, so the grace period is measured
    # from when work began rather than from when the watcher was armed.
    if done == prev and done == 0 and run == 0:
        last_progress = now
    quiet_s = now - last_progress

    with census.open("a") as f:
        f.write(f"[{ts}] CASE_CENSUS complete={done}/{ncases} ({pct}%) delta=+{done - prev} "
                f"marker={marker} jobs={jobs or 'UNSET'} running={run}\n")
        # An UNWIRED census cannot report a stall at all -- tasks_running() is 0 forever, so the
        # CASE_STALL branch below can never be reached. That is a check that cannot fail, and the
        # only thing worse than no stall detector is one that LOOKS armed
        # ([[feedback_a_check_that_cannot_fail]]). Say so, hourly, as an EVENT.
        if not jobs and streak >= a.stall_polls and streak % 6 == a.stall_polls:
            f.write(f"[{ts}] CENSUS_UNWIRED A2MC_CENSUS_JOBIDS is empty, so the stall detector "
                    f"is DISABLED ({streak} flat polls). Set it in the round config and re-source.\n")
        # Crossings, never exact counts: farm workers finish in bursts, so an equality filter
        # misses most of the values it is watching for.
        if pct > ppct:
            f.write(f"[{ts}] CASE_MILESTONE {pct}% complete={done}/{ncases}\n")
        # THE STALL TEST. Two conditions, and both are load-bearing:
        #   * tasks are RUNNING -- queued-and-quiet is the normal state, not an event;
        #   * no completion for longer than `stall_grace_mult` EXPECTED CASE DURATIONS -- the only
        #     unit in which "long enough that something should have finished" is expressible.
        # Re-reported at most hourly so a genuine stall stays visible without becoming a firehose.
        if a.case_seconds is None:
            if streak >= a.stall_polls and streak % 6 == a.stall_polls:
                f.write(f"[{ts}] CENSUS_NO_CASE_TIME no expected case duration, so the stall "
                        f"detector is DISABLED. Set A2MC_EXPECTED_CASE_SECONDS in the round "
                        f"config (a MEASURED per-case wall time) or pass --case-seconds.\n")
        elif run > 0 and quiet_s > a.case_seconds * a.stall_grace_mult \
                and now - last_stall >= 3600:
            last_stall = now
            f.write(f"[{ts}] CASE_STALL no completion for {quiet_s // 60} min "
                    f"({quiet_s / a.case_seconds:.1f} expected case durations), "
                    f"{run} task(s) RUNNING, complete={done}/{ncases}\n")

    prev_file.write_text(f"{done},{streak},{last_progress},{last_stall}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
