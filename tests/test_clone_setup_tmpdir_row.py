"""The per-clone row added for register item F1: is a RUNTIME temp write legal on this machine?

WHY THE ROW EXISTS. NERSC's hard rule is no writes outside $HOME, and the PreToolUse hook that
enforces it reads a command's TEXT, so a path a program builds at runtime carries no literal for
it to match. Pointing the temp-directory variable inside $HOME closes that by construction. But it
lives in a shell profile, which git cannot carry, so a fresh clone or another machine silently has
only the backstop -- and until 2026-09-22 nothing reported it, including the setup checker whose
whole job is the things git cannot carry.

The tests drive the row through the environment, because that is the only input it has.
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


def _row(monkeypatch, value, nersc=True):
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
    return C._tmpdir_row()


def test_a_temp_dir_inside_HOME_passes(monkeypatch, tmp_path):
    status, label, detail = _row(monkeypatch, Path.home())
    assert status == C.PASS, detail
    assert VAR in label


def test_the_repo_tmp_is_recognised_as_such(monkeypatch):
    """The recommended target should read as the recommended target, not as a bare path."""
    (REPO / "tmp").mkdir(exist_ok=True)
    status, _, detail = _row(monkeypatch, REPO / "tmp")
    assert status == C.PASS
    assert "repo" in detail


def test_a_temp_dir_OUTSIDE_home_fails_and_says_how_to_fix_it(monkeypatch):
    """The case the row exists for: another machine, or a clone nobody ran the setup in."""
    status, _, detail = _row(monkeypatch, os.sep + "var" + os.sep + "spool")
    assert status == C.FAIL
    assert "outside" in detail
    assert "SLURM_JOB_ID" in detail, "the batch-job guard must be part of the advice"


def test_an_UNSET_variable_fails_rather_than_passing_quietly(monkeypatch):
    """Unset is the default state of a fresh clone, and it is not a pass."""
    status, _, detail = _row(monkeypatch, None)
    assert status == C.FAIL
    assert "unset" in detail


def test_the_row_is_WIRED_into_the_clone_report(monkeypatch):
    """A row nothing calls reports nothing. This is the half that actually closes the gap."""
    monkeypatch.setenv(VAR, str(Path.home()))
    labels = [label for _, label, _ in C.clone_rows()]
    assert any(VAR in l for l in labels), labels


def test_OFF_NERSC_the_row_is_NA_not_a_failure(monkeypatch):
    """A laptop has TMPDIR unset (Linux) or under /var/folders (macOS). The rule is NERSC's, so
    off NERSC the row cannot apply, and a row that cannot apply is NA (audit 20260923b, F28)."""
    for value in (None, "/var/folders/xy/T"):
        status, label, detail = _row(monkeypatch, value, nersc=False)
        assert status == C.NA, (value, detail)
        assert "NERSC" in detail
