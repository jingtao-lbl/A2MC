#!/usr/bin/env python
"""Report whether a `watch_slurm_array.sh` watcher is alive, finished, or silently dead.

    python tools/check_watcher_state.py <state.json> [--quiet]

Exit: 0 alive-and-running · 0 CLEANLY finished · 1 STALE / DIED / a terminal claim that does
not hold up · 2 unreadable/malformed.

WHY THIS EXISTS
---------------
On 2026-08-15 an array watcher stopped at complete=227/258 without writing its terminal line. Its
log simply stopped growing, and nothing distinguishes that from "still running, nothing changed" --
so a finished 258-case ensemble sat unnoticed. The watcher now publishes a state file whose MTIME
is a heartbeat; this reads it and applies the one test the log cannot support.

The load-bearing case is STALE: `status` still says RUNNING but the heartbeat has gone quiet. That
is the SIGKILL / node-reboot / vanished-session death, which no shell trap can catch, so it is the
reason liveness lives here rather than in the watcher's own exit handler.

AND A TERMINAL STATUS IS NOT TAKEN ON TRUST (added 2026-09-04)
-------------------------------------------------------------
The first version treated any terminal status as a pass, so a watcher that died WHILE WRITING a
false terminal blinded the layer built to catch it. That is not hypothetical and it was predicted
in writing before it happened: commit 5f613ec6 fixed a bad squeue poll that made one empty read
look like "no jobs left", and its own message warned that "the health guard would have reported
wave 2 FINISHED indefinitely rather than stale -- the layer built to catch a dead watcher was
blinded by the dead watcher's own final write." Two days later, on 2026-09-03, exactly that
happened on a different array: the state file read ENDED_UNACCOUNTED with complete=233 of 4097
while 3,733 tasks were still live, and this checker exited 0 over it for 31 hours.

So a terminal claim now has to survive two tests before it passes:

  ARITHMETIC (always available, and decisive for the case above)
      complete + failed must equal total. ENDED_UNACCOUNTED means BY DEFINITION that it does not,
      so it can no longer exit 0 -- the old code printed "inspect the logs before treating this as
      a clean finish" and then returned 0, which is a warning nothing reads.

  ACCOUNTING CROSS-CHECK (best-effort; adds errors, never removes them)
      The job's own record in sacct: if any task still has a non-final status (PENDING, RUNNING,
      REQUEUED, ...), the terminal claim is FALSE regardless of what the arithmetic says. The
      QUEUE is deliberately not asked. A job's absence from squeue is not a status, and squeue
      forgets every finished job after MinJobAge, so "the queue no longer knows it" would read a
      purged job as agreement. Reports UNKNOWN honestly when sacct cannot be read, rather than
      treating "cannot tell" as "fine" -- the whole failure class this tool exists for is a check
      that passes because it could not see anything.
"""

import argparse
import json
import pathlib
import shutil
import subprocess
import sys
import time

# Two missed polls before calling it dead. One is too tight: a poll can be late when the SLURM
# controller is slow, and the watcher deliberately `timeout`-wraps those calls (up to 50 s of
# tolerated hang per cycle), so a single-interval threshold would cry dead on a healthy watcher.
STALE_INTERVALS = 2.0
TERMINAL = {"ENDED", "ENDED_UNACCOUNTED", "DIED"}


# A task in any of these has finished. Anything else (PENDING, RUNNING, REQUEUED, SUSPENDED,
# COMPLETING, ...) has not. Kept identical to the watcher's allow-list.
FINAL_STATES = ("COMPLETED", "FAILED", "TIMEOUT", "CANCELLED", "NODE_FAIL", "OUT_OF_MEMORY",
                "BOOT_FAIL", "DEADLINE")


def _accounting_still_has_live_tasks(job: str):
    """(has_live, note) from the job's sacct record — True / False / None when undeterminable.

    Reads each task's STATUS, which the accounting database keeps after the job has left the
    queue. `-P` because the default output truncates states (CANCELLED+) and is not data. A
    pending array range folds to one line (`123_[5-99]  PENDING`), which is still correctly
    counted as live. An empty or failed read is UNKNOWN, never "no live tasks".
    """
    if not job:
        return None, "the state file names no job id"
    if shutil.which("sacct") is None:
        return None, "sacct is not on PATH (off-cluster?)"
    try:
        # stdout/stderr=PIPE + universal_newlines, not capture_output/text: those are Python 3.7+.
        r = subprocess.run(["sacct", "-j", str(job), "-P", "-n", "-X", "--format=JobID,State"],
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                           universal_newlines=True, timeout=30)
    except Exception as e:                                   # pragma: no cover - env-dependent
        return None, f"sacct could not be run ({e})"
    if r.returncode != 0:
        return None, f"sacct failed: {(r.stderr or '').strip()[:120]}"
    rows = [ln.split("|") for ln in r.stdout.splitlines() if ln.strip()]
    if not rows:
        return None, "sacct returned no record for this job id"
    live = [(jid, st) for jid, st, *_ in rows if not st.startswith(FINAL_STATES)]
    if live:
        shown = ", ".join(f"{j} {s}" for j, s in live[:3])
        return True, f"{len(live)} record(s) in sacct are not final ({shown})"
    return False, f"all {len(rows)} record(s) in sacct carry a final status"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--quiet", action="store_true", help="print nothing; use the exit code")
    a = ap.parse_args()

    p = pathlib.Path(a.state)
    if not p.is_file():
        if not a.quiet:
            print(f"UNREADABLE: no state file at {p}. The watcher never started, or was pointed "
                  f"somewhere else. This is NOT evidence the array is running.")
        return 2
    try:
        st = json.loads(p.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return _bail(f"MALFORMED: {p} is not readable JSON ({e}).", a.quiet)

    try:
        status = str(st["status"])
        epoch = float(st["epoch"])
        interval = float(st.get("interval_s", 300))
        done, bad, total = int(st["complete"]), int(st["failed"]), int(st["total"])
    except (KeyError, TypeError, ValueError) as e:
        return _bail(f"MALFORMED: {p} lacks the expected fields ({e}).", a.quiet)

    age = time.time() - epoch
    counts = f"complete={done} failed={bad} of {total}"

    if status in TERMINAL:
        if not a.quiet:
            verdict = {"ENDED": "FINISHED", "ENDED_UNACCOUNTED": "FINISHED (UNACCOUNTED)",
                       "DIED": "WATCHER DIED (reported its own death)"}[status]
            print(f"{verdict}: {counts}, last update {age / 60:.1f} min ago.")
            if status == "ENDED_UNACCOUNTED":
                print(f"  {total - done - bad} task(s) left no terminal state -- inspect the logs "
                      f"before treating this as a clean finish.")
            if status == "ENDED":
                print("  NOTE: 'ENDED' means the SCHEDULER is done. A task can exit 0 having "
                      "written partial output, so this is not a statement that the science is "
                      "valid -- the scoring path's window-coverage check is what catches that.")
            if status == "DIED":
                print("  The ARRAY's state is therefore unknown: the watcher stopped before the "
                      "array did. Query sacct directly.")
        # DIED is NOT a pass. It is the same thing STALE reports, only self-announced, and the
        # array's outcome is equally unknown either way -- so it must not exit 0 and slip through
        # a gate that treats 0 as "nothing to do".
        if status == "DIED":
            return 1

        # A terminal claim is CROSS-CHECKED, not trusted. See the module docstring for the
        # 2026-09-03 measurement this closes.
        problems = []
        if done + bad != total:
            problems.append(f"the numbers do not add up: complete+failed = {done + bad}, not "
                            f"{total}. A terminal state with unaccounted tasks is not a finish.")
        has_tasks, note = _accounting_still_has_live_tasks(str(st.get("job", "")))
        if has_tasks:
            problems.append(f"the job's accounting record DISAGREES: {note}. The watcher wrote a "
                            f"terminal state while the array is still live -- this is a FALSE TERMINAL.")

        if problems:
            if not a.quiet:
                print("  FALSE-TERMINAL CHECK FAILED:")
                for pr in problems:
                    print(f"    - {pr}")
                print("    Do NOT treat this as a finished ensemble. Re-launch the watcher and "
                      "query sacct directly.")
            return 1
        if not a.quiet and has_tasks is None:
            print(f"  cross-check: accounting state UNKNOWN ({note}); the arithmetic check passed "
                  f"({done + bad} of {total} accounted).")
        return 0

    if age > STALE_INTERVALS * interval:
        if not a.quiet:
            print(f"STALE: status is {status} but the heartbeat is {age / 60:.1f} min old "
                  f"(poll interval {interval / 60:.1f} min). The watcher is dead and did not get "
                  f"to say so -- a hard kill, a node loss, or a vanished session. Last seen: "
                  f"{counts}. Check the array directly with sacct before assuming anything.")
        return 1

    if not a.quiet:
        print(f"ALIVE: {status}, {counts}, heartbeat {age:.0f}s old (interval {interval:.0f}s).")
        _report_hook(st)
    return 0


def _report_hook(st: dict) -> None:
    """The refresh hook is the second signal; a hook that has been failing is a plot that quietly
    stopped updating, which is this whole tool's original bug wearing a different hat."""
    hs = st.get("hook_status", "NONE")
    if hs == "NONE":
        return
    streak = int(st.get("hook_fail_streak", 0) or 0)
    if hs == "OK":
        age = time.time() - float(st.get("hook_epoch", 0) or 0)
        print(f"  refresh hook: OK, last ran {age / 60:.1f} min ago.")
    else:
        print(f"  refresh hook: {hs} for {streak} consecutive attempt(s). The scheduler signal is "
              f"still good, but the filesystem/science signal is NOT being updated -- do not read "
              f"an unchanging plot as an unchanging ensemble.")


def _bail(msg: str, quiet: bool) -> int:
    if not quiet:
        print(msg)
    return 2


if __name__ == "__main__":
    sys.exit(main())
