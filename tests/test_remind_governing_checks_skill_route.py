"""The edit-time reminder routes a SKILL.md edit to the skill that governs it.

visibility: public

`.claude/hooks/remind-governing-checks.py` speaks when a file is about to be written. For a skill it
must say WHICH procedure applies: an existing skill is a contract, changed through `refine-skill`
(diff shown, approval, whole-file re-read); a new one is registered through `add-skill`. It fires
once per path per session, so every case below uses a fresh session id.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import json
import subprocess
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "remind-governing-checks.py"


def _say(rel: str) -> str:
    payload = {"tool_name": "Write", "session_id": "test-" + uuid.uuid4().hex,
               "tool_input": {"file_path": str(REPO / rel)}}
    r = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), capture_output=True,
                       text=True, timeout=60, env={"CLAUDE_PROJECT_DIR": str(REPO), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)["hookSpecificOutput"]["additionalContext"] if r.stdout.strip() else ""


def test_an_existing_skill_is_routed_to_refine_skill():
    said = _say(".claude/skills/log/SKILL.md")
    assert "`refine-skill`" in said and "WHOLE file" in said, said
    assert "`add-skill`" not in said, said


def test_a_new_skill_is_routed_to_add_skill():
    said = _say(".claude/skills/no-such-skill-%s/SKILL.md" % uuid.uuid4().hex[:8])
    assert "`add-skill`" in said, said
    assert "`refine-skill`" not in said, said


def test_a_non_skill_file_is_told_neither():
    said = _say("tools/check_clone_setup.py")
    assert "refine-skill" not in said and "add-skill" not in said, said
