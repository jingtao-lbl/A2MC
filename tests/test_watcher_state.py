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
                    return json.loads(state.read_text())
                except json.JSONDecodeError:
                    pass
            _t.sleep(0.2)
        raise AssertionError("watcher never published a state file")
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
