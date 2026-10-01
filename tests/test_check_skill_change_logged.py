"""A changed skill must carry a dev log in the same commit (pre-commit check 28).

visibility: public

Each case builds a throwaway git repository in pytest's temp dir with a skill and a dev-log folder,
so the real repository is never staged into. The decisive cases are the two that must FAIL -- a
content change and a new skill with no log -- since a check that only ever passes proves nothing.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[1] / "tools" / "check_skill_change_logged.py"
ENV = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t",
           GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
SKILL_TEXT = "---\nname: demo\n---\n\n# Demo\n\nA paragraph that is\nhard wrapped here.\n\n> a quote\n> that wraps\n"


def _git(repo, *args):
    subprocess.run(["git", "-C", str(repo)] + list(args), check=True, env=ENV,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "r"
    (r / ".claude" / "skills" / "demo").mkdir(parents=True)
    (r / "memory" / "dev_logs_x").mkdir(parents=True)
    (r / ".claude" / "skills" / "demo" / "SKILL.md").write_text(SKILL_TEXT)
    (r / "memory" / "dev_logs_x" / "README.md").write_text("logs\n")
    _git(r, "init", "-q")
    _git(r, "add", "-A")
    _git(r, "commit", "-qm", "base")
    return r


def _check(repo) -> int:
    return subprocess.run([sys.executable, str(TOOL), "--staged"], cwd=str(repo), env=ENV,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE).returncode


def _stage_skill(repo, text):
    (repo / ".claude" / "skills" / "demo" / "SKILL.md").write_text(text)
    _git(repo, "add", "-A")


def test_a_content_change_with_no_log_is_refused(repo):
    _stage_skill(repo, SKILL_TEXT.replace("A paragraph", "A changed paragraph"))
    assert _check(repo) == 1


def test_a_new_skill_with_no_log_is_refused(repo):
    (repo / ".claude" / "skills" / "other").mkdir()
    (repo / ".claude" / "skills" / "other" / "SKILL.md").write_text("---\nname: other\n---\n")
    _git(repo, "add", "-A")
    assert _check(repo) == 1


def test_the_same_change_with_a_dated_log_passes(repo):
    _stage_skill(repo, SKILL_TEXT.replace("A paragraph", "A changed paragraph"))
    (repo / "memory" / "dev_logs_x" / "20260930a_Why.md").write_text("# Why\n")
    _git(repo, "add", "-A")
    assert _check(repo) == 0


def test_an_undated_file_in_the_log_folder_does_not_count(repo):
    _stage_skill(repo, SKILL_TEXT.replace("A paragraph", "A changed paragraph"))
    (repo / "memory" / "dev_logs_x" / "README.md").write_text("logs, edited\n")
    _git(repo, "add", "-A")
    assert _check(repo) == 1


def test_a_reflow_that_only_moves_line_breaks_passes(repo):
    _stage_skill(repo, SKILL_TEXT.replace("is\nhard", "is hard").replace("> a quote\n> that", "> a quote that"))
    assert _check(repo) == 0


def test_a_commit_with_no_skill_passes(repo):
    (repo / "notes.txt").write_text("x\n")
    _git(repo, "add", "-A")
    assert _check(repo) == 0


def test_a_tree_with_no_dev_log_stream_is_not_applicable(repo):
    _git(repo, "rm", "-rq", "memory")
    _git(repo, "commit", "-qm", "no logs")
    import shutil
    shutil.rmtree(repo / "memory", ignore_errors=True)
    _stage_skill(repo, SKILL_TEXT.replace("A paragraph", "A changed paragraph"))
    assert _check(repo) == 0
