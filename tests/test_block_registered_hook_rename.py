"""Moving or deleting a hook that .claude/settings.json registers is refused at the Bash call.

visibility: public

The real hook against the real settings.json, plus a synthetic tree to prove the registered names are
READ from settings.json rather than listed in the hook. Account:
`memory/dev_logs_adapterkit/20261015i_A_Registered_Hook_Keeps_Its_Name_And_Phase_6_Queries_The_KB.md`.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
HOOK = REPO / ".claude" / "hooks" / "block-registered-hook-rename.py"


def _decide(cmd: str, root: Path = REPO):
    r = subprocess.run(["python3", str(HOOK)], input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}),
                       capture_output=True, text=True, timeout=30,
                       env={"CLAUDE_PROJECT_DIR": str(root), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0, r.stderr
    if not r.stdout.strip():
        return None
    return json.loads(r.stdout)["hookSpecificOutput"]


def test_moving_a_registered_bash_hook_is_refused():
    d = _decide("git mv .claude/hooks/remind-pipeline-exit-status.py .claude/hooks/renamed.py")
    assert d and d["permissionDecision"] == "deny", d
    assert "remind-pipeline-exit-status.py" in d["permissionDecisionReason"]
    assert "feedback_registered_hook_filename_is_an_interface" in d["permissionDecisionReason"]


def test_deleting_a_registered_hook_is_refused():
    for cmd in ("rm .claude/hooks/block-ai-attribution.py", "git rm -q .claude/hooks/remind-governing-checks.py",
                "cd /x && mv .claude/hooks/session-start.py /tmp/y"):
        d = _decide(cmd)
        assert d and d["permissionDecision"] == "deny", cmd


def test_CONTROL_an_unregistered_hook_moves_freely():
    assert _decide("git mv .claude/hooks/a_draft_hook.py .claude/hooks/a_better_name.py") is None
    # a name that shares a prefix with registered hooks (remind-*, block-*) is still a different file
    assert _decide("git mv .claude/hooks/remind-draft.py .claude/hooks/remind-draft-2.py") is None


def test_CONTROL_reading_or_editing_a_registered_hook_is_not_moving_it():
    for cmd in ("cat .claude/hooks/remind-pipeline-exit-status.py", "git diff .claude/hooks/session-start.py",
                "python3 .claude/hooks/remind-per-model-kb-tools.py < x.json", "git mv .claude_memory/a.md .claude_memory/b.md"):
        assert _decide(cmd) is None, cmd


def test_CONTROL_a_commit_whose_message_says_mv_and_rm_is_not_a_move():
    """Regression: a `git add` of registered hooks, then a heredoc message mentioning mv and rm, was refused."""
    cmd = ("git add .claude/hooks/remind-governing-checks.py .claude/hooks/remind-kb-before-source.py && "
           "git commit -F - <<'EOF'\nrefuses mv, git mv,\n  rm and git rm on a registered hook\nEOF")
    assert _decide(cmd) is None


def test_a_move_split_over_a_line_continuation_is_still_caught():
    d = _decide("git mv .claude/hooks/session-start.py \\\n    .claude/hooks/session-begin.py")
    assert d and d["permissionDecision"] == "deny", d


def test_the_registered_names_are_read_from_settings(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR}/.claude/hooks/only_this_one.py\""}]}]}}))
    assert _decide("mv .claude/hooks/only_this_one.py .claude/hooks/z.py", tmp_path)["permissionDecision"] == "deny"
    assert _decide("mv .claude/hooks/remind-pipeline-exit-status.py z.py", tmp_path) is None


def test_no_settings_and_a_broken_payload_never_block(tmp_path):
    assert _decide("git mv .claude/hooks/x.py .claude/hooks/y.py", tmp_path) is None
    r = subprocess.run(["python3", str(HOOK)], input="not json", capture_output=True, text=True, timeout=30,
                       env={"CLAUDE_PROJECT_DIR": str(REPO), "PATH": "/usr/bin:/bin"})
    assert r.returncode == 0 and r.stdout.strip() == ""
