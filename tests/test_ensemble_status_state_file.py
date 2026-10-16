#!/usr/bin/env python
"""The heartbeat/singleton contract of `model_ensemble_status.py --state-file`.

visibility: public

Three properties, each of which a hand-rolled watcher has gotten wrong, and none of
which a single-file test can catch on its own:

  * ONE WATCHER PER STATE FILE. Two instances publishing to one path means whichever
    writes last is what every reader sees, and a stale instance can therefore publish a
    count the live one disagrees with.
  * `total` COMES FROM THE SCAN. A hardcoded total makes the watcher's own finish test
    unreachable whenever the arm count differs from it, which presents as a healthy
    watcher that never terminates rather than as an error.
  * THE KEY NAMES ARE THE CONSUMER'S. `tools/check_watcher_state.py` reads `job`,
    singular; a producer writing `jobs` disables that reader's sacct cross-check and
    nothing reports it, because a matcher finding nothing looks like a matcher finding
    no problem.

The schema assertions below are therefore spelled by READING the consumer's source
rather than by carrying a copy of its key list: the failure being pinned is a producer
and a consumer each being internally consistent and disagreeing with each other.

Full account: `memory/dev_logs_adapterkit/20261009n_One_Watcher_Per_State_File_And_The_Total_Comes_From_The_Scan.md`

Author: Jing Tao with Claude
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
PY = sys.executable


def _load():
    spec = importlib.util.spec_from_file_location(
        "mes", REPO / "tools" / "model_ensemble_status.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


mes = _load()


# --------------------------------------------------------------- schema contract
def _consumer_keys():
    """The keys `check_watcher_state.py` actually reads, taken from its source.

    Read rather than listed, so adding a key there fails this test instead of silently
    going unwritten -- the defect being pinned is precisely a name agreed by nobody.
    """
    src = (REPO / "tools" / "check_watcher_state.py").read_text()
    required = []
    for key in ("status", "epoch", "interval_s", "complete", "failed", "total", "job"):
        if f'"{key}"' in src or f"'{key}'" in src:
            required.append(key)
    return required


def test_state_file_carries_every_key_the_consumer_reads(tmp_path):
    st = mes.StateFile(tmp_path / "s.json", 60, "note")
    st.write("RUNNING", {"COMPLETED": 1, "FAILED": 0, "PENDING": 2}, 3, job="111,222")
    payload = json.loads((tmp_path / "s.json").read_text())
    missing = [k for k in _consumer_keys() if k not in payload]
    assert not missing, f"check_watcher_state.py reads {missing}, which are not published"


def test_job_key_is_singular_not_plural(tmp_path):
    """`jobs` silences the consumer's sacct leg without raising anything."""
    st = mes.StateFile(tmp_path / "s.json", 60)
    st.write("RUNNING", {}, 1, job="999")
    payload = json.loads((tmp_path / "s.json").read_text())
    assert payload["job"] == "999"
    assert "jobs" not in payload, "'jobs' is the name the consumer does NOT read"


def test_check_watcher_state_accepts_what_we_write(tmp_path):
    """End-to-end against the real consumer, not against our idea of it."""
    st = mes.StateFile(tmp_path / "s.json", 60, "arms")
    st.write("RUNNING", {"COMPLETED": 0, "FAILED": 0, "PENDING": 3}, 3, job="")
    r = subprocess.run([PY, str(REPO / "tools" / "check_watcher_state.py"),
                        str(tmp_path / "s.json")], capture_output=True, text=True)
    assert r.returncode == 0, f"consumer rejected a fresh RUNNING state: {r.stdout}{r.stderr}"
    assert "ALIVE" in r.stdout, r.stdout


def test_stale_heartbeat_is_caught_by_the_consumer(tmp_path):
    """NEGATIVE CONTROL for the whole mechanism: backdate it and the reader must fail."""
    p = tmp_path / "s.json"
    st = mes.StateFile(p, 60)
    st.write("RUNNING", {"PENDING": 3}, 3)
    d = json.loads(p.read_text())
    d["epoch"] = int(time.time()) - 10 * 60      # 10 min on a 60 s interval
    p.write_text(json.dumps(d))
    r = subprocess.run([PY, str(REPO / "tools" / "check_watcher_state.py"), str(p)],
                       capture_output=True, text=True)
    assert r.returncode != 0, "a 10-min-old heartbeat on a 60 s interval must not pass"
    assert "STALE" in r.stdout, r.stdout


# ------------------------------------------------------------------- singleton
def test_second_instance_on_the_same_state_file_refuses(tmp_path, monkeypatch):
    p = tmp_path / "s.json"
    mes.StateFile(p, 60)                      # first claim, by THIS process
    # A second StateFile in-process is the same pid, which is allowed (re-entry).
    # Simulate a DIFFERENT live process by writing a pid whose cmdline names the path:
    # our own pid qualifies only if we pretend to be someone else.
    real_pid = os.getpid()
    token = mes.StateFile._starttime(real_pid)
    (tmp_path / "s.json.pid").write_text(f"{real_pid} {token}\n")
    monkeypatch.setattr(mes.os, "getpid", lambda: real_pid + 1)
    with pytest.raises(SystemExit) as exc:
        mes.StateFile(p, 60)
    assert "REFUSING TO START" in str(exc.value)
    assert str(real_pid) in str(exc.value), "the refusal must name the pid to stop"


def test_a_dead_owner_does_not_block_a_restart(tmp_path):
    """The guard must not be so strict that a crashed watcher wedges the path.

    A pid file outlives its process, so refusing on its mere existence would mean every
    SIGKILLed watcher needs manual cleanup -- and a guard people must defeat routinely
    is a guard they defeat when it matters.
    """
    p = tmp_path / "s.json"
    (tmp_path / "s.json.pid").write_text("999999999\n")   # not a live pid
    st = mes.StateFile(p, 60)                              # must not raise
    st.write("RUNNING", {}, 1)
    assert p.exists()


def test_recycled_pid_is_not_mistaken_for_the_owner(tmp_path, monkeypatch):
    """Liveness alone is not ownership: pid 1 is alive and is not our watcher.

    Without the start-time token this test is what fails -- and it fails CLOSED, wedging
    the path behind a guard the operator can only defeat by deleting a file.
    """
    p = tmp_path / "s.json"
    (tmp_path / "s.json.pid").write_text("1 999999999999\n")   # live pid, wrong instance
    monkeypatch.setattr(mes.os, "getpid", lambda: 424242)
    st = mes.StateFile(p, 60)      # pid 1 is live but is not the instance that claimed
    st.write("RUNNING", {}, 1)
    assert p.exists()


# ------------------------------------------------------- terminal classification
def test_full_account_is_ENDED(tmp_path):
    st = mes.StateFile(tmp_path / "s.json", 60)
    assert st.terminal({"COMPLETED": 2, "FAILED": 1}, 3) == "ENDED"


def test_partial_account_is_ENDED_UNACCOUNTED(tmp_path):
    """complete+failed != total is not a finish, and must not be published as one."""
    st = mes.StateFile(tmp_path / "s.json", 60)
    assert st.terminal({"COMPLETED": 2, "FAILED": 0}, 3) == "ENDED_UNACCOUNTED"
    r = subprocess.run([PY, str(REPO / "tools" / "check_watcher_state.py"),
                        str(tmp_path / "s.json")], capture_output=True, text=True)
    assert r.returncode != 0, "an unaccounted finish must not exit 0"


def test_died_stamp_is_written(tmp_path):
    p = tmp_path / "s.json"
    st = mes.StateFile(p, 60)
    st.died({"COMPLETED": 1}, 3)
    assert json.loads(p.read_text())["status"] == "DIED"


# ------------------------------------------------------------------- CLI wiring
def test_state_file_without_watch_is_refused(tmp_path):
    """A one-shot stamp would read as a live watcher forever -- the file IS the signal."""
    r = subprocess.run([PY, str(REPO / "tools" / "model_ensemble_status.py"),
                        "--model", "ecosim", "--run-root", str(tmp_path),
                        "--state-file", str(tmp_path / "s.json")],
                       capture_output=True, text=True)
    assert r.returncode == 1, r.stdout + r.stderr
    assert "requires --watch" in r.stderr, r.stderr
