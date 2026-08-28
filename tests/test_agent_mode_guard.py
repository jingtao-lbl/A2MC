"""`A2MC_AGENT_MODE` defaults to 'online' and NOTHING in any config sets it.

THE FINDING. Measured 2026-08-22 while triaging `config_graph.py --orphans`: the ONLY setters of
`A2MC_AGENT_MODE` in the whole repository are test files. `tools/phase_logger.py` reads it with
`os.environ.get('A2MC_AGENT_MODE', 'online')`, so the interactive (offline) agent must export it by
hand every session.

WHY FORGETTING IS SILENT AND EXPENSIVE. Offline mode writes `logs/{stem}.md` flat; online mode
writes `logs/{session_id}/phase{N}_{name}/...`. But `topic_artifact_dir()` returns the SAME offline
stem in either mode -- so a forgotten export puts the log in one layout while the artifacts keep the
other's name, producing a `phase_results/{stem}/` with no matching `logs/{stem}.md`. That is exactly
the orphan the stem invariant forbids, caused by one missing export and reported by nothing.

The guard is decidable: writing in ONLINE layout into a `logs/` that already holds OFFLINE-stem logs
is a mode error. WARN, never raise -- a site may legitimately be run by both agents over its life,
and erroring would gate the autonomous loop on a bookkeeping artifact.

Author: Jing Tao with Claude
"""
from __future__ import annotations

import os
import sys
import warnings
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from tools.phase_logger import PhaseLogger        # noqa: E402


def _site(tmp_path: Path, *log_names: str) -> Path:
    d = tmp_path / "site"
    (d / "memory" / "logs").mkdir(parents=True, exist_ok=True)
    for n in log_names:
        (d / "memory" / "logs" / n).write_text("# x\n")
    return d


def _build(site: Path, **kw):
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        PhaseLogger(site_dir=str(site), calibration_round=1, **kw)
        return [x for x in w if issubclass(x.category, RuntimeWarning)]


@pytest.fixture(autouse=True)
def _no_env(monkeypatch):
    monkeypatch.delenv("A2MC_AGENT_MODE", raising=False)


OFFLINE_LOG = "20260822a_phase5_testing_r03_c01_something.md"


def test_it_warns_when_online_by_default_but_offline_logs_exist(tmp_path):
    """MUTATION: delete the guard call -> this fails.

    This is the real case: the interactive agent forgets the export, and the site already has 96
    offline-stem logs from previous sessions.
    """
    assert _build(_site(tmp_path, OFFLINE_LOG)), "must warn on a silent mode mismatch"


def test_an_explicit_online_choice_is_respected(tmp_path):
    """MUTATION: warn regardless of how the mode was chosen -> this fails.

    The guard fires only when the mode was DEFAULTED. Someone who passes agent_mode='online'
    explicitly has made a choice, and second-guessing it is how a warning becomes noise.
    """
    assert not _build(_site(tmp_path, OFFLINE_LOG), agent_mode="online")


def test_offline_never_warns(tmp_path):
    assert not _build(_site(tmp_path, OFFLINE_LOG), agent_mode="offline")


def test_a_fresh_site_is_silent(tmp_path):
    """MUTATION: warn whenever the env is unset -> this fails.

    The autonomous agent on a new site is in the RIGHT mode; nagging it there would train everyone
    to ignore the warning before it ever fires on a real mismatch.
    """
    assert not _build(_site(tmp_path))


def test_an_online_only_site_is_silent(tmp_path):
    """A site holding only online session dirs is not evidence of an offline campaign."""
    d = _site(tmp_path)
    (d / "memory" / "logs" / "20260101_120000").mkdir(parents=True, exist_ok=True)
    assert not _build(d)


@pytest.mark.parametrize("name", [
    "notes.md",                                   # prose, not a phase log
    "2026082a_phase5_x.md",                       # 7-digit date, not a stem
    "20260822_phase5_x.md",                        # no letter
    "20260822a_something_else.md",                 # no _phase<N>_
])
def test_non_offline_stems_do_not_trigger_it(tmp_path, name):
    """MUTATION: loosen `_OFFLINE_STEM` to any .md -> these fail.

    A false trigger here is worse than none: it fires on the autonomous agent's own correct runs.
    """
    assert not _build(_site(tmp_path, name))


# ------------------------------------------------ a phase-6 decision expires with its cycle

def _staged():
    from tools.workflow_state_offline import WorkflowStateOffline as W
    # site_dir explicit since 2026-08-25 (T9.2): the constructor no longer falls back to
    # use_cases/TEMPLATE, because save() would CREATE a state file there. Never saved here.
    st = W(site_dir='tmp/_guard_tests', calibration_round=9)
    st.data["experiment_count"] = 1
    st.set_phase6_decision("rethink_6to3", binding_target="x", objective="o",
                           best_so_far="b", next_targeted_experiment="something")
    return st


def test_a_cycle_advance_expires_the_phase6_decision():
    """MUTATION: drop the clearing branch in set_position -> this fails.

    The block records the routing call for ONE cycle. `resolve_next_action()` routes on it and
    `validate_phase6_decision()` checks the next gate against its premises, so one left standing
    into the following cycle misdrives both. It happened twice on 2026-08-22 and a review caught it
    both times, which is why it is now structural.
    """
    st = _staged()
    st.set_position(experiment_count=2)
    assert st.data["phase6_decision"] is None


@pytest.mark.parametrize("move", [
    {"current_phase": "testing"},        # moving phase WITHIN a cycle
    {"experiment_count": 1},             # re-setting the same count is not an advance
    {"converged": True},
])
def test_a_non_advance_leaves_the_decision_alone(move):
    """MUTATION: clear on every set_position call -> these fail.

    Over-clearing is the opposite defect and is worse in one way: it would wipe the gate the driver
    is about to read, mid-cycle, with nothing to show it happened.
    """
    st = _staged()
    st.set_position(**move)
    assert st.data["phase6_decision"] is not None
