"""The watcher's liveness contract — pinned because every earlier version of this guard
could not fire.

Chronology on 2026-08-15, all measured rather than reasoned about:
  v1  reported only to a log     -> a dead watcher is byte-identical to a quiet one.
  v2  added an EXIT/INT/TERM trap -> SIGKILL cannot be trapped at all, and under SIGTERM bash
                                     defers the trap until the current command returns, so a
                                     watcher in `sleep 300` stamped nothing for five minutes.
  v3  backgrounded the sleep      -> the handler ran, wrote DIED, and then the LOOP RESUMED and
                                     overwrote the file with RUNNING one second later, because a
                                     bash signal handler returns unless it exits.
  v4  handler exits; the HEARTBEAT is the primary mechanism and the trap is a convenience.

So these tests assert the two properties that survive every death mode: a terminal status is
durable, and a stale heartbeat is reported as death even when the file still says RUNNING.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

# `watch_slurm_array.sh` wraps every squeue/sacct/hook call in GNU `timeout` and keys the hook
# verdict on its exit code 124. macOS ships no `timeout`, so every wrapped call yields nothing,
# the squeue/sacct shims below are never reached, and the watcher reports ENDED_UNACCOUNTED.
# Two of these would otherwise pass VACUOUSLY off-Linux (a completely dead hook path still
# yields FAIL / NONE), so gate every harness test rather than keep a tick that proves nothing.
requires_gnu_timeout = pytest.mark.skipif(
    shutil.which("timeout") is None,
    reason="needs GNU coreutils `timeout` (absent on macOS); the watcher runs on Perlmutter")



REPO = Path(__file__).resolve().parents[1]
CHECKER = REPO / "tools" / "check_watcher_state.py"
WATCHER = REPO / "tools" / "watch_slurm_array.sh"


def _check(path: Path):
    r = subprocess.run([sys.executable, str(CHECKER), str(path)], capture_output=True, text=True)
    return r.returncode, r.stdout


def _state(tmp_path: Path, **kw) -> Path:
    base = dict(ts="x", epoch=time.time(), status="RUNNING", job="1", pending=0, running=1,
                complete=10, failed=0, total=100, interval_s=300)
    base.update(kw)
    p = tmp_path / "state.json"
    p.write_text(json.dumps(base))
    return p


def test_stale_heartbeat_is_reported_as_death_even_though_status_says_running(tmp_path):
    """THE load-bearing case: SIGKILL, node loss, vanished session. No trap can catch these, so
    the file is left permanently claiming RUNNING. Only the heartbeat age reveals it."""
    rc, out = _check(_state(tmp_path, epoch=time.time() - 3600, interval_s=300))
    assert rc == 1, f"a stale heartbeat must be a FAILURE, got rc={rc}:\n{out}"
    assert "STALE" in out


def test_a_fresh_heartbeat_is_alive(tmp_path):
    rc, out = _check(_state(tmp_path))
    assert rc == 0 and "ALIVE" in out, out


def test_one_late_poll_is_not_yet_death(tmp_path):
    """The watcher timeout-wraps squeue/sacct and tolerates up to ~50s of controller hang per
    cycle, so a single missed interval must NOT be called death or the check cries wolf."""
    rc, out = _check(_state(tmp_path, epoch=time.time() - 320, interval_s=300))
    assert rc == 0, f"1.07 intervals is a late poll, not a death:\n{out}"


def test_died_does_not_exit_zero(tmp_path):
    """A self-announced death leaves the ARRAY's outcome just as unknown as a stale one. If it
    exited 0 it would slip through any gate that reads 0 as 'nothing to do'."""
    rc, out = _check(_state(tmp_path, status="DIED"))
    assert rc == 1, f"DIED must not pass, got rc={rc}:\n{out}"


def test_ended_is_a_pass_but_says_it_is_only_about_the_scheduler(tmp_path):
    rc, out = _check(_state(tmp_path, status="ENDED", complete=100, running=0))
    assert rc == 0 and "FINISHED" in out
    assert "SCHEDULER" in out, ("ENDED must not read as 'the science is valid' — 9 of 258 probe "
                                "tasks exited 0 with truncated output")


def test_missing_state_file_is_not_evidence_of_anything(tmp_path):
    rc, out = _check(tmp_path / "absent.json")
    assert rc == 2 and "NOT evidence" in out, out


def test_malformed_state_file_fails_loudly(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{not json")
    rc, out = _check(p)
    assert rc == 2 and "MALFORMED" in out, out


@pytest.mark.skipif(not WATCHER.is_file(), reason="watcher script absent")
def test_watcher_script_is_syntactically_valid():
    r = subprocess.run(["bash", "-n", str(WATCHER)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.skipif(not WATCHER.is_file(), reason="watcher script absent")
def test_signal_handler_exits_rather_than_resuming_the_loop():
    """v3's exact bug: `trap on_exit EXIT INT TERM` ran the handler and then RESUMED, overwriting
    DIED with RUNNING. A signal handler that does not exit produces a liveness signal that lies."""
    src = WATCHER.read_text()
    assert "on_signal() { stamp_died; exit" in src, "the signal handler must exit"
    assert "trap on_signal INT TERM" in src, "INT/TERM must use the exiting handler"
    assert "trap stamp_died EXIT" in src, "EXIT keeps the non-exiting stamp"


# ---------------------------------------------------------------------------
# The refresh hook (-x): the SECOND signal, and its own failure must be visible
# ---------------------------------------------------------------------------
def _run_watcher(tmp_path, hook=None, every=None, timeout=None, extra_env=None):
    """Run the watcher against a finished array (it exits after one poll)."""
    state = tmp_path / "s.json"
    cmd = ["bash", str(WATCHER), "-j", "1", "-n", "1", "-s", str(state), "-i", "5"]
    if hook is not None:
        cmd += ["-x", hook]
    if every is not None:
        cmd += ["-e", str(every)]
    if timeout is not None:
        cmd += ["-t", str(timeout)]
    shim = tmp_path / "shim"
    shim.mkdir(exist_ok=True)
    # squeue: nothing queued/running -> the watcher takes its terminal branch after one poll.
    (shim / "squeue").write_text("#!/bin/bash\nexit 0\n")
    (shim / "sacct").write_text("#!/bin/bash\necho COMPLETED\n")
    for f in ("squeue", "sacct"):
        (shim / f).chmod(0o755)
    import os
    env = dict(os.environ, PATH=f"{shim}:{os.environ['PATH']}")
    env.update(extra_env or {})
    r = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=120)
    return json.loads(state.read_text()), r.stdout


@requires_gnu_timeout
def test_hook_runs_and_its_success_is_published(tmp_path):
    marker = tmp_path / "ran"
    st, out = _run_watcher(tmp_path, hook=f"touch {marker}")
    assert marker.exists(), f"the refresh hook must actually run:\n{out}"
    assert st["hook_status"] == "OK" and st["hook_fail_streak"] == 0, st


@requires_gnu_timeout
def test_a_failing_hook_is_recorded_not_swallowed(tmp_path):
    """A refresh that silently stops updating is the ORIGINAL bug in a new place. The plot going
    stale must be a reportable state, not an absence."""
    st, out = _run_watcher(tmp_path, hook="exit 3")
    assert st["hook_status"] == "FAILED", st
    assert st["hook_fail_streak"] >= 1, st
    assert "HOOK FAILED" in out


@requires_gnu_timeout
def test_a_slow_hook_times_out_and_does_not_stall_the_watcher(tmp_path):
    """A hook slower than the poll interval must not wedge the loop: a stalled loop stops writing
    the heartbeat, and the watcher would then report ITSELF stale while perfectly healthy."""
    st, out = _run_watcher(tmp_path, hook="sleep 30", timeout=2)
    assert st["hook_status"] == "TIMEOUT", st
    assert "HOOK TIMEOUT" in out
    assert st["status"] == "ENDED", "the watcher must still reach its terminal state"


@requires_gnu_timeout
def test_hook_every_n_skips_intermediate_polls(tmp_path):
    """-e decouples refresh cadence from poll cadence, which matters when a full plot pass costs
    minutes (measured: 197 s for 258 EcoSIM cases) but the scheduler should be polled often."""
    marker = tmp_path / "ran"
    st, _ = _run_watcher(tmp_path, hook=f"touch {marker}", every=5)
    assert not marker.exists(), "poll 1 of every 5 must not fire the hook"
    assert st["hook_status"] == "NONE", st


@requires_gnu_timeout
def test_no_hook_is_the_default_and_reports_NONE(tmp_path):
    st, _ = _run_watcher(tmp_path)
    assert st["hook_status"] == "NONE" and st["status"] == "ENDED", st


def test_checker_surfaces_a_failing_hook(tmp_path):
    """Recording the hook's status is pointless if nothing reads it."""
    rc, out = _check(_state(tmp_path, hook_status="FAILED", hook_fail_streak=7))
    assert rc == 0, "a failing hook does not mean the WATCHER is dead"
    assert "refresh hook: FAILED for 7" in out, out
    assert "do not read an unchanging plot as an unchanging ensemble" in out


def test_checker_is_silent_about_a_hook_that_was_never_configured(tmp_path):
    rc, out = _check(_state(tmp_path))
    assert "refresh hook" not in out, out


# ---------------------------------------------------------------------------
# The pending count must survive SLURM's COMPACT array form (-r)
# ---------------------------------------------------------------------------
def _run_watcher_nonterminal(tmp_path, squeue_body, seconds=20):
    """Run the watcher against a STILL-ACTIVE array and read the first published state.

    The `_run_watcher` helper above relies on the array being finished so the watcher exits after
    one poll. This bug only shows while tasks are still queued, so here the watcher is started,
    its first heartbeat is read, and it is then terminated.
    """
    import os, time as _t
    state = tmp_path / "s.json"
    shim = tmp_path / "shim"
    shim.mkdir(exist_ok=True)
    (shim / "squeue").write_text(squeue_body)
    (shim / "sacct").write_text("#!/bin/bash\nexit 0\n")
    for f in ("squeue", "sacct"):
        (shim / f).chmod(0o755)
    env = dict(os.environ, PATH=f"{shim}:{os.environ['PATH']}")
    proc = subprocess.Popen(
        ["bash", str(WATCHER), "-j", "9", "-n", "7", "-s", str(state), "-i", "5"],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    try:
        deadline = _t.time() + seconds
        while _t.time() < deadline:
            if state.exists():
                try:
                    st = json.loads(state.read_text())
                except json.JSONDecodeError:
                    st = None
                # SKIP THE STARTING RECORD. The watcher publishes `write_state "STARTING" 0 0 0 0`
                # BEFORE its first poll, so returning on mere existence can hand back a record whose
                # counts are all zero by construction -- and a test asserting pending==7 then fails
                # or, worse, a test asserting pending==0 PASSES for the wrong reason. This helper
                # wants the first POLL result, not the startup stamp. Measured 2026-09-04: the
                # compact-array test failed once in five combined runs on exactly this race, having
                # been passing on timing luck since it was written.
                if st is not None and st.get("status") != "STARTING":
                    return st
            _t.sleep(0.2)
        raise AssertionError("watcher never published a POLL state (only STARTING, or nothing)")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()


# squeue emulating SLURM: a pending array range collapses to ONE line unless -r is passed.
_SQUEUE_COMPACT_AWARE = """#!/bin/bash
if [[ "$*" == *"-t PENDING"* ]]; then
  if [[ "$*" == *" -r "* ]]; then
    for i in 1 2 3 4 5 6 7; do echo "9_$i"; done
  else
    echo "9_[1-7]"
  fi
fi
exit 0
"""


@requires_gnu_timeout
def test_pending_count_expands_the_compact_array_form(tmp_path):
    """Without -r, `squeue -h -t PENDING -o %i | wc -l` returns 1 for ANY number of queued tasks.

    Measured on EcoSIM_BioCON R3 chunk 1 (2026-08-20): the state file published "pending": 1 while
    4,959 tasks were genuinely queued. Control flow was unaffected (milestones come from sacct, and
    the terminal test only needs zero vs nonzero), but the published number was off by three orders
    of magnitude, and a liveness signal that misreports is the class of bug this file exists for.
    """
    st = _run_watcher_nonterminal(tmp_path, _SQUEUE_COMPACT_AWARE)
    assert st["pending"] == 7, f'expected the expanded count, got {st["pending"]}: {st}'


@requires_gnu_timeout
def test_zero_pending_still_reads_as_zero(tmp_path):
    """The fix must not disturb the terminal test, which asks PEND -eq 0."""
    st = _run_watcher_nonterminal(
        tmp_path,
        '#!/bin/bash\nif [[ "$*" == *"-t RUNNING"* ]]; then echo "9_1"; fi\nexit 0\n')
    assert st["pending"] == 0, st
    assert st["running"] == 1, st


# =================================================================================================
# HARDENING 1 (2026-09-04) -- a terminal status is CROSS-CHECKED, not trusted.
#
# The 2026-09-03 failure in one line: the state file read ENDED_UNACCOUNTED with complete=233 of
# 4097 while 3,733 tasks were still live, and this checker exited 0 over it for 31 hours. The old
# code printed "inspect the logs before treating this as a clean finish" and then RETURNED 0 --
# a warning nothing reads, in the layer built to catch exactly this.
# =================================================================================================

def test_a_terminal_status_with_unaccounted_tasks_is_NOT_a_pass(tmp_path):
    """The real 2026-09-03 shape, reduced: terminal, but the numbers do not add up."""
    rc, out = _check(_state(tmp_path, status="ENDED_UNACCOUNTED", job="",
                            complete=233, failed=5, total=4097))
    assert rc == 1, f"233+5 of 4097 is not a finish; got rc={rc}:\n{out}"
    assert "FALSE-TERMINAL" in out and "do not add up" in out, out


def test_ENDED_that_actually_adds_up_still_passes(tmp_path):
    """CONTROL. Without this, a checker that failed EVERY terminal state would pass the test
    above while being useless -- the failure mode the check itself exists to prevent."""
    rc, out = _check(_state(tmp_path, status="ENDED", job="",
                            complete=95, failed=5, total=100))
    assert rc == 0, f"a fully accounted ENDED is a clean finish; got rc={rc}:\n{out}"
    assert "FALSE-TERMINAL" not in out, out


def test_the_REAL_2026_09_03_state_file_is_rejected(tmp_path):
    """Against the ACTUAL artifact, preserved when the watcher died. Reduced shapes can drift
    from the thing they model; this one cannot, because it IS the thing."""
    import json as _json
    real = (REPO / "use_cases/EcoSIM_TeRaCON/memory/phase_results"
                 / "20260901a_phase0_design_r01_r1_parameter_design_and_the_recovery_of_bounds_provenance"
                 / "watch_state.json.false_terminal_20260903")
    if not real.is_file():
        pytest.skip("the preserved 2026-09-03 state file is not in this checkout")
    st = _json.loads(real.read_text())
    assert st["status"] == "ENDED_UNACCOUNTED" and st["complete"] + st["failed"] < st["total"], st
    # Copy rather than point at it, so a stray write can never touch the preserved evidence.
    copy = tmp_path / "state.json"
    copy.write_text(real.read_text())
    rc, out = _check(copy)
    assert rc == 1, f"the state file that cost 31 h of blind runtime must not pass:\n{out}"


def test_the_cross_check_reports_UNKNOWN_rather_than_assuming_fine(tmp_path):
    """A checker that treats 'cannot tell' as a pass is the whole failure class. When the
    scheduler cannot be consulted, the arithmetic still decides and the gap is stated."""
    rc, out = _check(_state(tmp_path, status="ENDED", job="", complete=100, failed=0, total=100))
    assert rc == 0, out
    assert "UNKNOWN" in out, ("with no job id the scheduler leg cannot run, and that must be "
                              f"SAID rather than silently skipped:\n{out}")


# =================================================================================================
# HARDENING 2 (2026-09-04) -- the watcher execs a RUN-SCOPED COPY of itself.
#
# Bash reads a script by byte offset as it executes, and parses the poll loop as ONE compound
# command -- so an edit does not bite while the loop spins, it bites when the loop EXITS and bash
# reads further into a file whose offsets have shifted. That is where the real watcher died:
#   watch_slurm_array.sh: line 190: syntax error near unexpected token `)'
# INSIDE the block the fix being deployed had just added.
# =================================================================================================

def _run_watcher_and_edit_it_mid_run(tmp_path, watcher_src):
    """Launch a watcher, mutate its file while the loop spins, then let it fall out of the loop.

    SEQUENCING IS THE TEST. A first version of this harness drove the watcher to its terminal
    block within two seconds, so both arms finished BEFORE the edit and it proved nothing. The
    squeue stub is therefore stateful: it reports a live task until the marker file is removed.
    """
    import os, shutil as _sh, subprocess as _sp, time as _t
    work = tmp_path / "w"; (work / "bin").mkdir(parents=True)
    marker = work / "KEEP_RUNNING"; marker.touch()
    (work / "bin" / "squeue").write_text(
        f'#!/bin/bash\n[ -f "{marker}" ] && echo "999999_1"\nexit 0\n')
    (work / "bin" / "sacct").write_text('#!/bin/bash\nexit 0\n')
    for b in ("squeue", "sacct"):
        os.chmod(work / "bin" / b, 0o755)

    under_test = work / "watcher_under_test.sh"
    _sh.copy(watcher_src, under_test)
    log = work / "watch.log"
    env = dict(os.environ, PATH=f"{work / 'bin'}:{os.environ['PATH']}")
    with open(log, "w") as fh:
        proc = _sp.Popen(["bash", str(under_test), "-j", "999999", "-n", "4",
                          "-s", str(work / "state.json"), "-i", "1"],
                         stdout=fh, stderr=_sp.STDOUT, env=env)
    try:
        _t.sleep(3)                                    # get well into the loop
        lines = under_test.read_text().split("\n")     # THE MUTATION: shift every offset below
        under_test.write_text("\n".join(lines[:3] + ["# " + "x" * 70] * 20 + lines[3:]))
        _t.sleep(3)
        marker.unlink()                                # fall out of the loop, POST-mutation
        _t.sleep(6)
    finally:
        proc.kill()
    return log.read_text()


@requires_gnu_timeout
def test_editing_the_watcher_mid_run_no_longer_kills_it(tmp_path):
    out = _run_watcher_and_edit_it_mid_run(tmp_path, WATCHER)
    assert "run-scoped snapshot" in out, f"the watcher must exec its own copy:\n{out[-800:]}"
    low = out.lower()
    assert "syntax error" not in low and "unexpected token" not in low, \
        f"an edit under the running watcher still killed it:\n{out[-800:]}"
    assert "ARRAY ENDED" in out, f"it must still reach its terminal block:\n{out[-800:]}"


@requires_gnu_timeout
def test_the_harness_ACTUALLY_reproduces_the_death_without_the_fix(tmp_path):
    """CONTROL, and the load-bearing one. Without it the test above could pass because the
    harness never reproduces anything -- which is the same 'check that cannot fail' shape the
    fix exists to close. Strips the snapshot block and asserts the death comes back."""
    src = WATCHER.read_text()
    marker = 'if [ -z "${A2MC_WATCHER_SNAPSHOT:-}" ]; then'
    assert marker in src, "the snapshot block moved; this control needs updating"
    start = src.index(marker)
    end = src.index("EMPTY_STREAK=0", start)
    unhardened = tmp_path / "unhardened.sh"
    unhardened.write_text(src[:start] + src[end:])
    out = _run_watcher_and_edit_it_mid_run(tmp_path / "ctl", unhardened)
    low = out.lower()
    assert "syntax error" in low or "unexpected token" in low, \
        ("the harness did not reproduce the 2026-09-03 death, so the test above proves nothing:\n"
         + out[-800:])


# =================================================================================================
# HARDENING 3 (2026-09-23) -- "finished" is a FINISHED STATUS in the accounting record, never an
# inference from the queue.
#
# The watcher used to declare ENDED on two consecutive EMPTY squeue polls. squeue forgets every
# finished job after MinJobAge (300 s on Perlmutter) and then answers "Invalid job id", so whenever
# those two polls straddled the purge the watcher held for ever. Measured on V0 job 58788324: ended
# 08:36:07, purged ~08:41:07, second poll 08:41:38, held until stopped by hand. The fix is NOT to
# read "Invalid job id" as finished -- a job's absence is not a status -- but to decide on sacct,
# which keeps each task's final state after the queue has let it go (PI, 2026-09-23).
# =================================================================================================
_SQUEUE_PURGED = ('#!/bin/bash\necho "slurm_load_jobs error: Invalid job id specified" >&2\n'
                  'exit 1\n')


def _run_watcher_with(tmp_path, squeue_body, sacct_body, ntasks=1, seconds=25):
    """Run the watcher against arbitrary squeue/sacct shims; return (final state, log text).

    Stops at the first terminal status or after `seconds`, whichever comes first, so a watcher
    that correctly HOLDS is observed holding rather than hanging the test.
    """
    import os, time as _t
    state = tmp_path / "s.json"
    shim = tmp_path / "shim"
    shim.mkdir(exist_ok=True)
    (shim / "squeue").write_text(squeue_body)
    (shim / "sacct").write_text(sacct_body)
    for f in ("squeue", "sacct"):
        (shim / f).chmod(0o755)
    env = dict(os.environ, PATH=f"{shim}:{os.environ['PATH']}")
    log = tmp_path / "watch.log"
    with open(log, "w") as fh:
        proc = subprocess.Popen(["bash", str(WATCHER), "-j", "7", "-n", str(ntasks),
                                 "-s", str(state), "-i", "1"],
                                stdout=fh, stderr=subprocess.STDOUT, env=env)
    observed = None
    try:
        deadline = _t.time() + seconds
        while _t.time() < deadline and proc.poll() is None:
            _t.sleep(0.3)
        # READ BEFORE STOPPING: terminating a still-holding watcher makes its signal handler stamp
        # DIED, which would hide the very status (a correct hold) the caller is asking about.
        observed = json.loads(state.read_text())
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=10)
    return observed, log.read_text()


@requires_gnu_timeout
def test_a_job_purged_from_the_queue_still_ends_on_its_final_status(tmp_path):
    """The 2026-09-23 case: squeue has forgotten the job, sacct records it COMPLETED."""
    st, log = _run_watcher_with(tmp_path, _SQUEUE_PURGED, "#!/bin/bash\necho COMPLETED\n")
    assert st["status"] == "ENDED", f"a COMPLETED job must end even after its purge:\n{log}"
    assert "final status from sacct" in log, log


@requires_gnu_timeout
def test_CONTROL_a_purged_job_without_a_final_status_does_not_end(tmp_path):
    """CONTROL for the test above. If sacct does not say the task finished, the watcher holds:
    the queue having forgotten the job is not, by itself, evidence of anything."""
    st, log = _run_watcher_with(tmp_path, _SQUEUE_PURGED, "#!/bin/bash\necho RUNNING\n", seconds=8)
    assert st["status"] == "RUNNING", f"no final status, so no finish:\n{log}"
    assert "ARRAY ENDED" not in log, log


@requires_gnu_timeout
def test_a_failed_sacct_read_never_counts_as_finished(tmp_path):
    """An empty queue plus an UNREADABLE accounting record is two absences, not a status."""
    st, log = _run_watcher_with(tmp_path, "#!/bin/bash\nexit 0\n",
                                "#!/bin/bash\necho 'sacct: error: slurmdbd down' >&2\nexit 1\n",
                                seconds=8)
    assert st["status"] == "RUNNING", f"a failed sacct must hold, not end:\n{log}"
    assert "sacct read FAILED" in log, log


@requires_gnu_timeout
def test_final_statuses_while_the_queue_still_lists_live_tasks_hold(tmp_path):
    """sacct says all final, squeue SUCCESSFULLY lists a running task: they disagree, so hold."""
    st, log = _run_watcher_with(
        tmp_path, '#!/bin/bash\nif [[ "$*" == *"-t RUNNING"* ]]; then echo "7_1"; fi\nexit 0\n',
        "#!/bin/bash\necho COMPLETED\n", seconds=8)
    assert st["status"] == "RUNNING", f"a live task in the queue must block the finish:\n{log}"
    assert "holding until they agree" in log, log


@requires_gnu_timeout
def test_failed_tasks_are_final_and_the_array_still_ends(tmp_path):
    """A FAILED or TIMEOUT task has finished (badly). The array ends, and the failures are counted."""
    st, log = _run_watcher_with(tmp_path, "#!/bin/bash\nexit 0\n",
                                "#!/bin/bash\nprintf 'COMPLETED\\nTIMEOUT\\nCANCELLED by 42\\n'\n",
                                ntasks=3)
    assert st["status"] == "ENDED", log
    assert (st["complete"], st["failed"]) == (1, 2), st


# ---- the checker's cross-check reads the same record -----------------------------------------------
def _check_with_sacct(tmp_path, sacct_body, **state_kw):
    import os
    shim = tmp_path / "cshim"
    shim.mkdir(exist_ok=True)
    (shim / "sacct").write_text(sacct_body)
    (shim / "sacct").chmod(0o755)
    (shim / "squeue").write_text(_SQUEUE_PURGED)      # present, and deliberately unhelpful
    (shim / "squeue").chmod(0o755)
    env = dict(os.environ, PATH=f"{shim}:{os.environ['PATH']}")
    r = subprocess.run([sys.executable, str(CHECKER), str(_state(tmp_path, **state_kw))],
                       capture_output=True, text=True, env=env)
    return r.returncode, r.stdout


def test_checker_confirms_a_finish_from_the_accounting_record(tmp_path):
    rc, out = _check_with_sacct(tmp_path, "#!/bin/bash\necho '7|COMPLETED'\n",
                                status="ENDED", job="7", complete=1, failed=0, total=1)
    assert rc == 0, out
    assert "FALSE-TERMINAL" not in out and "UNKNOWN" not in out, out


def test_checker_rejects_a_terminal_claim_the_record_contradicts(tmp_path):
    """CONTROL: the same ENDED claim, but sacct shows a task still RUNNING."""
    rc, out = _check_with_sacct(tmp_path, "#!/bin/bash\nprintf '7_1|COMPLETED\\n7_2|RUNNING\\n'\n",
                                status="ENDED", job="7", complete=2, failed=0, total=2)
    assert rc == 1, out
    assert "FALSE-TERMINAL" in out and "accounting record DISAGREES" in out, out


def test_checker_says_UNKNOWN_when_the_record_cannot_be_read(tmp_path):
    rc, out = _check_with_sacct(tmp_path, "#!/bin/bash\nexit 1\n",
                                status="ENDED", job="7", complete=1, failed=0, total=1)
    assert rc == 0, out
    assert "UNKNOWN" in out, out
