""".claude/hooks/remind-kg-html.py: after a graph changes, say so if its HTML view is stale.

visibility: public

The hook delegates the comparison to tools/check_kg_html_current.py (tested on its own); these tests
pin the hook's half: when it looks, that it stays silent on a current page, and that it speaks when
the checker reports a stale one. The stale case uses a stand-in interpreter that reports a stale page.
It runs under the system python3, as the harness runs it.
"""
import json
import os
import stat
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / ".claude" / "hooks" / "remind-kg-html.py"


def run(payload, env_extra=None):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(ROOT), **(env_extra or {}))
    r = subprocess.run(["python3", str(HOOK)], input=json.dumps(payload), stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, universal_newlines=True, env=env, timeout=120)
    assert r.returncode == 0
    return r.stdout


def fake_python(tmp_path, rc, text):
    p = tmp_path / "fakepy"
    p.write_text("#!/bin/sh\necho '%s'\nexit %d\n" % (text, rc))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)


def test_stale_page_is_reported(tmp_path):
    py = fake_python(tmp_path, 1, "FAIL: page STALE against its graph")
    out = run({"tool_name": "Bash", "tool_input": {"command": "python scripts/build_ecosim_rag.py --rebuild"}},
              {"A2MC_PYTHON": py})
    assert "STALE" in out and "pre-commit 35" in json.loads(out)["hookSpecificOutput"]["additionalContext"]


def test_unrelated_command_is_silent(tmp_path):
    py = fake_python(tmp_path, 1, "FAIL: would have spoken")
    assert run({"tool_name": "Bash", "tool_input": {"command": "ls tools"}}, {"A2MC_PYTHON": py}) == ""


def test_checker_ok_is_silent(tmp_path):
    py = fake_python(tmp_path, 0, "OK: 1 page in step")
    assert run({"tool_name": "Write", "tool_input": {"file_path": str(ROOT / "rag/graphs/x.json")}},
               {"A2MC_PYTHON": py}) == ""


def test_real_repo_page_is_current():
    out = run({"tool_name": "Bash", "tool_input": {"command": "python tools/render_kg_html.py --profile ecosim-cb243228"}})
    assert out == ""
