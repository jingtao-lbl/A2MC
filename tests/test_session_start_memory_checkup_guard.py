"""The SessionStart memory-checkup reminder must stay silent in a clone that cannot act on it.

The checkup skill is visibility: private and .claude_memory/ is excluded from both sync legs, so a
public clone has neither. Before 2026-09-23 the hook told every public clone, at every session, to
run a skill it does not have (audit 20260923b, finding F39).

Author: Jing Tao with Claude.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HOOK = REPO / ".claude" / "hooks" / "session-start.py"


def _hook():
    spec = importlib.util.spec_from_file_location("_session_start", HOOK)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_a_public_clone_without_the_bucket_gets_no_checkup_line(tmp_path):
    lines = []
    _hook().memory_checkup_due(str(tmp_path), lines)
    assert lines == []


def test_a_bucket_without_the_private_skill_gets_no_checkup_line(tmp_path):
    (tmp_path / ".claude_memory").mkdir()
    lines = []
    _hook().memory_checkup_due(str(tmp_path), lines)
    assert lines == []


def test_the_dev_clone_with_both_still_gets_the_reminder(tmp_path):
    (tmp_path / ".claude_memory").mkdir()
    (tmp_path / ".claude" / "skills" / "memory-checkup").mkdir(parents=True)
    lines = []
    _hook().memory_checkup_due(str(tmp_path), lines)
    assert lines and "memory-checkup" in lines[0], lines
