"""The phase-skill prompt: warn while a phase is CURRENT if its skill was never invoked.

This closes the gap `check_skill_claims.py` cannot: that one verifies a skill a log CLAIMS was
really invoked, but is blind to a skill simply never invoked and never claimed -- skip it, write
"Skills: none", and the record is honest while the work is still wrong.

Each test names a way the check must FAIL (`feedback_a_check_that_cannot_fail`).

Author: Jing Tao with Claude
"""
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))
cw = pytest.importorskip("check_workflow_state_offline")


def _state(tmp_path, rr="03", phase="diagnosis", converged=False):
    d = tmp_path / "SiteX" / "memory"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"workflow_state_offline_r{rr}.json"
    p.write_text(json.dumps({"current_phase": phase, "converged": converged, "decisions": []}))
    return p


def test_it_warns_when_the_current_phase_skill_was_not_invoked(tmp_path, monkeypatch):
    monkeypatch.setattr(cw, "_skills_invoked_cached", None, raising=False)
    p = _state(tmp_path, phase="diagnosis")
    monkeypatch.setitem(sys.modules, "_stub", None)
    import check_skill_claims as csc
    monkeypatch.setattr(csc, "invoked_skills", lambda: ({"calibration-log": "20260822"}, 1))
    w = cw._check_phase_skill_invoked(p, json.loads(p.read_text()))
    assert any("phase3-diagnosis" in x and "NOT been invoked" in x for x in w)


def test_it_is_silent_when_the_skill_WAS_invoked(tmp_path, monkeypatch):
    p = _state(tmp_path, phase="diagnosis")
    import check_skill_claims as csc
    monkeypatch.setattr(csc, "invoked_skills", lambda: ({"phase3-diagnosis": "20260822"}, 1))
    assert cw._check_phase_skill_invoked(p, json.loads(p.read_text())) == []


def test_the_mapping_covers_every_real_phase(monkeypatch):
    """Anchored to VALID_PHASES, NOT to PHASE_SKILL itself.

    Iterating PHASE_SKILL to test PHASE_SKILL is circular: drop a row and the loop simply stops
    testing it. Measured -- a mutation removing the `hypothesis` row left all six tests green.
    VALID_PHASES is derived independently, so a dropped row now fails here.
    """
    covered = set(cw.PHASE_SKILL) | {"converged"}     # phase 7 is terminal and has no skill
    assert set(cw.VALID_PHASES) <= covered, f"unmapped phase(s): {set(cw.VALID_PHASES) - covered}"


def test_it_maps_every_phase_to_a_skill(tmp_path, monkeypatch):
    """Each mapped phase must actually produce a warning naming its skill."""
    import check_skill_claims as csc
    monkeypatch.setattr(csc, "invoked_skills", lambda: ({}, 1))
    for phase, skill in cw.PHASE_SKILL.items():
        p = _state(tmp_path / phase, phase=phase)
        w = cw._check_phase_skill_invoked(p, json.loads(p.read_text()))
        assert any(skill in x for x in w), f"{phase} did not name {skill}"


def test_a_converged_round_is_silent(tmp_path, monkeypatch):
    p = _state(tmp_path, phase="diagnosis", converged=True)
    import check_skill_claims as csc
    monkeypatch.setattr(csc, "invoked_skills", lambda: ({}, 1))
    assert cw._check_phase_skill_invoked(p, json.loads(p.read_text())) == []


def test_a_SUPERSEDED_round_is_silent(tmp_path, monkeypatch):
    """A finished round warning forever is how a nudge becomes noise and gets tuned out."""
    import check_skill_claims as csc
    monkeypatch.setattr(csc, "invoked_skills", lambda: ({}, 1))
    old = _state(tmp_path, rr="02", phase="refinement")
    _state(tmp_path, rr="03", phase="diagnosis")          # a newer sibling exists
    assert cw._check_phase_skill_invoked(old, json.loads(old.read_text())) == []


def test_no_transcript_means_silence_not_a_false_warning(tmp_path, monkeypatch):
    """With no transcript the check knows nothing; inventing a warning would train it to be ignored."""
    p = _state(tmp_path, phase="diagnosis")
    import check_skill_claims as csc
    monkeypatch.setattr(csc, "invoked_skills", lambda: ({}, 0))
    assert cw._check_phase_skill_invoked(p, json.loads(p.read_text())) == []


# --------------------------------------------------------------- the loop limit must be a number

def _resolver():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "cwso", REPO / "tools" / "check_workflow_state_offline.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


@pytest.mark.parametrize("state,want_err", [
    ({"max_experiments": 10}, False),
    ({}, False),                                          # absent is fine -> default
    ({"phase6_decision": {"max_experiments": 10}}, False),
    ({"max_experiments": None}, True),                    # THE BUG: R3 carried exactly this
    ({"phase6_decision": {"max_experiments": None}}, True),
    ({"max_experiments": "ten"}, True),
    ({"max_experiments": 0}, True),
    ({"max_experiments": True}, True),                    # a bool is not a count
])
def test_the_loop_limit_must_resolve_to_a_positive_int(state, want_err):
    """MUTATION: revert to `.get("max_experiments", 10)` -> the None rows fail.

    `.get(k, default)` does NOT protect against a key PRESENT with value None; it returns None. That
    is why both original call sites looked safe and neither was. With None the middle loop becomes
    undecidable -- `experiment_count == max_experiments` can never be true, so a round can never
    legitimately reach the per-round checklist -- and the comparison raises TypeError.
    """
    v, err = _resolver().resolve_max_experiments(state)
    assert isinstance(v, int) and v >= 1, "must always yield a usable limit"
    assert bool(err) is want_err, f"{state}: expected error={want_err}, got {err!r}"


@pytest.mark.parametrize("mx", [None, "ten", 0])
def test_a_premature_stop_is_rejected_not_raised_on_a_bad_limit(mx):
    """MUTATION: drop the coercion in validate_phase6_decision -> these RAISE instead of rejecting.

    A raise is not a safe failure here: it makes the premature-stop guard UNAVAILABLE at the one
    moment it exists for, and any caller wrapping it in try/except turns that into a fail-open.
    """
    import sys
    sys.path.insert(0, str(REPO))
    from tools.workflow_state_offline import WorkflowStateOffline as W
    # site_dir explicit since 2026-08-25 (T9.2); this state is never saved.
    st = W(site_dir='tmp/_prompt_tests', calibration_round=3)
    st.data["experiment_count"] = 1
    st.set_phase6_decision("stop_model_dev", binding_target="Fs", next_targeted_experiment="NONE",
                           exhaustion_justification="x", objective="o", best_so_far="b",
                           max_experiments=mx)
    errs = st.validate_phase6_decision()          # must not raise
    assert errs, "a premature stop_model_dev must be rejected regardless of a malformed limit"
