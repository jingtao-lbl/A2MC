"""The Bash-time reminder names the per-model knowledge-base tools table when a KB tool is about to run.

visibility: public

Each case runs the REAL hook against the REAL repo with a fresh session id, because the hook speaks
once per tool per session (`feedback_run_the_tool_where_it_runs`). The one exception repoints
CLAUDE_PROJECT_DIR at an empty tree, which is exactly the released case: the hook ships, the memory
bucket does not. Account: `memory/dev_logs_adapterkit/20261015g_A_Knowledge_Base_Command_Names_Its_Step_For_Every_Model.md`.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "remind-per-model-kb-tools.py"
MEM = REPO / ".claude_memory" / "reference_per_model_kb_build_tools.md"


def _say(cmd: str, session: str | None = None, root: Path = REPO) -> str:
    payload = {"tool_name": "Bash", "session_id": session or "test-" + uuid.uuid4().hex,
               "tool_input": {"command": cmd}}
    r = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                       timeout=30, env={"CLAUDE_PROJECT_DIR": str(root), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


def test_running_the_fates_builder_shows_every_models_builder():
    said = _say("~/a2mc_env/bin/python scripts/build_rag_index.py --rebuild --test")
    assert "reference_per_model_kb_build_tools" in said, said
    assert "build_ecosim_rag.py" in said and "build_pflotran_rag.py" in said, said


def test_running_a_fates_checker_shows_the_adapter_checker():
    said = _say("python tools/check_rag_queries.py --profile api-43-1")
    assert "check_ecosim_rag_queries.py --model pflotran" in said, said


def test_the_row_is_read_from_the_memory_not_restated():
    """Change the table and the hook's output changes with it: the row printed is the memory's row."""
    row = next(l for l in MEM.read_text().splitlines() if "`yaml_wiki_validator.py`" in l)
    step = row.strip().strip("|").split("|")[0].strip()
    said = _say("$PY tools/yaml_wiki_validator.py --model ecosim --yaml x")
    assert said.splitlines()[1].strip().startswith(step + " --"), said


def test_once_per_tool_per_session():
    s = "test-" + uuid.uuid4().hex
    assert _say("python3 tools/kb_patch.py plan --profile p --to c", s)
    assert _say("python3 tools/kb_patch.py apply --profile p --to c", s) == ""
    assert _say("python3 tools/validate_wiki_vs_source.py --model ecosim --wiki w --source s", s)


def test_CONTROL_reading_a_tool_is_not_running_it():
    for cmd in ("sed -n 1,40p tools/kb_patch.py", "git grep -n build_rag_index -- scripts",
                "cat scripts/build_ecosim_rag.py | head", "python tools/check_stage_ready.py --model ecosim",
                "python -m pytest tests/test_kb_patch_and_profile.py -q"):
        assert _say(cmd) == "", cmd


def test_CONTROL_a_non_bash_payload_is_ignored():
    payload = {"tool_name": "Write", "session_id": "x", "tool_input": {"command": "python scripts/build_rag_index.py"}}
    r = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True,
                       timeout=30, env={"CLAUDE_PROJECT_DIR": str(REPO), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0 and r.stdout.strip() == ""


def test_without_the_memory_the_rule_still_travels(tmp_path):
    """The hook ships and the bucket does not: a released tree gets the rule and a note, no row."""
    said = _say("python scripts/build_rag_index.py --rebuild", root=tmp_path)
    assert "DIFFERENT tool per model" in said and "do not ship with A2MC" in said, said
    assert "build_ecosim_rag.py" not in said, said


def test_a_broken_payload_never_breaks_the_command():
    r = subprocess.run(["python3", str(HOOK)], input="not json", capture_output=True, text=True, timeout=30,
                       env={"CLAUDE_PROJECT_DIR": str(REPO), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0 and r.stdout.strip() == ""
