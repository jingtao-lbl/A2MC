#!/usr/bin/env python
"""Report whether a `watch_slurm_array.sh` watcher is alive, finished, or silently dead.

    python tools/check_watcher_state.py <state.json> [--quiet]

Exit: 0 alive-and-running · 0 finished · 1 STALE (watcher died) · 2 unreadable/malformed.

WHY THIS EXISTS
---------------
On 2026-08-15 an array watcher stopped at complete=227/258 without writing its terminal line. Its
log simply stopped growing, and nothing distinguishes that from "still running, nothing changed" --
so a finished 258-case ensemble sat unnoticed. The watcher now publishes a state file whose MTIME
is a heartbeat; this reads it and applies the one test the log cannot support.

The load-bearing case is STALE: `status` still says RUNNING but the heartbeat has gone quiet. That
is the SIGKILL / node-reboot / vanished-session death, which no shell trap can catch, so it is the
reason liveness lives here rather than in the watcher's own exit handler.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import time

# Two missed polls before calling it dead. One is too tight: a poll can be late when the SLURM
# controller is slow, and the watcher deliberately `timeout`-wraps those calls (up to 50 s of
# tolerated hang per cycle), so a single-interval threshold would cry dead on a healthy watcher.
STALE_INTERVALS = 2.0
TERMINAL = {"ENDED", "ENDED_UNACCOUNTED", "DIED"}


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
        return 1 if status == "DIED" else 0

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
