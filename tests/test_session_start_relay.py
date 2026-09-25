"""The SessionStart snapshot must tell the AGENT to relay what the USER needs to know.

Claude Code gives a SessionStart hook's output to the model, not to the person at the terminal:
plain stdout, `additionalContext` and `systemMessage` alike are added to Claude's context, and the
user sees at most a collapsed hook line (code.claude.com/docs/en/hooks, SessionStart "Decision
control"; this repo's own session transcript stores the snapshot as `hook_success` and
`hook_additional_context` attachments). So until 2026-09-23 "THIS CLONE IS NOT FULLY SET UP"
reached nobody it was about. The hook now collects the user's business in a `relay` list and puts it
first, under one instruction to say it.

Each relay source is tested with a CONTROL that must stay silent, because a relay that fires on
everything is noise a user learns to ignore -- the resource control is the real case: a machine
without `myquota` prints "QUOTA UNREADABLE [absent]" at every session, and that is not "disk low".

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "session-start.py"


def _hook():
    spec = importlib.util.spec_from_file_location("_session_start_relay", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def _stub(root: Path, name: str, body: str) -> None:
    (root / "tools").mkdir(parents=True, exist_ok=True)
    (root / "tools" / name).write_text(body)


_CLONE_BAD = ('FAIL = "FAIL"\n'
              'def clone_rows():\n'
              '    return [(FAIL, "commit hooks active", "core.hooksPath unset"),\n'
              '            ("PASS", "author name", "Jing")]\n')
_CLONE_OK = ('FAIL = "FAIL"\n'
             'def clone_rows():\n'
             '    return [("PASS", "commit hooks active", "on")]\n')


# ---- render(): the header exists only when there is something to relay ----------------------------
def test_render_puts_the_relay_first_under_one_instruction():
    m = _hook()
    out = m.render(["Branch: x"], ["A thing the user must know."])
    head, first, blank = out.splitlines()[1:4]
    assert head == m.RELAY_HEADER
    assert first == "  - A thing the user must know."
    assert blank == "" and "Branch: x" in out


def test_CONTROL_render_with_nothing_to_relay_has_no_header():
    m = _hook()
    out = m.render(["Branch: x"], [])
    assert "TELL THE USER" not in out
    assert out.splitlines()[1] == "Branch: x"


# ---- the clone check ------------------------------------------------------------------------------
def test_an_unfinished_clone_is_relayed(tmp_path):
    _stub(tmp_path, "check_clone_setup.py", _CLONE_BAD)
    lines, relay = [], []
    _hook().clone_setup(str(tmp_path), lines, relay)
    assert len(relay) == 1 and "not fully set up" in relay[0], relay
    assert "commit hooks active" in relay[0] and "a2mc-init" in relay[0], relay


def test_CONTROL_a_finished_clone_relays_nothing(tmp_path):
    _stub(tmp_path, "check_clone_setup.py", _CLONE_OK)
    lines, relay = [], []
    _hook().clone_setup(str(tmp_path), lines, relay)
    assert relay == [] and lines == []


# ---- the setup stage ------------------------------------------------------------------------------
def test_an_unfinished_setup_stage_is_relayed(tmp_path):
    _stub(tmp_path, "check_stage_ready.py",
          'def detect_stage():\n    return 3, "a case is in setup"\n')
    lines, relay = [], []
    _hook().setup_stage(str(tmp_path), lines, relay)
    assert len(relay) == 1 and "stage 3" in relay[0] and "onboard-case" in relay[0], relay


def test_CONTROL_a_finished_setup_relays_nothing(tmp_path):
    _stub(tmp_path, "check_stage_ready.py", 'def detect_stage():\n    return 4, ""\n')
    lines, relay = [], []
    _hook().setup_stage(str(tmp_path), lines, relay)
    assert relay == [] and lines == []


# ---- disk and allocation headroom -----------------------------------------------------------------
def test_a_crossed_quota_threshold_is_relayed(tmp_path):
    _stub(tmp_path, "check_resources.py",
          'print("!! home           39.07 /     40.00 GiB    97.7% used        0.93 GiB free")\n')
    lines, relay = [], []
    _hook().resource_headroom(str(tmp_path), lines, relay)
    assert len(relay) == 1 and "home" in relay[0] and "97.7% used" in relay[0], relay


def test_CONTROL_an_unreadable_quota_is_not_called_low_disk(tmp_path):
    """A laptop has no `myquota`. That is not a disk problem and must not be relayed as one."""
    _stub(tmp_path, "check_resources.py",
          'print("  QUOTA UNREADABLE [absent]: myquota is not on PATH")\n'
          'print("  ALLOCATION UNREADABLE [absent]: iris is not on PATH")\n')
    lines, relay = [], []
    _hook().resource_headroom(str(tmp_path), lines, relay)
    assert relay == [], relay
    assert any("UNREADABLE" in l for l in lines), "the agent still sees it in the snapshot"


# ---- under the interpreter Claude Code actually uses ---------------------------------------------
def _old_python():
    """The system python3 when it is older than 3.7 (Perlmutter: 3.6.15), else None."""
    p = shutil.which("python3", path="/usr/bin:/bin")
    if not p:
        return None
    v = subprocess.run([p, "-c", "import sys; print(sys.version_info[:2] < (3, 7))"],
                       stdout=subprocess.PIPE, universal_newlines=True)
    return p if v.stdout.strip() == "True" else None


@pytest.mark.skipif(_old_python() is None, reason="no system python3 older than 3.7 here")
def test_the_relay_works_under_the_system_python3_the_hook_runs_with(tmp_path):
    """Claude Code runs the hook as `python3`, which on Perlmutter is 3.6. A relay that only
    works under a2mc_env would be the same silent failure it exists to end."""
    _stub(tmp_path, "check_clone_setup.py", _CLONE_BAD)
    prog = (
        "import importlib.util, json\n"
        f"s = importlib.util.spec_from_file_location('h', {str(HOOK)!r})\n"
        "m = importlib.util.module_from_spec(s); s.loader.exec_module(m)\n"
        "lines, relay = [], []\n"
        f"m.clone_setup({str(tmp_path)!r}, lines, relay)\n"
        "print(json.dumps(m.render(lines, relay)))\n")
    r = subprocess.run([_old_python(), "-c", prog], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True, timeout=60)
    assert r.returncode == 0, r.stderr
    out = json.loads(r.stdout)
    assert "TELL THE USER" in out and "not fully set up" in out, out
