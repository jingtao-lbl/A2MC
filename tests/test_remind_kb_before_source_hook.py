"""The KB-first reminder fires when model source is read before the knowledge base was queried.

visibility: public

Run against the REAL hook in the REAL repo (it has cases with calibration state) with a fresh session
id per case, since the hook speaks once per session. The onboarding case repoints CLAUDE_PROJECT_DIR
at an empty tree, which is what a clone with no calibrated case looks like. Account:
`memory/dev_logs_adapterkit/20261015h_Phase_3_And_4_Query_The_Knowledge_Base_Before_The_Source.md`.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "remind-kb-before-source.py"
SRC = "~/EcoSIM-latest/f90src/Microbial_bgc/Box_Micmodel/MicBGCMod.F90"


def _say(tool, tool_input, session=None, root=REPO):
    payload = {"tool_name": tool, "session_id": session or "test-" + uuid.uuid4().hex, "tool_input": tool_input}
    r = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                       timeout=30, env={"CLAUDE_PROJECT_DIR": str(root), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


def test_reading_model_source_first_is_caught():
    said = _say("Read", {"file_path": SRC})
    assert "KB FIRST" in said and "kb_network.py" in said and "MicBGCMod.F90" in said, said


def test_grepping_model_source_first_is_caught():
    said = _say("Bash", {"command": "grep -n RMOM %s | head" % SRC})
    assert "KB FIRST" in said, said


def test_once_per_session():
    s = "test-" + uuid.uuid4().hex
    assert _say("Read", {"file_path": SRC}, s)
    assert _say("Read", {"file_path": SRC.replace("MicBGCMod", "NitroPars")}, s) == ""


def test_a_session_that_queried_the_kb_first_is_not_reminded():
    s = "test-" + uuid.uuid4().hex
    assert _say("Bash", {"command": "~/a2mc_env/bin/python tools/kb_network.py --model ecosim --params RMOM "
                                    "--out-dir x"}, s) == ""
    assert _say("Read", {"file_path": SRC}, s) == ""


def test_CONTROL_repo_files_are_not_model_source():
    for f in (REPO / "tools" / "kb_network.py", REPO / "README.md"):
        assert _say("Read", {"file_path": str(f)}) == "", f
    assert _say("Bash", {"command": "sed -n 1,20p tools/kb_network.py"}) == ""


def test_CONTROL_a_non_source_file_in_the_model_checkout_is_not_source():
    """The model checkout holds documents and build files too; reading those is not the shortcut."""
    for f in ("README.md", "CMakeLists.txt", "python_tools/plot.py"):
        assert _say("Read", {"file_path": SRC.rsplit("/f90src/", 1)[0] + "/" + f}) == "", f


def test_CONTROL_silent_while_onboarding(tmp_path):
    """No case with calibration state: the knowledge base may not exist yet, and source is correct."""
    assert _say("Read", {"file_path": SRC}, root=tmp_path) == ""


def test_a_broken_payload_never_breaks_the_tool_call():
    r = subprocess.run(["python3", str(HOOK)], input="not json", capture_output=True, text=True, timeout=30,
                       env={"CLAUDE_PROJECT_DIR": str(REPO), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0 and r.stdout.strip() == ""
