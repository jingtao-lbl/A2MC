"""The offline-state checker warns when a case has moved but no findings were recorded.

Added 2026-08-21. The state is not only a program counter: `PhaseLogger` rebuilds its
"Reasoning chain" block from `decisions` on every log write, so a finding that never reaches the
state is invisible to the next phase — the re-derivation the loop exists to prevent.

Measured that day: a full day of R3 work established eight substantive findings and the state
recorded TWO decisions, both from that morning. Everything else lived as prose in `next_action`
(the program counter, not the record) and in commit messages. Nothing flagged it; the gap surfaced
only because the PI asked.

Every test names a way the warning must fire, or a way it must STAY SILENT — a nudge that fires on
everything gets tuned out, which would leave the real case unwatched.
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import tools.check_workflow_state_offline as ck  # noqa: E402


class _Run:
    def __init__(self, out, rc=0):
        self.stdout, self.returncode = out, rc


def _state(tmp_path, name="workflow_state_offline_r03.json", decisions=None, converged=False):
    d = tmp_path / "case" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    p.write_text(json.dumps({
        "calibration_round": 3, "converged": converged,
        "decisions": decisions if decisions is not None else [],
    }))
    return p


def _commits(monkeypatch, n):
    monkeypatch.setattr(ck.subprocess, "run",
                        lambda *a, **k: _Run("\n".join(f"abc{i}" for i in range(n))))


def test_warns_when_the_case_moved_and_nothing_was_recorded(tmp_path, monkeypatch):
    """THE case. Many commits, newest decision older than all of them."""
    _commits(monkeypatch, 40)
    p = _state(tmp_path, decisions=[{"date": "2026-07-01", "decision": "x"}])
    w = ck._check_decisions_current(p, json.loads(p.read_text()))
    assert w and "since the newest decision" in w[0]


def test_warns_when_there_are_no_decisions_at_all(tmp_path, monkeypatch):
    _commits(monkeypatch, 40)
    p = _state(tmp_path, decisions=[])
    w = ck._check_decisions_current(p, json.loads(p.read_text()))
    assert w and "no decisions recorded" in w[0]


def test_silent_when_findings_are_current(tmp_path, monkeypatch):
    """A recently-fed state must not nag."""
    _commits(monkeypatch, 2)
    p = _state(tmp_path, decisions=[{"date": "2026-08-21", "decision": "x"}])
    assert ck._check_decisions_current(p, json.loads(p.read_text())) == []


def test_silent_on_a_converged_round(tmp_path, monkeypatch):
    _commits(monkeypatch, 99)
    p = _state(tmp_path, decisions=[], converged=True)
    assert ck._check_decisions_current(p, json.loads(p.read_text())) == []


def test_silent_on_a_SUPERSEDED_round(tmp_path, monkeypatch):
    """Only the active (highest-numbered) round is watched.

    Without this, a closed round warns forever — measured: r02 warned about 130 commits since
    2026-07-21 while r03, the round actually being worked, was clean. A permanent warning is how a
    nudge becomes noise and gets ignored.
    """
    _commits(monkeypatch, 99)
    _state(tmp_path, name="workflow_state_offline_r03.json",
           decisions=[{"date": "2026-08-21", "decision": "x"}])
    old = _state(tmp_path, name="workflow_state_offline_r02.json", decisions=[])
    assert ck._check_decisions_current(old, json.loads(old.read_text())) == []


def test_silent_when_git_is_unavailable(tmp_path, monkeypatch):
    """An unreadable history is not evidence of a missing finding."""
    def boom(*a, **k):
        raise OSError("no git")
    monkeypatch.setattr(ck.subprocess, "run", boom)
    p = _state(tmp_path, decisions=[])
    assert ck._check_decisions_current(p, json.loads(p.read_text())) == []


def test_silent_when_git_returns_nonzero(tmp_path, monkeypatch):
    monkeypatch.setattr(ck.subprocess, "run", lambda *a, **k: _Run("", rc=128))
    p = _state(tmp_path, decisions=[])
    assert ck._check_decisions_current(p, json.loads(p.read_text())) == []


def test_a_few_commits_do_not_trip_it(tmp_path, monkeypatch):
    """The threshold is deliberately loose: a habit nudge, not a gate."""
    _commits(monkeypatch, ck.DECISION_STALE_COMMITS - 1)
    p = _state(tmp_path, decisions=[{"date": "2026-08-01", "decision": "x"}])
    assert ck._check_decisions_current(p, json.loads(p.read_text())) == []


def test_it_is_a_WARNING_not_an_error():
    """It must never block the loop: the state is valid, the habit is not.

    A gate here would stop work on a bookkeeping artifact, which is how gates get bypassed.
    """
    src = (REPO / "tools/check_workflow_state_offline.py").read_text()
    i = src.index("def _check_decisions_current")
    body = src[i:src.index("\ndef ", i + 10)]
    assert "errors" not in body.replace("errors, warnings", ""), "must contribute warnings only"
