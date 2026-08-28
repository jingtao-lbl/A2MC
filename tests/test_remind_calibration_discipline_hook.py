"""The calibration reminder must catch the bookkeeping the agent FORGOT, not just the writes it made.

Trigger A watches state writes. On its own that is blind to the failure that matters: an agent that
forgets to update the state never triggers a hook keyed on state writes. Trigger B therefore watches
the WORK (a `phase{N}` log, a `phase_results/` artifact) and asks whether the state followed.

Noise is the failure mode here in a way it is not for setup: calibration is the main working loop, so
these tests assert silence at least as hard as they assert firing.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "remind-calibration-discipline.py"


def clone(tmp: Path, *, state_date="2026-08-18", work_stem=None, state=True) -> Path:
    (tmp / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
    (tmp / "tools").mkdir(exist_ok=True)
    shutil.copy(HOOK, tmp / ".claude" / "hooks")
    shutil.copy(REPO / "tools" / "check_workflow_state_offline.py", tmp / "tools")
    # the validator loads this sibling directly by file path, so a clone without it crashes
    # on import -- which the hook must (and does) treat as "our tool broke", not "your state
    # is invalid". Copy it so trigger A is exercised for real.
    shutil.copy(REPO / "tools" / "workflow_state_offline.py", tmp / "tools")
    logs = tmp / "use_cases" / "C" / "memory" / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    if state:
        (tmp / "use_cases" / "C" / "memory" / "workflow_state_offline_r01.json").write_text(
            json.dumps({"updated_at": state_date, "current_phase": "diagnosis"}))
    if work_stem:
        (logs / f"{work_stem}_phase3_diagnosis_r01_c00_x.md").write_text("# log\n")
    return tmp


def fire(root: Path, path: str, tool="Write", ok=True) -> str:
    payload = {"tool_name": tool, "tool_input": {"file_path": path},
               "tool_response": {"success": ok}}
    r = subprocess.run([sys.executable, str(root / ".claude" / "hooks" / "remind-calibration-discipline.py")],
                       input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


LOG = "use_cases/C/memory/logs/20260819a_phase3_diagnosis_r01_c00_x.md"


# ------------------------------------------------- trigger B: the forgotten update
def test_fires_when_phase_work_landed_and_state_did_not_follow(tmp_path):
    """The case a state-write trigger can never see."""
    out = fire(clone(tmp_path, state_date="2026-08-10", work_stem="20260819a"), LOG)
    assert "STATE NOT UPDATED" in out, out
    assert "20260819" in out and "2026-08-10" in out, "must show both dates: " + out
    assert "check_workflow_state_offline.py" in out, out


def test_silent_when_the_state_is_newer_than_the_work(tmp_path):
    assert fire(clone(tmp_path, state_date="2026-08-20", work_stem="20260819a"), LOG) == ""


def test_silent_when_there_is_no_offline_campaign(tmp_path):
    """No state file at all is not a violation — it is a case that does not run the offline loop."""
    assert fire(clone(tmp_path, state=False, work_stem="20260819a"), LOG) == ""


def test_repeat_is_suppressed(tmp_path):
    root = clone(tmp_path, state_date="2026-08-10", work_stem="20260819a")
    assert fire(root, LOG) != ""
    assert fire(root, LOG) == "", "must fire on the condition, not on every write"


def test_a_backwards_phase_move_is_not_treated_as_staleness(tmp_path):
    """A Phase-6 -> Phase-0 redesign moves the phase BACKWARDS, so comparing the log's phase to
    current_phase would false-positive on a correct state. Measured on EcoSIM_BioCON R3, which is
    exactly that: newest log says phase6, state says design, and the state is right."""
    root = clone(tmp_path, state_date="2026-08-20")
    logs = root / "use_cases" / "C" / "memory" / "logs"
    (logs / "20260819a_phase6_refinement_r01_c00_x.md").write_text("# log\n")
    out = fire(root, "use_cases/C/memory/logs/20260819a_phase6_refinement_r01_c00_x.md")
    assert out == "", "state is newer, so a backwards phase move must stay silent: " + out


# ------------------------------------------------- trigger A: the state that was written
def test_fires_when_a_written_state_is_invalid(tmp_path):
    root = clone(tmp_path)
    sf = root / "use_cases" / "C" / "memory" / "workflow_state_offline_r01.json"
    sf.write_text("{ not valid json")
    out = fire(root, "use_cases/C/memory/workflow_state_offline_r01.json")
    assert "OFFLINE STATE INVALID" in out, out


def test_silent_when_a_written_state_is_valid(tmp_path):
    """Uses the repo's real state, which the validator passes, so a green run stays quiet.

    The state's `round_close.report_path` is materialised in the clone too. Since 2026-08-25 the
    validator ERRORS on a round-close pointer that does not resolve -- a pointer to nothing is
    worse than no pointer, because it READS as evidence -- and copying a state without the
    artifact it cites makes the clone an incomplete copy of the case rather than a valid one.
    The fixture, not the check, was wrong: this test asserts that a VALID state is quiet, and a
    state whose cited report is absent is not valid.
    """
    root = clone(tmp_path)
    real = REPO / "use_cases" / "EcoSIM_BioCON" / "memory" / "workflow_state_offline_r03.json"
    dst = root / "use_cases" / "C" / "memory" / "workflow_state_offline_r01.json"
    shutil.copy(real, dst)
    rp = (json.loads(real.read_text()).get("round_close") or {}).get("report_path")
    if rp:
        cited = root / rp
        cited.parent.mkdir(parents=True, exist_ok=True)
        cited.write_text("# stand-in for the cited round report\n")
    assert fire(root, "use_cases/C/memory/workflow_state_offline_r01.json") == ""


# ------------------------------------------------- it stays out of the way
def test_silent_on_an_unrelated_write(tmp_path):
    assert fire(clone(tmp_path, state_date="2026-08-10", work_stem="20260819a"),
                "docs/README.md") == ""


def test_silent_when_the_write_failed(tmp_path):
    assert fire(clone(tmp_path, state_date="2026-08-10", work_stem="20260819a"), LOG, ok=False) == ""


def test_unparseable_payload_is_silent(tmp_path):
    root = clone(tmp_path)
    r = subprocess.run([sys.executable, str(root / ".claude" / "hooks" / "remind-calibration-discipline.py")],
                       input="not json", capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_registered_under_a_matcher_covering_the_write_tools():
    d = json.loads((REPO / ".claude" / "settings.json").read_text())
    entries = [m for m in d["hooks"]["PostToolUse"]
               if any("remind-calibration-discipline" in c.get("command", "") for c in m.get("hooks", []))]
    assert entries, "hook is not registered on PostToolUse"
    for tool in ("Write", "Edit"):
        assert tool in entries[0].get("matcher", ""), entries[0].get("matcher")


def test_a_crashed_validator_is_not_reported_as_an_invalid_state(tmp_path):
    """Crying wolf about the user's data because our own tool broke is worse than staying quiet.
    Removing the validator's sibling dependency makes it crash on import; the hook must be silent."""
    root = clone(tmp_path)
    (root / "tools" / "workflow_state_offline.py").unlink()
    (root / "use_cases" / "C" / "memory" / "workflow_state_offline_r01.json").write_text("{ bad")
    assert fire(root, "use_cases/C/memory/workflow_state_offline_r01.json") == ""
