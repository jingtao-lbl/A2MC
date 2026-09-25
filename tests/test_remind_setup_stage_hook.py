"""The setup-stage reminder must fire on a stage TRANSITION and be quiet otherwise.

`SessionStart` answers "which stage" once. The stage advances during the session, and the moment it
advances goes unobserved -- the same failure `remind-arm-monitoring.py` exists for. This hook
observes it, which means two properties have to hold together and are asserted separately:

1. **It fires**, naming the skill and the SPECIFIC outstanding items (a generic nudge gets
   acknowledged and ignored).
2. **It stays quiet** on previews, failures, unrelated writes, a configured clone, and on repeats
   within one stage. A reminder that fires on every write trains the reader to skip it, which is the
   same outcome as not having it.

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "remind-setup-stage.py"


def clone(tmp: Path, *, model=True, case=False, offline=False) -> Path:
    """A synthetic clone carrying its own copy of the hook + the tool it reuses."""
    (tmp / ".claude" / "hooks").mkdir(parents=True, exist_ok=True)
    (tmp / "tools").mkdir(exist_ok=True)
    shutil.copy(HOOK, tmp / ".claude" / "hooks")
    shutil.copy(REPO / "tools" / "check_stage_ready.py", tmp / "tools")
    # stage2_rows() loads the knowledge-store resolver by file path from tools/
    shutil.copy(REPO / "tools" / "model_knowledge_store.py", tmp / "tools")
    (tmp / "use_cases" / "TEMPLATE").mkdir(parents=True, exist_ok=True)
    (tmp / "rag").mkdir(exist_ok=True)
    (tmp / "rag" / "milestones.json").write_text('{"milestones":{}}')
    if model:
        d = tmp / "models" / "ecosim"
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("register_model(object())")
    if case:
        c = tmp / "use_cases" / "EcoSIM_BioCON"
        (c / "config").mkdir(parents=True, exist_ok=True)
        (c / "memory").mkdir(exist_ok=True)
        if offline:
            (c / "memory" / "workflow_state_offline_r01.json").write_text("{}")
    return tmp


def fire(root: Path, payload: dict) -> str:
    r = subprocess.run([sys.executable, str(root / ".claude" / "hooks" / "remind-setup-stage.py")],
                       input=json.dumps(payload), capture_output=True, text=True, timeout=60)
    if not r.stdout.strip():
        return ""
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"]


WRITE_CFG = {"tool_name": "Write",
             "tool_input": {"file_path": "use_cases/EcoSIM_Foo/config/site.sh"},
             "tool_response": {"success": True}}
RUN_SCAFFOLD = {"tool_name": "Bash",
                "tool_input": {"command": "python3 tools/create_use_case.py --model ecosim --case Foo"},
                "tool_response": {"success": True}}


# ------------------------------------------------------------------ it fires
def test_fires_naming_the_next_skill_at_stage1(tmp_path):
    """A wired clone with no case is sent onward. Until 20260923b the stage-1 'gap' was
    A2MC_MODEL_PATH, which a non-CIME user sets only in a case's site config, so it could never
    clear (audit F31); the next skill is what the reader needs."""
    out = fire(clone(tmp_path), WRITE_CFG)
    assert "SETUP STAGE 1" in out and "onboard-case" in out, out
    assert "setup-discipline" in out and "check_stage_ready.py" in out, out


def test_fires_naming_the_specific_gaps_and_whose_they_are(tmp_path):
    """At stage 3 the gaps are the case's own, labelled with the case (F108), and an unedited
    template copy is a gap rather than 'nothing outstanding' (F32)."""
    root = clone(tmp_path, case=True)
    cfg = root / "use_cases" / "EcoSIM_BioCON" / "config" / "site.sh"
    cfg.write_text('export A2MC_MODEL_PATH="<PATH_TO_ECOSIM_CHECKOUT>"\n')
    out = fire(root, WRITE_CFG)
    assert "SETUP STAGE 3" in out and "outstanding" in out, out
    assert "case EcoSIM_BioCON" in out and "template placeholders" in out, out


def test_an_onboard_model_action_audits_that_model_not_stage1(tmp_path):
    """Stage 2 is never auto-detected on a line that ships registered adapters, so mid-onboarding
    the hook used to announce stage 1 / a2mc-init (F33)."""
    p = {"tool_name": "Bash", "tool_input": {"command": "python scripts/build_ecosim_rag.py --rebuild"},
         "tool_response": {"success": True}}
    out = fire(clone(tmp_path), p)
    assert "SETUP STAGE 2" in out and "model ecosim" in out, out


def test_a_scaffold_command_also_crosses_the_boundary(tmp_path):
    assert "SETUP STAGE" in fire(clone(tmp_path), RUN_SCAFFOLD)


# ------------------------------------------------------------------ it stays quiet
def test_repeat_within_one_stage_is_suppressed(tmp_path):
    """Fires on the TRANSITION, not the state. Re-emitting on every write is how it gets muted."""
    root = clone(tmp_path)
    assert fire(root, WRITE_CFG) != ""
    assert fire(root, WRITE_CFG) == "", "second identical call must be silent"


def test_silent_on_a_preview(tmp_path):
    p = {**RUN_SCAFFOLD, "tool_input": {"command": "python3 tools/create_use_case.py --dry-run"}}
    assert fire(clone(tmp_path), p) == ""


def test_silent_when_the_action_failed(tmp_path):
    p = {**RUN_SCAFFOLD, "tool_response": {"success": False}}
    assert fire(clone(tmp_path), p) == ""


def test_silent_on_an_unrelated_write(tmp_path):
    p = {"tool_name": "Write", "tool_input": {"file_path": "docs/README.md"},
         "tool_response": {"success": True}}
    assert fire(clone(tmp_path), p) == ""


def test_silent_on_a_configured_clone(tmp_path):
    """Stage 4 = setup done. A normal session must pay nothing."""
    root = clone(tmp_path, case=True, offline=True)
    assert fire(root, WRITE_CFG) == ""


def test_never_raises_when_the_tool_is_missing(tmp_path):
    """A hook that raises costs every session, not just the one it meant to help."""
    root = clone(tmp_path)
    (root / "tools" / "check_stage_ready.py").unlink()
    assert fire(root, WRITE_CFG) == ""


def test_unparseable_payload_is_silent(tmp_path):
    root = clone(tmp_path)
    r = subprocess.run([sys.executable, str(root / ".claude" / "hooks" / "remind-setup-stage.py")],
                       input="not json", capture_output=True, text=True, timeout=60)
    assert r.returncode == 0 and r.stdout.strip() == ""


# ------------------------------------------------------------------ registration
def test_registered_under_a_matcher_that_covers_its_triggers():
    """It inspects Write/Edit paths as well as Bash commands. Registering it under the existing
    Bash-only matcher would silently disable every path trigger -- caught exactly that way."""
    d = json.loads((REPO / ".claude" / "settings.json").read_text())
    entries = [m for m in d["hooks"]["PostToolUse"]
               if any("remind-setup-stage" in c.get("command", "") for c in m.get("hooks", []))]
    assert entries, "hook is not registered on PostToolUse"
    matcher = entries[0].get("matcher", "")
    for tool in ("Bash", "Write", "Edit"):
        assert tool in matcher, f"matcher {matcher!r} does not cover {tool}"
