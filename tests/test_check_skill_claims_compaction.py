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


def _rel(p):
    """The key the checker uses: path relative to the repo, or the bare name if outside it.

    pytest's tmp_path lands INSIDE the repo here (TMPDIR points at ./tmp), so a fixture that
    guessed `p.name` would silently exercise the edit branch instead of the add branch.
    """
    try:
        return str(p.relative_to(C.REPO))
    except ValueError:
        return p.name


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
        # `*_` absorbs the log-basename argument `invoked_skills` takes: the checker passes one so
        # it can pick the AUTHORING transcript rather than the most recently flushed, which
        # concurrent sessions in a shared clone had made a coin flip. A zero-arg stub raises
        # TypeError and fails all 8 tests in this file without saying why.
        monkeypatch.setattr(C, "invoked_skills",
                            lambda *_: ({s: "20260906" for s in positions}, positions, boundary, 1))
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


# --------------------------------------------------------------------------------------------
# The EDIT tier: a log being corrected is answerable only for the claims the edit ADDS.
# --------------------------------------------------------------------------------------------

def test_an_EDIT_is_judged_on_what_it_adds_not_on_the_whole_section(tmp_path, patched, monkeypatch):
    """A supersede banner must not be blocked by the original session's claims.

    An edit to an existing log is made in a LATER session -- a dated correction, a banner, a
    corrected number -- and its capability section records what the ORIGINAL session did. This
    checker can only see the CURRENT session, so validating the whole section against it reports
    every pre-existing claim as never invoked. Measured 2026-09-22: a commit adding correction
    banners to five logs was refused over a `plotting` claim written days earlier.
    """
    patched({"calibration-log": 150}, boundary=100)
    p = _log(tmp_path, ["phase3-diagnosis", "calibration-log"])   # phase3-diagnosis NOT invoked
    rel = str(p)
    monkeypatch.setattr(C, "staged_logs", lambda: [p])
    monkeypatch.setattr(C, "staged_added_paths", lambda: set())          # an EDIT, not an add
    monkeypatch.setattr(C, "staged_added_text", lambda r: "> **CORRECTION (2026-09-22):** typo.")
    assert C.main(["--staged"]) == 0, "an edit that adds no claim must not be judged on old ones"


def test_an_EDIT_that_ADDS_a_false_claim_is_still_caught(tmp_path, patched, monkeypatch):
    """The other half. Scoping to added lines must not become a way to launder a claim in."""
    patched({"calibration-log": 150}, boundary=100)
    p = _log(tmp_path, ["phase3-diagnosis", "calibration-log"])
    monkeypatch.setattr(C, "staged_logs", lambda: [p])
    monkeypatch.setattr(C, "staged_added_paths", lambda: set())
    monkeypatch.setattr(C, "staged_added_text",
                        lambda r: "- **Skills:** `phase3-diagnosis`")
    assert C.main(["--staged"]) != 0, "a claim added by the edit must still be verified"


def test_a_NEW_log_is_still_judged_on_its_whole_section(tmp_path, patched, monkeypatch):
    """Adding a log is authored in this session, so the whole section is this session's claim."""
    patched({"calibration-log": 150}, boundary=100)
    p = _log(tmp_path, ["phase3-diagnosis", "calibration-log"])
    monkeypatch.setattr(C, "staged_logs", lambda: [p])
    monkeypatch.setattr(C, "staged_added_paths", lambda: {_rel(p)})
    assert C.main(["--staged"]) != 0
