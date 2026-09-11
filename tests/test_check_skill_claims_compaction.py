"""The compaction tier of check_skill_claims: a claim whose last invocation predates the
session's newest `compact_boundary` is an ERROR, not a pass.

WHY THIS TEST EXISTS. The checker's scope was "invoked anywhere in the current session", justified
as "a skill invoked on its first day is still loaded and governing on its third". A compaction
falsifies exactly that: it discards the skill's TEXT from context while leaving the invocation in
the transcript, so the claim outlives the instructions it names. Measured on the session that
prompted the change: seven compaction boundaries, and only 6 of 23 distinct skills invoked after
the last one.

The tests monkeypatch `invoked_skills` rather than fabricating a transcript, so they exercise the
TIER LOGIC and stay valid when the transcript format changes.
"""
import subprocess, sys, pathlib
import pytest

REPO = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import tools.check_skill_claims as C


def _log(tmp_path, skills):
    p = tmp_path / "20260906z_phase3_diagnosis_r01_c01_iter01_probe.md"
    p.write_text(
        "# Probe\n\n**Site:** X\n**Phase:** 3 - Diagnosis\n\n"
        "## Skills and memory invoked\n\n"
        "- **Skills:** " + ", ".join(f"`{s}`" for s in skills) + "\n")
    return p


@pytest.fixture
def patched(monkeypatch):
    """invoked -> {skill: day}, positions -> {skill: transcript line}, boundary at line 100."""
    def make(positions, boundary):
        monkeypatch.setattr(C, "invoked_skills",
                            lambda: ({s: "20260906" for s in positions}, positions, boundary, 1))
        monkeypatch.setattr(C, "known_skills", lambda: {"phase3-diagnosis", "calibration-log"})
        monkeypatch.setattr(C, "known_memories", lambda: set())
    return make


def test_fresh_claim_passes(tmp_path, patched):
    """Invoked AFTER the boundary -> clean."""
    patched({"phase3-diagnosis": 150, "calibration-log": 160}, boundary=100)
    assert C.main([str(_log(tmp_path, ["phase3-diagnosis", "calibration-log"]))]) == 0


def test_stale_claim_errors(tmp_path, patched):
    """Invoked only BEFORE the boundary -> ERROR. This is the whole point of the tier."""
    patched({"phase3-diagnosis": 40, "calibration-log": 50}, boundary=100)
    assert C.main([str(_log(tmp_path, ["phase3-diagnosis", "calibration-log"]))]) == 2


def test_one_stale_among_fresh_still_errors(tmp_path, patched):
    patched({"phase3-diagnosis": 150, "calibration-log": 50}, boundary=100)
    assert C.main([str(_log(tmp_path, ["phase3-diagnosis", "calibration-log"]))]) == 2


def test_never_invoked_still_errors(tmp_path, patched):
    """The pre-existing tier is unchanged."""
    patched({"calibration-log": 150}, boundary=100)
    assert C.main([str(_log(tmp_path, ["phase3-diagnosis", "calibration-log"]))]) == 2


def test_no_compaction_in_session_leaves_tier_inert(tmp_path, patched):
    """boundary = -1 (no compaction yet) must not turn every claim stale."""
    patched({"phase3-diagnosis": 40, "calibration-log": 50}, boundary=-1)
    assert C.main([str(_log(tmp_path, ["phase3-diagnosis", "calibration-log"]))]) == 0
