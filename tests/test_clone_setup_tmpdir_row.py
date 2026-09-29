"""The per-clone row added for register item F1: is a RUNTIME temp write legal on this machine?

WHY THE ROW EXISTS. NERSC's hard rule is no writes outside $HOME, and the PreToolUse hook that
enforces it reads a command's TEXT, so a path a program builds at runtime carries no literal for
it to match. Pointing the temp-directory variable inside $HOME closes that by construction.

WHAT IT MEASURES NOW. The SessionStart hook exports the variable for the agent's shell, per session,
as the clone's own tmp/ (tools/session_tmpdir.py). So the row judges the value a Bash command will
actually run with -- this session's export first, else the inherited one -- and, from a plain shell,
whether the hook can export a legal path for this clone at all. It must never advise a shell
profile: that sends every repository on the account into one clone's tmp/.

The tests drive the row through the environment and a stand-in harness config dir, so neither the
suite's own session nor the machine it runs on decides the outcome.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import check_clone_setup as C  # noqa: E402

VAR = "TMP" + "DIR"
SYS_TMP = os.sep + "tmp"


def _row(monkeypatch, tmp_path, value, nersc=True, sid="", export=None):
    # The row applies only on a NERSC machine; the tests below that exercise it say so explicitly
    # rather than depending on where the suite happens to run.
    if nersc:
        monkeypatch.setenv("NERSC_HOST", "perlmutter")
    else:
        monkeypatch.delenv("NERSC_HOST", raising=False)
    if value is None:
        monkeypatch.delenv(VAR, raising=False)
    else:
        monkeypatch.setenv(VAR, str(value))
    cfg = tmp_path / "config"
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    if sid:
        monkeypatch.setenv("CLAUDE_CODE_SESSION_ID", sid)
    else:
        monkeypatch.delenv("CLAUDE_CODE_SESSION_ID", raising=False)
    if export is not None:
        d = cfg / "session-env" / (sid or "none")
        d.mkdir(parents=True)
        (d / "sessionstart-hook-0.sh").write_text("export %s=%s\n" % (VAR, export))
    return C._tmpdir_row()


def test_a_temp_dir_inside_HOME_passes(monkeypatch, tmp_path):
    status, label, detail = _row(monkeypatch, tmp_path, Path.home())
    assert status == C.PASS, detail
    assert VAR in label


def test_the_repo_tmp_is_recognised_as_such(monkeypatch, tmp_path):
    """The recommended target should read as the recommended target, not as a bare path."""
    (REPO / "tmp").mkdir(exist_ok=True)
    status, _, detail = _row(monkeypatch, tmp_path, REPO / "tmp")
    assert status == C.PASS
    assert "repo" in detail


def test_a_SESSION_export_is_what_counts_not_the_inherited_value(monkeypatch, tmp_path):
    """Inside a session the hook process inherits system temp, while the agent's shell runs with
    the export. The row must judge the second."""
    status, _, detail = _row(monkeypatch, tmp_path, SYS_TMP, sid="s1", export=REPO / "tmp")
    assert status == C.PASS, detail
    assert "SessionStart" in detail


def test_a_session_WITHOUT_the_export_fails_and_never_advises_a_shell_profile(monkeypatch, tmp_path):
    """The case the row exists for inside a session: the hook did not run, or this Claude Code
    cannot pass a variable from it. The advice must not be the one that broke every other repo."""
    status, _, detail = _row(monkeypatch, tmp_path, SYS_TMP, sid="s1")
    assert status == C.FAIL
    assert "restart" in detail
    assert "Do NOT export it in a shell profile" in detail


def test_a_PLAIN_shell_passes_because_git_carries_the_fix(monkeypatch, tmp_path):
    """No session: the shell's own value is system temp, but every session in this clone will get
    the repo's tmp/, so the clone is set up. It says which shell it is judging."""
    for value in (SYS_TMP, None):
        status, _, detail = _row(monkeypatch, tmp_path, value)
        assert status == C.PASS, (value, detail)
        assert "SessionStart hook" in detail


def test_a_clone_OUTSIDE_home_fails_since_its_tmp_is_illegal_too(monkeypatch, tmp_path):
    """The one condition git cannot fix: the hook exports the clone's own tmp/, so a clone outside
    $HOME has nothing legal to export."""
    monkeypatch.setattr(C, "ROOT", Path(os.sep + "var") / "spool" / "A2MC")
    status, _, detail = _row(monkeypatch, tmp_path, SYS_TMP)
    assert status == C.FAIL
    assert "outside $HOME" in detail


def test_the_row_is_WIRED_into_the_clone_report(monkeypatch):
    """A row nothing calls reports nothing. This is the half that actually closes the gap."""
    monkeypatch.setenv(VAR, str(Path.home()))
    labels = [label for _, label, _ in C.clone_rows()]
    assert any(VAR in l for l in labels), labels


def test_OFF_NERSC_the_row_is_NA_not_a_failure(monkeypatch, tmp_path):
    """A laptop has TMPDIR unset (Linux) or under /var/folders (macOS). The rule is NERSC's, so
    off NERSC the row cannot apply, and a row that cannot apply is NA (audit 20260923b, F28)."""
    for value in (None, "/var/folders/xy/T"):
        status, label, detail = _row(monkeypatch, tmp_path, value, nersc=False)
        assert status == C.NA, (value, detail)
        assert "NERSC" in detail
