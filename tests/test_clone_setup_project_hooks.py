"""A repository's OWN tracked hooks directory counts as wired, and `setup_clone.sh` keeps it.

WHY. A repository can carry a project folder with its own commit checks, whose own onboarding
points `core.hooksPath` at them. If A2MC's clone check passed only `.githooks`, such a clone would
read "not fully set up", and `setup_clone.sh` would reset the path and break the project's own
check, so the two could never both pass.

The CONTROLS keep the new rule from becoming "anything goes": a hooks directory git does not track,
one outside the repository, one with no hook in it, and an unset path all still FAIL, and
`setup_clone.sh` still sets `.githooks` for them.

Author: Jing Tao with Claude on Perlmutter.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tools.check_clone_setup as C            # noqa: E402

SETUP = REPO / "scripts" / "setup_clone.sh"


def _git(repo, *args):
    return subprocess.run(["git", "-C", str(repo)] + list(args), check=True,
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          universal_newlines=True).stdout


@pytest.fixture
def repo(tmp_path, monkeypatch):
    """Root `.githooks/`, a project folder with TRACKED hooks, a folder with none, and a hooks
    directory git does not track."""
    r = tmp_path / "clone"
    r.mkdir()
    _git(r, "init", "-q")
    for rel in (".githooks/pre-commit", "Project/.githooks/pre-commit",
                "Project/.githooks/commit-msg", "NoHooks/README.md"):
        f = r / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("#!/bin/sh\nexit 0\n")
    _git(r, "add", "-A")
    _git(r, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "seed")
    stray = r / "Stray" / ".githooks" / "pre-commit"
    stray.parent.mkdir(parents=True)
    stray.write_text("#!/bin/sh\nexit 0\n")          # present on disk, never committed
    monkeypatch.setattr(C, "ROOT", r)
    return r


def _row(repo, path):
    if path is None:
        subprocess.run(["git", "-C", str(repo), "config", "--unset", "core.hooksPath"])
    else:
        _git(repo, "config", "core.hooksPath", path)
    return C._hooks_row()


# ---- check_clone_setup ------------------------------------------------------------------------
def test_the_framework_hooks_pass(repo):
    assert _row(repo, ".githooks")[0] == C.PASS


@pytest.mark.parametrize("path", ["Project/.githooks", "Project/.githooks/"])
def test_a_project_folders_own_tracked_hooks_pass(repo, path):
    status, _, detail = _row(repo, path)
    assert status == C.PASS, detail
    assert "own tracked hooks" in detail


@pytest.mark.parametrize("path", [
    "Stray/.githooks",           # on disk, but git does not track it
    "NoHooks",                   # tracked folder, no hook in it
    "Missing/.githooks",         # does not exist
    "../elsewhere/.githooks",    # outside the repository
    "/tmp/hooks",                # absolute
])
def test_CONTROL_anything_else_still_fails(repo, path):
    assert _row(repo, path)[0] == C.FAIL, path


def test_CONTROL_unset_still_fails(repo):
    assert _row(repo, None)[0] == C.FAIL


# ---- setup_clone.sh ---------------------------------------------------------------------------
def _setup_dry_run(repo, path):
    _git(repo, "config", "core.hooksPath", path)
    (repo / "scripts").mkdir(exist_ok=True)
    shutil.copy(SETUP, repo / "scripts" / "setup_clone.sh")
    r = subprocess.run(["bash", "scripts/setup_clone.sh", "--dry-run"], cwd=str(repo),
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       universal_newlines=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout


def test_setup_clone_keeps_a_project_folders_own_hooks(repo):
    out = _setup_dry_run(repo, "Project/.githooks")
    assert "kept: core.hooksPath = Project/.githooks" in out, out
    assert "would run: git config core.hooksPath .githooks" not in out


def test_CONTROL_setup_clone_still_sets_githooks_over_a_stray_path(repo):
    out = _setup_dry_run(repo, "Stray/.githooks")
    assert "would run: git config core.hooksPath .githooks" in out, out
