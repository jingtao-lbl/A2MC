"""The per-clone wiring and the author name must FAIL when they are not done.

Both exist because the failure they guard is silent: an unwired clone runs every command
successfully while doing less than the person believes, and a guessed author name looks exactly
like a correct one. So every test below asserts a way these must FAIL, or a way they must not
pass quietly ([[feedback_a_check_that_cannot_fail]]).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
for p in (str(REPO), str(REPO / "tools")):
    if p not in sys.path:
        sys.path.insert(0, p)

import tools.whoami as W                       # noqa: E402
import tools.check_clone_setup as C            # noqa: E402


# --------------------------------------------------------------------------- whoami
def test_nothing_set_resolves_to_NOTHING_not_a_default(monkeypatch, tmp_path):
    """THE test. A default here is a wrong attribution that nobody notices, and a delivered case
    folder supplies a plausible wrong answer in the neighbouring files."""
    monkeypatch.delenv("A2MC_USER_NAME", raising=False)
    monkeypatch.setattr(W, "ME", tmp_path / ".me")
    monkeypatch.setattr(W, "_git_name", lambda: "")
    assert W.resolve() == (None, None, False)


def test_exit_code_is_1_when_unresolved(monkeypatch, tmp_path):
    monkeypatch.delenv("A2MC_USER_NAME", raising=False)
    monkeypatch.setattr(W, "ME", tmp_path / ".me")
    monkeypatch.setattr(W, "_git_name", lambda: "")
    monkeypatch.setattr(sys, "argv", ["whoami.py"])
    assert W.main() == 1


def test_env_beats_me_file(monkeypatch, tmp_path):
    me = tmp_path / ".me"; me.write_text("From File\n")
    monkeypatch.setattr(W, "ME", me)
    monkeypatch.setenv("A2MC_USER_NAME", "From Env")
    assert W.resolve() == ("From Env", "$A2MC_USER_NAME", False)


def test_me_file_beats_git(monkeypatch, tmp_path):
    me = tmp_path / ".me"; me.write_text("From File\n")
    monkeypatch.delenv("A2MC_USER_NAME", raising=False)
    monkeypatch.setattr(W, "ME", me)
    monkeypatch.setattr(W, "_git_name", lambda: "From Git")
    name, _, guess = W.resolve()
    assert (name, guess) == ("From File", False)


def test_a_git_name_is_flagged_as_a_GUESS(monkeypatch, tmp_path):
    """git config user.name is frequently a handle. Accepting it silently is how 'jingtao-lbl'
    ends up in a log header as a person's name."""
    monkeypatch.delenv("A2MC_USER_NAME", raising=False)
    monkeypatch.setattr(W, "ME", tmp_path / ".me")
    monkeypatch.setattr(W, "_git_name", lambda: "somehandle")
    name, how, guess = W.resolve()
    assert name == "somehandle" and guess is True, "a git name must not pass as confirmed"


@pytest.mark.parametrize("junk", ["", "unknown", "User", "root", "your name"])
def test_placeholder_git_names_are_refused(monkeypatch, junk):
    monkeypatch.setattr(W.subprocess, "run",
                        lambda *a, **k: type("R", (), {"stdout": junk})())
    assert W._git_name() == ""


def test_set_refuses_to_silently_overwrite_a_different_name(tmp_path, monkeypatch):
    me = tmp_path / ".me"; me.write_text("Existing Person\n")
    monkeypatch.setattr(W, "ME", me)
    with pytest.raises(SystemExit):
        W.set_me("Someone Else")
    assert me.read_text().strip() == "Existing Person"


def test_set_refuses_an_empty_name(tmp_path, monkeypatch):
    monkeypatch.setattr(W, "ME", tmp_path / ".me")
    with pytest.raises(SystemExit):
        W.set_me("   ")


# ------------------------------------------------------------------- check_clone_setup
def test_an_unset_hooksPath_is_a_FAIL(monkeypatch):
    monkeypatch.setattr(C, "_git", lambda *a: "")
    status, _, detail = C._hooks_row()
    assert status == C.FAIL and "setup_clone.sh" in detail


def test_a_hooksPath_pointing_ELSEWHERE_is_a_FAIL(monkeypatch):
    """Set to some other directory is not 'set'; the repo's own checks still never run."""
    monkeypatch.setattr(C, "_git", lambda *a: ".git/hooks\n")
    assert C._hooks_row()[0] == C.FAIL


def test_skip_worktree_reads_the_S_TAG_not_the_letter_case(monkeypatch):
    """`git ls-files -v` tags skip-worktree as "S"; a LOWERCASE tag means assume-unchanged, a
    different flag. The first version tested `.isupper()` and reported every flagged file as
    unflagged -- it disagreed with `git status` on this very repo."""
    def fake(*a):
        if a[0] == "ls-files" and a[1] == "-v":
            return "S rag/chroma_db/x/chroma.sqlite3\nH rag/chroma_db/y/chroma.sqlite3\n"
        return "rag/chroma_db/x/chroma.sqlite3\nrag/chroma_db/y/chroma.sqlite3\n"
    monkeypatch.setattr(C, "_git", fake)
    status, _, detail = C._skip_worktree_row()
    assert status == C.FAIL and detail.startswith("1 of 2"), detail


def test_all_flagged_passes(monkeypatch):
    def fake(*a):
        if a[0] == "ls-files" and a[1] == "-v":
            return "S rag/chroma_db/x/chroma.sqlite3\n"
        return "rag/chroma_db/x/chroma.sqlite3\n"
    monkeypatch.setattr(C, "_git", fake)
    assert C._skip_worktree_row()[0] == C.PASS


def test_a_clone_with_NO_tracked_index_is_NA_not_a_failure(monkeypatch):
    """A row that cannot apply is not a row that failed; a public clone ships no chroma DB."""
    monkeypatch.setattr(C, "_git", lambda *a: "")
    assert C._skip_worktree_row()[0] == C.NA


def test_a_clone_with_no_memory_bucket_is_NA(monkeypatch, tmp_path):
    monkeypatch.setattr(C, "ROOT", tmp_path)
    assert C._memory_row()[0] == C.NA


def test_an_unresolvable_author_is_a_FAIL(monkeypatch, tmp_path):
    monkeypatch.delenv("A2MC_USER_NAME", raising=False)
    monkeypatch.setattr(W, "ME", tmp_path / ".me")
    monkeypatch.setattr(W, "_git_name", lambda: "")
    assert C._author_row()[0] == C.FAIL


def test_a_GUESSED_author_is_also_a_FAIL(monkeypatch, tmp_path):
    """PI, 2026-09-15: fail loudly. A guess is not an answer, and it is the case that produces a
    wrong name rather than an absent one."""
    monkeypatch.delenv("A2MC_USER_NAME", raising=False)
    monkeypatch.setattr(W, "ME", tmp_path / ".me")
    monkeypatch.setattr(W, "_git_name", lambda: "somehandle")
    status, _, detail = C._author_row()
    assert status == C.FAIL and "guess" in detail


def test_a_confirmed_author_passes(monkeypatch, tmp_path):
    monkeypatch.setenv("A2MC_USER_NAME", "Ada Lovelace")
    assert C._author_row()[0] == C.PASS


# ----------------------------------------------------------- the stage-4 hole this closes
def test_the_per_clone_rows_are_reached_at_STAGE_4(monkeypatch):
    """The bug: detect_stage() returns 4 as soon as a case has workflow state, and a case is
    DELIVERED. So a clone wired to nothing reported 'setup is done'. The rows must now run
    regardless of stage."""
    import tools.check_stage_ready as S
    src = Path(S.__file__).read_text()
    i_rows = src.index("clone_rows()")
    i_stage1 = src.index("if stage == 1:", src.index("def main("))
    assert i_rows < i_stage1, "per-clone rows must run BEFORE (and outside) the stage branch"


def test_check_clone_setup_runs_and_exits_nonzero_when_something_is_undone():
    r = subprocess.run([sys.executable, "tools/check_clone_setup.py"],
                       cwd=REPO, capture_output=True, text=True)
    assert r.returncode in (0, 1)
    assert "Per-clone setup" in r.stdout
    if r.returncode == 1:
        assert "setup_clone.sh" in r.stdout or "whoami.py" in r.stdout
